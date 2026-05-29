"""
geology_v2.fusion_engine

将 cell_evidence_df 与 normalized_evidence_df 融合成 geo_states_df。

输入：
    cells_df:
        build_chainage_cells 的输出。

    cell_evidence_df:
        project_evidence_to_cells 的输出。

    normalized_evidence_df:
        normalize_evidence_df 的输出。

输出：
    geo_states_df:
        每一行对应一个 cell 的融合地质状态 GeoState。

设计原则：
1. 不直接修改旧逻辑；
2. 输出结构化数据，不生成大段自然语言；
3. 围岩等级形成 grade_distribution，不简单取最差；
4. hazard 形成 hazard_scores，不只拼字符串；
5. 无证据时 has_geology_evidence=False，不写“无风险/无异常”；
6. conflict_level 表示多源证据冲突程度；
7. GRS_geo_base 是纯地质基础关注度，不引入 RAI。
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from geology_v2.config import (
    CONFIDENCE_THRESHOLDS,
    CONFLICT_THRESHOLDS,
    GRADE_ATTENTION_SCORE,
    GRADE_ORDER,
    get_hazard_weight,
    normalize_hazard_tag,
)


# ============================================================
# 1. 输出字段
# ============================================================

GEO_STATE_COLUMNS = [
    "cell_id",
    "cell_start",
    "cell_end",
    "cell_center",

    "has_geology_evidence",

    "fused_grade",
    "grade_distribution",

    "hazard_scores",
    "main_hazards",

    "water_score",
    "collapse_score",
    "deformation_score",

    "source_support",
    "source_type_count",
    "evidence_count",

    "confidence_score",
    "uncertainty_level",

    "conflict_level",
    "conflict_reasons",

    "supporting_evidence_ids",

    "source_trace",

    "GRS_geo_base",
    
]


HAZARD_LABELS = {
    "water": "出水",
    # 注意：
    # 不把线状出水、股状出水、渗滴水默认升级成“突涌水”。
    # 只有 parser 明确抽取到“突涌水/突水”时，后续再单独设 explicit_water_inrush。
    "water_inrush": "出水增强",
    "collapse": "坍塌",
    "block_fall": "掉块",
    "deformation": "变形",
    "fractured_rock": "围岩破碎",
    "extremely_fractured_rock": "围岩极破碎",
    "joint_development": "裂隙发育",
    "dense_joints": "裂隙密集",
    "weak_interlayer": "软弱夹层",
    "mud_filling": "泥质填充",
    "soft_hard_uneven": "软硬不均",
    "reflection_anomaly": "反射异常",
    "strong_reflection_anomaly": "明显反射异常",
    "poor_stability": "稳定性较差",
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(_safe_float(value, default=default))
    except Exception:
        return int(default)


def _safe_str(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    return str(value).strip()


def _clip01(value: Any) -> float:
    return float(max(0.0, min(_safe_float(value), 1.0)))


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
        # 兼容类似 "['出水', '掉块']" 或 JSON list。
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
        for sep in ["；", ";", "，", ",", "|"]:
            if sep in text:
                return [x.strip() for x in text.split(sep) if x.strip()]
        return [text]
    return [value]


def _json_clean(value: Any) -> Any:
    """
    将 numpy / pandas 类型清洗成 JSON 友好类型。
    """
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


def _normalize_grade(value: Any) -> Optional[str]:
    if _is_missing(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    mapping = {
        "1": "Ⅰ",
        "2": "Ⅱ",
        "3": "Ⅲ",
        "4": "Ⅳ",
        "5": "Ⅴ",
        "I": "Ⅰ",
        "II": "Ⅱ",
        "III": "Ⅲ",
        "IV": "Ⅳ",
        "V": "Ⅴ",
        "Ⅰ": "Ⅰ",
        "Ⅱ": "Ⅱ",
        "Ⅲ": "Ⅲ",
        "Ⅳ": "Ⅳ",
        "Ⅴ": "Ⅴ",
    }
    return mapping.get(text.upper(), mapping.get(text, text))


def _grade_order(grade: Any) -> int:
    g = _normalize_grade(grade)
    if g is None:
        return 0
    return int(GRADE_ORDER.get(g, 0))


def _grade_attention_score(grade: Any) -> float:
    g = _normalize_grade(grade)
    if g is None:
        return 0.0
    return _clip01(GRADE_ATTENTION_SCORE.get(g, 0.0))


def _confidence_to_level(score: float) -> str:
    score = _clip01(score)
    if score >= float(CONFIDENCE_THRESHOLDS.get("high", 0.75)):
        return "high"
    if score >= float(CONFIDENCE_THRESHOLDS.get("medium", 0.45)):
        return "medium"
    if score >= float(CONFIDENCE_THRESHOLDS.get("low", 0.20)):
        return "low"
    return "none"


def _uncertainty_from_conflict_and_confidence(conflict_score: float, confidence_score: float) -> str:
    """
    uncertainty 越高，表示融合结果越需要谨慎解释。

    注意：
    - 无证据时返回 unknown；
    - 有证据但 confidence 低或 conflict 高时，uncertainty 升高。
    """
    conflict_score = _clip01(conflict_score)
    confidence_score = _clip01(confidence_score)

    uncertainty_score = max(1.0 - confidence_score, conflict_score)

    if uncertainty_score >= float(CONFLICT_THRESHOLDS.get("high", 0.75)):
        return "high"
    if uncertainty_score >= float(CONFLICT_THRESHOLDS.get("medium", 0.50)):
        return "medium"
    if uncertainty_score >= float(CONFLICT_THRESHOLDS.get("low", 0.25)):
        return "low"
    return "none"


def _conflict_level(conflict_score: float) -> str:
    conflict_score = _clip01(conflict_score)

    if conflict_score >= float(CONFLICT_THRESHOLDS.get("high", 0.75)):
        return "high"
    if conflict_score >= float(CONFLICT_THRESHOLDS.get("medium", 0.50)):
        return "medium"
    if conflict_score >= float(CONFLICT_THRESHOLDS.get("low", 0.25)):
        return "low"
    return "none"


# ============================================================
# 3. evidence-cell 去重降权
# ============================================================

def _make_dedup_key(row: pd.Series) -> str:
    """
    构造 cell 内证据去重 key。

    目的：
    同一报告、同一来源、同一空间类型、同一中心里程、同一主要信息的重复记录，
    不应在同一 cell 内无限线性叠加。

    例如 HSP collapse_points 被拆成多个 anomaly_point 后，
    如果同一个点被多个相似行重复命中，需要 capped aggregation。
    """
    report_id = _safe_str(row.get("report_id"), default="")
    source_type = _safe_str(row.get("source_type_norm"), default="unknown")
    spatial_type = _safe_str(row.get("spatial_type"), default="unknown")
    center = round(_safe_float(row.get("center_chainage"), default=-999999.0), 1)
    grade = _normalize_grade(row.get("grade")) or ""
    tags = "|".join(sorted([str(x) for x in _as_list(row.get("hazard_tags"))]))

    return f"{report_id}::{source_type}::{spatial_type}::{center}::{grade}::{tags}"


def _cap_duplicate_effective_weights(group: pd.DataFrame) -> pd.DataFrame:
    """
    对同一个 cell 内的重复证据做 capped weighting。

    做法：
    - 对相同 dedup_key 的多条记录，不让权重总和等于简单 sum；
    - 将该组总权重压缩为 max_weight * log1p(n)，最多不超过原 sum；
    - 这样既保留多条证据的支持感，又避免重复解析导致无限放大。
    """
    if group is None or group.empty:
        return group

    out = group.copy()
    out["effective_weight"] = pd.to_numeric(out["effective_weight"], errors="coerce").fillna(0.0)
    out["_dedup_key"] = out.apply(_make_dedup_key, axis=1)
    out["effective_weight_capped"] = out["effective_weight"]

    for _, idx in out.groupby("_dedup_key").groups.items():
        idx = list(idx)
        if len(idx) <= 1:
            continue

        weights = out.loc[idx, "effective_weight"].astype(float)
        raw_sum = float(weights.sum())
        max_weight = float(weights.max())
        capped_sum = min(raw_sum, max_weight * (1.0 + math.log(len(idx))))

        if raw_sum > 1e-12:
            scale = capped_sum / raw_sum
            out.loc[idx, "effective_weight_capped"] = weights * scale

    return out


# ============================================================
# 4. 分布与评分
# ============================================================

def _build_grade_distribution(group: pd.DataFrame) -> Tuple[Dict[str, Dict[str, float]], Optional[str]]:
    """
    构建围岩等级支持分布，并给出 fused_grade。

    fused_grade 不是简单取最差：
    1. 先按有效权重形成 grade_distribution；
    2. 默认取支持度最高的等级；
    3. 若第二支持等级与最高等级接近，且更差，则做保守修正。
    """
    if group is None or group.empty or "grade" not in group.columns:
        return {}, None

    work = group.copy()
    work["__grade"] = work["grade"].map(_normalize_grade)
    work = work[work["__grade"].notna()].copy()

    if work.empty:
        return {}, None

    weight_col = "effective_weight_capped" if "effective_weight_capped" in work.columns else "effective_weight"
    work["__weight"] = pd.to_numeric(work[weight_col], errors="coerce").fillna(0.0).clip(lower=0.0)

    support = work.groupby("__grade")["__weight"].sum().to_dict()
    total = float(sum(support.values()))

    if total <= 1e-12:
        return {}, None

    distribution: Dict[str, Dict[str, float]] = {}
    for grade, value in support.items():
        distribution[str(grade)] = {
            "support": float(value),
            "share": float(value / total),
            "attention_score": float(_grade_attention_score(grade)),
        }

    sorted_items = sorted(
        distribution.items(),
        key=lambda kv: (kv[1]["support"], _grade_order(kv[0])),
        reverse=True,
    )

    best_grade = sorted_items[0][0]
    best_support = sorted_items[0][1]["support"]

    # 保守修正：如果更差等级支持度接近最高支持度，则取更差的那个。
    conservative_candidates = []
    for grade, info in sorted_items:
        if info["support"] >= 0.75 * best_support:
            conservative_candidates.append(grade)

    if conservative_candidates:
        fused_grade = max(conservative_candidates, key=_grade_order)
    else:
        fused_grade = best_grade

    return _json_clean(distribution), fused_grade


def _event_state(row: pd.Series, state_col: str, fallback_flag_col: str) -> str:
    """
    读取三态字段：positive / negative / unknown。

    兼容旧数据：
    如果没有 state_col，但 fallback_flag_col == 1，则认为 positive；
    否则 unknown。
    """
    value = row.get(state_col)

    if not _is_missing(value):
        text = str(value).strip().lower()
        if text == "positive":
            return "positive"
        if text == "negative":
            return "negative"
        if text == "unknown":
            # 对新 normalizer 输出的 unknown，仍允许旧 flag=1 兜底，
            # 避免 HSP anomaly_point 等派生证据被 unknown 掩盖。
            if fallback_flag_col in row and _safe_int(row.get(fallback_flag_col)) == 1:
                return "positive"
            return "unknown"

    if fallback_flag_col in row and _safe_int(row.get(fallback_flag_col)) == 1:
        return "positive"

    return "unknown"


def _append_valid_hazard_key(keys: List[str], key: Any) -> None:
    """
    只保留 config 中明确有权重的 hazard key。
    """
    if key is None:
        return

    text = str(key).strip()
    if not text:
        return

    if get_hazard_weight(text) > 0:
        keys.append(text)


def _collect_hazard_keys(row: pd.Series) -> List[str]:
    """
    从一条 evidence 里收集 hazard key。

    注意：
    1. hazard_tags 已在 normalizer 中清洗；
    2. water/collapse/deformation 使用三态字段；
    3. unknown 不作为 negative，也不参与 hazard 增强。
    """
    keys: List[str] = []

    for tag in _as_list(row.get("hazard_tags")):
        key = normalize_hazard_tag(str(tag))
        _append_valid_hazard_key(keys, key)

    water_state = _event_state(row, "water_state", "water_flag")
    collapse_state = _event_state(row, "collapse_state", "collapse_flag")
    deformation_state = _event_state(row, "deformation_state", "deformation_flag")

    if water_state == "positive":
        water_type = _safe_str(row.get("water_type"))
        if water_type:
            key = normalize_hazard_tag(water_type) or "water"
            _append_valid_hazard_key(keys, key)
        else:
            _append_valid_hazard_key(keys, "water")

    if collapse_state == "positive":
        _append_valid_hazard_key(keys, "block_fall")

    if deformation_state == "positive":
        _append_valid_hazard_key(keys, "deformation")

    joint = _safe_str(row.get("joint_development"))
    if joint:
        if "密集" in joint:
            _append_valid_hazard_key(keys, "dense_joints")
        elif "发育" in joint:
            _append_valid_hazard_key(keys, "joint_development")

    rock_mass = _safe_str(row.get("rock_mass_state"))
    if rock_mass:
        if "极破碎" in rock_mass:
            _append_valid_hazard_key(keys, "extremely_fractured_rock")
        elif "破碎" in rock_mass:
            _append_valid_hazard_key(keys, "fractured_rock")

    stability = _safe_str(row.get("stability"))
    if stability and "差" in stability:
        _append_valid_hazard_key(keys, "poor_stability")

    return _dedup_keep_order(keys)

def _combine_noisy_or(values: List[float]) -> float:
    """
    用 Noisy-OR 合成同一 hazard 的多条证据贡献。

    作用：
    1. 多条证据会提高 hazard score；
    2. 分数不会简单线性叠加；
    3. 输出限制在 0~1；
    4. 避免 HSP anomaly_point 重复证据把分数无限放大。
    """
    if not values:
        return 0.0

    product = 1.0

    for value in values:
        v = _clip01(value)
        product *= 1.0 - v

    return _clip01(1.0 - product)


def _build_hazard_scores(group: pd.DataFrame) -> Dict[str, float]:
    """
    构建 hazard_scores。

    每个 hazard 的贡献：
        contribution = hazard_weight * min(effective_weight_capped, 1.5)

    同一 hazard 多条证据使用 Noisy-OR 合成。
    """
    if group is None or group.empty:
        return {}

    weight_col = "effective_weight_capped" if "effective_weight_capped" in group.columns else "effective_weight"

    bucket: Dict[str, List[float]] = {}

    for _, row in group.iterrows():
        evidence_weight = min(_safe_float(row.get(weight_col), default=0.0), 1.5)
        if evidence_weight <= 1e-12:
            continue

        hazard_keys = _collect_hazard_keys(row)
        for key in hazard_keys:
            if not key:
                continue
            hazard_weight = get_hazard_weight(key)
            if hazard_weight <= 0:
                continue

            contribution = _clip01(hazard_weight * evidence_weight)
            bucket.setdefault(key, []).append(contribution)

    scores = {
        key: _combine_noisy_or(values)
        for key, values in bucket.items()
    }

    return _json_clean(dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True)))


def _main_hazards_from_scores(hazard_scores: Dict[str, float], top_k: int = 5) -> List[str]:
    if not hazard_scores:
        return []

    items = sorted(
        hazard_scores.items(),
        key=lambda kv: float(kv[1]),
        reverse=True,
    )

    selected = []
    for key, value in items[:top_k]:
        if float(value) <= 0.05:
            continue
        selected.append(HAZARD_LABELS.get(key, key))

    return selected


def _source_support(group: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    if group is None or group.empty:
        return {}

    weight_col = "effective_weight_capped" if "effective_weight_capped" in group.columns else "effective_weight"
    out: Dict[str, Dict[str, float]] = {}

    for source, part in group.groupby("source_type_norm"):
        source_key = _safe_str(source, default="unknown")
        weights = pd.to_numeric(part[weight_col], errors="coerce").fillna(0.0)

        out[source_key] = {
            "weight_sum": float(weights.sum()),
            "weight_max": float(weights.max()) if len(weights) else 0.0,
            "evidence_count": int(part["evidence_id"].nunique()) if "evidence_id" in part.columns else int(len(part)),
        }

    return _json_clean(out)
def _compact_raw_text(value: Any, max_chars: int = 160) -> str:
    """
    压缩原文片段，只用于溯源展示。
    不在这里生成新的地质判断。
    """
    text = _safe_str(value)
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join([line.strip() for line in text.split("\n") if line.strip()])
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def _trace_range(row: pd.Series) -> dict[str, Any]:
    return {
        "start_chainage": _safe_float(row.get("start_chainage"), default=None),
        "end_chainage": _safe_float(row.get("end_chainage"), default=None),
        "center_chainage": _safe_float(row.get("center_chainage"), default=None),
        "face_chainage": _safe_float(row.get("face_chainage"), default=None),
    }


def _build_source_trace(group: pd.DataFrame, top_n: int = 12) -> list[dict[str, Any]]:
    """
    构造 cell 级证据溯源列表。

    目的：
    1. 后续文本能说明“来自哪一份报告/哪一段/哪条证据”；
    2. 不允许 report_renderer 自己编造来源；
    3. 保留 evidence_id/report_id/raw_text_snippet，便于人工审查。
    """
    if group is None or group.empty:
        return []

    weight_col = "effective_weight_capped" if "effective_weight_capped" in group.columns else "effective_weight"

    work = group.copy()
    work["__weight"] = pd.to_numeric(work[weight_col], errors="coerce").fillna(0.0)
    work = work.sort_values("__weight", ascending=False)

    traces: list[dict[str, Any]] = []
    seen = set()

    for _, row in work.iterrows():
        evidence_id = _safe_str(row.get("evidence_id"))
        if not evidence_id or evidence_id in seen:
            continue
        seen.add(evidence_id)

        trace = {
            "evidence_id": evidence_id,
            "report_id": _safe_str(row.get("report_id")),
            "source_type": _safe_str(row.get("source_type_norm")),
            "evidence_role": _safe_str(row.get("evidence_role")),
            "spatial_type": _safe_str(row.get("spatial_type")),
            "range": _trace_range(row),
            "grade": _normalize_grade(row.get("grade")),
            "hazard_tags": _json_clean(_as_list(row.get("hazard_tags"))),
            "attribute_tags": _json_clean(_as_list(row.get("attribute_tags"))),
            "method_tags": _json_clean(_as_list(row.get("method_tags"))),
            "water_state": _safe_str(row.get("water_state"), default="unknown"),
            "collapse_state": _safe_str(row.get("collapse_state"), default="unknown"),
            "deformation_state": _safe_str(row.get("deformation_state"), default="unknown"),
            "effective_weight": float(_safe_float(row.get(weight_col), default=0.0)),
            "raw_text_snippet": _compact_raw_text(row.get("raw_text")),
        }

        traces.append(_json_clean(trace))

        if len(traces) >= top_n:
            break

    return traces

def _confidence_score(group: pd.DataFrame, conflict_score: float) -> float:
    """
    融合置信度。

    影响因素：
    1. 总证据权重；
    2. 来源类型数量；
    3. 证据数量；
    4. conflict 惩罚。

    注意：
    confidence_score 只是融合置信度，不是准确率。
    """
    if group is None or group.empty:
        return 0.0

    weight_col = "effective_weight_capped" if "effective_weight_capped" in group.columns else "effective_weight"
    weights = pd.to_numeric(group[weight_col], errors="coerce").fillna(0.0).clip(lower=0.0)

    total_weight = float(weights.sum())
    evidence_count = int(group["evidence_id"].nunique()) if "evidence_id" in group.columns else int(len(group))
    source_type_count = int(group["source_type_norm"].nunique()) if "source_type_norm" in group.columns else 1

    weight_factor = 1.0 - math.exp(-total_weight / 3.0)
    evidence_factor = min(1.0, 0.50 + 0.10 * evidence_count)
    source_factor = min(1.0, 0.70 + 0.15 * max(source_type_count - 1, 0))

    conflict_penalty = 1.0 - 0.35 * _clip01(conflict_score)

    return _clip01(weight_factor * evidence_factor * source_factor * conflict_penalty)


def _grs_geo_base(
    fused_grade: Optional[str],
    hazard_scores: Dict[str, float],
    confidence_score: float,
    has_geology_evidence: bool,
) -> float:
    """
    纯地质基础关注度 GRS_geo_base。

    不引入 RAI，不引入施工响应。
    """
    if not has_geology_evidence:
        return 0.0

    grade_score = _grade_attention_score(fused_grade)
    hazard_score = max([float(v) for v in hazard_scores.values()], default=0.0)
    avg_hazard_score = (
        sum(float(v) for v in hazard_scores.values()) / max(len(hazard_scores), 1)
        if hazard_scores else 0.0
    )

    # max hazard 反映主控风险，avg hazard 反映多灾种叠加。
    hazard_component = _clip01(0.75 * hazard_score + 0.25 * avg_hazard_score)

    value = (
        0.45 * grade_score
        + 0.45 * hazard_component
        + 0.10 * _clip01(confidence_score)
    )

    return _clip01(value)


# ============================================================
# 5. 冲突检测
# ============================================================

def _source_grade_map(group: pd.DataFrame) -> Dict[str, str]:
    out: Dict[str, str] = {}

    if group is None or group.empty or "grade" not in group.columns:
        return out

    weight_col = "effective_weight_capped" if "effective_weight_capped" in group.columns else "effective_weight"

    for source, part in group.groupby("source_type_norm"):
        part = part.copy()
        part["__grade"] = part["grade"].map(_normalize_grade)
        part = part[part["__grade"].notna()].copy()
        if part.empty:
            continue

        support = (
            part.groupby("__grade")[weight_col]
            .sum()
            .sort_values(ascending=False)
        )

        if not support.empty:
            out[_safe_str(source, default="unknown")] = str(support.index[0])

    return out


def _detect_grade_conflict(
    group: pd.DataFrame,
    grade_distribution: Dict[str, Dict[str, float]],
) -> Tuple[float, List[str]]:
    """
    检测围岩等级冲突。

    主要看：
    1. grade_distribution 中等级跨度；
    2. 次级支持度是否足够高；
    3. 不同 source_type 的主导等级是否差异较大。
    """
    reasons: List[str] = []

    if not grade_distribution or len(grade_distribution) <= 1:
        return 0.0, reasons

    grades = list(grade_distribution.keys())
    orders = [_grade_order(g) for g in grades if _grade_order(g) > 0]

    if not orders:
        return 0.0, reasons

    span = max(orders) - min(orders)
    supports = sorted(
        [float(info.get("share", 0.0)) for info in grade_distribution.values()],
        reverse=True,
    )

    second_share = supports[1] if len(supports) > 1 else 0.0

    score = 0.0

    if span >= 2 and second_share >= 0.20:
        score = max(score, 0.70)
        reasons.append(
            f"围岩等级证据存在差异：等级跨度 {span} 级，次级支持占比 {second_share:.2f}"
        )
    elif span >= 1 and second_share >= 0.30:
        score = max(score, 0.45)
        reasons.append(
            f"围岩等级证据存在一定差异：次级支持占比 {second_share:.2f}"
        )

    source_map = _source_grade_map(group)
    if len(source_map) >= 2:
        source_orders = [_grade_order(g) for g in source_map.values() if _grade_order(g) > 0]
        if source_orders and max(source_orders) - min(source_orders) >= 2:
            score = max(score, 0.75)
            reasons.append(f"不同来源主导围岩等级不一致：{source_map}")

    return _clip01(score), reasons


def _detect_state_conflict(
    group: pd.DataFrame,
    state_col: str,
    fallback_flag_col: str,
    label: str,
) -> Tuple[float, List[str]]:
    """
    检测 water/collapse/deformation 三态冲突。

    只比较：
        positive vs negative

    不比较：
        positive vs unknown

    因为 unknown 只是未提及，不能当成否定证据。
    """
    reasons: List[str] = []

    if group is None or group.empty:
        return 0.0, reasons

    weight_col = "effective_weight_capped" if "effective_weight_capped" in group.columns else "effective_weight"

    work = group.copy()
    work["__state"] = work.apply(
        lambda row: _event_state(row, state_col, fallback_flag_col),
        axis=1,
    )

    work["__weight"] = pd.to_numeric(
        work[weight_col],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)

    positive = work[work["__state"] == "positive"]
    negative = work[work["__state"] == "negative"]

    # unknown 不参与冲突检测。
    if positive.empty or negative.empty:
        return 0.0, reasons

    positive_weight = float(positive["__weight"].sum())
    negative_weight = float(negative["__weight"].sum())

    positive_sources = set(positive["source_type_norm"].astype(str).tolist()) if "source_type_norm" in work.columns else set()
    negative_sources = set(negative["source_type_norm"].astype(str).tolist()) if "source_type_norm" in work.columns else set()

    if positive_weight >= 0.60 and negative_weight >= 0.60:
        score = 0.45

        if positive_sources and negative_sources and positive_sources.isdisjoint(negative_sources):
            score = 0.60

        reasons.append(
            f"{label}判断存在差异：部分证据明确提示{label}，部分证据明确否定{label}"
        )
        return score, reasons

    return 0.0, reasons


def _detect_conflicts(
    group: pd.DataFrame,
    grade_distribution: Dict[str, Dict[str, float]],
) -> Tuple[float, str, List[str]]:
    grade_score, grade_reasons = _detect_grade_conflict(group, grade_distribution)
    water_score, water_reasons = _detect_state_conflict(
        group,
        state_col="water_state",
        fallback_flag_col="water_flag",
        label="出水",
    )

    collapse_score, collapse_reasons = _detect_state_conflict(
        group,
        state_col="collapse_state",
        fallback_flag_col="collapse_flag",
        label="掉块/坍塌",
    )

    deformation_score, deformation_reasons = _detect_state_conflict(
        group,
        state_col="deformation_state",
        fallback_flag_col="deformation_flag",
        label="变形",
    )

    conflict_score = max(grade_score, water_score, collapse_score, deformation_score)
    reasons = grade_reasons + water_reasons + collapse_reasons + deformation_reasons
    level = _conflict_level(conflict_score)

    return _clip01(conflict_score), level, _dedup_keep_order(reasons)


# ============================================================
# 6. 单 cell 融合
# ============================================================

def _empty_geo_state(cell: pd.Series) -> Dict[str, Any]:
    return {
        "cell_id": _safe_str(cell.get("cell_id")),
        "cell_start": _safe_float(cell.get("cell_start")),
        "cell_end": _safe_float(cell.get("cell_end")),
        "cell_center": _safe_float(cell.get("cell_center")),

        "has_geology_evidence": False,

        "fused_grade": None,
        "grade_distribution": {},

        "hazard_scores": {},
        "main_hazards": [],

        "water_score": 0.0,
        "collapse_score": 0.0,
        "deformation_score": 0.0,

        "source_support": {},
        "source_type_count": 0,
        "evidence_count": 0,

        "confidence_score": 0.0,
        "uncertainty_level": "unknown",

        "conflict_level": "none",
        "conflict_reasons": [],

        "supporting_evidence_ids": [],
        "source_trace": [],
        "GRS_geo_base": 0.0,
    }


def _fuse_one_cell(cell: pd.Series, group: pd.DataFrame) -> Dict[str, Any]:
    if group is None or group.empty:
        return _empty_geo_state(cell)

    group = _cap_duplicate_effective_weights(group)

    supporting_ids = _dedup_keep_order(group["evidence_id"].tolist())
    source_support = _source_support(group)
    source_trace = _build_source_trace(group)
    source_trace = _build_source_trace(group)

    grade_distribution, fused_grade = _build_grade_distribution(group)
    conflict_score, conflict_level, conflict_reasons = _detect_conflicts(group, grade_distribution)

    hazard_scores = _build_hazard_scores(group)
    main_hazards = _main_hazards_from_scores(hazard_scores)

    water_score = max(
        float(hazard_scores.get("water", 0.0)),
        float(hazard_scores.get("water_inrush", 0.0)),
    )
    collapse_score = max(
        float(hazard_scores.get("collapse", 0.0)),
        float(hazard_scores.get("block_fall", 0.0)),
    )
    deformation_score = float(hazard_scores.get("deformation", 0.0))

    source_type_count = int(group["source_type_norm"].nunique()) if "source_type_norm" in group.columns else 0
    evidence_count = int(group["evidence_id"].nunique()) if "evidence_id" in group.columns else len(group)

    confidence_score = _confidence_score(group, conflict_score)
    uncertainty_level = _uncertainty_from_conflict_and_confidence(conflict_score, confidence_score)

    grs_geo_base = _grs_geo_base(
        fused_grade=fused_grade,
        hazard_scores=hazard_scores,
        confidence_score=confidence_score,
        has_geology_evidence=True,
    )

    return {
        "cell_id": _safe_str(cell.get("cell_id")),
        "cell_start": _safe_float(cell.get("cell_start")),
        "cell_end": _safe_float(cell.get("cell_end")),
        "cell_center": _safe_float(cell.get("cell_center")),

        "has_geology_evidence": True,

        "fused_grade": fused_grade,
        "grade_distribution": _json_clean(grade_distribution),

        "hazard_scores": _json_clean(hazard_scores),
        "main_hazards": _json_clean(main_hazards),

        "water_score": float(water_score),
        "collapse_score": float(collapse_score),
        "deformation_score": float(deformation_score),

        "source_support": _json_clean(source_support),
        "source_type_count": int(source_type_count),
        "evidence_count": int(evidence_count),

        "confidence_score": float(confidence_score),
        "uncertainty_level": uncertainty_level,

        "conflict_level": conflict_level,
        "conflict_reasons": _json_clean(conflict_reasons),

        "supporting_evidence_ids": _json_clean(supporting_ids),
        "source_trace": _json_clean(source_trace),

        "GRS_geo_base": float(grs_geo_base),
    }


# ============================================================
# 7. 主入口
# ============================================================

def fuse_geo_states(
    cells_df: pd.DataFrame,
    cell_evidence_df: pd.DataFrame,
    normalized_evidence_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    融合每个 cell 的地质状态。

    参数：
        cells_df:
            build_chainage_cells 输出。

        cell_evidence_df:
            project_evidence_to_cells 输出。

        normalized_evidence_df:
            normalize_evidence_df 输出。

    返回：
        geo_states_df，每个 cell 一行。

    输出字段：
        cell_id
        cell_start
        cell_end
        cell_center
        has_geology_evidence
        fused_grade
        grade_distribution
        hazard_scores
        main_hazards
        water_score
        collapse_score
        deformation_score
        source_support
        source_type_count
        evidence_count
        confidence_score
        uncertainty_level
        conflict_level
        conflict_reasons
        supporting_evidence_ids
        GRS_geo_base
    """
    if cells_df is None or cells_df.empty:
        return pd.DataFrame(columns=GEO_STATE_COLUMNS)

    cells = cells_df.copy()

    required_cell_cols = {"cell_id", "cell_start", "cell_end", "cell_center"}
    missing_cell_cols = required_cell_cols - set(cells.columns)
    if missing_cell_cols:
        raise ValueError(f"cells_df missing required columns: {sorted(missing_cell_cols)}")

    # 如果没有任何投影关系，也要返回每个 cell 的空状态。
    if cell_evidence_df is None or cell_evidence_df.empty:
        records = [_empty_geo_state(row) for _, row in cells.iterrows()]
        return pd.DataFrame(records)[GEO_STATE_COLUMNS]

    if normalized_evidence_df is None or normalized_evidence_df.empty:
        records = [_empty_geo_state(row) for _, row in cells.iterrows()]
        return pd.DataFrame(records)[GEO_STATE_COLUMNS]

    ce = cell_evidence_df.copy()
    ne = normalized_evidence_df.copy()

    required_ce_cols = {"cell_id", "evidence_id", "effective_weight"}
    missing_ce_cols = required_ce_cols - set(ce.columns)
    if missing_ce_cols:
        raise ValueError(f"cell_evidence_df missing required columns: {sorted(missing_ce_cols)}")

    required_ne_cols = {"evidence_id"}
    missing_ne_cols = required_ne_cols - set(ne.columns)
    if missing_ne_cols:
        raise ValueError(f"normalized_evidence_df missing required columns: {sorted(missing_ne_cols)}")

    # 避免 merge 后 source_type_norm / spatial_type 冲突：
    # 以 cell_evidence_df 的投影字段为准，normalized 只补充地质属性。
    ne_cols = [
        "evidence_id",
        "report_id",
        "report_date",
        "issue_date",
        "evidence_role",
        "start_chainage",
        "end_chainage",
        "center_chainage",
        "face_chainage",
        "grade",
        "lithology",
        "weathering",
        "joint_development",
        "rock_mass_state",
        "stability",

        # 旧兼容字段。
        "water_flag",
        "water_type",
        "collapse_flag",
        "deformation_flag",

        # 新三态字段。
        "water_state",
        "collapse_state",
        "deformation_state",

        # tag 分层。
        "hazard_tags",
        "attribute_tags",
        "method_tags",
        "unknown_hazard_tags",

        "confidence_text",
        "raw_text",
        "attrs_obj",
        "parse_warnings",
    ]
    ne_cols = [c for c in ne_cols if c in ne.columns]

    merged = ce.merge(
        ne[ne_cols],
        on="evidence_id",
        how="left",
        suffixes=("", "_evidence"),
    )

    # 确保必要字段存在。
    for col, default in [
        ("source_type_norm", "unknown"),
        ("spatial_type", "unknown"),
        ("effective_weight", 0.0),
        ("water_flag", 0),
        ("collapse_flag", 0),
        ("deformation_flag", 0),
        ("water_state", "unknown"),
        ("collapse_state", "unknown"),
        ("deformation_state", "unknown"),
        ("hazard_tags", []),
        ("attribute_tags", []),
        ("method_tags", []),
        ("unknown_hazard_tags", []),
    ]:
        if col not in merged.columns:
            # list 默认值不能直接复用同一个对象。
            if isinstance(default, list):
                merged[col] = [[] for _ in range(len(merged))]
            else:
                merged[col] = default

    merged["effective_weight"] = pd.to_numeric(
        merged["effective_weight"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)

    # 过滤掉无效权重。
    merged = merged[merged["effective_weight"] > 1e-12].copy()

    group_map = {
        str(cell_id): part.copy()
        for cell_id, part in merged.groupby("cell_id", sort=False)
    }

    records = []
    for _, cell in cells.iterrows():
        cell_id = _safe_str(cell.get("cell_id"))
        group = group_map.get(cell_id, pd.DataFrame())
        records.append(_fuse_one_cell(cell, group))

    out = pd.DataFrame(records)

    for col in GEO_STATE_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[GEO_STATE_COLUMNS].copy()

    # 数值列整理。
    numeric_cols = [
        "cell_start",
        "cell_end",
        "cell_center",
        "water_score",
        "collapse_score",
        "deformation_score",
        "source_type_count",
        "evidence_count",
        "confidence_score",
        "GRS_geo_base",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    out["source_type_count"] = out["source_type_count"].astype(int)
    out["evidence_count"] = out["evidence_count"].astype(int)
    out["has_geology_evidence"] = out["has_geology_evidence"].astype(bool)

    return out


# ============================================================
# 8. 便捷摘要函数
# ============================================================

def summarize_geo_states(geo_states_df: pd.DataFrame) -> Dict[str, Any]:
    """
    调试用摘要。

    注意：
    high_attention_cell_count 只是基于 GRS_geo_base 的高关注 cell 数，
    不是灾害发生概率。
    """
    if geo_states_df is None or geo_states_df.empty:
        return {
            "cell_count": 0,
            "evidence_cell_count": 0,
            "high_attention_cell_count": 0,
            "grade_counts": {},
            "main_hazard_counts": {},
            "conflict_level_counts": {},
            "uncertainty_level_counts": {},
            "GRS_geo_base_max": 0.0,
            "GRS_geo_base_mean": 0.0,
        }

    df = geo_states_df.copy()

    has_evidence = df.get("has_geology_evidence", pd.Series(False, index=df.index)).astype(bool)
    grs = pd.to_numeric(df.get("GRS_geo_base", 0.0), errors="coerce").fillna(0.0)

    hazard_counter: Dict[str, int] = {}
    if "main_hazards" in df.columns:
        for items in df["main_hazards"].tolist():
            for item in _as_list(items):
                text = str(item).strip()
                if not text:
                    continue
                hazard_counter[text] = hazard_counter.get(text, 0) + 1

    return _json_clean(
        {
            "cell_count": int(len(df)),
            "evidence_cell_count": int(has_evidence.sum()),
            "high_attention_cell_count": int((grs >= 0.55).sum()),
            "grade_counts": df["fused_grade"].dropna().value_counts().to_dict()
            if "fused_grade" in df.columns else {},
            "main_hazard_counts": dict(sorted(hazard_counter.items(), key=lambda kv: kv[1], reverse=True)),
            "conflict_level_counts": df["conflict_level"].value_counts(dropna=False).to_dict()
            if "conflict_level" in df.columns else {},
            "uncertainty_level_counts": df["uncertainty_level"].value_counts(dropna=False).to_dict()
            if "uncertainty_level" in df.columns else {},
            "GRS_geo_base_max": float(grs.max()) if len(grs) else 0.0,
            "GRS_geo_base_mean": float(grs.mean()) if len(grs) else 0.0,
        }
    )
