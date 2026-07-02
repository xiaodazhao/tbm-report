from __future__ import annotations

from typing import Any

from evidence_governance import build_evidence_governance_context
from schemas.pipeline import ConstructionStateCell
from schemas.twin import (
    DailyConstructionTwin,
    TwinCellView,
    TwinScope,
    TwinStateSummary,
    TwinTraceIndex,
)


def build_daily_construction_twin(
    *,
    date: str,
    construction_state_cells: list[ConstructionStateCell],
    operation_summary: dict[str, Any] | None = None,
    cluster_summary: dict[str, Any] | None = None,
    gas_summary: dict[str, Any] | None = None,
    forward_profile: dict[str, Any] | None = None,
    high_grci_cells: list[dict[str, Any]] | None = None,
    quality_summary: dict[str, Any] | None = None,
    trace_summary: dict[str, Any] | None = None,
    scope_summary: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    debug: dict[str, Any] | None = None,
) -> DailyConstructionTwin:
    """Build the cell-level evidence twin without recomputing RAI/GRS/GRCI."""
    scope_summary = scope_summary or {}
    warnings = list(warnings or [])
    cell_views = [_cell_to_twin_view(cell) for cell in construction_state_cells]
    daily_review = [cell for cell in cell_views if cell.cell_role == "daily_review"]
    forward_attention = [_strip_forward_grci(cell) for cell in cell_views if cell.cell_role == "forward_attention"]
    local_background = [cell for cell in cell_views if cell.cell_role == "local_background"]
    high_cells = [
        item for item in (high_grci_cells or [])
        if not item.get("is_forward_cell") and item.get("cell_role") in {None, "daily_review"}
    ]

    governance = build_evidence_governance_context(cell_views, warnings=warnings)
    twin = DailyConstructionTwin(
        date=date,
        scope=_build_scope(date, scope_summary, warnings),
        cells=cell_views,
        daily_review_cells=daily_review,
        forward_attention_cells=forward_attention,
        local_background_cells=local_background,
        high_grci_cells=high_cells,
        summaries=_build_summaries(
            cell_views,
            operation_summary=operation_summary or {},
            cluster_summary=cluster_summary or {},
            gas_summary=gas_summary or {},
            forward_profile=forward_profile or {},
            quality_summary=quality_summary or {},
            trace_summary=trace_summary or {},
        ),
        trace_index=_build_trace_index(cell_views, warnings),
        governance=governance,
        debug=debug or {},
        warnings=warnings,
    )
    return twin


def _build_scope(date: str, scope: dict[str, Any], warnings: list[str]) -> TwinScope:
    daily_plc_range = dict(scope.get("daily_plc_range") or scope.get("daily_chainage_raw") or {})
    if not daily_plc_range:
        daily_plc_range = {
            "start_chainage": scope.get("daily_chainage_min"),
            "end_chainage": scope.get("daily_chainage_max"),
            "daily_advance_m": scope.get("daily_advance_m"),
            "meaning": "PLC measured daily advance range.",
        }
    daily_excavated_scope = dict(scope.get("daily_excavated_scope") or {})
    daily_excavated_scope.setdefault(
        "meaning",
        "10m-cell aligned excavated review scope; not the actual PLC advance distance.",
    )
    return TwinScope(
        date=date,
        daily_plc_range=daily_plc_range,
        daily_excavated_scope=daily_excavated_scope,
        current_chainage=_num(scope.get("current_chainage")),
        face_chainage=_num(scope.get("current_chainage")),
        forward_scope=dict(scope.get("forward_scope") or {}),
        local_background_scope=dict(scope.get("local_background_scope") or {}),
        cell_length_m=_num(scope.get("cell_length_m")),
        warnings=warnings,
    )


