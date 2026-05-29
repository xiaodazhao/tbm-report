# -*- coding: utf-8 -*-
"""
geology_v2/explainability.py

用途：
    对 geology_v2 的单个 cell 融合结果做“可解释性输出”。

核心函数：
    explain_geo_state(cell_id, geo_states_df, cell_evidence_df, normalized_df)
    explain_geo_state_text(cell_id, geo_states_df, cell_evidence_df, normalized_df)

说明：
    1. GRS_geo_base 解释优先读取 fusion_engine.py 已经输出的真实组件：
       grade_score_component / hazard_component / confidence_component。
    2. 如果旧数据没有这些字段，才回退到解释模块反推。
    3. 如果 HSP anomaly_point 做过去重合并，并带有 duplicate_count / duplicate_evidence_ids，
       则在 top evidence 中展示合并信息。
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

try:
    from utils.chainage_utils import format_chainage_dk
except Exception:  # pragma: no cover
    def format_chainage_dk(value, unknown="未知里程", prefix="DK"):
        try:
            if value is None:
                return unknown
            x = float(value)
            if not math.isfinite(x):
                return unknown
            if abs(x) >= 100000:
                km = int(math.floor(x / 1000))
                meter = int(round(x - km * 1000))
            else:
                km = int(math.floor(x))
                meter = int(round((x - km) * 1000))
            if meter >= 1000:
                km += meter // 1000
                meter = meter % 1000
            return f"{prefix}{km}+{meter:03d}"
        except Exception:
            return unknown


GRADE_SCORE_MAP = {
    "Ⅰ": 0.05,
    "I": 0.05,
    "Ⅱ": 0.20,
    "II": 0.20,
    "Ⅲ": 0.40,
    "III": 0.40,
    "Ⅳ": 0.70,
    "IV": 0.70,
    "Ⅴ": 1.00,
    "V": 1.00,
}


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    return text if text else default


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None:
            return default
        x = float(value)
        if not math.isfinite(x):
            return default
        return x
    except Exception:
        return default


def _clip01(value: Any) -> float:
    x = _safe_float(value, 0.0)
    if x is None:
        x = 0.0
    return float(max(0.0, min(float(x), 1.0)))


def _dk(value: Any) -> str:
    return format_chainage_dk(value, unknown="未知里程", prefix="DK")


def _dk_range(start: Any, end: Any) -> str:
    return f"{_dk(start)}～{_dk(end)}"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
            try:
                obj = json.loads(text)
                if isinstance(obj, list):
                    return obj
                return [obj]
            except Exception:
                pass

        if text.startswith("[") and text.endswith("]"):
            body = text[1:-1].strip()
            if not body:
                return []
            return [x.strip().strip("'").strip('"') for x in body.split(",") if x.strip()]

        return [text]

    return [value]


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _dedup_keep_order(values: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _short_text(text: Any, max_chars: int = 120) -> str:
    s = _safe_str(text)
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_chars:
        return s[: max_chars - 3].rstrip() + "..."
    return s


def _extract_grade_distribution(value: Any) -> Dict[str, Dict[str, float]]:
    obj = _as_dict(value)
    out: Dict[str, Dict[str, float]] = {}
    for grade, info in obj.items():
        if isinstance(info, dict):
            out[str(grade)] = {
                "support": float(_safe_float(info.get("support"), 0.0) or 0.0),
                "share": float(_safe_float(info.get("share"), 0.0) or 0.0),
                "attention_score": float(_safe_float(info.get("attention_score"), 0.0) or 0.0),
            }
        else:
            out[str(grade)] = {
                "support": float(_safe_float(info, 0.0) or 0.0),
                "share": 0.0,
                "attention_score": float(GRADE_SCORE_MAP.get(str(grade), 0.0)),
            }
    return out


def _extract_hazard_scores(value: Any) -> Dict[str, float]:
    obj = _as_dict(value)
    out: Dict[str, float] = {}
    for key, score in obj.items():
        out[str(key)] = float(_safe_float(score, 0.0) or 0.0)
    return out


def _make_evidence_lookup(normalized_df: pd.DataFrame) -> pd.DataFrame:
    if normalized_df is None or normalized_df.empty:
        return pd.DataFrame()

    ev = normalized_df.copy()
    if "evidence_id" not in ev.columns:
        return pd.DataFrame()

    ev = ev.drop_duplicates(subset=["evidence_id"], keep="first")
    return ev


def _join_cell_evidence(
    cell_id: str,
    cell_evidence_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
) -> pd.DataFrame:
    if cell_evidence_df is None or cell_evidence_df.empty:
        return pd.DataFrame()

    ce = cell_evidence_df[cell_evidence_df["cell_id"].astype(str) == str(cell_id)].copy()
    if ce.empty:
        return ce

    ev = _make_evidence_lookup(normalized_df)
    if not ev.empty:
        keep_cols = [
            "evidence_id",
            "report_id",
            "source_type_norm",
            "evidence_role",
            "spatial_type",
            "start_chainage",
            "end_chainage",
            "center_chainage",
            "face_chainage",
            "grade",
            "hazard_tags",
            "attribute_tags",
            "method_tags",
            "water_state",
            "collapse_state",
            "deformation_state",
            "raw_text",

            # HSP anomaly_point dedup fields
            "duplicate_count",
            "duplicate_evidence_ids",
            "dedup_key",
            "dedup_note",
            "duplicate_raw_text_snippets",
        ]
        keep_cols = [c for c in keep_cols if c in ev.columns]
        ce = ce.merge(ev[keep_cols], on="evidence_id", how="left", suffixes=("", "_ev"))

    weight_col = "effective_weight_capped" if "effective_weight_capped" in ce.columns else "effective_weight"
    if weight_col in ce.columns:
        ce["__weight"] = pd.to_numeric(ce[weight_col], errors="coerce").fillna(0.0)
        ce = ce.sort_values("__weight", ascending=False).reset_index(drop=True)
    else:
        ce["__weight"] = 0.0

    return ce


def _explain_grade(row: pd.Series, evidence_part: pd.DataFrame) -> Dict[str, Any]:
    fused_grade = _safe_str(row.get("fused_grade"), default="未形成明确等级")
    grade_distribution = _extract_grade_distribution(row.get("grade_distribution"))

    evidence_items: List[Dict[str, Any]] = []
    if not evidence_part.empty and "grade" in evidence_part.columns:
        for _, ev in evidence_part.iterrows():
            grade = _safe_str(ev.get("grade"))
            if not grade:
                continue
            evidence_items.append(
                {
                    "evidence_id": _safe_str(ev.get("evidence_id")),
                    "report_id": _safe_str(ev.get("report_id")),
                    "source_type": _safe_str(ev.get("source_type_norm")),
                    "spatial_type": _safe_str(ev.get("spatial_type")),
                    "grade": grade,
                    "effective_weight": float(_safe_float(ev.get("__weight"), 0.0) or 0.0),
                    "range": {
                        "start": _safe_float(ev.get("start_chainage"), None),
                        "end": _safe_float(ev.get("end_chainage"), None),
                        "center": _safe_float(ev.get("center_chainage"), None),
                        "face": _safe_float(ev.get("face_chainage"), None),
                    },
                }
            )

    sorted_dist = sorted(
        grade_distribution.items(),
        key=lambda kv: float(kv[1].get("support", 0.0)),
        reverse=True,
    )

    return {
        "fused_grade": fused_grade,
        "grade_distribution": grade_distribution,
        "grade_distribution_sorted": [
            {"grade": k, **v} for k, v in sorted_dist
        ],
        "evidence_items": evidence_items[:10],
        "logic": (
            "fused_grade 由 grade_distribution 中不同围岩等级的有效权重支持度决定；"
            "通常以支持度最高等级为主，并在相邻等级接近时保守解释。"
        ),
    }


def _explain_hazards(row: pd.Series, evidence_part: pd.DataFrame) -> Dict[str, Any]:
    main_hazards = [_safe_str(x) for x in _as_list(row.get("main_hazards")) if _safe_str(x)]
    hazard_scores = _extract_hazard_scores(row.get("hazard_scores"))

    support_by_hazard: Dict[str, List[Dict[str, Any]]] = {h: [] for h in main_hazards}

    if not evidence_part.empty and "hazard_tags" in evidence_part.columns:
        for _, ev in evidence_part.iterrows():
            tags = [_safe_str(x) for x in _as_list(ev.get("hazard_tags")) if _safe_str(x)]
            if not tags:
                continue

            for hazard in main_hazards:
                if hazard not in tags:
                    continue

                support_by_hazard.setdefault(hazard, []).append(
                    {
                        "evidence_id": _safe_str(ev.get("evidence_id")),
                        "report_id": _safe_str(ev.get("report_id")),
                        "source_type": _safe_str(ev.get("source_type_norm")),
                        "spatial_type": _safe_str(ev.get("spatial_type")),
                        "effective_weight": float(_safe_float(ev.get("__weight"), 0.0) or 0.0),
                        "raw_text_snippet": _short_text(ev.get("raw_text"), 140),
                    }
                )

    for hazard, items in list(support_by_hazard.items()):
        support_by_hazard[hazard] = sorted(
            items,
            key=lambda x: x.get("effective_weight", 0.0),
            reverse=True,
        )[:6]

    sorted_scores = sorted(hazard_scores.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "main_hazards": main_hazards,
        "hazard_scores_sorted": [
            {"hazard_key": k, "score": float(v)} for k, v in sorted_scores
        ],
        "support_by_hazard": support_by_hazard,
        "logic": (
            "main_hazards 来自 hazard_scores 排名前列的结构化地质关注项；"
            "hazard_scores 由命中该 cell 的多条证据按 effective_weight 叠加/融合得到，"
            "只解释证据中已经出现的标签，不新增报告没有出现的地质现象。"
        ),
    }


def _infer_grs_components(row: pd.Series) -> Dict[str, Any]:
    """
    尽量解释 GRS_geo_base 的组成。

    优先级：
    1. 如果 geo_states_df 中已有 fusion_engine 真实输出组件，
       直接读取 grade_score_component / hazard_component / confidence_component；
    2. 如果没有真实组件，则回退到旧的解释性反推。
    """
    grs = float(_safe_float(row.get("GRS_geo_base"), 0.0) or 0.0)

    has_direct_components = all(
        name in row.index
        for name in [
            "grade_score_component",
            "hazard_component",
            "confidence_component",
        ]
    )

    if has_direct_components:
        grade_score_component = float(_safe_float(row.get("grade_score_component"), 0.0) or 0.0)
        hazard_component = float(_safe_float(row.get("hazard_component"), 0.0) or 0.0)
        confidence_component = float(_safe_float(row.get("confidence_component"), 0.0) or 0.0)

        formula_text = _safe_str(
            row.get("GRS_formula_text"),
            default=(
                "GRS_geo_base = 0.45×grade_score_component "
                "+ 0.45×hazard_component + 0.10×confidence_component"
            ),
        )

        component_method = _safe_str(
            row.get("GRS_component_method"),
            default="direct_from_fusion_engine",
        )

        reconstructed = _clip01(
            0.45 * grade_score_component
            + 0.45 * hazard_component
            + 0.10 * confidence_component
        )
        residual = grs - reconstructed

        return {
            "component_source": "direct_from_geo_states_df",
            "GRS_geo_base": grs,
            "grade_score_component": grade_score_component,
            "hazard_component": hazard_component,
            "confidence_component": confidence_component,
            "GRS_formula_text": formula_text,
            "GRS_component_method": component_method,
            "reconstructed_formula": formula_text,
            "reconstructed_value": float(reconstructed),
            "residual_to_actual": float(residual),
            "note": (
                "当前 GRS 组件来自 fusion_engine 在计算 GRS_geo_base 时的真实输出，"
                "不是 explainability 模块反推。"
            ),
        }

    # fallback：旧数据没有真实组件时才反推
    fused_grade = _safe_str(row.get("fused_grade"))
    grade_score = float(GRADE_SCORE_MAP.get(fused_grade, 0.0))

    hazard_scores = _extract_hazard_scores(row.get("hazard_scores"))
    hazard_component = max(hazard_scores.values()) if hazard_scores else 0.0

    confidence_score = float(_safe_float(row.get("confidence_score"), 0.0) or 0.0)

    reconstructed = 0.45 * grade_score + 0.45 * hazard_component + 0.10 * confidence_score
    residual = grs - reconstructed

    return {
        "component_source": "inferred_fallback",
        "GRS_geo_base": grs,
        "fused_grade": fused_grade,
        "grade_score_inferred": grade_score,
        "hazard_component_inferred": float(hazard_component),
        "confidence_score": confidence_score,
        "reconstructed_formula": "0.45×grade_score + 0.45×hazard_component + 0.10×confidence_score",
        "reconstructed_value": float(reconstructed),
        "residual_to_actual": float(residual),
        "note": (
            "当前 geo_states_df 未提供真实 GRS 组件，因此使用解释性反推；"
            "若 residual_to_actual 偏差较大，应以 fusion_engine 实际公式为准。"
        ),
    }


def _explain_confidence_conflict(row: pd.Series, evidence_part: pd.DataFrame) -> Dict[str, Any]:
    confidence_score = float(_safe_float(row.get("confidence_score"), 0.0) or 0.0)
    uncertainty_level = _safe_str(row.get("uncertainty_level"), default="unknown")
    conflict_level = _safe_str(row.get("conflict_level"), default="unknown")
    conflict_reasons = _as_list(row.get("conflict_reasons"))

    source_types = []
    if not evidence_part.empty:
        col = "source_type_norm" if "source_type_norm" in evidence_part.columns else "source_type"
        if col in evidence_part.columns:
            source_types = _dedup_keep_order([_safe_str(x) for x in evidence_part[col].tolist() if _safe_str(x)])

    evidence_count = int(_safe_float(row.get("evidence_count"), len(evidence_part)) or 0)
    source_type_count = int(_safe_float(row.get("source_type_count"), len(source_types)) or 0)

    return {
        "confidence_score": confidence_score,
        "uncertainty_level": uncertainty_level,
        "conflict_level": conflict_level,
        "conflict_reasons": conflict_reasons,
        "source_types": source_types,
        "source_type_count": source_type_count,
        "evidence_count": evidence_count,
        "logic": (
            "confidence_score 表示当前 cell 融合判断的证据支持充分程度，通常受有效证据权重、"
            "证据条数、来源类型数和冲突惩罚共同影响；conflict_level 只表示证据之间是否存在明确矛盾，"
            "例如 positive 与 negative 的冲突，unknown 不应被当作明确否定。"
        ),
    }


def _top_evidence(evidence_part: pd.DataFrame, top_n: int = 10) -> List[Dict[str, Any]]:
    if evidence_part is None or evidence_part.empty:
        return []

    out: List[Dict[str, Any]] = []
    for _, ev in evidence_part.head(top_n).iterrows():
        start = _safe_float(ev.get("start_chainage"), None)
        end = _safe_float(ev.get("end_chainage"), None)
        center = _safe_float(ev.get("center_chainage"), None)
        face = _safe_float(ev.get("face_chainage"), None)

        if start is not None and end is not None:
            loc_text = _dk_range(start, end)
        elif center is not None:
            loc_text = _dk(center)
        else:
            loc_text = "未知里程"

        duplicate_count = int(_safe_float(ev.get("duplicate_count"), 1) or 1)
        duplicate_evidence_ids = [
            _safe_str(x)
            for x in _as_list(ev.get("duplicate_evidence_ids"))
            if _safe_str(x)
        ]

        out.append(
            {
                "evidence_id": _safe_str(ev.get("evidence_id")),
                "report_id": _safe_str(ev.get("report_id")),
                "source_type": _safe_str(ev.get("source_type_norm")),
                "evidence_role": _safe_str(ev.get("evidence_role")),
                "spatial_type": _safe_str(ev.get("spatial_type")),
                "location_text": loc_text,
                "face_chainage_text": _dk(face) if face is not None else "",
                "grade": _safe_str(ev.get("grade")),
                "hazard_tags": [_safe_str(x) for x in _as_list(ev.get("hazard_tags")) if _safe_str(x)],
                "effective_weight": float(_safe_float(ev.get("__weight"), 0.0) or 0.0),
                "raw_text_snippet": _short_text(ev.get("raw_text"), 160),

                # HSP anomaly_point dedup fields
                "duplicate_count": duplicate_count,
                "duplicate_evidence_ids": duplicate_evidence_ids,
                "dedup_key": _safe_str(ev.get("dedup_key")),
                "dedup_note": _safe_str(ev.get("dedup_note")),
            }
        )

    return out


def explain_geo_state(
    cell_id: str,
    geo_states_df: pd.DataFrame,
    cell_evidence_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
    top_n_evidence: int = 10,
) -> Dict[str, Any]:
    """
    解释一个 cell 的地质融合结果。

    返回 dict，适合调试、保存 JSON、给前端展示。
    """
    if geo_states_df is None or geo_states_df.empty:
        return {
            "ok": False,
            "message": "geo_states_df 为空，无法解释。",
            "cell_id": cell_id,
        }

    if "cell_id" not in geo_states_df.columns:
        return {
            "ok": False,
            "message": "geo_states_df 缺少 cell_id 字段。",
            "cell_id": cell_id,
        }

    matched = geo_states_df[geo_states_df["cell_id"].astype(str) == str(cell_id)]
    if matched.empty:
        return {
            "ok": False,
            "message": f"未在 geo_states_df 中找到 cell_id={cell_id}。",
            "cell_id": cell_id,
        }

    row = matched.iloc[0]
    evidence_part = _join_cell_evidence(cell_id, cell_evidence_df, normalized_df)

    cell_start = row.get("cell_start")
    cell_end = row.get("cell_end")
    cell_center = row.get("cell_center")

    result = {
        "ok": True,
        "cell_id": cell_id,
        "cell_range": {
            "cell_start": _safe_float(cell_start, None),
            "cell_end": _safe_float(cell_end, None),
            "cell_center": _safe_float(cell_center, None),
            "cell_start_dk": _dk(cell_start),
            "cell_end_dk": _dk(cell_end),
            "cell_center_dk": _dk(cell_center),
            "cell_range_dk": _dk_range(cell_start, cell_end),
        },
        "basic_result": {
            "has_geology_evidence": bool(row.get("has_geology_evidence", False)),
            "fused_grade": _safe_str(row.get("fused_grade"), default="未形成明确等级"),
            "main_hazards": [_safe_str(x) for x in _as_list(row.get("main_hazards")) if _safe_str(x)],
            "water_score": float(_safe_float(row.get("water_score"), 0.0) or 0.0),
            "collapse_score": float(_safe_float(row.get("collapse_score"), 0.0) or 0.0),
            "deformation_score": float(_safe_float(row.get("deformation_score"), 0.0) or 0.0),
            "GRS_geo_base": float(_safe_float(row.get("GRS_geo_base"), 0.0) or 0.0),
            "confidence_score": float(_safe_float(row.get("confidence_score"), 0.0) or 0.0),
            "uncertainty_level": _safe_str(row.get("uncertainty_level"), default="unknown"),
            "conflict_level": _safe_str(row.get("conflict_level"), default="unknown"),
        },
        "grade_explanation": _explain_grade(row, evidence_part),
        "hazard_explanation": _explain_hazards(row, evidence_part),
        "grs_explanation": _infer_grs_components(row),
        "confidence_conflict_explanation": _explain_confidence_conflict(row, evidence_part),
        "top_supporting_evidence": _top_evidence(evidence_part, top_n=top_n_evidence),
        "supporting_evidence_count": int(len(evidence_part)),
    }
    return result


def explain_geo_state_text(explanation: Dict[str, Any]) -> str:
    """
    将 explain_geo_state() 的 dict 转成可读文本。
    """
    if not explanation or not explanation.get("ok", False):
        return explanation.get("message", "未形成可解释结果。") if isinstance(explanation, dict) else "未形成可解释结果。"

    cell = explanation["cell_range"]
    basic = explanation["basic_result"]
    grade_exp = explanation["grade_explanation"]
    hazard_exp = explanation["hazard_explanation"]
    grs_exp = explanation["grs_explanation"]
    conf_exp = explanation["confidence_conflict_explanation"]
    evidences = explanation.get("top_supporting_evidence", [])

    lines: List[str] = []
    lines.append(f"【cell 可解释性说明】{explanation.get('cell_id')}（{cell.get('cell_range_dk')}）")
    lines.append("")

    lines.append("1. 基础融合结果")
    lines.append(f"- 融合围岩等级：{basic.get('fused_grade')}")
    lines.append(f"- 主要关注项：{'、'.join(basic.get('main_hazards') or []) or '无'}")
    lines.append(f"- GRS_geo_base：{basic.get('GRS_geo_base'):.3f}")
    lines.append(f"- 融合置信度：{basic.get('confidence_score'):.3f}")
    lines.append(f"- 不确定性：{basic.get('uncertainty_level')}")
    lines.append(f"- 冲突等级：{basic.get('conflict_level')}")
    lines.append("")

    lines.append("2. fused_grade 为什么是这个等级")
    dist = grade_exp.get("grade_distribution_sorted", [])
    if dist:
        for item in dist:
            lines.append(
                f"- {item.get('grade')}级：support={item.get('support', 0):.3f}，"
                f"share={item.get('share', 0):.3f}，attention_score={item.get('attention_score', 0):.3f}"
            )
    else:
        lines.append("- 未找到 grade_distribution。")
    lines.append(f"- 解释逻辑：{grade_exp.get('logic')}")
    if grade_exp.get("evidence_items"):
        lines.append("- 主要等级证据：")
        for ev in grade_exp["evidence_items"][:5]:
            r = ev.get("range", {})
            if r.get("start") is not None and r.get("end") is not None:
                loc = _dk_range(r.get("start"), r.get("end"))
            elif r.get("center") is not None:
                loc = _dk(r.get("center"))
            else:
                loc = "未知里程"
            lines.append(
                f"  · {ev.get('source_type')}/{ev.get('spatial_type')}，{loc}，"
                f"grade={ev.get('grade')}，weight={ev.get('effective_weight', 0):.3f}，"
                f"id={_short_text(ev.get('evidence_id'), 90)}"
            )
    lines.append("")

    lines.append("3. main_hazards 为什么有这些")
    scores = hazard_exp.get("hazard_scores_sorted", [])
    if scores:
        lines.append("- hazard_scores 排名前列：")
        for item in scores[:8]:
            lines.append(f"  · {item.get('hazard_key')}: {item.get('score', 0):.3f}")
    else:
        lines.append("- 未找到 hazard_scores。")

    support_by_hazard = hazard_exp.get("support_by_hazard", {})
    if support_by_hazard:
        lines.append("- 主要关注项证据来源：")
        for hazard, items in support_by_hazard.items():
            lines.append(f"  · {hazard}:")
            if not items:
                lines.append("    - 未找到直接命中的 evidence hazard_tags，可能来自标准化映射或上游融合。")
                continue
            for ev in items[:3]:
                lines.append(
                    f"    - {ev.get('source_type')}/{ev.get('spatial_type')}，"
                    f"weight={ev.get('effective_weight', 0):.3f}，"
                    f"id={_short_text(ev.get('evidence_id'), 90)}"
                )
    lines.append(f"- 解释逻辑：{hazard_exp.get('logic')}")
    lines.append("")

    lines.append("4. GRS_geo_base 怎么解释")
    lines.append(f"- 实际 GRS_geo_base：{grs_exp.get('GRS_geo_base', 0):.3f}")

    if grs_exp.get("component_source") == "direct_from_geo_states_df":
        lines.append("- 组件来源：fusion_engine 真实输出")
        lines.append(f"- grade_score_component：{grs_exp.get('grade_score_component', 0):.3f}")
        lines.append(f"- hazard_component：{grs_exp.get('hazard_component', 0):.3f}")
        lines.append(f"- confidence_component：{grs_exp.get('confidence_component', 0):.3f}")
        lines.append(f"- 计算公式：{grs_exp.get('GRS_formula_text')}")
        lines.append(f"- 组件方法：{grs_exp.get('GRS_component_method')}")
        lines.append(f"- 按公式重构值：{grs_exp.get('reconstructed_value', 0):.3f}")
        lines.append(f"- 与实际值差异 residual：{grs_exp.get('residual_to_actual', 0):.6f}")
        lines.append(f"- 说明：{grs_exp.get('note')}")
    else:
        lines.append("- 组件来源：解释模块反推")
        lines.append(f"- 推断 grade_score：{grs_exp.get('grade_score_inferred', 0):.3f}")
        lines.append(f"- 推断 hazard_component：{grs_exp.get('hazard_component_inferred', 0):.3f}")
        lines.append(f"- confidence_score：{grs_exp.get('confidence_score', 0):.3f}")
        lines.append(f"- 解释公式：{grs_exp.get('reconstructed_formula')}")
        lines.append(f"- 按解释公式重构值：{grs_exp.get('reconstructed_value', 0):.3f}")
        lines.append(f"- 与实际值差异 residual：{grs_exp.get('residual_to_actual', 0):.3f}")
        lines.append("- 注意：当前 geo_states_df 未提供真实 GRS 组件，因此使用解释性反推。")
    lines.append("")

    lines.append("5. confidence / conflict 怎么解释")
    lines.append(f"- source_types：{'、'.join(conf_exp.get('source_types') or []) or '无'}")
    lines.append(f"- source_type_count：{conf_exp.get('source_type_count')}")
    lines.append(f"- evidence_count：{conf_exp.get('evidence_count')}")
    lines.append(f"- confidence_score：{conf_exp.get('confidence_score'):.3f}")
    lines.append(f"- uncertainty_level：{conf_exp.get('uncertainty_level')}")
    lines.append(f"- conflict_level：{conf_exp.get('conflict_level')}")
    reasons = conf_exp.get("conflict_reasons") or []
    lines.append(f"- conflict_reasons：{reasons if reasons else '无明确冲突原因'}")
    lines.append(f"- 解释逻辑：{conf_exp.get('logic')}")
    lines.append("")

    lines.append("6. 主要支撑证据 top list")
    if not evidences:
        lines.append("- 未找到支撑证据。")
    else:
        for i, ev in enumerate(evidences, start=1):
            hazards = "、".join(ev.get("hazard_tags") or [])
            lines.append(
                f"- 证据{i}: {ev.get('source_type')}/{ev.get('spatial_type')}，"
                f"{ev.get('location_text')}，face={ev.get('face_chainage_text') or '无'}，"
                f"weight={ev.get('effective_weight', 0):.3f}"
            )

            duplicate_count = int(_safe_float(ev.get("duplicate_count"), 1) or 1)
            if duplicate_count > 1:
                duplicate_ids = ev.get("duplicate_evidence_ids") or []
                lines.append(
                    f"  duplicate_count={duplicate_count}，已合并重复边界 anomaly_point"
                )
                if duplicate_ids:
                    lines.append(
                        f"  duplicate_evidence_ids={duplicate_ids}"
                    )

            lines.append(f"  id={_short_text(ev.get('evidence_id'), 120)}")
            if ev.get("grade"):
                lines.append(f"  grade={ev.get('grade')}")
            if hazards:
                lines.append(f"  hazard_tags={hazards}")
            if ev.get("raw_text_snippet"):
                lines.append(f"  raw_text={ev.get('raw_text_snippet')}")

    return "\n".join(lines)


def print_geo_state_explanation(
    cell_id: str,
    geo_states_df: pd.DataFrame,
    cell_evidence_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
    top_n_evidence: int = 10,
) -> Dict[str, Any]:
    """
    方便 ceshi.py 直接调用。
    """
    explanation = explain_geo_state(
        cell_id=cell_id,
        geo_states_df=geo_states_df,
        cell_evidence_df=cell_evidence_df,
        normalized_df=normalized_df,
        top_n_evidence=top_n_evidence,
    )
    print(explain_geo_state_text(explanation))
    return explanation