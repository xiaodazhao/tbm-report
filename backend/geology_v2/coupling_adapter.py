"""
geology_v2.coupling_adapter

地质-施工响应耦合适配器。

输入：
    geo_states_df:
        fuse_geo_states 输出，包含 GRS_geo_base。

    response_df:
        施工响应异常指数数据，至少包含：
        - cell_id
        - RAI

    或者：
    df_plc + cells_df:
        从 PLC 特征临时计算 RAI。

输出：
    coupled_df:
        每个 cell 一行，包含：
        - GRS_geo_base
        - RAI
        - GRCI
        - coupling_level
        - coupling_type
        - coupling_explanation

设计原则：
1. GRS_geo_base 表示纯地质基础关注度；
2. RAI 表示施工响应异常指数；
3. GRCI 表示地质-施工响应耦合关注度；
4. GRCI 不表示灾害概率；
5. 没有施工响应数据时，不强行计算 GRCI；
6. 保留 has_response_evidence 字段，避免把缺少响应数据误写成施工正常。
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


# ============================================================
# 1. 输出字段
# ============================================================

COUPLED_COLUMNS = [
    "cell_id",
    "cell_start",
    "cell_end",
    "cell_center",

    "has_geology_evidence",
    "GRS_geo_base",
    "fused_grade",
    "main_hazards",

    "has_response_evidence",
    "RAI",
    "response_support_count",
    "response_metrics",

    "GRCI",
    "coupling_level",
    "coupling_type",
    "coupling_explanation",
]


CHAINAGE_COLUMN_CANDIDATES = [
    "chainage",
    "里程",
    "当前里程",
    "桩号",
    "推进里程",
    "mile",
    "mileage",
]

DEFAULT_PLC_FEATURE_RULES = {
    # 特征名: 异常方向
    # high 表示高于正常水平为异常
    # low 表示低于正常水平为异常
    # deviation 表示偏离正常水平为异常
    "推力": "high",
    "刀盘扭矩": "high",
    "推进速度": "low",
    "刀盘实际转速": "deviation",
}


# ============================================================
# 2. 基础工具
# ============================================================

def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, tuple, set)):
        return False
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    if _is_missing(value):
        return float(default)
    try:
        x = float(value)
        if math.isfinite(x):
            return float(x)
    except Exception:
        pass
    return float(default)


def _safe_str(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    text = str(value).strip()
    return text if text else default


def _clip01(value: Any) -> float:
    return float(max(0.0, min(_safe_float(value), 1.0)))


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
        return [text]
    return [value]


def _dedup_keep_order(items: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    for item in items:
        if _is_missing(item):
            continue

        text = str(item).strip()
        if not text:
            continue

        if text not in seen:
            out.append(text)
            seen.add(text)

    return out


def _json_clean(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        x = float(value)
        return x if math.isfinite(x) else None

    if isinstance(value, dict):
        return {str(k): _json_clean(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_clean(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return str(value)


def _find_chainage_col(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return None

    lower_map = {str(col).strip().lower(): col for col in df.columns}

    for name in CHAINAGE_COLUMN_CANDIDATES:
        key = name.lower()
        if key in lower_map:
            return lower_map[key]

    for col in df.columns:
        text = str(col).strip().lower()
        if "chainage" in text or "里程" in text or "桩号" in text:
            return col

    return None


def _level_from_score(score: Optional[float]) -> str:
    if score is None:
        return "unknown"

    value = _safe_float(score)

    if value >= 0.75:
        return "high"
    if value >= 0.50:
        return "medium"
    if value >= 0.25:
        return "low"
    return "none"


def _level_cn(level: str) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无明显",
        "unknown": "未知",
    }.get(str(level), "未知")


# ============================================================
# 3. 从 PLC 临时构建 RAI
# ============================================================

def _robust_center_scale(series: pd.Series) -> tuple[float, float]:
    """
    使用 median + MAD 计算稳健中心和尺度。
    """
    s = pd.to_numeric(series, errors="coerce").dropna()

    if s.empty:
        return 0.0, 1.0

    median = float(s.median())
    mad = float((s - median).abs().median())

    # MAD 转近似标准差
    scale = 1.4826 * mad

    if scale <= 1e-12:
        std = float(s.std())
        if math.isfinite(std) and std > 1e-12:
            scale = std
        else:
            scale = 1.0

    return median, scale


def _feature_anomaly_score(value: float, center: float, scale: float, direction: str) -> float:
    """
    单个特征的异常分数，输出 0~1。

    high:
        高于中心更异常。
    low:
        低于中心更异常。
    deviation:
        偏离中心更异常。
    """
    if not math.isfinite(value):
        return 0.0

    scale = max(float(scale), 1e-6)
    direction = str(direction or "deviation").lower()

    if direction == "high":
        z = max(0.0, (value - center) / scale)
    elif direction == "low":
        z = max(0.0, (center - value) / scale)
    else:
        z = abs(value - center) / scale

    # z=3 约等于异常分数 1
    return _clip01(z / 3.0)


def build_response_index_from_plc(
    df_plc: pd.DataFrame,
    cells_df: pd.DataFrame,
    feature_rules: Optional[Dict[str, str]] = None,
    chainage_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    从 PLC 数据临时计算每个 cell 的 RAI。

    参数：
        df_plc:
            PLC 数据，需要包含里程列和若干施工参数列。

        cells_df:
            build_chainage_cells 输出。

        feature_rules:
            特征规则，例如：
            {
                "推力": "high",
                "刀盘扭矩": "high",
                "推进速度": "low",
                "刀盘实际转速": "deviation",
            }

        chainage_col:
            可选。指定 PLC 里程列。

    返回：
        response_df:
            cell_id
            RAI
            response_support_count
            response_metrics

    注意：
        这是一个轻量 RAI 计算方法，适合先打通流程。
        后续如果你已有更正式的 RAI 计算结果，可以直接传 response_df，不用这个函数。
    """
    if cells_df is None or cells_df.empty:
        return pd.DataFrame(
            columns=[
                "cell_id",
                "RAI",
                "response_support_count",
                "response_metrics",
            ]
        )

    if df_plc is None or df_plc.empty:
        return pd.DataFrame(
            {
                "cell_id": cells_df["cell_id"].astype(str).tolist(),
                "RAI": [np.nan] * len(cells_df),
                "response_support_count": [0] * len(cells_df),
                "response_metrics": [{} for _ in range(len(cells_df))],
            }
        )

    rules = feature_rules or DEFAULT_PLC_FEATURE_RULES

    df = df_plc.copy()

    if chainage_col is None:
        chainage_col = _find_chainage_col(df)

    if chainage_col is None or chainage_col not in df.columns:
        raise ValueError("df_plc 缺少里程列，无法计算 cell 级 RAI。")

    df["__chainage"] = pd.to_numeric(df[chainage_col], errors="coerce")
    df = df.dropna(subset=["__chainage"]).copy()

    if df.empty:
        return pd.DataFrame(
            {
                "cell_id": cells_df["cell_id"].astype(str).tolist(),
                "RAI": [np.nan] * len(cells_df),
                "response_support_count": [0] * len(cells_df),
                "response_metrics": [{} for _ in range(len(cells_df))],
            }
        )

    available_rules = {
        col: direction
        for col, direction in rules.items()
        if col in df.columns
    }

    if not available_rules:
        raise ValueError(
            f"df_plc 中没有找到可用于 RAI 的特征列。候选列为：{list(rules.keys())}"
        )

    # 全局稳健中心和尺度
    stats = {}
    for col, direction in available_rules.items():
        center, scale = _robust_center_scale(df[col])
        stats[col] = {
            "center": center,
            "scale": scale,
            "direction": direction,
        }

    records = []

    for _, cell in cells_df.iterrows():
        cell_id = _safe_str(cell.get("cell_id"))
        start = _safe_float(cell.get("cell_start"))
        end = _safe_float(cell.get("cell_end"))

        part = df[
            (df["__chainage"] >= min(start, end))
            & (df["__chainage"] < max(start, end))
        ].copy()

        if part.empty:
            records.append(
                {
                    "cell_id": cell_id,
                    "RAI": np.nan,
                    "response_support_count": 0,
                    "response_metrics": {},
                }
            )
            continue

        feature_scores = {}
        feature_values = {}

        for col, cfg in stats.items():
            values = pd.to_numeric(part[col], errors="coerce").dropna()

            if values.empty:
                continue

            center = float(cfg["center"])
            scale = float(cfg["scale"])
            direction = str(cfg["direction"])

            scores = [
                _feature_anomaly_score(float(v), center, scale, direction)
                for v in values.tolist()
            ]

            feature_scores[col] = float(max(scores)) if scores else 0.0
            feature_values[col] = {
                "mean": float(values.mean()),
                "max": float(values.max()),
                "min": float(values.min()),
                "anomaly_score": feature_scores[col],
                "direction": direction,
            }

        if feature_scores:
            # max 表示主控异常，mean 表示整体异常背景
            max_score = max(feature_scores.values())
            mean_score = sum(feature_scores.values()) / len(feature_scores)
            rai = _clip01(0.70 * max_score + 0.30 * mean_score)
        else:
            rai = np.nan

        records.append(
            {
                "cell_id": cell_id,
                "RAI": rai,
                "response_support_count": int(len(part)),
                "response_metrics": _json_clean(feature_values),
            }
        )

    return pd.DataFrame(records)


