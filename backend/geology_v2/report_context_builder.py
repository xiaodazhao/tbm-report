"""
geology_v2.report_context_builder

Build a stable geology_v2 report context without replacing the existing
texts/sections/summary structure.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from utils.chainage_utils import format_chainage_dk, format_chainage_range_dk

from geology_v2.coupling_adapter import coupled_df_to_text, summarize_coupled_df
from geology_v2.forward_profile import summarize_forward_profile
from geology_v2.fusion_engine import summarize_geo_states
from geology_v2.text_builder import (
    build_geology_v2_prompt_block,
    forward_profile_to_text,
    geo_states_to_brief_text,
)


REPORT_CONTEXT_VERSION = "geology_v2_report_context_v1"
SCHEMA_VERSION = "geology_v2_context_1.0"
ATTENTION_LEVEL_THRESHOLDS = {
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
}
RELATIVE_RANGE_PATTERN = re.compile(
    r"^\s*(?P<start>-?\d+(?:\.\d+)?)\s*-\s*(?P<end>-?\d+(?:\.\d+)?)\s*m\s*$",
    re.IGNORECASE,
)


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


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    if _is_missing(value):
        return default
    try:
        x = float(value)
        if math.isfinite(x):
            return float(x)
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    x = _safe_float(value, default=None)
    if x is None:
        return int(default)
    return int(round(x))


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return parsed
        for sep in ["|", ";", ",", "、", "，"]:
            if sep in text:
                return [item.strip() for item in text.split(sep) if item.strip()]
        return [text]
    return [value]


def _dedup_keep_order(items: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        if _is_missing(item):
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _json_clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
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


def _df_preview_records(df: Optional[pd.DataFrame], max_rows: int = 20) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    return _json_clean(df.head(max_rows).to_dict(orient="records"))


def _chainage_text(value: Optional[float]) -> str:
    if value is None:
        return "未知里程"
    return format_chainage_dk(value, unknown="未知里程", prefix="DK")


def _chainage_range_text(chainage_min: Optional[float], chainage_max: Optional[float]) -> str:
    if chainage_min is None or chainage_max is None:
        return "未知里程范围"
    return format_chainage_range_dk(chainage_min, chainage_max, separator="～")


def _compact_excerpt(value: Any, max_chars: int = 160) -> str:
    text = _safe_str(value)
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(line.strip() for line in text.split("\n") if line.strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _list_of_str(value: Any) -> List[str]:
    return _dedup_keep_order(_as_list(value))


def _value_counts(series: pd.Series) -> Dict[str, int]:
    if series is None or len(series) == 0:
        return {}
    cleaned = series.dropna().astype(str)
    cleaned = cleaned[cleaned.str.strip() != ""]
    if cleaned.empty:
        return {}
    return {str(k): int(v) for k, v in cleaned.value_counts().to_dict().items()}


def _merge_count_dicts(*maps: dict[str, int]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for mapping in maps:
        for key, value in (mapping or {}).items():
            text = _safe_str(key)
            if not text:
                continue
            out[text] = out.get(text, 0) + int(value or 0)
    return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))


def _attention_level(score: Any, has_evidence: bool) -> str:
    if not has_evidence:
        return "none"
    value = _safe_float(score, default=0.0) or 0.0
    if value >= ATTENTION_LEVEL_THRESHOLDS["high"]:
        return "high"
    if value >= ATTENTION_LEVEL_THRESHOLDS["medium"]:
        return "medium"
    if value >= ATTENTION_LEVEL_THRESHOLDS["low"]:
        return "low"
    return "none"


def _parse_relative_range(
    range_label: Any,
    start_chainage: Any,
    end_chainage: Any,
    current_chainage: Optional[float],
) -> tuple[str, Optional[float], Optional[float]]:
    label = _safe_str(range_label)
    if label:
        match = RELATIVE_RANGE_PATTERN.match(label)
        if match:
            start_m = _safe_float(match.group("start"), default=None)
            end_m = _safe_float(match.group("end"), default=None)
            return label, start_m, end_m
        return label, None, None

    current = _safe_float(current_chainage, default=None)
    start = _safe_float(start_chainage, default=None)
    end = _safe_float(end_chainage, default=None)
    if current is None or start is None or end is None:
        return "未知前方分段", None, None

    start_m = abs(start - current)
    end_m = abs(end - current)
    lo = min(start_m, end_m)
    hi = max(start_m, end_m)
    return f"{int(round(lo))}-{int(round(hi))}m", lo, hi


def _prepare_evidence_lookup(normalized_df: Optional[pd.DataFrame]) -> Dict[str, dict[str, Any]]:
    if normalized_df is None or normalized_df.empty or "evidence_id" not in normalized_df.columns:
        return {}
    lookup: Dict[str, dict[str, Any]] = {}
    for _, row in normalized_df.iterrows():
        evidence_id = _safe_str(row.get("evidence_id"))
        if evidence_id and evidence_id not in lookup:
            lookup[evidence_id] = row.to_dict()
    return lookup


def _group_cell_evidence(cell_evidence_df: Optional[pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    if cell_evidence_df is None or cell_evidence_df.empty or "cell_id" not in cell_evidence_df.columns:
        return {}
    return {
        _safe_str(cell_id): part.copy()
        for cell_id, part in cell_evidence_df.groupby("cell_id", sort=False)
    }


def _unique_evidence_ids(
    cell_id: str,
    supporting_evidence_ids: Any,
    cell_group_map: Dict[str, pd.DataFrame],
) -> List[str]:
    ids = _list_of_str(supporting_evidence_ids)
    if ids:
        return ids

    cell_rows = cell_group_map.get(cell_id)
    if cell_rows is None or cell_rows.empty or "evidence_id" not in cell_rows.columns:
        return []
    return _dedup_keep_order(cell_rows["evidence_id"].tolist())


def _build_source_trace_from_rows(
    evidence_ids: List[str],
    cell_rows: Optional[pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
    max_items: int = 8,
) -> List[dict[str, Any]]:
    traces: List[dict[str, Any]] = []
    if not evidence_ids:
        return traces

    cell_rows_local = cell_rows if isinstance(cell_rows, pd.DataFrame) else pd.DataFrame()
    for evidence_id in evidence_ids:
        if len(traces) >= max_items:
            break

        norm_row = evidence_lookup.get(evidence_id, {})
        weight_row = pd.Series(dtype=object)
        if not cell_rows_local.empty and "evidence_id" in cell_rows_local.columns:
            matched = cell_rows_local[cell_rows_local["evidence_id"].astype(str) == evidence_id]
            if not matched.empty:
                weight_row = matched.iloc[0]

        source_type = (
            _safe_str(norm_row.get("source_type_norm"))
            or _safe_str(weight_row.get("source_type_norm"))
        )
        spatial_type = (
            _safe_str(norm_row.get("spatial_type"))
            or _safe_str(weight_row.get("spatial_type"))
        )
        confidence = _safe_float(norm_row.get("confidence"), default=None)
        if confidence is None:
            confidence = _safe_float(norm_row.get("confidence_score"), default=None)

        trace = {
            "evidence_id": evidence_id,
            "report_id": _safe_str(norm_row.get("report_id")),
            "source_type": source_type,
            "evidence_role": _safe_str(norm_row.get("evidence_role")),
            "spatial_type": spatial_type,
            "start_chainage": _safe_float(norm_row.get("start_chainage"), default=None),
            "end_chainage": _safe_float(norm_row.get("end_chainage"), default=None),
            "center_chainage": _safe_float(norm_row.get("center_chainage"), default=None),
            "face_chainage": _safe_float(norm_row.get("face_chainage"), default=None),
            "hazard_tags": _list_of_str(norm_row.get("hazard_tags")),
            "effective_weight": _safe_float(
                weight_row.get("effective_weight") if not weight_row.empty else None,
                default=None,
            ),
            "confidence": confidence,
            "raw_text_excerpt": _compact_excerpt(norm_row.get("raw_text"), max_chars=160),
        }
        traces.append(_json_clean(trace))

    return traces


def _build_source_trace_for_cell_prepared(
    cell_id: str,
    supporting_evidence_ids: Any,
    cell_group_map: Dict[str, pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
    max_items: int = 8,
) -> List[dict[str, Any]]:
    evidence_ids = _unique_evidence_ids(cell_id, supporting_evidence_ids, cell_group_map)
    cell_rows = cell_group_map.get(cell_id)
    return _build_source_trace_from_rows(
        evidence_ids=evidence_ids,
        cell_rows=cell_rows,
        evidence_lookup=evidence_lookup,
        max_items=max_items,
    )


def _build_source_trace_for_cell(
    cell_id: str,
    supporting_evidence_ids: Any,
    cell_evidence_df: Optional[pd.DataFrame],
    normalized_df: Optional[pd.DataFrame],
    max_items: int = 8,
) -> List[dict[str, Any]]:
    cell_group_map = _group_cell_evidence(cell_evidence_df)
    evidence_lookup = _prepare_evidence_lookup(normalized_df)
    return _build_source_trace_for_cell_prepared(
        cell_id=cell_id,
        supporting_evidence_ids=supporting_evidence_ids,
        cell_group_map=cell_group_map,
        evidence_lookup=evidence_lookup,
        max_items=max_items,
    )


def _source_types_from_trace_or_rows(
    trace: List[dict[str, Any]],
    cell_rows: Optional[pd.DataFrame],
    fallback: Any = None,
) -> List[str]:
    source_types = [_safe_str(item.get("source_type")) for item in trace if _safe_str(item.get("source_type"))]
    if source_types:
        return _dedup_keep_order(source_types)

    if isinstance(cell_rows, pd.DataFrame) and not cell_rows.empty and "source_type_norm" in cell_rows.columns:
        return _dedup_keep_order(cell_rows["source_type_norm"].tolist())

    if isinstance(fallback, dict):
        return _dedup_keep_order(fallback.keys())

    return _list_of_str(fallback)


def _current_window_evidence_ids(
    geo_states_df: Optional[pd.DataFrame],
    cell_group_map: Dict[str, pd.DataFrame],
) -> List[str]:
    if geo_states_df is None or geo_states_df.empty:
        return []
    evidence_ids: List[str] = []
    for cell_id in geo_states_df.get("cell_id", pd.Series(dtype=object)).tolist():
        cell_rows = cell_group_map.get(_safe_str(cell_id))
        if cell_rows is None or cell_rows.empty or "evidence_id" not in cell_rows.columns:
            continue
        evidence_ids.extend(cell_rows["evidence_id"].tolist())
    return _dedup_keep_order(evidence_ids)


def _build_current_window_summary(
    geo_states_df: Optional[pd.DataFrame],
    cell_group_map: Dict[str, pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
) -> Dict[str, Any]:
    if geo_states_df is None or geo_states_df.empty:
        return {
            "cell_count": 0,
            "evidence_cell_count": 0,
            "grade_distribution": {},
            "main_hazards": [],
            "hazard_counts": {},
            "attention_level_counts": {},
            "source_type_counts": {},
            "uncertainty_level_counts": {},
            "conflict_level_counts": {},
            "GRS_geo_base_max": 0.0,
            "GRS_geo_base_mean": 0.0,
        }

    df = geo_states_df.copy()
    has_evidence = df.get("has_geology_evidence", pd.Series(False, index=df.index)).astype(bool)
    grs = pd.to_numeric(df.get("GRS_geo_base", 0.0), errors="coerce").fillna(0.0)

    hazard_counts: Dict[str, int] = {}
    for hazards in df.get("main_hazards", pd.Series(dtype=object)).tolist():
        for hazard in _list_of_str(hazards):
            hazard_counts[hazard] = hazard_counts.get(hazard, 0) + 1
    hazard_counts = dict(sorted(hazard_counts.items(), key=lambda item: (-item[1], item[0])))

    attention_levels = [
        _attention_level(score, bool(flag))
        for score, flag in zip(grs.tolist(), has_evidence.tolist())
    ]
    attention_level_counts = _value_counts(pd.Series(attention_levels, dtype=object))

    evidence_ids = _current_window_evidence_ids(df, cell_group_map)
    source_type_counts: Dict[str, int] = {}
    for evidence_id in evidence_ids:
        source_type = _safe_str(evidence_lookup.get(evidence_id, {}).get("source_type_norm"))
        if source_type:
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
    source_type_counts = dict(sorted(source_type_counts.items(), key=lambda item: (-item[1], item[0])))

    return {
        "cell_count": int(len(df)),
        "evidence_cell_count": int(has_evidence.sum()),
        "grade_distribution": _value_counts(df.get("fused_grade", pd.Series(dtype=object))),
        "main_hazards": list(hazard_counts.keys())[:8],
        "hazard_counts": hazard_counts,
        "attention_level_counts": attention_level_counts,
        "source_type_counts": source_type_counts,
        "uncertainty_level_counts": _value_counts(df.get("uncertainty_level", pd.Series(dtype=object))),
        "conflict_level_counts": _value_counts(df.get("conflict_level", pd.Series(dtype=object))),
        "GRS_geo_base_max": float(grs.max()) if len(grs) else 0.0,
        "GRS_geo_base_mean": float(grs.mean()) if len(grs) else 0.0,
    }


def _select_key_cells(geo_states_df: Optional[pd.DataFrame], max_items: int = 5) -> List[dict[str, Any]]:
    if geo_states_df is None or geo_states_df.empty:
        return []

    work = geo_states_df.copy()
    work["__has_evidence"] = work.get("has_geology_evidence", False).astype(bool)
    work["__grs"] = pd.to_numeric(work.get("GRS_geo_base", 0.0), errors="coerce").fillna(0.0)
    work["__evidence_count"] = pd.to_numeric(work.get("evidence_count", 0), errors="coerce").fillna(0)
    work["__source_type_count"] = pd.to_numeric(work.get("source_type_count", 0), errors="coerce").fillna(0)
    work["__uncertainty_high"] = work.get("uncertainty_level", "").astype(str).isin(["high", "高"])
    work["__conflict_flag"] = ~work.get("conflict_level", "none").astype(str).isin(["", "none", "None", "null"])
    work["__priority"] = (
        work["__grs"]
        + 0.02 * work["__evidence_count"].clip(upper=20)
        + 0.02 * work["__source_type_count"].clip(upper=10)
        + 0.08 * work["__uncertainty_high"].astype(int)
        + 0.06 * work["__conflict_flag"].astype(int)
    )
    work = work.sort_values(
        by=["__has_evidence", "__priority", "__evidence_count", "__source_type_count", "cell_center"],
        ascending=[False, False, False, False, True],
    )
    return work.head(max_items).to_dict(orient="records")


def _build_key_cells(
    geo_states_df: Optional[pd.DataFrame],
    cell_group_map: Dict[str, pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
    structured_warnings: List[str],
    max_items: int = 5,
) -> List[dict[str, Any]]:
    key_cells: List[dict[str, Any]] = []
    for row in _select_key_cells(geo_states_df, max_items=max_items):
        cell_id = _safe_str(row.get("cell_id"))
        supporting_evidence_ids = _list_of_str(row.get("supporting_evidence_ids"))
        source_trace = _build_source_trace_for_cell_prepared(
            cell_id=cell_id,
            supporting_evidence_ids=supporting_evidence_ids,
            cell_group_map=cell_group_map,
            evidence_lookup=evidence_lookup,
            max_items=8,
        )
        cell_rows = cell_group_map.get(cell_id)
        source_types = _source_types_from_trace_or_rows(
            source_trace,
            cell_rows,
            fallback=row.get("source_support"),
        )
        evidence_count = len(_unique_evidence_ids(cell_id, supporting_evidence_ids, cell_group_map))
        if evidence_count == 0:
            evidence_count = _safe_int(row.get("evidence_count"), default=0)
        if row.get("has_geology_evidence") and not source_trace:
            structured_warnings.append(f"关键 cell {cell_id} 未展开证据来源摘要。")

        key_cells.append(
            {
                "cell_id": cell_id,
                "range_dk": _chainage_range_text(
                    _safe_float(row.get("cell_start"), default=None),
                    _safe_float(row.get("cell_end"), default=None),
                ),
                "cell_start": _safe_float(row.get("cell_start"), default=None),
                "cell_end": _safe_float(row.get("cell_end"), default=None),
                "cell_center": _safe_float(row.get("cell_center"), default=None),
                "fused_grade": _safe_str(row.get("fused_grade"), default=""),
                "GRS_geo_base": _safe_float(row.get("GRS_geo_base"), default=None),
                "confidence": _safe_float(row.get("confidence_score"), default=None),
                "uncertainty_level": _safe_str(row.get("uncertainty_level"), default="unknown"),
                "conflict_level": _safe_str(row.get("conflict_level"), default="none"),
                "conflict_reasons": _as_list(row.get("conflict_reasons")),
                "main_hazards": _list_of_str(row.get("main_hazards")),
                "source_types": source_types,
                "evidence_count": int(evidence_count),
                "supporting_evidence_ids": supporting_evidence_ids,
                "source_trace": source_trace,
            }
        )
    return _json_clean(key_cells)


def _build_segment_source_trace(
    segment: dict[str, Any],
    cell_group_map: Dict[str, pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
    max_items: int = 8,
) -> List[dict[str, Any]]:
    supporting_evidence_ids = _list_of_str(segment.get("supporting_evidence_ids"))
    supporting_cell_ids = _list_of_str(segment.get("supporting_cell_ids"))

    if not supporting_evidence_ids and supporting_cell_ids:
        for cell_id in supporting_cell_ids:
            cell_rows = cell_group_map.get(cell_id)
            if cell_rows is None or cell_rows.empty or "evidence_id" not in cell_rows.columns:
                continue
            supporting_evidence_ids.extend(cell_rows["evidence_id"].tolist())
        supporting_evidence_ids = _dedup_keep_order(supporting_evidence_ids)

    if not supporting_evidence_ids and isinstance(segment.get("source_trace"), list):
        sanitized = []
        for item in segment.get("source_trace", []):
            if not isinstance(item, dict):
                continue
            sanitized.append(
                {
                    "evidence_id": _safe_str(item.get("evidence_id")),
                    "report_id": _safe_str(item.get("report_id")),
                    "source_type": _safe_str(item.get("source_type")),
                    "evidence_role": _safe_str(item.get("evidence_role")),
                    "spatial_type": _safe_str(item.get("spatial_type")),
                    "start_chainage": _safe_float(item.get("start_chainage"), default=None),
                    "end_chainage": _safe_float(item.get("end_chainage"), default=None),
                    "center_chainage": _safe_float(item.get("center_chainage"), default=None),
                    "face_chainage": _safe_float(item.get("face_chainage"), default=None),
                    "hazard_tags": _list_of_str(item.get("hazard_tags")),
                    "effective_weight": _safe_float(item.get("effective_weight"), default=None),
                    "confidence": _safe_float(item.get("confidence"), default=None),
                    "raw_text_excerpt": _compact_excerpt(
                        item.get("raw_text_excerpt") or item.get("raw_text_snippet"),
                        max_chars=160,
                    ),
                }
            )
            if len(sanitized) >= max_items:
                break
        return _json_clean(sanitized)

    if not supporting_evidence_ids:
        return []

    frames = [cell_group_map.get(cell_id) for cell_id in supporting_cell_ids if cell_id in cell_group_map]
    cell_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return _build_source_trace_from_rows(
        evidence_ids=supporting_evidence_ids,
        cell_rows=cell_rows,
        evidence_lookup=evidence_lookup,
        max_items=max_items,
    )


def _build_forward_segments(
    forward_profile: Optional[Dict[str, Any]],
    current_chainage: Optional[float],
    cell_group_map: Dict[str, pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
    structured_warnings: List[str],
) -> List[dict[str, Any]]:
    profile = _as_list(_as_dict(forward_profile).get("profile"))
    segments: List[dict[str, Any]] = []
    for item in profile:
        if not isinstance(item, dict):
            continue
        start_chainage = _safe_float(item.get("start_chainage"), default=None)
        end_chainage = _safe_float(item.get("end_chainage"), default=None)
        relative_range, relative_start_m, relative_end_m = _parse_relative_range(
            item.get("relative_range") or item.get("range_label"),
            start_chainage,
            end_chainage,
            current_chainage,
        )
        source_trace = _build_segment_source_trace(
            segment=item,
            cell_group_map=cell_group_map,
            evidence_lookup=evidence_lookup,
            max_items=8,
        )
        source_types = _source_types_from_trace_or_rows(
            source_trace,
            None,
            fallback=item.get("source_types"),
        )
        evidence_count = _safe_int(item.get("evidence_count"), default=0)
        if evidence_count <= 0:
            evidence_count = len(_list_of_str(item.get("supporting_evidence_ids")))
        if evidence_count <= 0:
            evidence_count = len(source_trace)
        if _safe_str(item.get("attention_level")) != "none" and not source_trace:
            structured_warnings.append(
                f"前方分段 {relative_range} 未展开证据来源摘要。"
            )
        segments.append(
            {
                "relative_range": relative_range,
                "range_dk": _chainage_range_text(start_chainage, end_chainage),
                "relative_start_m": relative_start_m,
                "relative_end_m": relative_end_m,
                "start_chainage": start_chainage,
                "end_chainage": end_chainage,
                "attention_level": _safe_str(item.get("attention_level"), default="none"),
                "main_hazards": _list_of_str(item.get("main_hazards")),
                "evidence_count": int(evidence_count),
                "source_types": source_types,
                "confidence": _safe_float(item.get("confidence_score"), default=None),
                "uncertainty_level": _safe_str(item.get("uncertainty_level"), default="unknown"),
                "source_trace": source_trace,
            }
        )
    return _json_clean(segments)


def _build_source_trace_summary(
    geo_states_df: Optional[pd.DataFrame],
    cell_group_map: Dict[str, pd.DataFrame],
    evidence_lookup: Dict[str, dict[str, Any]],
) -> Dict[str, Any]:
    evidence_ids = _current_window_evidence_ids(geo_states_df, cell_group_map)
    source_type_counts: Dict[str, int] = {}
    report_ids = set()
    for evidence_id in evidence_ids:
        row = evidence_lookup.get(evidence_id, {})
        source_type = _safe_str(row.get("source_type_norm"))
        report_id = _safe_str(row.get("report_id"))
        if source_type:
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        if report_id:
            report_ids.add(report_id)
    source_type_counts = dict(sorted(source_type_counts.items(), key=lambda item: (-item[1], item[0])))
    return {
        "trace_available": bool(evidence_ids and evidence_lookup),
        "traced_evidence_count": int(len(evidence_ids)),
        "source_type_counts": source_type_counts,
        "report_id_count": int(len(report_ids)),
    }


def _build_current_face_section(
    face_context: Optional[Dict[str, Any]],
    current_chainage: Optional[float],
) -> Dict[str, Any]:
    face_context = _as_dict(face_context)
    text = _safe_str(
        face_context.get("text")
        or face_context.get("face_geo_text")
        or face_context.get("description"),
        default="当前掌子面描述暂未形成有效结构化结果。",
    )
    has_direct_face_observation = bool(face_context.get("has_direct_face_observation"))
    has_face_evidence = bool(face_context.get("has_face_evidence", bool(face_context)))
    return {
        "title": "当前掌子面描述",
        "spatial_scope": "current_face",
        "current_chainage": current_chainage,
        "has_face_evidence": has_face_evidence,
        "has_direct_face_observation": has_direct_face_observation,
        "text": text,
        "notes": [
            "当前掌子面描述只对应当前或最近邻现场揭示位置，不替代前方预报。",
        ],
    }


def _build_excavated_review_section(
    geo_states_df: Optional[pd.DataFrame],
    geo_brief_text: str,
    chainage_min: Optional[float],
    chainage_max: Optional[float],
) -> Dict[str, Any]:
    has_geo_states = bool(geo_states_df is not None and not geo_states_df.empty)
    return {
        "title": "已开挖区段地质复核",
        "spatial_scope": "excavated_or_selected_range",
        "chainage_range": {
            "start": chainage_min,
            "end": chainage_max,
            "text": _chainage_range_text(chainage_min, chainage_max),
        },
        "has_geo_states": has_geo_states,
        "text": geo_brief_text,
        "notes": [
            "已开挖区段地质复核属于回顾性或指定范围复核，不应写成尚未开挖的前方风险。",
        ],
    }


def _build_forward_section(
    forward_profile: Optional[Dict[str, Any]],
    forward_text: str,
) -> Dict[str, Any]:
    forward_profile = _as_dict(forward_profile)
    profile = _as_list(forward_profile.get("profile"))
    return {
        "title": "前方30m分段提示",
        "spatial_scope": "forward_lookahead",
        "has_forward_evidence": bool(forward_profile.get("has_forward_evidence")),
        "current_chainage": forward_profile.get("current_chainage"),
        "lookahead_m": forward_profile.get("lookahead_m"),
        "overall_attention_level": forward_profile.get("overall_attention_level"),
        "profile_count": len(profile),
        "profile": _json_clean(profile),
        "text": forward_text,
        "notes": [
            "前方分段提示来自 forward_profile，不应与已开挖区段复核混写。",
            "缺少前方证据时只能说明证据不足，不得写成无风险。",
        ],
    }


def _build_coupling_section(
    coupled_df: Optional[pd.DataFrame],
    coupling_text: str,
    chainage_min: Optional[float],
    chainage_max: Optional[float],
) -> Dict[str, Any]:
    has_coupling = bool(coupled_df is not None and not coupled_df.empty)
    summary = summarize_coupled_df(coupled_df) if has_coupling else {
        "cell_count": 0,
        "has_response_cell_count": 0,
        "computed_grci_cell_count": 0,
        "coupling_level_counts": {},
        "coupling_type_counts": {},
        "GRCI_max": 0.0,
        "GRCI_mean": 0.0,
    }
    return {
        "title": "地质-施工响应耦合分析",
        "spatial_scope": "excavated_or_selected_range",
        "chainage_range": {
            "start": chainage_min,
            "end": chainage_max,
            "text": _chainage_range_text(chainage_min, chainage_max),
        },
        "has_coupling": has_coupling,
        "summary": _json_clean(summary),
        "text": coupling_text,
        "notes": [
            "GRCI 表示复盘窗口内地质证据与施工响应之间的耦合关注程度，不表示灾害概率。",
            "缺少施工响应数据时，不得据此判断施工响应正常。",
        ],
    }


def _build_operation_section(operation_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    operation_context = _as_dict(operation_context)
    text = _safe_str(
        operation_context.get("text")
        or operation_context.get("operation_text")
        or operation_context.get("summary_text"),
        default="本阶段未接入基础工况结构化上下文。",
    )
    return {
        "title": "基础工况上下文",
        "spatial_scope": "time_window",
        "has_operation_context": bool(operation_context),
        "text": text,
        "data": _json_clean(operation_context),
    }


def _build_gas_section(gas_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    gas_context = _as_dict(gas_context)
    text = _safe_str(
        gas_context.get("text")
        or gas_context.get("gas_text")
        or gas_context.get("summary_text"),
        default="本阶段未接入气体监测结构化上下文。",
    )
    return {
        "title": "气体监测上下文",
        "spatial_scope": "time_window",
        "has_gas_context": bool(gas_context),
        "text": text,
        "data": _json_clean(gas_context),
    }


def _build_conclusion_section(
    forward_profile: Optional[Dict[str, Any]],
    coupled_df: Optional[pd.DataFrame],
    geo_states_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    warnings: List[str] = []
    if geo_states_df is None or geo_states_df.empty:
        warnings.append("地质融合状态为空，不能给出地质关注降低判断。")
    fp = _as_dict(forward_profile)
    if not fp.get("has_forward_evidence"):
        warnings.append("前方窗口缺少有效地质证据，不得表述为前方无风险。")
    if coupled_df is None or coupled_df.empty:
        warnings.append("缺少地质-施工响应耦合结果，不能据此判断施工响应是否同步异常。")
    else:
        valid_grci = pd.to_numeric(coupled_df.get("GRCI"), errors="coerce")
        if not valid_grci.notna().any():
            warnings.append("GRCI 未形成有效值，多数情况下是施工响应数据缺失。")
    if not warnings:
        warnings.append("结论应基于结构化证据审慎表述，不得扩展到未覆盖里程或未覆盖时段。")
    return {
        "title": "结论与建议约束",
        "spatial_scope": "report_level",
        "text": "结论应综合地质融合、前方分段剖面、施工响应耦合和气体监测结果形成。",
        "constraints": warnings,
    }


def build_geology_v2_report_context(
    geo_states_df: Optional[pd.DataFrame] = None,
    forward_profile: Optional[Dict[str, Any]] = None,
    coupled_df: Optional[pd.DataFrame] = None,
    operation_context: Optional[Dict[str, Any]] = None,
    gas_context: Optional[Dict[str, Any]] = None,
    face_context: Optional[Dict[str, Any]] = None,
    current_chainage: Optional[float] = None,
    chainage_min: Optional[float] = None,
    chainage_max: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    include_data_preview: bool = True,
    all_geo_states_df: Optional[pd.DataFrame] = None,
    forward_profile_summary: Optional[Dict[str, Any]] = None,
    all_coupled_df: Optional[pd.DataFrame] = None,
    analysis_date: Optional[Any] = None,
    report_date: Optional[Any] = None,
    review_back_m: Optional[float] = None,
    review_forward_m: Optional[float] = None,
    base_context: Optional[Dict[str, Any]] = None,
    normalized_df: Optional[pd.DataFrame] = None,
    cell_evidence_df: Optional[pd.DataFrame] = None,
    cells_df: Optional[pd.DataFrame] = None,
    all_normalized_df: Optional[pd.DataFrame] = None,
    all_cell_evidence_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    structured_warnings: List[str] = []
    metadata = _as_dict(metadata)
    base_context = _as_dict(base_context)

    trace_normalized_df = normalized_df if isinstance(normalized_df, pd.DataFrame) else all_normalized_df
    trace_cell_evidence_df = (
        cell_evidence_df if isinstance(cell_evidence_df, pd.DataFrame) else all_cell_evidence_df
    )
    focus_geo_states_df = geo_states_df if isinstance(geo_states_df, pd.DataFrame) else all_geo_states_df

    if chainage_min is None and current_chainage is not None and review_back_m is not None:
        chainage_min = float(current_chainage) - float(review_back_m)
    if chainage_max is None and current_chainage is not None and review_forward_m is not None:
        chainage_max = float(current_chainage) + float(review_forward_m)

    if focus_geo_states_df is None or focus_geo_states_df.empty:
        warnings.append("geo_states_df 为空，当前范围未形成地质融合状态。")
    if not isinstance(forward_profile, dict):
        warnings.append("forward_profile 为空或格式不正确，前方分段提示不可用。")
    if coupled_df is None or coupled_df.empty:
        warnings.append("coupled_df 为空，地质-施工响应耦合文本不可用。")
    if trace_normalized_df is None or trace_normalized_df.empty:
        structured_warnings.append("normalized_df 缺失或为空，证据来源摘要能力受限。")
    if trace_cell_evidence_df is None or trace_cell_evidence_df.empty:
        structured_warnings.append("cell_evidence_df 缺失或为空，cell 级证据溯源能力受限。")

    geo_brief_text = geo_states_to_brief_text(
        geo_states_df=focus_geo_states_df,
        chainage_min=chainage_min,
        chainage_max=chainage_max,
        top_k=5,
    ) if isinstance(focus_geo_states_df, pd.DataFrame) else "当前范围未形成可用地质融合状态。"

    forward_text = forward_profile_to_text(forward_profile or {})
    coupling_text = coupled_df_to_text(
        coupled_df=coupled_df,
        chainage_min=chainage_min,
        chainage_max=chainage_max,
        top_k=5,
    ) if isinstance(coupled_df, pd.DataFrame) else "当前范围未形成地质-施工响应耦合结果。"

    geology_prompt_block = build_geology_v2_prompt_block(
        geo_states_df=focus_geo_states_df,
        forward_profile=forward_profile,
        include_geo_states_brief=True,
        include_forward_profile=True,
        chainage_min=chainage_min,
        chainage_max=chainage_max,
    )

    prompt_block = "\n\n".join(
        [
            geology_prompt_block,
            "【地质-施工响应耦合分析】",
            coupling_text,
            "【写作约束】",
            "1. 关注等级表示证据融合关注程度，不等同于灾害发生概率。",
            "2. 前方提示不是当前掌子面已经发生的事实。",
            "3. GRCI 只能写成复盘耦合关注指标，不得写成预测概率。",
            "4. 无证据覆盖不得写成无风险或低风险。",
            "5. 当前掌子面揭示只能来自明确的现场素描或掌子面地质编录。",
            "6. source_trace 只是证据来源摘要，不可超出原文含义。",
        ]
    )

    cell_group_map = _group_cell_evidence(trace_cell_evidence_df)
    evidence_lookup = _prepare_evidence_lookup(trace_normalized_df)

    current_window_summary = _build_current_window_summary(
        focus_geo_states_df,
        cell_group_map,
        evidence_lookup,
    )
    key_cells = _build_key_cells(
        focus_geo_states_df,
        cell_group_map,
        evidence_lookup,
        structured_warnings,
        max_items=5,
    )
    forward_segments = _build_forward_segments(
        forward_profile,
        _safe_float(current_chainage, default=None),
        cell_group_map,
        evidence_lookup,
        structured_warnings,
    )
    source_trace_summary = _build_source_trace_summary(
        focus_geo_states_df,
        cell_group_map,
        evidence_lookup,
    )

    face_section = _build_current_face_section(face_context, current_chainage)
    sections = {
        "operation": _build_operation_section(operation_context),
        "current_face": face_section,
        "excavated_review": _build_excavated_review_section(
            geo_states_df=focus_geo_states_df,
            geo_brief_text=geo_brief_text,
            chainage_min=chainage_min,
            chainage_max=chainage_max,
        ),
        "forward_profile": _build_forward_section(
            forward_profile=forward_profile,
            forward_text=forward_text,
        ),
        "coupling": _build_coupling_section(
            coupled_df=coupled_df,
            coupling_text=coupling_text,
            chainage_min=chainage_min,
            chainage_max=chainage_max,
        ),
        "gas": _build_gas_section(gas_context),
        "conclusion": _build_conclusion_section(
            forward_profile=forward_profile,
            coupled_df=coupled_df,
            geo_states_df=focus_geo_states_df,
        ),
    }

    summary_forward = _as_dict(forward_profile_summary)
    if not summary_forward:
        summary_forward = summarize_forward_profile(forward_profile or {})

    data_summary = {
        "geo_states_summary": summarize_geo_states(focus_geo_states_df)
        if isinstance(focus_geo_states_df, pd.DataFrame) else {},
        "forward_profile_summary": summary_forward,
        "coupled_summary": summarize_coupled_df(coupled_df)
        if isinstance(coupled_df, pd.DataFrame) else {},
    }

    data_preview = {}
    if include_data_preview:
        data_preview = {
            "geo_states_preview": _df_preview_records(focus_geo_states_df, max_rows=10),
            "coupled_preview": _df_preview_records(coupled_df, max_rows=10),
            "forward_profile": _json_clean(forward_profile or {}),
        }

    context = {
        "ok": True,
        "version": "geology_v2",
        "context_version": REPORT_CONTEXT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": {
            **metadata,
            **({"analysis_date": analysis_date} if analysis_date is not None else {}),
            **({"report_date": report_date} if report_date is not None else {}),
            **({"source_name": base_context.get("source_name")} if base_context.get("source_name") else {}),
            **({"source_path": base_context.get("source_path")} if base_context.get("source_path") else {}),
            "current_chainage": current_chainage,
            "current_chainage_dk": _chainage_text(_safe_float(current_chainage, default=None)),
            "chainage_min": chainage_min,
            "chainage_max": chainage_max,
            "chainage_range_text": _chainage_range_text(chainage_min, chainage_max),
        },
        "current_position": {
            "current_chainage": _safe_float(current_chainage, default=None),
            "current_chainage_dk": _chainage_text(_safe_float(current_chainage, default=None)),
            "advance_direction": _safe_int(metadata.get("advance_direction"), default=0)
            if metadata.get("advance_direction") is not None else None,
            "review_back_m": _safe_float(review_back_m, default=None),
            "review_forward_m": _safe_float(review_forward_m, default=None),
        },
        "current_window_summary": current_window_summary,
        "key_cells": key_cells,
        "forward_segments": forward_segments,
        "source_trace_summary": source_trace_summary,
        "structured_warnings": _dedup_keep_order(structured_warnings),
        "current_face": {
            "has_direct_face_observation": bool(face_section.get("has_direct_face_observation")),
            "has_face_evidence": bool(face_section.get("has_face_evidence")),
            "current_chainage": _safe_float(current_chainage, default=None),
            "text": face_section.get("text"),
        },
        "texts": {
            "geo_brief_text": geo_brief_text,
            "forward_text": forward_text,
            "coupling_text": coupling_text,
            "prompt_block": prompt_block,
        },
        "sections": sections,
        "data_summary": _json_clean(data_summary),
        "data_preview": _json_clean(data_preview),
        "warnings": _dedup_keep_order(warnings),
    }

    if focus_geo_states_df is not None and not focus_geo_states_df.empty:
        if current_window_summary.get("evidence_cell_count", 0) > 0 and not source_trace_summary.get("trace_available"):
            context["structured_warnings"].append("当前窗口存在有证据 cell，但未成功展开来源摘要。")

    return _json_clean(context)


def report_context_to_prompt_text(report_context: Dict[str, Any]) -> str:
    context = _as_dict(report_context)
    texts = _as_dict(context.get("texts"))
    return _safe_str(texts.get("prompt_block"), default="")
