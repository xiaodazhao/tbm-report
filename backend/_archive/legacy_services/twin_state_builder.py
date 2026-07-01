from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any

import numpy as np
import pandas as pd

from schemas.twin_state_schema import TWIN_STATE_PAYLOAD_VERSION
from utils.chainage_utils import format_chainage_dk


SCHEMA_VERSION = TWIN_STATE_PAYLOAD_VERSION
MAX_KEY_CELLS = 5
MAX_FORWARD_SEGMENTS = 6
MAX_SOURCE_TRACE = 8
MAX_EXCERPT_CHARS = 200


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, (tuple, set)):
        return list(value)
    return []


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        x = float(value)
        if not math.isfinite(x):
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    x = _safe_float(value, default=None)
    if x is None:
        return int(default)
    return int(round(x))


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, dict):
        for key in ("text", "summary_text", "advice_text", "forward_advice_text", "message"):
            text = _safe_text(value.get(key), default="")
            if text:
                return text
        return default
    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(parts) if parts else default
    text = str(value).strip()
    return text or default


def _dedup_text(items: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        text = _safe_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _trim_excerpt(value: Any, max_chars: int = MAX_EXCERPT_CHARS) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    text = " ".join(text.replace("\r", "\n").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


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
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_clean(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _json_clean(value.item())
        except Exception:
            pass
    return str(value)


def _format_dk(value: Any) -> str | None:
    chainage = _safe_float(value, default=None)
    if chainage is None:
        return None
    try:
        return format_chainage_dk(chainage)
    except Exception:
        return None


def _sanitize_source_trace(value: Any, max_items: int = MAX_SOURCE_TRACE) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _as_list(value)[: max(int(max_items), 0)]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "evidence_id": _safe_text(item.get("evidence_id")) or None,
                "report_id": _safe_text(item.get("report_id")) or None,
                "source_type": _safe_text(item.get("source_type")) or None,
                "evidence_role": _safe_text(item.get("evidence_role")) or None,
                "spatial_type": _safe_text(item.get("spatial_type")) or None,
                "start_chainage": _safe_float(item.get("start_chainage"), default=None),
                "end_chainage": _safe_float(item.get("end_chainage"), default=None),
                "center_chainage": _safe_float(item.get("center_chainage"), default=None),
                "hazard_tags": _dedup_text(_as_list(item.get("hazard_tags"))),
                "effective_weight": _safe_float(item.get("effective_weight"), default=None),
                "confidence": _safe_float(item.get("confidence"), default=None),
                "raw_text_excerpt": _trim_excerpt(
                    item.get("raw_text_excerpt") or item.get("raw_text_snippet")
                ),
            }
        )
    return _json_clean(out)


def _sanitize_key_cells(geology_context: dict[str, Any], max_items: int = MAX_KEY_CELLS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _as_list(geology_context.get("key_cells"))[: max(int(max_items), 0)]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "cell_id": _safe_text(item.get("cell_id")) or None,
                "range_dk": _safe_text(item.get("range_dk")) or None,
                "cell_start": _safe_float(item.get("cell_start"), default=None),
                "cell_end": _safe_float(item.get("cell_end"), default=None),
                "cell_center": _safe_float(item.get("cell_center"), default=None),
                "fused_grade": _safe_text(item.get("fused_grade")) or None,
                "GRS_geo_base": _safe_float(item.get("GRS_geo_base"), default=None),
                "confidence": _safe_float(item.get("confidence"), default=None),
                "uncertainty_level": _safe_text(item.get("uncertainty_level")) or None,
                "conflict_level": _safe_text(item.get("conflict_level")) or None,
                "main_hazards": _dedup_text(_as_list(item.get("main_hazards"))),
                "source_types": _dedup_text(_as_list(item.get("source_types"))),
                "evidence_count": _safe_int(item.get("evidence_count"), default=0),
                "source_trace": _sanitize_source_trace(item.get("source_trace"), max_items=MAX_SOURCE_TRACE),
            }
        )
    return _json_clean(out)