# ============================================================
# 4. response_df 标准化
# ============================================================

def normalize_response_df(
    response_df: pd.DataFrame,
    cells_df: Optional[pd.DataFrame] = None,
    rai_col: str = "RAI",
) -> pd.DataFrame:
    """
    标准化外部传入的 response_df。

    支持两种情况：
    1. response_df 已经有 cell_id 和 RAI；
    2. response_df 没有 cell_id，但有 chainage 和 RAI，此时需要 cells_df 映射。
    """
    if response_df is None or response_df.empty:
        return pd.DataFrame(
            columns=[
                "cell_id",
                "RAI",
                "response_support_count",
                "response_metrics",
            ]
        )

    df = response_df.copy()

    if rai_col not in df.columns:
        raise ValueError(f"response_df 缺少 RAI 列：{rai_col}")

    df["RAI"] = pd.to_numeric(df[rai_col], errors="coerce")

    if "cell_id" in df.columns:
        out = df.copy()
        out["cell_id"] = out["cell_id"].astype(str)

        if "response_support_count" not in out.columns:
            out["response_support_count"] = 1

        if "response_metrics" not in out.columns:
            out["response_metrics"] = [{} for _ in range(len(out))]

        # 如果同一个 cell 有多行，取 RAI 最大值，support_count 求和。
        records = []
        for cell_id, part in out.groupby("cell_id"):
            metrics = {}
            for item in part["response_metrics"].tolist():
                if isinstance(item, dict):
                    metrics.update(item)

            records.append(
                {
                    "cell_id": str(cell_id),
                    "RAI": float(pd.to_numeric(part["RAI"], errors="coerce").max()),
                    "response_support_count": int(
                        pd.to_numeric(
                            part["response_support_count"],
                            errors="coerce",
                        ).fillna(0).sum()
                    ),
                    "response_metrics": _json_clean(metrics),
                }
            )

        return pd.DataFrame(records)

    if cells_df is None or cells_df.empty:
        raise ValueError("response_df 没有 cell_id 时，必须提供 cells_df 进行里程映射。")

    chainage_col = _find_chainage_col(df)

    if chainage_col is None:
        raise ValueError("response_df 既没有 cell_id，也没有可识别的里程列。")

    df["__chainage"] = pd.to_numeric(df[chainage_col], errors="coerce")
    df = df.dropna(subset=["__chainage"]).copy()

    records = []

    for _, cell in cells_df.iterrows():
        cell_id = _safe_str(cell.get("cell_id"))
        start = _safe_float(cell.get("cell_start"))
        end = _safe_float(cell.get("cell_end"))

        part = df[
            (df["__chainage"] >= min(start, end))
            & (df["__chainage"] < max(start, end))
        ].copy()

        if part.empty:
            records.append(
                {
                    "cell_id": cell_id,
                    "RAI": np.nan,
                    "response_support_count": 0,
                    "response_metrics": {},
                }
            )
            continue

        rai_values = pd.to_numeric(part["RAI"], errors="coerce").dropna()

        records.append(
            {
                "cell_id": cell_id,
                "RAI": float(rai_values.max()) if not rai_values.empty else np.nan,
                "response_support_count": int(len(part)),
                "response_metrics": {
                    "RAI_mean": float(rai_values.mean()) if not rai_values.empty else None,
                    "RAI_max": float(rai_values.max()) if not rai_values.empty else None,
                },
            }
        )

    return pd.DataFrame(records)