def _cell_to_twin_view(cell: ConstructionStateCell) -> TwinCellView:
    plc_metrics = dict(cell.plc_metrics or {})
    source_trace = list(cell.source_trace or [])
    return TwinCellView(
        cell_id=cell.cell_id,
        mileage_start=cell.cell_start,
        mileage_end=cell.cell_end,
        cell_role=cell.cell_role,
        distance_to_face_m=cell.distance_to_face_m,
        position_state={
            "cell_id": cell.cell_id,
            "cell_start": cell.cell_start,
            "cell_end": cell.cell_end,
            "cell_center": cell.cell_center,
            "is_excavated_today": cell.is_excavated_today,
            "is_current_face_cell": cell.is_current_face_cell,
            "is_forward_cell": cell.is_forward_cell,
            "distance_to_face_m": cell.distance_to_face_m,
            "forward_distance_band": cell.forward_distance_band,
        },
        operation_state={
            "operation_state": cell.operation_state,
            "stop_duration_min": cell.stop_duration_min,
            "stop_ratio": cell.stop_ratio,
            "abnormal_ratio": cell.abnormal_ratio,
            "stop_reason_available": cell.stop_reason_available,
            "planned_stop_distinguishable": cell.planned_stop_distinguishable,
            "stop_interpretation_warning": cell.stop_interpretation_warning,
        },
        response_state={
            "RAI": cell.RAI,
            "RAI_formula_text": cell.RAI_formula_text,
            "speed_mean": cell.speed_mean,
            "thrust_mean": cell.thrust_mean,
            "torque_mean": cell.torque_mean,
            "plc_metrics": plc_metrics,
            "working_sample_count": plc_metrics.get("working_sample_count"),
            "working_ratio": plc_metrics.get("working_ratio"),
            "insufficient_working_samples": plc_metrics.get("insufficient_working_samples"),
            "working_metrics_source": plc_metrics.get("working_metrics_source"),
            "working_speed_cv": plc_metrics.get("working_speed_cv"),
            "working_thrust_cv": plc_metrics.get("working_thrust_cv"),
            "working_torque_cv": plc_metrics.get("working_torque_cv"),
            "penetration_mean": plc_metrics.get("penetration_mean"),
            "cutterhead_power_proxy": plc_metrics.get("cutterhead_power_proxy"),
            "thrust_per_penetration": plc_metrics.get("thrust_per_penetration"),
            "torque_per_penetration": plc_metrics.get("torque_per_penetration"),
            "steady_state_available": plc_metrics.get("steady_state_available"),
            "steady_sample_count": plc_metrics.get("steady_sample_count"),
            "steady_ratio": plc_metrics.get("steady_ratio"),
            "steady_to_working_ratio": plc_metrics.get("steady_to_working_ratio"),
            "steady_speed_mean": plc_metrics.get("steady_speed_mean"),
            "steady_speed_std": plc_metrics.get("steady_speed_std"),
            "steady_speed_cv": plc_metrics.get("steady_speed_cv"),
            "steady_thrust_mean": plc_metrics.get("steady_thrust_mean"),
            "steady_thrust_std": plc_metrics.get("steady_thrust_std"),
            "steady_thrust_cv": plc_metrics.get("steady_thrust_cv"),
            "steady_torque_mean": plc_metrics.get("steady_torque_mean"),
            "steady_torque_std": plc_metrics.get("steady_torque_std"),
            "steady_torque_cv": plc_metrics.get("steady_torque_cv"),
            "steady_rpm_mean": plc_metrics.get("steady_rpm_mean"),
            "steady_rpm_std": plc_metrics.get("steady_rpm_std"),
            "steady_rpm_cv": plc_metrics.get("steady_rpm_cv"),
            "steady_penetration_mean": plc_metrics.get("steady_penetration_mean"),
            "steady_penetration_std": plc_metrics.get("steady_penetration_std"),
            "steady_penetration_cv": plc_metrics.get("steady_penetration_cv"),
            "steady_cutterhead_power_proxy": plc_metrics.get("steady_cutterhead_power_proxy"),
            "steady_thrust_per_penetration": plc_metrics.get("steady_thrust_per_penetration"),
            "steady_torque_per_penetration": plc_metrics.get("steady_torque_per_penetration"),
            "steady_state_fallback_used": plc_metrics.get("steady_state_fallback_used"),
            "steady_state_fallback_reason": plc_metrics.get("steady_state_fallback_reason"),
            "steady_detection_signal": plc_metrics.get("steady_detection_signal"),
            "plc_preprocessing_quality_grade": plc_metrics.get("plc_preprocessing_quality_grade"),
            "plc_preprocessing_quality_reason": plc_metrics.get("plc_preprocessing_quality_reason"),
            "plc_preprocessing_boundary": plc_metrics.get("plc_preprocessing_boundary"),
            "proxy_boundary": "PLC enhanced metrics are excavated-scope response evidence, not physical power or geological proof.",
        },
        geology_state={
            "GRS_geo_base": cell.GRS_geo_base,
            "GRS_available": cell.GRS_available,
            "GRS_unavailable_reason": cell.GRS_unavailable_reason,
            "fused_grade": cell.fused_grade,
            "main_hazards": cell.main_hazards,
            "hazard_scores": cell.hazard_scores,
            "confidence_score": cell.confidence_score,
            "evidence_count": cell.evidence_count,
            "supporting_evidence_ids": cell.supporting_evidence_ids,
            "source_trace": source_trace,
        },
        forward_state={
            "is_forward_cell": cell.is_forward_cell,
            "forward_distance_band": cell.forward_distance_band,
            "forward_distance_weight": cell.forward_distance_weight,
            "distance_to_face_m": cell.distance_to_face_m,
            "GRCI_available": False if cell.cell_role == "forward_attention" else cell.GRCI_available,
            "boundary": "forward_attention is a forward indication role and must not use GRCI as a forward risk metric.",
        },
        gas_state={},
        coupling_state={
            "GRCI": None if cell.cell_role == "forward_attention" else cell.GRCI,
            "GRCI_available": False if cell.cell_role == "forward_attention" else cell.GRCI_available,
            "GRCI_source": cell.GRCI_source,
            "GRCI_unavailable_reason": cell.GRCI_unavailable_reason,
            "coupling_level": cell.coupling_level,
            "coupling_explanation": cell.coupling_explanation,
            "GRCI_formula_text": cell.GRCI_formula_text,
            "boundary": "GRCI is an excavated-scope review index, not a disaster probability.",
        },
        quality_state={
            "has_plc_response": cell.has_plc_response,
            "has_geology_evidence": cell.has_geology_evidence,
            "GRS_available": cell.GRS_available,
            "GRCI_available": False if cell.cell_role == "forward_attention" else cell.GRCI_available,
            "insufficient_working_samples": plc_metrics.get("insufficient_working_samples"),
            "plc_preprocessing_quality_grade": plc_metrics.get("plc_preprocessing_quality_grade"),
            "steady_state_fallback_used": plc_metrics.get("steady_state_fallback_used"),
            "warnings": [
                item for item in [
                    cell.stop_interpretation_warning,
                    plc_metrics.get("steady_state_fallback_reason"),
                    cell.GRCI_unavailable_reason,
                    cell.GRS_unavailable_reason,
                ]
                if item
            ],
        },
        trace_state={
            "supporting_evidence_ids": cell.supporting_evidence_ids,
            "trace_refs": cell.trace_refs,
            "source_trace": source_trace,
            "trace_completeness": cell.trace_completeness,
        },
    )