def _sanitize_forward_segments(
    geology_context: dict[str, Any],
    forward_context: dict[str, Any],
    max_items: int = MAX_FORWARD_SEGMENTS,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    geology_segments = _as_list(geology_context.get("forward_segments"))
    raw_segments = geology_segments
    if not raw_segments:
        raw_segments = _as_list(forward_context.get("profile"))
        if raw_segments:
            warnings.append("forward_state 使用了 forward_context.profile fallback。")

    out: list[dict[str, Any]] = []
    for item in raw_segments[: max(int(max_items), 0)]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "relative_range": _safe_text(item.get("relative_range") or item.get("range_label")) or None,
                "range_dk": _safe_text(item.get("range_dk")) or None,
                "relative_start_m": _safe_float(
                    item.get("relative_start_m", item.get("start_m")),
                    default=None,
                ),
                "relative_end_m": _safe_float(
                    item.get("relative_end_m", item.get("end_m")),
                    default=None,
                ),
                "start_chainage": _safe_float(item.get("start_chainage"), default=None),
                "end_chainage": _safe_float(item.get("end_chainage"), default=None),
                "attention_level": _safe_text(
                    item.get("attention_level")
                    or item.get("forward_attention_level")
                    or item.get("risk_level")
                )
                or None,
                "main_hazards": _dedup_text(
                    _as_list(
                        item.get("main_hazards")
                        or item.get("forward_main_hazard_tags")
                        or item.get("hazards")
                    )
                ),
                "evidence_count": _safe_int(item.get("evidence_count"), default=0),
                "source_types": _dedup_text(_as_list(item.get("source_types"))),
                "confidence": _safe_float(
                    item.get("confidence", item.get("confidence_score")),
                    default=None,
                ),
                "uncertainty_level": _safe_text(item.get("uncertainty_level")) or None,
                "source_trace": _sanitize_source_trace(item.get("source_trace"), max_items=MAX_SOURCE_TRACE),
            }
        )
    return _json_clean(out), warnings


def _collect_used_evidence_ids(geology_context: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for cell in _as_list(geology_context.get("key_cells")):
        if not isinstance(cell, dict):
            continue
        ids.extend(str(item.get("evidence_id")) for item in _as_list(cell.get("source_trace")) if isinstance(item, dict) and item.get("evidence_id"))
    for segment in _as_list(geology_context.get("forward_segments")):
        if not isinstance(segment, dict):
            continue
        ids.extend(str(item.get("evidence_id")) for item in _as_list(segment.get("source_trace")) if isinstance(item, dict) and item.get("evidence_id"))
    return _dedup_text(ids)


def _collect_source_type_counts(geology_context: dict[str, Any]) -> dict[str, int]:
    source_summary = _as_dict(geology_context.get("source_trace_summary"))
    counts = _as_dict(source_summary.get("source_type_counts"))
    if counts:
        return {str(key): _safe_int(value, default=0) for key, value in counts.items()}

    out: dict[str, int] = {}
    for cell in _as_list(geology_context.get("key_cells")):
        for trace in _as_list(_as_dict(cell).get("source_trace")):
            if not isinstance(trace, dict):
                continue
            source_type = _safe_text(trace.get("source_type"))
            if source_type:
                out[source_type] = out.get(source_type, 0) + 1
    return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))