# ============================================================
# 5. 耦合计算
# ============================================================

def _compute_grci(grs_geo_base: float, rai: float) -> float:
    """
    计算 GRCI。

    公式：
        GRCI = 0.55 * GRS + 0.35 * RAI + 0.10 * GRS * RAI

    解释：
        - GRS 表示地质证据基础关注度；
        - RAI 表示施工响应异常；
        - GRS * RAI 表示二者同步增强时的耦合项。

    注意：
        GRCI 是耦合关注度，不是灾害概率。
    """
    grs = _clip01(grs_geo_base)
    response = _clip01(rai)

    value = 0.55 * grs + 0.35 * response + 0.10 * grs * response

    return _clip01(value)


def _coupling_type(grs_geo_base: float, rai: float, has_response: bool) -> str:
    if not has_response:
        return "no_response_evidence"

    grs_level = _level_from_score(grs_geo_base)
    rai_level = _level_from_score(rai)

    if grs_level in {"high", "medium"} and rai_level in {"high", "medium"}:
        return "geo_response_coupled"

    if grs_level in {"high", "medium"} and rai_level in {"low", "none"}:
        return "geo_dominant_no_obvious_response"

    if grs_level in {"low", "none"} and rai_level in {"high", "medium"}:
        return "response_anomaly_without_strong_geo_support"

    return "low_coupling"


