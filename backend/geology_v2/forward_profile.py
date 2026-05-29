"""
geology_v2.forward_profile

基于 geo_states_df 构建前方分段关注剖面。

输入：
    geo_states_df:
        fuse_geo_states 输出，每个 cell 一行。

输出：
    forward_profile dict:
        {
            "has_forward_evidence": bool,
            "current_chainage": float,
            "lookahead_m": 30.0,
            "overall_attention_level": "none/low/medium/high",
            "profile": [...]
        }

注意：
1. attention_level 表示关注等级，不是风险概率；
2. has_forward_evidence=False 只能表示前方窗口缺少地质证据，不能写成无风险；
3. main_hazards 来自 geo_states_df 的结构化 hazard_scores / main_hazards；
4. 不生成大段报告文字，只返回结构化数据。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from geology_v2.config import ATTENTION_LEVEL_THRESHOLDS, GRADE_ORDER


# ============================================================
# 1. 基础工具
# ============================================================

def _as_list_safe(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _merge_source_trace(values, max_items: int = 12) -> list[dict]:
    """
    合并多个 cell 的 source_trace。
    """
    out = []
    seen = set()

    for value in values:
        for item in _as_list_safe(value):
            if not isinstance(item, dict):
                continue

            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in seen:
                continue

            seen.add(evidence_id)
            out.append(item)

            if len(out) >= max_items:
                return out

    return out

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
    return str(value).strip()


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


# ============================================================
# 2. attention level
# ============================================================

def _attention_level(score: float, has_evidence: bool) -> str:
    """
    根据 GRS_geo_base 得到关注等级。

    注意：
    关注等级不是概率。
    """
    if not has_evidence:
        return "none"

    value = _safe_float(score)

    if value >= float(ATTENTION_LEVEL_THRESHOLDS.get("high", 0.75)):
        return "high"
    if value >= float(ATTENTION_LEVEL_THRESHOLDS.get("medium", 0.50)):
        return "medium"
    if value >= float(ATTENTION_LEVEL_THRESHOLDS.get("low", 0.25)):
        return "low"
    return "none"


def _overall_attention_level(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "none"

    order = {
        "none": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
    }

    best = "none"
    for item in items:
        level = str(item.get("attention_level", "none"))
        if order.get(level, 0) > order.get(best, 0):
            best = level

    return best


# ============================================================
# 3. 分段聚合
# ============================================================

def _pick_fused_grade(part: pd.DataFrame) -> Optional[str]:
    """
    聚合一个 forward range 内的 fused_grade。

    不是简单取最差：
    1. 优先按 GRS_geo_base 加权支持；
    2. 取支持度最高等级；
    3. 若较差等级支持接近，则保守修正。
    """
    if part is None or part.empty or "fused_grade" not in part.columns:
        return None

    work = part.copy()
    work["__grade"] = work["fused_grade"].map(_normalize_grade)
    work = work[work["__grade"].notna()].copy()

    if work.empty:
        return None

    if "GRS_geo_base" in work.columns:
        work["__weight"] = pd.to_numeric(work["GRS_geo_base"], errors="coerce").fillna(0.0).clip(lower=0.0)
    else:
        work["__weight"] = 1.0

    support = work.groupby("__grade")["__weight"].sum().to_dict()
    if not support:
        return None

    sorted_items = sorted(
        support.items(),
        key=lambda kv: (kv[1], _grade_order(kv[0])),
        reverse=True,
    )

    best_grade = sorted_items[0][0]
    best_support = float(sorted_items[0][1])

    candidates = []
    for grade, value in sorted_items:
        if best_support <= 1e-12:
            continue
        if float(value) >= 0.75 * best_support:
            candidates.append(grade)

    if candidates:
        return max(candidates, key=_grade_order)

    return best_grade


def _aggregate_main_hazards(part: pd.DataFrame, top_k: int = 5) -> List[str]:
    """
    聚合 main_hazards。

    以 cell 的 GRS_geo_base 和 confidence_score 作为权重，
    避免低置信 cell 对前方剖面影响过大。
    """
    if part is None or part.empty or "main_hazards" not in part.columns:
        return []

    scores: Dict[str, float] = {}

    for _, row in part.iterrows():
        grs = _safe_float(row.get("GRS_geo_base"), default=0.0)
        confidence = _safe_float(row.get("confidence_score"), default=0.5)
        weight = max(grs, 0.1) * max(confidence, 0.3)

        for hazard in _as_list(row.get("main_hazards")):
            text = str(hazard).strip()
            if not text:
                continue
            scores[text] = scores.get(text, 0.0) + weight

    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in items[:top_k]]


def _aggregate_confidence(part: pd.DataFrame) -> float:
    if part is None or part.empty or "confidence_score" not in part.columns:
        return 0.0

    values = pd.to_numeric(part["confidence_score"], errors="coerce").fillna(0.0).clip(0, 1)

    if "GRS_geo_base" in part.columns:
        weights = pd.to_numeric(part["GRS_geo_base"], errors="coerce").fillna(0.0).clip(lower=0.0)
        if float(weights.sum()) > 1e-12:
            return float((values * weights).sum() / weights.sum())

    return float(values.mean())


def _aggregate_uncertainty(part: pd.DataFrame) -> str:
    """
    聚合 uncertainty_level。

    只要有 high，就 high；
    否则有 medium，就 medium；
    否则有 low，就 low；
    否则 none/unknown。
    """
    if part is None or part.empty or "uncertainty_level" not in part.columns:
        return "unknown"

    values = set(part["uncertainty_level"].dropna().astype(str).tolist())

    if "high" in values:
        return "high"
    if "medium" in values:
        return "medium"
    if "low" in values:
        return "low"
    if "none" in values:
        return "none"
    return "unknown"


def _collect_supporting_ids(part: pd.DataFrame, col: str) -> List[str]:
    ids: List[Any] = []

    if part is None or part.empty or col not in part.columns:
        return []

    for value in part[col].tolist():
        ids.extend(_as_list(value))

    return _dedup_keep_order(ids)


# ============================================================
# 4. 建议字段
# ============================================================

def _monitoring_focus(main_hazards: List[str], attention_level: str, uncertainty_level: str) -> List[str]:
    focus: List[str] = []

    hazard_text = "、".join(main_hazards)

    if main_hazards:
        focus.append(f"重点复核{hazard_text}相关地质迹象")
    else:
        focus.append("结合掌子面揭示资料复核前方地质条件")

    if any("水" in h for h in main_hazards):
        focus.append("加强掌子面及拱墙出水、渗水变化观察")

    if any(("掉块" in h or "坍塌" in h or "破碎" in h or "裂隙" in h) for h in main_hazards):
        focus.append("关注围岩破碎、裂隙发育及局部掉块迹象")

    if uncertainty_level in {"medium", "high", "unknown"}:
        focus.append("关注多源证据不确定性，必要时结合现场揭示进行核查")

    if attention_level == "high":
        focus.append("建议施工参数和支护响应联动跟踪")

    return _dedup_keep_order(focus)


def _support_actions(main_hazards: List[str], attention_level: str, uncertainty_level: str) -> List[str]:
    actions: List[str] = []

    if attention_level == "high":
        actions.append("施工前进行重点技术交底，保持审慎掘进")
    elif attention_level == "medium":
        actions.append("按中等关注区段进行过程跟踪")
    elif attention_level == "low":
        actions.append("保持常规监测并关注证据变化")
    else:
        actions.append("前方直接证据不足时，不宜作风险降低判断")

    if any("水" in h for h in main_hazards):
        actions.append("提前检查排水、超前探测及应急处置条件")

    if any(("掉块" in h or "坍塌" in h or "破碎" in h) for h in main_hazards):
        actions.append("关注支护时效，必要时加强超前支护或初期支护参数复核")

    if uncertainty_level in {"medium", "high", "unknown"}:
        actions.append("对冲突或不确定证据进行人工复核，不将缺证解释为低风险")

    return _dedup_keep_order(actions)


# ============================================================
# 5. 单个 forward range
# ============================================================

def _build_one_profile_item(
    geo_states_df: pd.DataFrame,
    range_label: str,
    start_chainage: float,
    end_chainage: float,
) -> Dict[str, Any]:
    start = min(float(start_chainage), float(end_chainage))
    end = max(float(start_chainage), float(end_chainage))

    part = geo_states_df[
        (geo_states_df["cell_center"] >= start)
        & (geo_states_df["cell_center"] < end)
    ].copy()

    if part.empty:
        return {
            "range_label": range_label,
            "start_chainage": float(start_chainage),
            "end_chainage": float(end_chainage),
            "main_hazards": [],
            "fused_grade": None,
            "attention_level": "none",
            "confidence_score": 0.0,
            "uncertainty_level": "unknown",
            "monitoring_focus": ["该分段缺少可用前方地质证据，不宜据此判断为低风险"],
            "support_actions": ["建议结合现场揭示和后续预报资料补充核查"],
            "supporting_cell_ids": [],
            "supporting_evidence_ids": [],
            "source_trace": [],
        }

    has_evidence_series = part.get("has_geology_evidence", pd.Series(False, index=part.index)).astype(bool)
    has_evidence = bool(has_evidence_series.any())

    evidence_part = part[has_evidence_series].copy()

    if evidence_part.empty:
        return {
            "range_label": range_label,
            "start_chainage": float(start_chainage),
            "end_chainage": float(end_chainage),
            "main_hazards": [],
            "fused_grade": None,
            "attention_level": "none",
            "confidence_score": 0.0,
            "uncertainty_level": "unknown",
            "monitoring_focus": ["该分段未形成有效地质证据覆盖，不宜据此判断为低风险"],
            "support_actions": ["建议结合现场揭示和后续预报资料补充核查"],
            "supporting_cell_ids": [],
            "supporting_evidence_ids": [],
            "source_trace": [],
        }

    grs = pd.to_numeric(evidence_part.get("GRS_geo_base", 0.0), errors="coerce").fillna(0.0).clip(0, 1)
    score = float(grs.max()) if len(grs) else 0.0

    attention_level = _attention_level(score, has_evidence=has_evidence)
    main_hazards = _aggregate_main_hazards(evidence_part)
    fused_grade = _pick_fused_grade(evidence_part)
    confidence_score = _aggregate_confidence(evidence_part)
    uncertainty_level = _aggregate_uncertainty(evidence_part)
    source_trace = _merge_source_trace(
        evidence_part["source_trace"].tolist()
        if "source_trace" in evidence_part.columns
        else []
    )

    return {
        "range_label": range_label,
        "start_chainage": float(start_chainage),
        "end_chainage": float(end_chainage),
        "main_hazards": _json_clean(main_hazards),
        "fused_grade": fused_grade,
        "attention_level": attention_level,
        "confidence_score": float(confidence_score),
        "uncertainty_level": uncertainty_level,
        "monitoring_focus": _json_clean(
            _monitoring_focus(main_hazards, attention_level, uncertainty_level)
        ),
        "support_actions": _json_clean(
            _support_actions(main_hazards, attention_level, uncertainty_level)
        ),
        "supporting_cell_ids": _json_clean(
            _dedup_keep_order(evidence_part["cell_id"].tolist())
            if "cell_id" in evidence_part.columns else []
        ),
        "supporting_evidence_ids": _json_clean(
            _collect_supporting_ids(evidence_part, "supporting_evidence_ids")
        ),
    }


# ============================================================
# 6. 主入口
# ============================================================

def build_forward_profile(
    geo_states_df: pd.DataFrame,
    current_chainage: float,
    lookahead_m: float = 30.0,
    step_m: float = 10.0,
    advance_direction: int = 1,
) -> dict:
    """
    构建前方分段地质关注剖面。

    参数：
        geo_states_df:
            fuse_geo_states 输出。

        current_chainage:
            当前掌子面或当前掘进里程。

        lookahead_m:
            前方查看距离，默认 30m。

        step_m:
            分段步长，默认 10m。

        advance_direction:
            掘进方向。
            1 表示里程增大方向；
            -1 表示里程减小方向。

    返回：
        {
            "has_forward_evidence": bool,
            "current_chainage": float,
            "lookahead_m": 30.0,
            "overall_attention_level": "none/low/medium/high",
            "profile": [...]
        }
    """
    current = _safe_float(current_chainage)
    lookahead = abs(_safe_float(lookahead_m, default=30.0))
    step = abs(_safe_float(step_m, default=10.0))

    if step <= 0:
        step = 10.0

    direction = 1 if int(advance_direction or 1) >= 0 else -1

    if geo_states_df is None or geo_states_df.empty:
        return {
            "has_forward_evidence": False,
            "current_chainage": current,
            "lookahead_m": float(lookahead),
            "overall_attention_level": "none",
            "profile": [],
        }

    df = geo_states_df.copy()

    required_cols = {"cell_id", "cell_center", "has_geology_evidence"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"geo_states_df missing required columns: {sorted(missing_cols)}")

    df["cell_center"] = pd.to_numeric(df["cell_center"], errors="coerce")
    df = df.dropna(subset=["cell_center"]).copy()

    profile: List[Dict[str, Any]] = []

    distance_start = 0.0
    while distance_start < lookahead - 1e-9:
        distance_end = min(distance_start + step, lookahead)

        if direction > 0:
            start_chainage = current + distance_start
            end_chainage = current + distance_end
        else:
            start_chainage = current - distance_start
            end_chainage = current - distance_end

        range_label = f"{int(distance_start)}-{int(distance_end)}m"

        item = _build_one_profile_item(
            geo_states_df=df,
            range_label=range_label,
            start_chainage=start_chainage,
            end_chainage=end_chainage,
        )
        profile.append(item)

        distance_start = distance_end

    has_forward_evidence = any(bool(item.get("supporting_cell_ids")) for item in profile)
    overall_level = _overall_attention_level(profile)

    return _json_clean(
        {
            "has_forward_evidence": bool(has_forward_evidence),
            "current_chainage": float(current),
            "lookahead_m": float(lookahead),
            "overall_attention_level": overall_level,
            "profile": profile,
        }
    )


def summarize_forward_profile(forward_profile: dict) -> dict:
    """
    调试用摘要。
    """
    if not isinstance(forward_profile, dict):
        return {
            "has_forward_evidence": False,
            "overall_attention_level": "none",
            "profile_count": 0,
            "range_levels": {},
        }

    profile = forward_profile.get("profile") or []
    range_levels = {
        item.get("range_label"): item.get("attention_level")
        for item in profile
        if isinstance(item, dict)
    }

    return {
        "has_forward_evidence": bool(forward_profile.get("has_forward_evidence")),
        "overall_attention_level": forward_profile.get("overall_attention_level", "none"),
        "profile_count": len(profile),
        "range_levels": range_levels,
    }