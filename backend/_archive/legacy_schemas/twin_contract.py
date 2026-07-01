from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


TWIN_STATE_SCHEMA_VERSION = "tbm_twin_state_v1"
TWIN_EVENT_SCHEMA_VERSION = "tbm_twin_event_v1"
TWIN_DIFF_SCHEMA_VERSION = "tbm_twin_diff_v1"
NO_TEXT = "暂无"

LEVEL_RECORD_WINDOW = "record_window"
LEVEL_SEGMENT_WINDOW = "segment_window"
LEVEL_CURRENT_FACE = "current_face"
LEVEL_FORWARD_WINDOW = "forward_window"
LEVEL_STATE_OVERVIEW = "state_overview"

STATE_OPERATION_MODE = "operation_mode"
STATE_CLUSTER_STATE = "cluster_state"
STATE_FACE_OBSERVATION = "face_observation"
STATE_EXCAVATED_SEGMENT = "excavated_segment"
STATE_FORWARD_EVIDENCE = "forward_evidence"
STATE_RESPONSE_ANOMALY = "response_anomaly"
STATE_GEO_RESPONSE_COUPLING = "geo_response_coupling"
STATE_GAS_SAFETY = "gas_safety"

SEMANTIC_OBSERVED = "observed_or_measured"
SEMANTIC_RETROSPECTIVE = "retrospective_excavated"
SEMANTIC_PREDICTIVE_EVIDENCE = "predictive_evidence"
SEMANTIC_TEXT_ADAPTER = "text_adapter"


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Return a JSON-safe float or default."""
    try:
        if value is None:
            return default
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Return a safe integer."""
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def safe_text(value: Any, default: str = NO_TEXT) -> str:
    """Return a compact non-structured text."""
    if value is None:
        return default
    if isinstance(value, dict):
        for key in ("text", "summary_text", "advice_text", "forward_advice_text", "comparison_text", "message"):
            if value.get(key):
                return safe_text(value.get(key), default=default)
        return default
    if isinstance(value, (list, tuple, set)):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(cleaned) if cleaned else default
    text = str(value).strip()
    return text or default


def clamp01(value: Any) -> float:
    """Clamp a numeric value to [0, 1]."""
    x = safe_float(value, 0.0) or 0.0
    return max(0.0, min(1.0, x))


def ensure_list(value: Any) -> list[Any]:
    """Normalize arbitrary value into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return deepcopy(value)
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def dedup_text(items: Any) -> list[str]:
    """Deduplicate strings while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for item in ensure_list(items):
        if item is None:
            continue
        if isinstance(item, (list, tuple, set)):
            for inner in dedup_text(item):
                if inner not in seen:
                    out.append(inner)
                    seen.add(inner)
            continue
        text = str(item).strip()
        if not text:
            continue
        if text not in seen:
            out.append(text)
            seen.add(text)
    return out


