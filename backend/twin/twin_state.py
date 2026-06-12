from __future__ import annotations

from typing import Any

from schemas.pipeline import ConstructionStateCell


def build_twin_state(
    *,
    date: str,
    current_chainage: float | None,
    operation_summary: dict[str, Any],
    cluster_summary: dict[str, Any],
    gas_summary: dict[str, Any],
    construction_state_cells: list[ConstructionStateCell],
    forward_profile: dict[str, Any],
    high_grci_cells: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the only retained daily-report twin state."""
    active_cell = _nearest_cell(construction_state_cells, current_chainage)
    return {
        "schema_version": "daily_report_twin_state_v1",
        "date": date,
        "operation_state": operation_summary.get("operation_mode_summary", {}),
        "cluster_state": {
            "has_cluster": cluster_summary.get("has_cluster"),
            "n_states": cluster_summary.get("n_states"),
            "cluster_quality": cluster_summary.get("cluster_quality", {}),
            "state_summaries": cluster_summary.get("state_summaries", []),
        },
        "geology_state": _cell_subset(active_cell),
        "response_state": _response_subset(active_cell),
        "gas_state": gas_summary.get("exceed_summary", {}),
        "forward_state": {
            "current_chainage": current_chainage,
            "profile": forward_profile.get("profile", []),
            "summary": forward_profile.get("summary", forward_profile.get("data_summary", {})),
        },
        "coupling_state": {
            "high_grci_cells": high_grci_cells,
            "active_cell": _cell_subset(active_cell),
        },
        "provenance_state": {
            "source": "run_daily_report_pipeline",
            "cell_count": len(construction_state_cells),
            "warning_count": len(warnings or []),
        },
        "trace_state": {
            "active_trace_refs": active_cell.trace_refs if active_cell else [],
            "high_grci_trace_refs": list(
                dict.fromkeys(
                    ref
                    for cell in construction_state_cells
                    if cell.GRCI is not None and cell.GRCI >= 0.5
                    for ref in cell.trace_refs
                )
            ),
        },
        "warnings": warnings or [],
    }


def _nearest_cell(cells: list[ConstructionStateCell], current_chainage: float | None) -> ConstructionStateCell | None:
    if not cells:
        return None
    if current_chainage is None:
        return cells[0]
    return min(
        cells,
        key=lambda cell: abs((cell.cell_center or current_chainage) - current_chainage),
    )


def _cell_subset(cell: ConstructionStateCell | None) -> dict[str, Any]:
    if cell is None:
        return {}
    return cell.model_dump(
        include={
            "cell_id",
            "cell_start",
            "cell_end",
            "cell_center",
            "fused_grade",
            "main_hazards",
            "confidence_score",
            "uncertainty_level",
            "conflict_level",
            "GRS_geo_base",
            "supporting_evidence_ids",
            "source_trace",
        }
    )


def _response_subset(cell: ConstructionStateCell | None) -> dict[str, Any]:
    if cell is None:
        return {}
    return cell.model_dump(
        include={
            "cell_id",
            "operation_state",
            "speed_mean",
            "thrust_mean",
            "torque_mean",
            "stop_duration_min",
            "abnormal_score",
            "RAI",
            "plc_metrics",
        }
    )

