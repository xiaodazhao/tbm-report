# -*- coding: utf-8 -*-
"""
geology_v2.evidence_dedup

用途：
    对 normalized_evidence_df 做轻量去重。

当前只处理：
    source_type_norm == "HSP"
    spatial_type == "anomaly_point"

解决问题：
    HSP 表格相邻分段边界处，同一个 collapse point 可能同时挂到上一段终点
    和下一段起点，导致同一 DK 里程的 anomaly_point 被重复投影、重复计权。

设计原则：
1. 不修改 HSP parser；
2. 不处理 TSP / face_sketch / HSP segment / report_conclusion / background；
3. 在 availability filter 之后、project_evidence_to_cells 之前执行；
4. 合并重复 anomaly_point 时保留一个 base row，同时记录 duplicate_count、
   duplicate_evidence_ids、dedup_key、dedup_note，方便 explainability 展示。
"""

from __future__ import annotations

import ast
import json
import math
from typing import Any, Iterable, List, Optional

import pandas as pd


# ============================================================
# 1. 基础安全工具
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


def _safe_str(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    text = str(value).strip()
    return text if text else default


def _to_numeric(value: Any, default: Optional[float] = None) -> Optional[float]:
    if _is_missing(value):
        return default

    try:
        x = float(value)
        if math.isfinite(x):
            return float(x)
    except Exception:
        pass

    return default


def _as_list(value: Any) -> List[Any]:
    """
    normalized_df 中 list 字段可能是真 list，也可能是字符串形式的 list。
    这里尽量安全地转成 list。
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)

    if isinstance(value, float) and math.isnan(value):
        return []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []

        # JSON list / dict
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                return [obj]
        except Exception:
            pass

        # Python literal list，例如 "['掉块', '围岩破碎']"
        try:
            obj = ast.literal_eval(text)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, tuple) or isinstance(obj, set):
                return list(obj)
            if isinstance(obj, dict):
                return [obj]
        except Exception:
            pass

        # 普通分隔字符串
        for sep in ["；", ";", "，", ",", "|"]:
            if sep in text:
                return [x.strip() for x in text.split(sep) if x.strip()]

        return [text]

    return [value]


def _dedup_keep_order(values: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    seen = set()

    for value in values:
        if _is_missing(value):
            continue

        try:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            key = str(value)

        if key in seen:
            continue

        seen.add(key)
        out.append(value)

    return out


def _round_chainage_key(value: Any, tol: float) -> Optional[float]:
    """
    按容差归一里程。

    例如：
        value=1013224.04, tol=0.5 -> 1013224.0
    """
    x = _to_numeric(value, default=None)
    if x is None:
        return None

    tol = abs(_to_numeric(tol, default=0.0) or 0.0)
    if tol <= 0:
        return float(x)

    return float(round(x / tol) * tol)


def _merge_state(values: Iterable[Any]) -> str:
    """
    三态合并：
        positive 优先，其次 negative，其次 unknown。
    """
    states = [_safe_str(v).lower() for v in values if _safe_str(v)]

    if "positive" in states:
        return "positive"
    if "negative" in states:
        return "negative"
    return "unknown"


def _short_text(value: Any, max_chars: int = 160) -> str:
    text = _safe_str(value)
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join([line.strip() for line in text.split("\n") if line.strip()])

    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."

    return text


def _json_clean(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

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


# ============================================================
# 2. hazard family 与 base row 选择
# ============================================================

def _hazard_family(row: pd.Series) -> str:
    """
    HSP anomaly_point 去重用 hazard family。

    注意：
    不要求 hazard_tags 完全一致。
    DK1013+224 这种边界点可能来自相邻分段，标签略有差异，
    但只要都表达 collapse / 掉块，就应视为同一个点状风险。
    """
    hazard_text = "；".join([str(x) for x in _as_list(row.get("hazard_tags"))])

    collapse_flag = int(_to_numeric(row.get("collapse_flag"), default=0) or 0)
    water_flag = int(_to_numeric(row.get("water_flag"), default=0) or 0)
    deformation_flag = int(_to_numeric(row.get("deformation_flag"), default=0) or 0)

    collapse_state = _safe_str(row.get("collapse_state")).lower()
    water_state = _safe_str(row.get("water_state")).lower()
    deformation_state = _safe_str(row.get("deformation_state")).lower()

    if (
        collapse_flag == 1
        or collapse_state == "positive"
        or "掉块" in hazard_text
        or "坍塌" in hazard_text
        or "塌" in hazard_text
    ):
        return "collapse"

    if (
        water_flag == 1
        or water_state == "positive"
        or "出水" in hazard_text
        or "涌水" in hazard_text
        or "突水" in hazard_text
    ):
        return "water"

    if deformation_flag == 1 or deformation_state == "positive":
        return "deformation"

    return "other"


def _score_base_row(row: pd.Series) -> tuple:
    """
    选择重复组中的 base row。

    优先级：
    1. evidence_strength 高；
    2. confidence 高；
    3. hazard_tags 数量多；
    4. raw_text 更长；
    5. 原始顺序更靠前。
    """
    evidence_strength = _to_numeric(row.get("evidence_strength"), default=0.0) or 0.0

    confidence = _to_numeric(row.get("confidence"), default=None)

    if confidence is None:
        confidence = _to_numeric(row.get("confidence_score"), default=None)

    if confidence is None:
        confidence_text = _safe_str(row.get("confidence_text")).lower()
        confidence = {
            "high": 1.0,
            "medium": 0.7,
            "low": 0.4,
            "unknown": 0.2,
        }.get(confidence_text, 0.0)

    hazard_tag_count = len(_as_list(row.get("hazard_tags")))
    raw_text_len = len(_safe_str(row.get("raw_text")))

    row_order = _to_numeric(row.get("__row_order"), default=0.0) or 0.0

    return (
        float(evidence_strength),
        float(confidence),
        int(hazard_tag_count),
        int(raw_text_len),
        -float(row_order),
    )


def _make_dedup_key(row: pd.Series, chainage_tol_m: float, face_tol_m: float) -> str:
    report_id = _safe_str(row.get("report_id"), default="")
    source_type_norm = _safe_str(row.get("source_type_norm"), default="")
    spatial_type = _safe_str(row.get("spatial_type"), default="")

    center_key = _round_chainage_key(row.get("center_chainage"), chainage_tol_m)
    face_key = _round_chainage_key(row.get("face_chainage"), face_tol_m)

    family = _hazard_family(row)

    key_obj = {
        "report_id": report_id,
        "source_type_norm": source_type_norm,
        "spatial_type": spatial_type,
        "face_chainage": face_key,
        "center_chainage": center_key,
        "hazard_family": family,
    }

    return json.dumps(key_obj, ensure_ascii=False, sort_keys=True)


# ============================================================
# 3. 重复组合并
# ============================================================

def _merge_duplicate_group(group: pd.DataFrame) -> dict:
    """
    合并一个 dedup_key 下的多条 HSP anomaly_point。

    说明：
    - 如果 group 只有 1 条，表示没有发生真实合并；
      duplicate_count=1，dedup_note 置空。
    - 如果 group 多于 1 条，才记录 dedup_note 和 deduplicated warning。
    """
    if group is None or group.empty:
        return {}

    work = group.copy()

    scores = []
    for idx, row in work.iterrows():
        scores.append((idx, _score_base_row(row)))

    best_idx = sorted(scores, key=lambda x: x[1], reverse=True)[0][0]
    base = work.loc[best_idx].to_dict()

    # 当前组内所有 evidence_id
    duplicate_evidence_ids = []
    if "evidence_id" in work.columns:
        duplicate_evidence_ids = _dedup_keep_order(
            [
                _safe_str(x)
                for x in work["evidence_id"].tolist()
                if _safe_str(x)
            ]
        )

    # base row 自己的 evidence_id，作为兜底
    base_evidence_id = _safe_str(base.get("evidence_id"))
    if not duplicate_evidence_ids and base_evidence_id:
        duplicate_evidence_ids = [base_evidence_id]

    duplicate_count = int(len(duplicate_evidence_ids)) if duplicate_evidence_ids else int(len(work))
    if duplicate_count <= 0:
        duplicate_count = 1

    base["duplicate_count"] = duplicate_count
    base["duplicate_evidence_ids"] = _json_clean(duplicate_evidence_ids)
    base["dedup_key"] = _safe_str(work.iloc[0].get("__dedup_key"))

    if duplicate_count > 1:
        base["dedup_note"] = "merged HSP anomaly_point duplicate records"
    else:
        base["dedup_note"] = ""

    # 合并 tags
    for col in [
        "hazard_tags",
        "attribute_tags",
        "method_tags",
        "unknown_hazard_tags",
    ]:
        merged = []
        if col in work.columns:
            for value in work[col].tolist():
                merged.extend(_as_list(value))
        base[col] = _json_clean(_dedup_keep_order(merged))

    # 三态字段合并
    for flag_col in ["water_flag", "collapse_flag", "deformation_flag"]:
        if flag_col in work.columns:
            nums = [
                int(_to_numeric(v, default=0) or 0)
                for v in work[flag_col].tolist()
            ]
            base[flag_col] = int(max(nums) if nums else 0)

    for state_col in ["water_state", "collapse_state", "deformation_state"]:
        if state_col in work.columns:
            base[state_col] = _merge_state(work[state_col].tolist())

    # 数值字段取 max
    for num_col in [
        "evidence_strength",
        "source_reliability",
        "effective_weight",
        "confidence",
        "confidence_score",
    ]:
        if num_col in work.columns:
            values = [
                _to_numeric(v, default=None)
                for v in work[num_col].tolist()
            ]
            values = [v for v in values if v is not None]
            if values:
                base[num_col] = float(max(values))

    # parse_warnings 合并
    parse_warnings = []
    if "parse_warnings" in work.columns:
        for value in work["parse_warnings"].tolist():
            parse_warnings.extend(_as_list(value))

    if duplicate_count > 1:
        parse_warnings.append(
            f"deduplicated_hsp_anomaly_point: merged {duplicate_count} duplicate records"
        )

    base["parse_warnings"] = _json_clean(_dedup_keep_order(parse_warnings))

    # raw_text 保留 base，其他重复项短文本另存
    duplicate_raw_text_snippets = []
    for idx, row in work.iterrows():
        if idx == best_idx:
            continue
        snippet = _short_text(row.get("raw_text"), max_chars=160)
        if snippet:
            duplicate_raw_text_snippets.append(snippet)

    base["duplicate_raw_text_snippets"] = _json_clean(
        _dedup_keep_order(duplicate_raw_text_snippets)
    )

    # source_trace 如果存在也合并
    if "source_trace" in work.columns:
        source_trace = []
        for value in work["source_trace"].tolist():
            source_trace.extend(_as_list(value))
        base["source_trace"] = _json_clean(_dedup_keep_order(source_trace))

    # 清理内部字段
    base.pop("__row_order", None)
    base.pop("__dedup_key", None)

    return _json_clean(base)

# ============================================================
# 4. 主函数
# ============================================================

def deduplicate_hsp_anomaly_points(
    normalized_df: pd.DataFrame,
    chainage_tol_m: float = 0.5,
    face_tol_m: float = 1.0,
) -> pd.DataFrame:
    """
    去重 HSP anomaly_point。

    只处理：
        source_type_norm == "HSP"
        spatial_type == "anomaly_point"

    其他证据原样保留。

    返回：
        去重后的 normalized_df，并在 attrs 中写入 hsp_anomaly_point_dedup 摘要。
    """
    if normalized_df is None or normalized_df.empty:
        return normalized_df

    df = normalized_df.copy()

    new_cols_defaults = {
        "duplicate_count": 1,
        "duplicate_evidence_ids": None,
        "dedup_key": "",
        "dedup_note": "",
        "duplicate_raw_text_snippets": None,
    }

    for col, default in new_cols_defaults.items():
        if col not in df.columns:
            if default is None:
                df[col] = [[] for _ in range(len(df))]
            else:
                df[col] = default

    if "source_type_norm" not in df.columns or "spatial_type" not in df.columns:
        out = df.copy()
        out.attrs.update(getattr(normalized_df, "attrs", {}))
        out.attrs["hsp_anomaly_point_dedup"] = {
            "enabled": True,
            "reason": "missing source_type_norm or spatial_type column",
            "input_count": int(len(df)),
            "output_count": int(len(df)),
            "input_hsp_anomaly_point_count": 0,
            "output_hsp_anomaly_point_count": 0,
            "merged_record_count": 0,
            "merged_group_count": 0,
        }
        return out

    source = df["source_type_norm"].astype(str)
    spatial = df["spatial_type"].astype(str)

    target_mask = source.eq("HSP") & spatial.eq("anomaly_point")

    target = df[target_mask].copy()
    others = df[~target_mask].copy()

    input_hsp_count = int(len(target))

    if target.empty:
        out = df.copy()
        out.attrs.update(getattr(normalized_df, "attrs", {}))
        out.attrs["hsp_anomaly_point_dedup"] = {
            "enabled": True,
            "input_count": int(len(df)),
            "output_count": int(len(out)),
            "input_hsp_anomaly_point_count": 0,
            "output_hsp_anomaly_point_count": 0,
            "merged_record_count": 0,
            "merged_group_count": 0,
        }
        return out

    target["__row_order"] = list(range(len(target)))
    target["__dedup_key"] = target.apply(
        lambda row: _make_dedup_key(
            row=row,
            chainage_tol_m=chainage_tol_m,
            face_tol_m=face_tol_m,
        ),
        axis=1,
    )

    merged_records = []
    duplicate_groups = []

    for dedup_key, group in target.groupby("__dedup_key", sort=False):
        merged = _merge_duplicate_group(group)
        if not merged:
            continue

        merged_records.append(merged)

        if len(group) > 1:
            duplicate_groups.append(
                {
                    "dedup_key": dedup_key,
                    "duplicate_count": int(len(group)),
                    "duplicate_evidence_ids": _dedup_keep_order(
                        [_safe_str(x) for x in group["evidence_id"].tolist()]
                        if "evidence_id" in group.columns else []
                    ),
                    "center_chainage_values": [
                        _to_numeric(x, default=None)
                        for x in group.get("center_chainage", pd.Series(dtype=float)).tolist()
                    ],
                    "face_chainage_values": [
                        _to_numeric(x, default=None)
                        for x in group.get("face_chainage", pd.Series(dtype=float)).tolist()
                    ],
                }
            )

    dedup_target = pd.DataFrame(merged_records)

    all_cols = list(df.columns)
    for col in dedup_target.columns:
        if col not in all_cols:
            all_cols.append(col)

    for col in all_cols:
        if col not in others.columns:
            if col in new_cols_defaults and new_cols_defaults[col] is None:
                others[col] = [[] for _ in range(len(others))]
            elif col in new_cols_defaults:
                others[col] = new_cols_defaults[col]
            else:
                others[col] = None

        if col not in dedup_target.columns:
            if col in new_cols_defaults and new_cols_defaults[col] is None:
                dedup_target[col] = [[] for _ in range(len(dedup_target))]
            elif col in new_cols_defaults:
                dedup_target[col] = new_cols_defaults[col]
            else:
                dedup_target[col] = None

    out = pd.concat(
        [
            others[all_cols],
            dedup_target[all_cols],
        ],
        ignore_index=True,
    )

    if "center_chainage" in out.columns:
        out["__sort_center"] = pd.to_numeric(out["center_chainage"], errors="coerce")
    else:
        out["__sort_center"] = float("nan")

    if "evidence_id" in out.columns:
        out["__sort_evidence_id"] = out["evidence_id"].astype(str)
    else:
        out["__sort_evidence_id"] = ""

    out = out.sort_values(
        by=["__sort_center", "__sort_evidence_id"],
        na_position="last",
    ).drop(columns=["__sort_center", "__sort_evidence_id"]).reset_index(drop=True)

    for col in [
        "start_chainage",
        "end_chainage",
        "center_chainage",
        "face_chainage",
        "source_reliability",
        "evidence_strength",
        "water_flag",
        "collapse_flag",
        "deformation_flag",
        "duplicate_count",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    for col in ["water_flag", "collapse_flag", "deformation_flag", "duplicate_count"]:
        if col in out.columns:
            out[col] = out[col].fillna(0).astype(int)

    output_hsp_count = int(
        (
            out.get("source_type_norm", pd.Series(dtype=str)).astype(str).eq("HSP")
            & out.get("spatial_type", pd.Series(dtype=str)).astype(str).eq("anomaly_point")
        ).sum()
    )

    dedup_info = {
        "enabled": True,
        "chainage_tol_m": float(chainage_tol_m),
        "face_tol_m": float(face_tol_m),
        "input_count": int(len(df)),
        "output_count": int(len(out)),
        "input_hsp_anomaly_point_count": input_hsp_count,
        "output_hsp_anomaly_point_count": output_hsp_count,
        "merged_record_count": int(input_hsp_count - output_hsp_count),
        "merged_group_count": int(len(duplicate_groups)),
        "duplicate_groups": _json_clean(duplicate_groups),
    }

    out.attrs.update(getattr(normalized_df, "attrs", {}))
    out.attrs["hsp_anomaly_point_dedup"] = dedup_info

    return out


def summarize_hsp_anomaly_point_dedup(normalized_df: pd.DataFrame) -> dict:
    """
    便捷摘要函数，ceshi.py 可选打印。
    """
    if normalized_df is None:
        return {
            "enabled": False,
            "reason": "normalized_df is None",
        }

    return dict(getattr(normalized_df, "attrs", {}).get("hsp_anomaly_point_dedup", {}))