def _coupling_explanation(
    grs_geo_base: float,
    rai: Optional[float],
    has_response: bool,
    coupling_type: str,
    main_hazards: List[str],
) -> str:
    hazards = "、".join(_dedup_keep_order(main_hazards)[:5]) if main_hazards else "未形成明确主控地质问题"

    if not has_response:
        return (
            f"该 cell 具有地质融合结果，主要关注 {hazards}；"
            "但缺少有效施工响应数据，因此不计算 GRCI，不能据此判断施工响应正常。"
        )

    grs_level = _level_cn(_level_from_score(grs_geo_base))
    rai_level = _level_cn(_level_from_score(rai))

    if coupling_type == "geo_response_coupled":
        return (
            f"该 cell 地质基础关注度为{grs_level}，施工响应异常指数为{rai_level}，"
            f"主要地质关注项包括 {hazards}；"
            "地质不良证据与施工响应异常存在同步增强特征，建议重点复核。"
        )

    if coupling_type == "geo_dominant_no_obvious_response":
        return (
            f"该 cell 地质基础关注度为{grs_level}，但施工响应异常指数为{rai_level}；"
            f"主要地质关注项包括 {hazards}。"
            "当前表现为地质证据主导，施工响应尚未明显同步增强，应继续跟踪。"
        )

    if coupling_type == "response_anomaly_without_strong_geo_support":
        return (
            f"该 cell 施工响应异常指数为{rai_level}，但地质基础关注度为{grs_level}；"
            "建议检查施工参数、设备工况或数据质量，并结合现场揭示复核。"
        )

    return (
        f"该 cell 地质基础关注度为{grs_level}，施工响应异常指数为{rai_level}，"
        "暂未形成明显地质-施工响应耦合增强特征。"
    )