def _strip_forward_grci(cell: TwinCellView) -> TwinCellView:
    cell.forward_state["GRCI_available"] = False
    cell.coupling_state["GRCI"] = None
    cell.coupling_state["GRCI_available"] = False
    return cell


def _build_summaries(
    cells: list[TwinCellView],
    *,
    operation_summary: dict[str, Any],
    cluster_summary: dict[str, Any],
    gas_summary: dict[str, Any],
    forward_profile: dict[str, Any],
    quality_summary: dict[str, Any],
    trace_summary: dict[str, Any],
) -> TwinStateSummary:
    return TwinStateSummary(
        operation_summary=operation_summary,
        response_summary={
            "cell_count": len(cells),
            "RAI_available_count": sum(1 for cell in cells if cell.response_state.get("RAI") is not None),
            "plc_enhanced_cell_count": sum(
                1 for cell in cells if cell.response_state.get("working_sample_count") is not None
            ),
            "cluster_summary": cluster_summary,
        },
        plc_response_summary={
            "working_sample_cell_count": sum(
                1 for cell in cells if cell.response_state.get("working_sample_count") is not None
            ),
        },
        geology_summary={
            "GRS_available_count": sum(1 for cell in cells if cell.geology_state.get("GRS_available")),
        },
        forward_summary=forward_profile,
        gas_summary=gas_summary,
        coupling_summary={
            "GRCI_available_count": sum(1 for cell in cells if cell.coupling_state.get("GRCI_available")),
            "high_or_medium_review_count": sum(
                1 for cell in cells
                if cell.cell_role == "daily_review" and cell.coupling_state.get("coupling_level") in {"high", "medium"}
            ),
        },
        quality_summary={**quality_summary, "trace_summary": trace_summary},
    )


def _build_trace_index(cells: list[TwinCellView], warnings: list[str]) -> TwinTraceIndex:
    cell_trace_index = {}
    evidence_trace_index: dict[str, Any] = {}
    plc_trace_index = {}
    geology_trace_index = {}
    source_trace_index = {}
    for cell in cells:
        cell_trace_index[cell.cell_id] = cell.trace_state
        plc_trace_index[cell.cell_id] = cell.response_state.get("plc_metrics", {})
        geology_trace_index[cell.cell_id] = {
            "GRS_geo_base": cell.geology_state.get("GRS_geo_base"),
            "supporting_evidence_ids": cell.geology_state.get("supporting_evidence_ids", []),
            "source_trace": cell.geology_state.get("source_trace", []),
        }
        for item in cell.trace_state.get("source_trace", []) or []:
            evidence_id = str(item.get("evidence_id") or "")
            if not evidence_id:
                continue
            evidence_trace_index[evidence_id] = item
            source_trace_index[evidence_id] = {
                "cell_id": cell.cell_id,
                **item,
            }
    return TwinTraceIndex(
        cell_trace_index=cell_trace_index,
        evidence_trace_index=evidence_trace_index,
        plc_trace_index=plc_trace_index,
        geology_trace_index=geology_trace_index,
        source_trace_index=source_trace_index,
        warning_index={"warnings": warnings},
    )


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None