def _build_position_state(
    *,
    operation_context: dict[str, Any],
    geology_context: dict[str, Any],
    run_metadata: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    operation_position = _as_dict(operation_context.get("position"))
    geology_position = _as_dict(geology_context.get("current_position"))
    metadata = _as_dict(geology_context.get("metadata"))

    start_chainage = _safe_float(
        operation_position.get("start_chainage", metadata.get("chainage_min")),
        default=None,
    )
    end_chainage = _safe_float(
        operation_position.get("end_chainage", metadata.get("chainage_max")),
        default=None,
    )
    current_chainage = _safe_float(
        geology_position.get("current_chainage", end_chainage),
        default=None,
    )
    advance_length_m = _safe_float(
        operation_position.get("advance_length_m"),
        default=None,
    )
    if advance_length_m is None and start_chainage is not None and end_chainage is not None:
        advance_length_m = end_chainage - start_chainage

    return _json_clean(
        {
            "current_chainage": current_chainage,
            "current_chainage_dk": (
                _safe_text(geology_position.get("current_chainage_dk"))
                or _format_dk(current_chainage)
            ),
            "start_chainage": start_chainage,
            "end_chainage": end_chainage,
            "start_chainage_dk": (
                _safe_text(operation_position.get("start_chainage_dk"))
                or _format_dk(start_chainage)
            ),
            "end_chainage_dk": (
                _safe_text(operation_position.get("end_chainage_dk"))
                or _format_dk(end_chainage)
            ),
            "advance_length_m": _safe_float(advance_length_m, default=None),
            "advance_direction": _safe_int(
                geology_position.get(
                    "advance_direction",
                    context.get("advance_direction", run_metadata.get("advance_direction")),
                ),
                default=0,
            )
            if any(
                value is not None
                for value in (
                    geology_position.get("advance_direction"),
                    context.get("advance_direction"),
                    run_metadata.get("advance_direction"),
                )
            )
            else None,
        }
    )


def _build_operation_state(operation_context: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(operation_context.get("operation_mode_summary"))
    return _json_clean(
        {
            "summary": summary,
            "key_segments": _as_list(operation_context.get("key_operation_segments")),
            "routine_stop_summary": _as_dict(operation_context.get("routine_stop_summary")),
            "warnings": _dedup_text(_as_list(operation_context.get("warnings"))),
        }
    )


def _build_cluster_state(cluster_context: dict[str, Any]) -> dict[str, Any]:
    return _json_clean(
        {
            "has_cluster": bool(cluster_context.get("has_cluster", False)),
            "cluster_quality": _as_dict(cluster_context.get("cluster_quality")),
            "state_summaries": _as_list(cluster_context.get("state_summaries")),
            "warnings": _dedup_text(_as_list(cluster_context.get("warnings"))),
        }
    )


def _build_gas_state(gas_context: dict[str, Any]) -> dict[str, Any]:
    return _json_clean(
        {
            "exceed_summary": _as_dict(gas_context.get("exceed_summary")),
            "gas_summaries": _as_list(gas_context.get("gas_summaries")),
            "gas_field_diagnostics": _as_dict(gas_context.get("gas_field_diagnostics")),
            "warnings": _dedup_text(_as_list(gas_context.get("warnings"))),
        }
    )


def _build_geology_state(geology_context: dict[str, Any]) -> dict[str, Any]:
    warnings = _dedup_text(
        _as_list(geology_context.get("warnings"))
        + _as_list(geology_context.get("structured_warnings"))
    )
    return _json_clean(
        {
            "current_window_summary": _as_dict(geology_context.get("current_window_summary")),
            "key_cells": _sanitize_key_cells(geology_context),
            "source_trace_summary": _as_dict(geology_context.get("source_trace_summary")),
            "warnings": warnings,
        }
    )


def _build_response_state(
    cell_response_summary: dict[str, Any],
    coupling_summary: dict[str, Any],
) -> dict[str, Any]:
    top_rai_segments = _as_list(
        coupling_summary.get("top_rai_segments", coupling_summary.get("high_attention_segments"))
    )
    rai_values = [
        _safe_float(item.get("RAI", item.get("response_anomaly_index")), default=None)
        for item in top_rai_segments
        if isinstance(item, dict)
    ]
    rai_values = [value for value in rai_values if value is not None]
    primary_segment = _as_dict(top_rai_segments[0]) if top_rai_segments else {}
    warnings = _dedup_text(_as_list(cell_response_summary.get("warnings")))
    return _json_clean(
        {
            "cell_response_summary": cell_response_summary,
            "RAI_summary": {
                "has_response_anomaly": bool(top_rai_segments)
                or _safe_int(cell_response_summary.get("high_response_cell_count"), default=0) > 0,
                "RAI_max": max(rai_values) if rai_values else None,
                "RAI_mean": round(sum(rai_values) / len(rai_values), 4) if rai_values else None,
                "top_rai_segment_count": len(top_rai_segments),
                "primary_segment": primary_segment,
                "summary_text": _safe_text(
                    coupling_summary.get("summary_text")
                    or primary_segment.get("summary_text")
                )
                or None,
            },
            "warnings": warnings,
        }
    )


def _build_coupling_state(coupling_summary: dict[str, Any]) -> dict[str, Any]:
    top_grci_segments = _as_list(
        coupling_summary.get("top_grci_segments", coupling_summary.get("high_attention_segments"))
    )
    top_grs_segments = _as_list(coupling_summary.get("top_grs_segments"))
    top_rai_segments = _as_list(coupling_summary.get("top_rai_segments"))
    has_coupling = bool(
        coupling_summary.get("has_coupling")
        or top_grci_segments
        or top_grs_segments
        or top_rai_segments
    )
    return _json_clean(
        {
            "has_coupling": has_coupling,
            "GRCI_summary": {
                "GRS_mean": _safe_float(coupling_summary.get("GRS_mean"), default=None),
                "GRS_max": _safe_float(coupling_summary.get("GRS_max"), default=None),
                "RAI_mean": _safe_float(coupling_summary.get("RAI_mean"), default=None),
                "RAI_max": _safe_float(coupling_summary.get("RAI_max"), default=None),
                "GRCI_mean": _safe_float(coupling_summary.get("GRCI_mean"), default=None),
                "GRCI_max": _safe_float(coupling_summary.get("GRCI_max"), default=None),
                "coupling_level_counts": _as_dict(
                    coupling_summary.get("coupling_level_counts", coupling_summary.get("level_counts"))
                ),
                "grci_class_counts": _as_dict(
                    coupling_summary.get("grci_class_counts", coupling_summary.get("class_counts"))
                ),
                "summary_text": _safe_text(coupling_summary.get("summary_text")) or None,
            },
            "top_grci_segments": top_grci_segments,
            "top_grs_segments": top_grs_segments,
            "top_rai_segments": top_rai_segments,
            "warnings": _dedup_text(_as_list(coupling_summary.get("warnings"))),
        }
    )


def _build_forward_state(
    geology_context: dict[str, Any],
    forward_context: dict[str, Any],
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    segments, fallback_warnings = _sanitize_forward_segments(geology_context, forward_context)
    summary_from_geology = _as_dict(geology_context.get("data_summary")).get("forward_profile_summary", {})
    attention_summary = _as_dict(summary_from_geology)
    if not attention_summary:
        attention_summary = {
            "has_forward_evidence": bool(
                forward_context.get("has_forward_evidence", forward_context.get("has_forward_risk"))
            ),
            "overall_attention_level": _safe_text(
                forward_context.get("overall_attention_level", forward_context.get("forward_advice_level"))
            )
            or None,
            "forward_evidence_count": _safe_int(
                forward_context.get("forward_evidence_count", forward_context.get("forward_segment_count")),
                default=0,
            ),
            "forward_report_source_count": _safe_int(
                forward_context.get("forward_report_source_count", forward_context.get("multi_source_count")),
                default=0,
            ),
            "main_hazards": _dedup_text(
                _as_list(
                    forward_context.get("forward_main_hazard_tags", forward_context.get("main_hazards"))
                )
            ),
        }

    warnings = _dedup_text(
        fallback_warnings
        + _as_list(geology_context.get("warnings"))
        + _as_list(geology_context.get("structured_warnings"))
    )
    return _json_clean(
        {
            "lookahead_m": _safe_float(
                forward_context.get("lookahead_m", run_metadata.get("lookahead_m")),
                default=None,
            ),
            "segments": segments,
            "attention_summary": attention_summary,
            "warnings": warnings,
        }
    )


def _build_quality_state(
    *,
    plc_quality_report: dict[str, Any],
    geology_context: dict[str, Any],
    operation_context: dict[str, Any],
    cluster_context: dict[str, Any],
    gas_context: dict[str, Any],
    cell_response_summary: dict[str, Any],
) -> dict[str, Any]:
    geology_warnings = _dedup_text(
        _as_list(geology_context.get("warnings"))
        + _as_list(geology_context.get("structured_warnings"))
    )
    fallback_flags: list[str] = []
    if not operation_context:
        fallback_flags.append("missing_operation_context")
    if not cluster_context:
        fallback_flags.append("missing_cluster_context")
    if not gas_context:
        fallback_flags.append("missing_gas_context")
    if not geology_context:
        fallback_flags.append("missing_geology_context")
    if not cell_response_summary:
        fallback_flags.append("missing_cell_response_summary")
    if not _as_list(geology_context.get("forward_segments")):
        fallback_flags.append("forward_segments_missing_or_fallback")

    data_quality_warnings = _dedup_text(
        _as_list(plc_quality_report.get("warnings"))
        + _as_list(operation_context.get("warnings"))
        + _as_list(cluster_context.get("warnings"))
        + _as_list(gas_context.get("warnings"))
        + _as_list(cell_response_summary.get("warnings"))
    )
    return _json_clean(
        {
            "plc_quality": plc_quality_report,
            "geology_warnings": geology_warnings,
            "fallback_flags": fallback_flags,
            "data_quality_warnings": data_quality_warnings,
            "warnings": _dedup_text(geology_warnings + data_quality_warnings + fallback_flags),
        }
    )


def _build_source_refs(
    *,
    run_metadata: dict[str, Any],
    geology_context: dict[str, Any],
) -> dict[str, Any]:
    source_trace_summary = _as_dict(geology_context.get("source_trace_summary"))
    source_type_counts = _collect_source_type_counts(geology_context)
    return _json_clean(
        {
            "plc_file": _safe_text(run_metadata.get("source_file")) or None,
            "source_path": _safe_text(run_metadata.get("source_path")) or None,
            "evidence_db_path": _safe_text(run_metadata.get("evidence_db_path")) or None,
            "used_evidence_ids": _collect_used_evidence_ids(geology_context),
            "source_type_counts": source_type_counts,
            "report_id_count": _safe_int(source_trace_summary.get("report_id_count"), default=0)
            if source_trace_summary.get("report_id_count") is not None
            else None,
        }
    )


def build_twin_state(
    *,
    date: str | None = None,
    context: dict | None = None,
    operation_context: dict | None = None,
    cluster_context: dict | None = None,
    gas_context: dict | None = None,
    geology_context: dict | None = None,
    coupling_summary: dict | None = None,
    forward_context: dict | None = None,
    plc_quality_report: dict | None = None,
    cell_response_summary: dict | None = None,
    run_metadata: dict | None = None,
    history_context: dict | None = None,
) -> dict[str, Any]:
    """Build a compact, prompt-facing twin state without raw dataframes or long raw text."""
    context = _as_dict(context)
    operation_context = _as_dict(operation_context)
    cluster_context = _as_dict(cluster_context)
    gas_context = _as_dict(gas_context)
    geology_context = _as_dict(geology_context)
    coupling_summary = _as_dict(coupling_summary)
    forward_context = _as_dict(forward_context)
    plc_quality_report = _as_dict(plc_quality_report)
    cell_response_summary = _as_dict(cell_response_summary)
    run_metadata = _as_dict(run_metadata)
    history_context = _as_dict(history_context)

    position_state = _build_position_state(
        operation_context=operation_context,
        geology_context=geology_context,
        run_metadata=run_metadata,
        context=context,
    )
    operation_state = _build_operation_state(operation_context)
    cluster_state = _build_cluster_state(cluster_context)
    gas_state = _build_gas_state(gas_context)
    geology_state = _build_geology_state(geology_context)
    response_state = _build_response_state(cell_response_summary, coupling_summary)
    coupling_state = _build_coupling_state(coupling_summary)
    forward_state = _build_forward_state(geology_context, forward_context, run_metadata)
    quality_state = _build_quality_state(
        plc_quality_report=plc_quality_report,
        geology_context=geology_context,
        operation_context=operation_context,
        cluster_context=cluster_context,
        gas_context=gas_context,
        cell_response_summary=cell_response_summary,
    )
    source_refs = _build_source_refs(
        run_metadata=run_metadata,
        geology_context=geology_context,
    )

    warnings = _dedup_text(
        _as_list(operation_state.get("warnings"))
        + _as_list(cluster_state.get("warnings"))
        + _as_list(gas_state.get("warnings"))
        + _as_list(geology_state.get("warnings"))
        + _as_list(response_state.get("warnings"))
        + _as_list(coupling_state.get("warnings"))
        + _as_list(forward_state.get("warnings"))
        + _as_list(quality_state.get("warnings"))
    )

    operation_summary = _as_dict(operation_state.get("summary"))
    current_window_summary = _as_dict(geology_state.get("current_window_summary"))
    ok = bool(
        operation_summary.get("dominant_mode")
        or _safe_float(operation_summary.get("work_total_min"), default=0.0)
        or _safe_float(operation_summary.get("stop_total_min"), default=0.0)
        or _safe_int(current_window_summary.get("cell_count"), default=0) > 0
        or bool(geology_state.get("key_cells"))
        or bool(forward_state.get("segments"))
    )

    return _json_clean(
        {
            "schema_version": SCHEMA_VERSION,
            "ok": ok,
            "date": date or run_metadata.get("analysis_date") or context.get("date"),
            "analysis_mode": context.get("analysis_mode") or run_metadata.get("analysis_mode"),
            "position_state": position_state,
            "operation_state": operation_state,
            "cluster_state": cluster_state,
            "gas_state": gas_state,
            "geology_state": geology_state,
            "response_state": response_state,
            "coupling_state": coupling_state,
            "forward_state": forward_state,
            "quality_state": quality_state,
            "source_refs": source_refs,
            "run_metadata": run_metadata,
            "history_state": history_context,
            "warnings": warnings,
        }
    )