def couple_geo_response(
    geo_states_df: pd.DataFrame,
    response_df: Optional[pd.DataFrame] = None,
    cells_df: Optional[pd.DataFrame] = None,
    df_plc: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    将 geo_states_df 与 response_df/df_plc 耦合，生成 GRCI。

    推荐用法：
        1. 如果已有 RAI：
            coupled_df = couple_geo_response(
                geo_states_df=geo_states_df,
                response_df=response_df,
            )

        2. 如果只有 PLC：
            coupled_df = couple_geo_response(
                geo_states_df=geo_states_df,
                cells_df=cells_df,
                df_plc=df_plc,
            )

    注意：
        没有 response 数据时，GRCI 设为 NaN。
    """
    if geo_states_df is None or geo_states_df.empty:
        return pd.DataFrame(columns=COUPLED_COLUMNS)

    geo = geo_states_df.copy()

    required_cols = {
        "cell_id",
        "cell_start",
        "cell_end",
        "cell_center",
        "has_geology_evidence",
        "GRS_geo_base",
    }
    missing_cols = required_cols - set(geo.columns)
    if missing_cols:
        raise ValueError(f"geo_states_df 缺少必要字段: {sorted(missing_cols)}")

    geo["cell_id"] = geo["cell_id"].astype(str)

    if response_df is not None and not response_df.empty:
        resp = normalize_response_df(response_df, cells_df=cells_df)
    elif df_plc is not None and cells_df is not None:
        resp = build_response_index_from_plc(
            df_plc=df_plc,
            cells_df=cells_df,
        )
    else:
        resp = pd.DataFrame(
            {
                "cell_id": geo["cell_id"].astype(str).tolist(),
                "RAI": [np.nan] * len(geo),
                "response_support_count": [0] * len(geo),
                "response_metrics": [{} for _ in range(len(geo))],
            }
        )

    if resp is None or resp.empty:
        resp = pd.DataFrame(
            {
                "cell_id": geo["cell_id"].astype(str).tolist(),
                "RAI": [np.nan] * len(geo),
                "response_support_count": [0] * len(geo),
                "response_metrics": [{} for _ in range(len(geo))],
            }
        )

    resp = resp.copy()
    resp["cell_id"] = resp["cell_id"].astype(str)

    merged = geo.merge(
        resp[["cell_id", "RAI", "response_support_count", "response_metrics"]],
        on="cell_id",
        how="left",
    )

    records = []

    for _, row in merged.iterrows():
        cell_id = _safe_str(row.get("cell_id"))

        has_geo = bool(row.get("has_geology_evidence"))
        grs = _clip01(row.get("GRS_geo_base"))

        rai_raw = row.get("RAI")
        response_support_count = int(_safe_float(row.get("response_support_count"), default=0))
        has_response = (
            response_support_count > 0
            and not _is_missing(rai_raw)
            and math.isfinite(_safe_float(rai_raw, default=np.nan))
        )

        if has_geo and has_response:
            rai = _clip01(rai_raw)
            grci = _compute_grci(grs, rai)
            coupling_level = _level_from_score(grci)
            coupling_type = _coupling_type(grs, rai, has_response=True)
        else:
            rai = np.nan if not has_response else _clip01(rai_raw)
            grci = np.nan
            coupling_level = "unknown"
            coupling_type = "no_response_evidence" if not has_response else "no_geo_evidence"

        main_hazards = _as_list(row.get("main_hazards"))

        explanation = _coupling_explanation(
            grs_geo_base=grs,
            rai=None if not has_response else rai,
            has_response=has_response,
            coupling_type=coupling_type,
            main_hazards=[str(x) for x in main_hazards],
        )

        records.append(
            {
                "cell_id": cell_id,
                "cell_start": _safe_float(row.get("cell_start")),
                "cell_end": _safe_float(row.get("cell_end")),
                "cell_center": _safe_float(row.get("cell_center")),

                "has_geology_evidence": bool(has_geo),
                "GRS_geo_base": float(grs),
                "fused_grade": row.get("fused_grade"),
                "main_hazards": _json_clean(main_hazards),

                "has_response_evidence": bool(has_response),
                "RAI": float(rai) if has_response else np.nan,
                "response_support_count": int(response_support_count),
                "response_metrics": _json_clean(row.get("response_metrics") or {}),

                "GRCI": float(grci) if math.isfinite(_safe_float(grci, default=np.nan)) else np.nan,
                "coupling_level": coupling_level,
                "coupling_type": coupling_type,
                "coupling_explanation": explanation,
            }
        )

    out = pd.DataFrame(records)

    for col in COUPLED_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[COUPLED_COLUMNS].copy()

    numeric_cols = [
        "cell_start",
        "cell_end",
        "cell_center",
        "GRS_geo_base",
        "RAI",
        "response_support_count",
        "GRCI",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["response_support_count"] = out["response_support_count"].fillna(0).astype(int)
    out["has_geology_evidence"] = out["has_geology_evidence"].astype(bool)
    out["has_response_evidence"] = out["has_response_evidence"].astype(bool)

    return out


# ============================================================
# 6. 摘要与文本
# ============================================================

def summarize_coupled_df(coupled_df: pd.DataFrame) -> Dict[str, Any]:
    """
    耦合结果摘要。
    """
    if coupled_df is None or coupled_df.empty:
        return {
            "cell_count": 0,
            "has_response_cell_count": 0,
            "computed_grci_cell_count": 0,
            "coupling_level_counts": {},
            "coupling_type_counts": {},
            "GRCI_max": 0.0,
            "GRCI_mean": 0.0,
        }

    df = coupled_df.copy()

    has_response = df.get("has_response_evidence", pd.Series(False, index=df.index)).astype(bool)
    grci = pd.to_numeric(df.get("GRCI", np.nan), errors="coerce")

    return _json_clean(
        {
            "cell_count": int(len(df)),
            "has_response_cell_count": int(has_response.sum()),
            "computed_grci_cell_count": int(grci.notna().sum()),
            "coupling_level_counts": df["coupling_level"].value_counts(dropna=False).to_dict()
            if "coupling_level" in df.columns else {},
            "coupling_type_counts": df["coupling_type"].value_counts(dropna=False).to_dict()
            if "coupling_type" in df.columns else {},
            "GRCI_max": float(grci.max()) if grci.notna().any() else 0.0,
            "GRCI_mean": float(grci.mean()) if grci.notna().any() else 0.0,
        }
    )


def coupled_df_to_text(
    coupled_df: pd.DataFrame,
    chainage_min: Optional[float] = None,
    chainage_max: Optional[float] = None,
    top_k: int = 5,
) -> str:
    """
    将耦合结果转成 prompt 可用短文本。
    """
    if coupled_df is None or coupled_df.empty:
        return "当前范围未形成地质-施工响应耦合结果。"

    df = coupled_df.copy()

    if chainage_min is not None:
        df = df[df["cell_center"] >= float(chainage_min)].copy()

    if chainage_max is not None:
        df = df[df["cell_center"] <= float(chainage_max)].copy()

    if df.empty:
        return "当前指定范围未形成地质-施工响应耦合结果。"

    valid = df[df["GRCI"].notna()].copy()

    if valid.empty:
        return (
            "当前指定范围具有地质融合结果，但缺少有效施工响应数据，"
            "因此未计算 GRCI；不得据此判断施工响应正常。"
        )

    valid = valid.sort_values("GRCI", ascending=False)

    level_counts = valid["coupling_level"].value_counts().to_dict()
    type_counts = valid["coupling_type"].value_counts().to_dict()

    lines = [
        (
            f"地质-施工响应耦合概览：当前范围共有 {len(df)} 个 cell，"
            f"其中 {len(valid)} 个 cell 形成 GRCI。"
            f"耦合等级统计为 {level_counts}，耦合类型统计为 {type_counts}。"
            "GRCI 表示地质-施工响应耦合关注度，不表示灾害发生概率。"
        ),
        "重点耦合 cell 摘要：",
    ]

    for _, row in valid.head(top_k).iterrows():
        grci = _safe_float(row.get("GRCI"))
        grs = _safe_float(row.get("GRS_geo_base"))
        rai = _safe_float(row.get("RAI"))
        level = _level_cn(_safe_str(row.get("coupling_level"), default="unknown"))

        lines.append(
            f"- {row.get('cell_start'):.1f}～{row.get('cell_end'):.1f}m："
            f"GRCI={grci:.2f}，耦合等级为{level}；"
            f"GRS_geo_base={grs:.2f}，RAI={rai:.2f}。"
            f"{row.get('coupling_explanation')}"
        )

    return "\n".join(lines)