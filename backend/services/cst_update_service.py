from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import uuid4

from schemas.cst_state import normalize_cst_state
from schemas.twin_contract import (
    NO_TEXT,
    TWIN_STATE_SCHEMA_VERSION,
    clamp01,
    dedup_text,
    normalize_twin_state,
    now_text,
    safe_float,
    safe_int,
    safe_text,
    split_tags,
)
from services.sqlite_storage_service import load_previous_cst_for_context, save_cst_state
from services.twin_diff_service import build_twin_diff, diff_to_text
from services.twin_event_service import build_twin_events
from services.twin_store_service import save_twin_snapshot
from utils.chainage_utils import format_chainage_dk
from utils.serialization import serialize_for_json


STATE_VERSION = TWIN_STATE_SCHEMA_VERSION
MAX_PERSISTENT_SEGMENTS = 5
MAX_PERSISTENT_HAZARDS = 8


def _compact_text(value: Any, max_lines: int = 8, max_chars: int = 1200) -> str:
    text = safe_text(value)
    if text == NO_TEXT:
        return text
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    compact = "\n".join(lines[:max_lines])
    if len(compact) > max_chars:
        compact = compact[: max_chars - 3].rstrip() + "..."
    return compact or NO_TEXT


def _state_key(context: dict[str, Any]) -> str:
    mode = context.get("analysis_mode") or "daily"
    date = context.get("date") or "unknown-date"
    if mode == "time_window":
        start = context.get("time_start") or "unknown-start"
        end = context.get("time_end") or "unknown-end"
        return f"time_window:{date}:{start}->{end}"
    return f"daily:{date}"


def _lineage(previous_state: dict[str, Any] | None) -> list[str]:
    if not isinstance(previous_state, dict):
        return []
    previous_lineage = previous_state.get("provenance_state", {}).get("lineage", []) or []
    lineage = [str(item) for item in previous_lineage if item]
    previous_id = previous_state.get("snapshot_id") or previous_state.get("cst_id")
    if previous_id:
        lineage.append(str(previous_id))
    return lineage[-20:]


def _dominant_operation(stats: dict[str, Any]) -> str | None:
    candidates = {
        "work": safe_float(stats.get("work_total_min"), 0.0) or 0.0,
        "stop": safe_float(stats.get("stop_total_min"), 0.0) or 0.0,
        "transition": safe_float(stats.get("transition_total_min"), 0.0) or 0.0,
        "abnormal": safe_float(stats.get("abnormal_total_min"), 0.0) or 0.0,
    }
    if not any(value > 0 for value in candidates.values()):
        return None
    return max(candidates.items(), key=lambda item: item[1])[0]


def _ratio(part: float, total: float) -> float | None:
    if total <= 0:
        return None
    return round(part / total, 6)