def split_tags(value: Any) -> list[str]:
    """Split hazard/tag text into a normalized tag list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return dedup_text(value)
    text = str(value).strip()
    if not text:
        return []
    for sep in ["+", "、", "，", ",", ";", "；", "/", "|", "\n", "\t"]:
        text = text.replace(sep, " ")
    return dedup_text([part for part in text.split(" ") if part.strip()])


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_empty_twin_state() -> dict[str, Any]:
    """Return the canonical structured TBM construction twin state.

    Canonical rule:
    - structure stays here;
    - natural-language text belongs to text adapter fields only;
    - forward evidence, excavated segment response and current face observation are separate states.
    """
    return {
        "schema_version": TWIN_STATE_SCHEMA_VERSION,
        "twin_id": None,
        "snapshot_id": None,
        "state_key": None,
        "previous_snapshot_id": None,
        "created_at": None,
        "updated_at": None,
        "project_id": None,
        "case_id": None,
        "tunnel_id": None,
        "line_id": None,
        "date": None,
        "analysis_mode": "daily",
        "data_window": {
            "start_time": None,
            "end_time": None,
            "duration_min": 0.0,
            "sample_count": 0,
            "source_path": None,
            "source_name": None,
        },
        "spatial_reference": {
            "reference_type": "linear_chainage",
            "chainage_unit": "m",
            "chainage_direction": "increasing",
            "route_id": None,
            "tunnel_id": None,
            "line_id": None,
            "chainage_start": None,
            "chainage_end": None,
            "face_chainage": None,
            "advance_length_m": 0.0,
            "forward_window": {
                "level": LEVEL_FORWARD_WINDOW,
                "semantic": SEMANTIC_PREDICTIVE_EVIDENCE,
                "lookahead_m": None,
                "start_chainage": None,
                "end_chainage": None,
                "window_min": None,
                "window_max": None,
            },
        },
        "temporal_state": {
            "level": LEVEL_RECORD_WINDOW,
            "sample_count": 0,
            "analysis_mode": "daily",
            "previous_date": None,
            "continuity_gap_days": None,
            "state_stability": 1.0,
        },
        "operation_state": {
            "state_space": STATE_OPERATION_MODE,
            "level": LEVEL_RECORD_WINDOW,
            "semantic": SEMANTIC_OBSERVED,
            "main_state": None,
            "work_duration_min": 0.0,
            "stop_duration_min": 0.0,
            "transition_duration_min": 0.0,
            "abnormal_duration_min": 0.0,
            "work_ratio": None,
            "stop_ratio": None,
            "state_switch_count": 0,
            "previous_main_state": None,
            "work_duration_delta_min": None,
            "stop_duration_delta_min": None,
        },
        "cluster_state": {
            "state_space": STATE_CLUSTER_STATE,
            "level": LEVEL_RECORD_WINDOW,
            "semantic": SEMANTIC_OBSERVED,
            "valid_samples": 0,
            "n_states": 0,
            "labels": {},
            "stats": {},
            "efficiency_table": [],
        },
        "face_state": {
            "state_space": STATE_FACE_OBSERVATION,
            "level": LEVEL_CURRENT_FACE,
            "semantic": SEMANTIC_OBSERVED,
            "has_direct_observation": False,
            "face_chainage": None,
            "face_chainage_dk": None,
            "source_type": None,
            "evidence_ids": [],
            "source_refs": [],
            "quality_flags": [],
        },
        "geological_state": {
            "state_space": STATE_EXCAVATED_SEGMENT,
            "level": LEVEL_SEGMENT_WINDOW,
            "semantic": SEMANTIC_RETROSPECTIVE,
            "has_geology": False,
            "geo_fused_grade": None,
            "geo_hazard_tags": [],
            "active_report_source_count": 0,
            "matched_evidence_record_count": 0,
            "evidence_support_weight_sum": 0.0,
            "geo_fusion_uncertainty": None,
            "high_geo_attention_segment_count": 0,
            "multi_report_source_segment_count": 0,
            "persistent_hazards": [],
        },
        "response_state": {
            "state_space": STATE_RESPONSE_ANOMALY,
            "level": LEVEL_SEGMENT_WINDOW,
            "semantic": SEMANTIC_RETROSPECTIVE,
            "RAI": 0.0,
            "response_anomaly_index": 0.0,
            "anomaly_type": None,
            "key_parameters": [],
            "top_rai_segments": [],
            "RAI_delta": None,
        },
        "attention_state": {
            "state_space": STATE_GEO_RESPONSE_COUPLING,
            "level": LEVEL_SEGMENT_WINDOW,
            "semantic": SEMANTIC_RETROSPECTIVE,
            "GRS_geo_base": 0.0,
            "GRS_adjusted": 0.0,
            "GRCI": 0.0,
            "geo_response_coupling_index": 0.0,
            "top_grci_segments": [],
            "top_grs_segments": [],
            "top_rai_segments": [],
            "coupling_level_counts": {},
            "grci_class_counts": {},
            "persistent_attention_segments": [],
            "trend_label": "initialized",
            "GRS_delta": None,
            "GRCI_delta": None,
        },
        "forward_state": {
            "state_space": STATE_FORWARD_EVIDENCE,
            "level": LEVEL_FORWARD_WINDOW,
            "semantic": SEMANTIC_PREDICTIVE_EVIDENCE,
            "has_forward_risk": False,
            "current_chainage": None,
            "lookahead_m": None,
            "forward_start": None,
            "forward_end": None,
            "forward_window_min": None,
            "forward_window_max": None,
            "forward_evidence_count": 0,
            "forward_high_source_risk_evidence_count": 0,
            "forward_report_source_count": 0,
            "forward_source_type_count": 0,
            "forward_source_risk_level_dist": {},
            "forward_main_hazard_tags": [],
            "forward_advice_level": None,
            "monitoring_focus": [],
            "support_actions": [],
        },
        "gas_state": {
            "state_space": STATE_GAS_SAFETY,
            "level": LEVEL_RECORD_WINDOW,
            "semantic": SEMANTIC_OBSERVED,
            "stats": {},
            "exceed_types": [],
            "exceed_event_count": 0,
        },
        "events": [],
        "diff_from_previous": {},
        "quality_flags": [],
        "source_refs": {
            "plc_file": None,
            "plc_path": None,
            "evidence_db": None,
            "matched_evidence_ids": [],
            "used_report_ids": [],
            "used_source_types": [],
        },
        "provenance_state": {
            "state_update_sources": [],
            "previous_change_summary": None,
            "lineage": [],
            "changed_fields": [],
            "state_confidence": 0.0,
            "update_strategy": "snapshot_then_recursive_update",
        },
        "text_adapters": {},
        "raw_twin_state": {},
        "warnings": [],
    }


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge patch into base."""
    out = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def normalize_twin_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize partial twin/CST payload into the canonical TwinState schema."""
    state = build_empty_twin_state()
    if not isinstance(payload, dict):
        return state
    normalized = deep_merge(state, payload)
    normalized["schema_version"] = normalized.get("schema_version") or TWIN_STATE_SCHEMA_VERSION
    normalized["analysis_mode"] = normalized.get("analysis_mode") or normalized.get("temporal_state", {}).get("analysis_mode") or "daily"
    normalized["temporal_state"]["analysis_mode"] = normalized["analysis_mode"]

    # Synchronize spatial aliases.
    spatial = normalized.get("spatial_reference", {})
    spatial["tunnel_id"] = spatial.get("tunnel_id") or normalized.get("tunnel_id")
    spatial["line_id"] = spatial.get("line_id") or normalized.get("line_id")
    if spatial.get("face_chainage") is None:
        spatial["face_chainage"] = normalized.get("forward_state", {}).get("current_chainage")

    # Normalize numeric metric ranges.
    for group_key, metric_keys in {
        "response_state": ["RAI", "response_anomaly_index"],
        "attention_state": ["GRS_geo_base", "GRS_adjusted", "GRCI", "geo_response_coupling_index"],
    }.items():
        group = normalized.get(group_key, {})
        for key in metric_keys:
            group[key] = clamp01(group.get(key))

    normalized["geological_state"]["geo_hazard_tags"] = split_tags(normalized["geological_state"].get("geo_hazard_tags"))
    normalized["forward_state"]["forward_main_hazard_tags"] = split_tags(normalized["forward_state"].get("forward_main_hazard_tags"))
    normalized["gas_state"]["exceed_types"] = dedup_text(normalized["gas_state"].get("exceed_types", []))
    normalized["events"] = ensure_list(normalized.get("events"))
    normalized["quality_flags"] = ensure_list(normalized.get("quality_flags"))
    return normalized


def build_legacy_cst_aliases(twin_state: dict[str, Any]) -> dict[str, Any]:
    """Expose compatibility aliases without changing canonical semantics."""
    state = normalize_twin_state(twin_state)
    geo = state.get("geological_state", {})
    attention = state.get("attention_state", {})
    operation = state.get("operation_state", {})
    spatial = state.get("spatial_reference", {})
    data_window = state.get("data_window", {})

    aliases = {
        "version": state.get("schema_version"),
        "cst_id": state.get("snapshot_id") or state.get("twin_id"),
        "updated_at": state.get("updated_at"),
        "case_id": state.get("case_id"),
        "date": state.get("date"),
        "time_window": {
            "start_time": data_window.get("start_time"),
            "end_time": data_window.get("end_time"),
            "duration_min": data_window.get("duration_min", 0.0),
        },
        "spatial_state": {
            "chainage_start": spatial.get("chainage_start"),
            "chainage_end": spatial.get("chainage_end"),
            "face_chainage": spatial.get("face_chainage"),
            "advance_length": spatial.get("advance_length_m"),
            "forward_window": [spatial.get("forward_window", {})] if spatial.get("forward_window") else [],
            "forward_focus_level": state.get("forward_state", {}).get("forward_advice_level"),
            "chainage_delta_from_previous": state.get("diff_from_previous", {}).get("spatial", {}).get("face_chainage_delta_m"),
        },
        "operation_state": {
            "main_state": operation.get("main_state"),
            "operation_mode": operation.get("main_state"),
            "working_duration_min": operation.get("work_duration_min", 0.0),
            "stoppage_duration_min": operation.get("stop_duration_min", 0.0),
            "transition_duration_min": operation.get("transition_duration_min", 0.0),
            "abnormal_duration_min": operation.get("abnormal_duration_min", 0.0),
            "state_switch_count": operation.get("state_switch_count", 0),
            "work_ratio": operation.get("work_ratio"),
            "stop_ratio": operation.get("stop_ratio"),
            "previous_main_state": operation.get("previous_main_state"),
            "work_duration_delta": operation.get("work_duration_delta_min"),
            "stop_duration_delta": operation.get("stop_duration_delta_min"),
        },
        "geological_state": {
            "geo_fused_grade": geo.get("geo_fused_grade"),
            "segment_grade": geo.get("geo_fused_grade"),
            "geo_hazard_tags": geo.get("geo_hazard_tags", []),
            "hazards": geo.get("geo_hazard_tags", []),
            "active_report_source_count": geo.get("active_report_source_count", 0),
            "matched_evidence_record_count": geo.get("matched_evidence_record_count", 0),
            "evidence_support_weight_sum": geo.get("evidence_support_weight_sum", 0.0),
            "evidence_count": geo.get("matched_evidence_record_count", 0),
            "geo_fusion_uncertainty": geo.get("geo_fusion_uncertainty"),
            "uncertainty": geo.get("geo_fusion_uncertainty"),
            "persistent_hazards": geo.get("persistent_hazards", []),
        },
        "response_state": deepcopy(state.get("response_state", {})),
        "attention_state": {
            **deepcopy(attention),
            "GRS": attention.get("GRS_adjusted", attention.get("GRS_geo_base", 0.0)),
            "high_attention_segments": attention.get("top_grci_segments", []),
        },
        "forward_state": deepcopy(state.get("forward_state", {})),
        "provenance_state": deepcopy(state.get("provenance_state", {})),
        "raw_twin_state": deepcopy(state.get("raw_twin_state", {})),
        "warnings": deepcopy(state.get("warnings", [])),
        "gas_state": deepcopy(state.get("gas_state", {})),
    }
    return aliases