def _first_segment(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    for item in candidates or []:
        if isinstance(item, dict):
            return deepcopy(item)
    return {}


def _collect_top_segments(analysis_result: dict[str, Any], coupling_summary: dict[str, Any]) -> tuple[list, list, list]:
    top_grci = analysis_result.get("top_grci_segments") or coupling_summary.get("top_grci_segments") or analysis_result.get("high_attention_segments") or coupling_summary.get("high_attention_segments") or []
    top_grs = analysis_result.get("top_grs_segments") or coupling_summary.get("top_grs_segments") or []
    top_rai = analysis_result.get("top_rai_segments") or coupling_summary.get("top_rai_segments") or []
    return serialize_for_json(top_grci), serialize_for_json(top_grs), serialize_for_json(top_rai)


def _segment_metric(item: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in item:
            return clamp01(item.get(key))
    return 0.0


def _collect_gas_exceed_types(gas_stats: dict[str, Any]) -> list[str]:
    gas_all = gas_stats.get("all", {}) if isinstance(gas_stats, dict) else {}
    out: list[str] = []
    for gas, stat in gas_all.items():
        if isinstance(stat, dict) and safe_int(stat.get("exceed_event_count")) > 0:
            out.append(str(gas))
    return dedup_text(out)


def _extract_matched_evidence_ids(*sources: Any) -> list[str]:
    out: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("matched_evidence_ids", "active_evidence_ids", "evidence_ids"):
            value = source.get(key)
            if isinstance(value, list):
                out.extend(str(item) for item in value if item)
        for item in source.get("typical_segments", []) or []:
            if isinstance(item, dict):
                value = item.get("matched_evidence_ids") or item.get("active_evidence_ids")
                if isinstance(value, list):
                    out.extend(str(v) for v in value if v)
    return dedup_text(out)


def _extract_report_ids(*sources: Any) -> list[str]:
    out: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("matched_report_ids", "active_report_ids", "report_ids", "used_report_ids"):
            value = source.get(key)
            if isinstance(value, list):
                out.extend(str(item) for item in value if item)
    return dedup_text(out)


def _quality_flags(analysis_result: dict[str, Any], twin_state: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    face_text = safe_text(analysis_result.get("face_geo_text"), default="")
    face_state = twin_state.get("face_state", {})
    if not face_state.get("has_direct_observation"):
        flags.append({"level": "warning", "type": "missing_face_observation", "message": "当前掌子面直接揭示资料不足。"})
    geo = twin_state.get("geological_state", {})
    if not geo.get("has_geology"):
        flags.append({"level": "warning", "type": "missing_geology_fusion", "message": "当前分析窗口未形成有效地质融合结果。"})
    elif safe_int(geo.get("matched_evidence_record_count")) <= 0 and safe_int(geo.get("active_report_source_count")) <= 0:
        flags.append({"level": "warning", "type": "low_evidence_coverage", "message": "地质证据覆盖较弱，相关结论需谨慎解释。"})
    if "不足" in face_text or "无直接" in face_text:
        flags.append({"level": "info", "type": "face_text_indicates_insufficient_data", "message": face_text[:160]})
    for warning in analysis_result.get("warnings", []) or []:
        flags.append({"level": "warning", "type": "module_warning", "message": str(warning)})
    return flags


def _persistent_hazards(previous_state: dict[str, Any] | None, current_hazards: list[str]) -> list[dict[str, Any]]:
    previous_items = []
    if isinstance(previous_state, dict):
        previous_items = previous_state.get("geological_state", {}).get("persistent_hazards", []) or []
    previous_index = {str(item.get("hazard")): item for item in previous_items if isinstance(item, dict) and item.get("hazard")}
    current_set = set(current_hazards)
    result = []
    for hazard in sorted(current_set | set(previous_index)):
        prev = previous_index.get(hazard, {})
        active = hazard in current_set
        streak = safe_int(prev.get("streak")) + 1 if active else max(safe_int(prev.get("streak")) - 1, 0)
        decay = 1.0 if active else round((safe_float(prev.get("decay_weight"), 0.0) or 0.0) * 0.65, 3)
        if streak <= 0 and decay < 0.15:
            continue
        result.append({"hazard": hazard, "is_active": active, "streak": streak, "decay_weight": decay})
    result.sort(key=lambda item: (-item["decay_weight"], -item["streak"], item["hazard"]))
    return result[:MAX_PERSISTENT_HAZARDS]


def _segment_name(item: dict[str, Any]) -> str:
    for key in ("segment", "segment_label_dk", "segment_name", "chainage_range", "chainage_range_dk"):
        if item.get(key):
            return str(item.get(key))
    return ""


def _persistent_segments(previous_state: dict[str, Any] | None, current_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous_items = []
    if isinstance(previous_state, dict):
        previous_items = previous_state.get("attention_state", {}).get("persistent_attention_segments", []) or []
    prev_index = {_segment_name(item): item for item in previous_items if isinstance(item, dict) and _segment_name(item)}
    cur_index = {_segment_name(item): item for item in current_segments if isinstance(item, dict) and _segment_name(item)}
    result = []
    for name in sorted(set(prev_index) | set(cur_index)):
        prev = prev_index.get(name, {})
        cur = cur_index.get(name)
        active = cur is not None
        streak = safe_int(prev.get("streak")) + 1 if active else max(safe_int(prev.get("streak")) - 1, 0)
        carry = 1.0 if active else round((safe_float(prev.get("carryover_score"), 0.0) or 0.0) * 0.6, 3)
        if streak <= 0 and carry < 0.15:
            continue
        base = deepcopy(cur) if cur else {"segment": name}
        base.update({"segment_name": name, "is_active": active, "streak": streak, "carryover_score": carry})
        result.append(base)
    result.sort(key=lambda item: (-(safe_float(item.get("GRCI"), 0.0) or 0.0), -(safe_float(item.get("carryover_score"), 0.0) or 0.0)))
    return serialize_for_json(result[:MAX_PERSISTENT_SEGMENTS])


def _state_confidence(twin_state: dict[str, Any]) -> float:
    sample_count = safe_float(twin_state.get("data_window", {}).get("sample_count"), 0.0) or 0.0
    evidence_count = safe_float(twin_state.get("geological_state", {}).get("matched_evidence_record_count"), 0.0) or 0.0
    source_count = safe_float(twin_state.get("geological_state", {}).get("active_report_source_count"), 0.0) or 0.0
    event_count = len(twin_state.get("events", []) or [])
    gas_cov = len((twin_state.get("gas_state", {}).get("stats", {}) or {}).get("all", {}) or {})
    score = 0.35 * min(sample_count / 1000.0, 1.0) + 0.25 * min(evidence_count / 5.0, 1.0) + 0.20 * min(source_count / 3.0, 1.0) + 0.10 * min(event_count / 5.0, 1.0) + 0.10 * (0.5 if gas_cov else 0.0)
    return round(max(0.0, min(1.0, score)), 3)


def build_cst_snapshot(
    analysis_result: dict[str, Any],
    *,
    case_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical TwinState snapshot from one analysis result.

    This function is the only producer of digital-twin/CST state.  It consumes
    structured analysis objects and never embeds full ``llm_summary`` or prompt
    text inside the twin state.
    """
    result = analysis_result if isinstance(analysis_result, dict) else {}
    context = context or {}
    raw_twin = deepcopy(result.get("digital_twin_state") or {})
    time_state = raw_twin.get("time_state", {}) if isinstance(raw_twin, dict) else {}
    position_state = raw_twin.get("position_state", {}) if isinstance(raw_twin, dict) else {}
    raw_operation = raw_twin.get("operation_state", {}) if isinstance(raw_twin, dict) else {}

    stats = deepcopy(result.get("stats") or {})
    state_stats = deepcopy(result.get("state_stats") or {})
    gas_stats = deepcopy(result.get("gas_stats") or {})
    geo_record = deepcopy(result.get("geo_summary_record") or {})
    geo_segment = deepcopy(result.get("geo_summary_segment") or {})
    coupling_summary = deepcopy(result.get("coupling_summary") or {})
    forward_summary = deepcopy(result.get("forward_risk_summary") or {})
    cluster_summary = deepcopy(result.get("cluster_state_summary") or {})

    top_grci, top_grs, top_rai = _collect_top_segments(result, coupling_summary)
    primary_grci = _first_segment(top_grci)
    primary_rai = _first_segment(top_rai) or primary_grci
    primary_grs = _first_segment(top_grs) or primary_grci

    work_min = safe_float(stats.get("work_total_min", raw_operation.get("work_total_min", 0.0)), 0.0) or 0.0
    stop_min = safe_float(stats.get("stop_total_min", raw_operation.get("stop_total_min", 0.0)), 0.0) or 0.0
    transition_min = safe_float(stats.get("transition_total_min", 0.0), 0.0) or 0.0
    abnormal_min = safe_float(stats.get("abnormal_total_min", 0.0), 0.0) or 0.0
    op_total = work_min + stop_min + transition_min + abnormal_min

    hazards = split_tags(
        geo_segment.get("main_hazards")
        or geo_record.get("main_hazards")
        or primary_grci.get("seg_geo_hazard_mode")
        or safe_text(result.get("face_geo_text"), default="")
    )
    matched_ids = _extract_matched_evidence_ids(geo_record, geo_segment, primary_grci, forward_summary)
    report_ids = _extract_report_ids(geo_record, geo_segment, primary_grci, forward_summary)
    source_types = dedup_text(forward_summary.get("forward_source_types", forward_summary.get("source_types", [])))
    gas_exceed_types = _collect_gas_exceed_types(gas_stats)

    forward_window = {
        "level": "forward_window",
        "semantic": "predictive_evidence",
        "lookahead_m": safe_float(forward_summary.get("lookahead_m")),
        "start_chainage": safe_float(forward_summary.get("forward_start")),
        "end_chainage": safe_float(forward_summary.get("forward_end")),
        "window_min": safe_float(forward_summary.get("forward_window_min")),
        "window_max": safe_float(forward_summary.get("forward_window_max")),
    }

    face_text = safe_text(result.get("face_geo_text"), default="")
    has_face_observation = bool(face_text and "不足" not in face_text and "暂无" not in face_text and "无直接" not in face_text)

    twin_state = normalize_twin_state({
        "schema_version": STATE_VERSION,
        "twin_id": context.get("twin_id") or context.get("project_id") or context.get("case_id") or "tbm_twin",
        "snapshot_id": str(uuid4()),
        "state_key": _state_key(context),
        "created_at": now_text(),
        "updated_at": now_text(),
        "project_id": context.get("project_id"),
        "case_id": case_id or context.get("case_id"),
        "tunnel_id": context.get("tunnel_id"),
        "line_id": context.get("line_id"),
        "date": context.get("date"),
        "analysis_mode": context.get("analysis_mode") or "daily",
        "data_window": {
            "start_time": context.get("time_start") or time_state.get("start_time"),
            "end_time": context.get("time_end") or time_state.get("end_time"),
            "duration_min": safe_float(time_state.get("duration_min"), 0.0) or 0.0,
            "sample_count": safe_int(time_state.get("sample_count", context.get("sample_count", 0))),
            "source_path": context.get("source_path"),
            "source_name": context.get("source_name"),
        },
        "spatial_reference": {
            "reference_type": "linear_chainage",
            "chainage_unit": "m",
            "chainage_direction": context.get("chainage_direction") or ("increasing" if safe_float(forward_summary.get("advance_direction"), 1.0) or 1 >= 0 else "decreasing"),
            "route_id": context.get("route_id"),
            "tunnel_id": context.get("tunnel_id"),
            "line_id": context.get("line_id"),
            "chainage_start": safe_float(context.get("chainage_start", position_state.get("start_chainage"))),
            "chainage_end": safe_float(context.get("chainage_end", position_state.get("end_chainage"))),
            "face_chainage": safe_float(position_state.get("current_chainage", forward_summary.get("current_chainage"))),
            "advance_length_m": safe_float(position_state.get("advance_length"), 0.0) or 0.0,
            "forward_window": forward_window,
        },
        "temporal_state": {
            "sample_count": safe_int(time_state.get("sample_count", 0)),
            "analysis_mode": context.get("analysis_mode") or "daily",
        },
        "operation_state": {
            "main_state": raw_operation.get("dominant_state") or _dominant_operation(stats),
            "work_duration_min": work_min,
            "stop_duration_min": stop_min,
            "transition_duration_min": transition_min,
            "abnormal_duration_min": abnormal_min,
            "work_ratio": _ratio(work_min, op_total),
            "stop_ratio": _ratio(stop_min, op_total),
            "state_switch_count": safe_int(state_stats.get("状态切换次数", raw_operation.get("state_switch_count", 0))) if isinstance(state_stats, dict) else safe_int(raw_operation.get("state_switch_count", 0)),
        },
        "cluster_state": {
            "valid_samples": safe_int(result.get("n_valid") or cluster_summary.get("valid_samples") or (result.get("llm_summary") or {}).get("valid_samples")),
            "n_states": safe_int((result.get("state_cfg") or {}).get("n_states") or (cluster_summary.get("config") or {}).get("n_states")),
            "labels": deepcopy(result.get("state_labels") or cluster_summary.get("labels") or {}),
            "stats": serialize_for_json(state_stats),
            "efficiency_table": serialize_for_json(result.get("eff_df").to_dict(orient="records") if hasattr(result.get("eff_df"), "to_dict") else cluster_summary.get("efficiency_table", [])),
        },
        "face_state": {
            "has_direct_observation": has_face_observation,
            "face_chainage": safe_float(position_state.get("current_chainage", forward_summary.get("current_chainage"))),
            "face_chainage_dk": position_state.get("current_chainage_dk") or forward_summary.get("current_chainage_dk"),
            "source_type": "sketch" if has_face_observation else None,
            "evidence_ids": geo_record.get("face_evidence_ids", []),
            "quality_flags": [] if has_face_observation else [{"level": "warning", "type": "missing_face_observation", "message": "当前掌子面直接揭示资料不足。"}],
        },
        "geological_state": {
            "has_geology": bool(geo_segment.get("has_geology", False) or geo_record.get("has_geology", False)),
            "geo_fused_grade": geo_segment.get("geo_fused_grade") or geo_segment.get("seg_geo_grade_mode") or geo_segment.get("segment_grade") or primary_grs.get("seg_geo_grade_mode"),
            "geo_hazard_tags": hazards,
            "active_report_source_count": safe_int(geo_record.get("max_active_report_source_count", geo_record.get("active_report_source_count", 0))),
            "matched_evidence_record_count": safe_int(geo_record.get("matched_evidence_record_count", geo_record.get("sample_count", len(matched_ids)))),
            "evidence_support_weight_sum": safe_float(geo_record.get("evidence_support_weight_sum"), 0.0) or 0.0,
            "geo_fusion_uncertainty": geo_segment.get("geo_fusion_uncertainty") or geo_segment.get("uncertainty") or geo_record.get("geo_fusion_uncertainty") or geo_record.get("uncertainty"),
            "high_geo_attention_segment_count": safe_int(geo_segment.get("high_geo_attention_segment_count", geo_segment.get("high_risk_segment_count", 0))),
            "multi_report_source_segment_count": safe_int(geo_segment.get("multi_report_source_segment_count", geo_segment.get("multi_source_segment_count", 0))),
        },
        "response_state": {
            "RAI": _segment_metric(primary_rai, "RAI", "response_anomaly_index"),
            "response_anomaly_index": _segment_metric(primary_rai, "response_anomaly_index", "RAI"),
            "anomaly_type": primary_rai.get("anomaly_type"),
            "key_parameters": dedup_text(primary_rai.get("key_parameters") or primary_rai.get("weak_anomaly_reasons")),
            "top_rai_segments": top_rai,
        },
        "attention_state": {
            "GRS_geo_base": _segment_metric(primary_grs, "GRS_geo_base", "GRS_base"),
            "GRS_adjusted": _segment_metric(primary_grci, "GRS_adjusted", "GRS", "GRS_corrected"),
            "GRCI": _segment_metric(primary_grci, "GRCI", "geo_response_coupling_index", "coupling_index"),
            "geo_response_coupling_index": _segment_metric(primary_grci, "geo_response_coupling_index", "GRCI", "coupling_index"),
            "top_grci_segments": top_grci,
            "top_grs_segments": top_grs,
            "top_rai_segments": top_rai,
            "coupling_level_counts": deepcopy(coupling_summary.get("coupling_level_counts", coupling_summary.get("level_counts", {}))),
            "grci_class_counts": deepcopy(coupling_summary.get("grci_class_counts", coupling_summary.get("class_counts", {}))),
        },
        "forward_state": {
            "has_forward_risk": bool(forward_summary.get("has_forward_risk", False)),
            "current_chainage": safe_float(forward_summary.get("current_chainage")),
            "lookahead_m": safe_float(forward_summary.get("lookahead_m")),
            "forward_start": safe_float(forward_summary.get("forward_start")),
            "forward_end": safe_float(forward_summary.get("forward_end")),
            "forward_window_min": safe_float(forward_summary.get("forward_window_min")),
            "forward_window_max": safe_float(forward_summary.get("forward_window_max")),
            "forward_evidence_count": safe_int(forward_summary.get("forward_evidence_count", forward_summary.get("forward_segment_count", 0))),
            "forward_high_source_risk_evidence_count": safe_int(forward_summary.get("forward_high_source_risk_evidence_count", forward_summary.get("high_risk_count", 0))),
            "forward_report_source_count": safe_int(forward_summary.get("forward_report_source_count", forward_summary.get("multi_source_count", 0))),
            "forward_source_type_count": safe_int(forward_summary.get("forward_source_type_count", len(source_types))),
            "forward_source_risk_level_dist": deepcopy(forward_summary.get("forward_source_risk_level_dist", forward_summary.get("risk_level_dist", {}))),
            "forward_main_hazard_tags": split_tags(forward_summary.get("forward_main_hazard_tags", forward_summary.get("main_hazards", []))),
            "forward_advice_level": forward_summary.get("forward_advice_level", forward_summary.get("advice_level")),
            "monitoring_focus": dedup_text(forward_summary.get("monitoring_focus", [])),
            "support_actions": dedup_text(forward_summary.get("support_actions", [])),
        },
        "gas_state": {
            "stats": serialize_for_json(gas_stats),
            "exceed_types": gas_exceed_types,
            "exceed_event_count": sum(safe_int(stat.get("exceed_event_count")) for stat in (gas_stats.get("all", {}) if isinstance(gas_stats, dict) else {}).values() if isinstance(stat, dict)),
        },
        "source_refs": {
            "plc_file": context.get("source_name"),
            "plc_path": context.get("source_path"),
            "evidence_db": context.get("evidence_db_path"),
            "matched_evidence_ids": matched_ids,
            "used_report_ids": report_ids,
            "used_source_types": source_types,
        },
        "provenance_state": {
            "state_update_sources": [
                {"type": "plc_csv", "path": context.get("source_path"), "name": context.get("source_name")},
                {"type": "evidence_db", "path": context.get("evidence_db_path"), "has_geology": bool(geo_segment.get("has_geology", False))},
                {"type": "analysis", "modules": ["operation", "cluster_state", "gas", "geology_fusion", "forward_window", "coupling"]},
            ],
            "update_strategy": "canonical_twin_snapshot_then_recursive_update",
        },
        "raw_twin_state": raw_twin,
        "warnings": result.get("warnings", []),
    })

    twin_state["quality_flags"] = _quality_flags(result, twin_state)
    twin_state["events"] = build_twin_events(result, twin_state)
    twin_state["provenance_state"]["state_confidence"] = _state_confidence(twin_state)
    return serialize_for_json(normalize_cst_state(twin_state))


def summarize_cst_delta(previous_cst: dict[str, Any] | None, current_cst: dict[str, Any]) -> str:
    """Generate a text summary from canonical TwinDiff."""
    return diff_to_text(build_twin_diff(previous_cst, current_cst))


def summarize_cst_for_prompt(cst_state: dict[str, Any] | None) -> str:
    """Build a compact CST-only summary block for prompts and reports.

    This is the text adapter for CST/TwinState.  It is intentionally separate
    from the structured twin state.
    """
    if not isinstance(cst_state, dict) or not cst_state:
        return "- 暂无可用的 CST 状态。"
    state = normalize_twin_state(cst_state)
    data = state.get("data_window", {})
    spatial = state.get("spatial_reference", {})
    op = state.get("operation_state", {})
    geo = state.get("geological_state", {})
    resp = state.get("response_state", {})
    att = state.get("attention_state", {})
    forward = state.get("forward_state", {})
    prov = state.get("provenance_state", {})
    face = state.get("face_state", {})

    face_chainage = spatial.get("face_chainage")
    face_dk = None
    try:
        face_dk = format_chainage_dk(face_chainage) if face_chainage is not None else None
    except Exception:
        face_dk = str(face_chainage) if face_chainage is not None else None
    hazards = geo.get("geo_hazard_tags", []) or []
    forward_hazards = forward.get("forward_main_hazard_tags", []) or []
    changed = prov.get("changed_fields", []) or []

    lines = [
        f"- 孪生状态版本：{state.get('schema_version')}，分析模式：{state.get('analysis_mode')}，样本数={data.get('sample_count', 0)}。",
        f"- 线性空间基准：掌子面里程={face_dk or face_chainage or '暂无'}，推进长度={spatial.get('advance_length_m', 0)} m，前方窗口={forward.get('lookahead_m') or spatial.get('forward_window', {}).get('lookahead_m') or '暂无'} m。",
        f"- 基础工况状态：主导工况={op.get('main_state') or '暂无'}，工作={op.get('work_duration_min', 0)} min，停机={op.get('stop_duration_min', 0)} min，异常={op.get('abnormal_duration_min', 0)} min。",
        f"- 当前掌子面状态：直接揭示资料={'有' if face.get('has_direct_observation') else '不足'}，资料不足时不得以前方预报或已开挖区段替代。",
        f"- 已开挖地质状态：融合围岩等级={geo.get('geo_fused_grade') or '暂无'}，关注标签={'、'.join(hazards) if hazards else '无'}，报告-来源数={geo.get('active_report_source_count', 0)}，证据记录数={geo.get('matched_evidence_record_count', 0)}。",
        f"- 区段响应与耦合：RAI={float(resp.get('RAI') or 0.0):.2f}，GRS_base={float(att.get('GRS_geo_base') or 0.0):.2f}，GRS_adjusted={float(att.get('GRS_adjusted') or 0.0):.2f}，GRCI={float(att.get('GRCI') or 0.0):.2f}，趋势={att.get('trend_label') or 'stable'}。",
        f"- 前方窗口证据提示：等级={forward.get('forward_advice_level') or '无'}，证据记录={forward.get('forward_evidence_count', 0)} 条，主要关注={'、'.join(forward_hazards) if forward_hazards else '无'}。",
        f"- 孪生事件：共 {len(state.get('events', []) or [])} 个，状态可信性={float(prov.get('state_confidence') or 0.0):.2f}，变化字段={'、'.join(changed) if changed else '无'}。",
    ]
    previous_change_summary = prov.get("previous_change_summary")
    if previous_change_summary:
        lines.append(f"- 与上一状态对比：{previous_change_summary}")
    return "\n".join(lines)


def update_cst(
    previous_cst: dict[str, Any] | None,
    snapshot: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update the canonical TwinState by comparing the current snapshot with previous state."""
    context = context or {}
    current = normalize_cst_state(snapshot)
    previous = normalize_cst_state(previous_cst) if isinstance(previous_cst, dict) else None

    previous_id = previous.get("snapshot_id") if isinstance(previous, dict) else None
    current["previous_snapshot_id"] = previous_id
    current["state_key"] = _state_key(context)
    current["updated_at"] = now_text()
    current["provenance_state"]["lineage"] = _lineage(previous)

    diff = build_twin_diff(previous, current)
    current["diff_from_previous"] = diff
    current["provenance_state"]["changed_fields"] = diff.get("changed_fields", [])
    current["provenance_state"]["previous_change_summary"] = diff_to_text(diff)

    if isinstance(previous, dict):
        current["operation_state"]["previous_main_state"] = previous.get("operation_state", {}).get("main_state")
        current["operation_state"]["work_duration_delta_min"] = (diff.get("operation", {}) or {}).get("work_duration_min_delta")
        current["operation_state"]["stop_duration_delta_min"] = (diff.get("operation", {}) or {}).get("stop_duration_min_delta")
        current["response_state"]["RAI_delta"] = (diff.get("response", {}) or {}).get("RAI_delta")
        current["attention_state"]["GRS_delta"] = (diff.get("attention", {}) or {}).get("GRS_adjusted_delta")
        current["attention_state"]["GRCI_delta"] = (diff.get("attention", {}) or {}).get("GRCI_delta")
        current["temporal_state"]["previous_date"] = previous.get("date")
        current["spatial_reference"]["face_chainage_delta_from_previous"] = (diff.get("spatial", {}) or {}).get("face_chainage_delta_m")
        current["geological_state"]["persistent_hazards"] = _persistent_hazards(previous, current.get("geological_state", {}).get("geo_hazard_tags", []))
        current["attention_state"]["persistent_attention_segments"] = _persistent_segments(previous, current.get("attention_state", {}).get("top_grci_segments", []))
    else:
        current["geological_state"]["persistent_hazards"] = _persistent_hazards(None, current.get("geological_state", {}).get("geo_hazard_tags", []))
        current["attention_state"]["persistent_attention_segments"] = _persistent_segments(None, current.get("attention_state", {}).get("top_grci_segments", []))

    # Stability is a function of diff intensity.
    if diff.get("has_previous"):
        deltas = [
            abs(float((diff.get("response", {}) or {}).get("RAI_delta") or 0.0)),
            abs(float((diff.get("attention", {}) or {}).get("GRS_adjusted_delta") or 0.0)),
            abs(float((diff.get("attention", {}) or {}).get("GRCI_delta") or 0.0)),
        ]
        current["temporal_state"]["state_stability"] = round(max(0.0, min(1.0, 1.0 - sum(deltas) / len(deltas))), 3)
    else:
        current["temporal_state"]["state_stability"] = 1.0

    grs_delta = current.get("attention_state", {}).get("GRS_delta") or 0.0
    rai_delta = current.get("response_state", {}).get("RAI_delta") or 0.0
    combined = float(grs_delta or 0.0) + float(rai_delta or 0.0)
    current["attention_state"]["trend_label"] = "strengthening" if combined > 0.12 else "weakening" if combined < -0.12 else "stable"
    current["provenance_state"]["state_confidence"] = _state_confidence(current)
    return serialize_for_json(normalize_cst_state(current))


def build_or_update_cst(
    analysis_result: dict[str, Any],
    *,
    case_id: str | None = None,
    context: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Create the current TwinState/CST and optionally persist SQLite + JSON snapshot."""
    context = context or {}
    previous_cst = None
    if persist:
        previous_cst = load_previous_cst_for_context(
            date=context.get("date"),
            analysis_mode=context.get("analysis_mode") or "daily",
            end_time=context.get("time_end"),
        )
    snapshot = build_cst_snapshot(analysis_result, case_id=case_id, context=context)
    cst_state = update_cst(previous_cst, snapshot, context=context)
    if persist and cst_state.get("state_key"):
        save_cst_state(cst_state)
        try:
            cst_state.setdefault("provenance_state", {})["json_snapshot"] = save_twin_snapshot(cst_state)
        except Exception as exc:  # pragma: no cover - snapshot failures should not break analysis
            cst_state.setdefault("warnings", []).append(f"failed to save twin snapshot json: {exc}")
    return cst_state
