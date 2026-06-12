from __future__ import annotations

from typing import Any

import pandas as pd

from analysis.dataprocess import (
    annotate_operation_mode,
    annotate_routine_ring_building_stops,
    build_operation_context,
    compute_stats,
    load_and_process,
)
from analysis.excavation_state import (
    build_cluster_context,
    detect_excavation_state,
    excavation_state_efficiency,
    excavation_state_segments,
    excavation_state_stats,
    explain_excavation_states,
)
from analysis.gas_analysis import build_gas_context, compute_gas_stats
from analysis.plc_quality_checker import check_plc_quality
from .cell_response import project_plc_response_to_cells


def analyze_plc_response(
    df_plc: pd.DataFrame,
    date: str | None = None,
    cell_length: float = 10.0,
) -> dict[str, Any]:
    """Run the retained PLC branch: quality, operation, cluster, gas, RAI cells."""
    warnings: list[str] = []
    if df_plc is None or df_plc.empty:
        warnings.append("PLC dataframe is empty")
        return {
            "df_plc_annotated": pd.DataFrame(),
            "quality_report": {},
            "operation_summary": {},
            "cluster_summary": {},
            "gas_summary": {},
            "cell_response_df": pd.DataFrame(),
            "current_chainage": None,
            "day_start_chainage": None,
            "day_end_chainage": None,
            "warnings": warnings,
        }

    quality_report = check_plc_quality(df_plc, date=date)
    df_operation = annotate_operation_mode(df_plc)
    df_operation = annotate_routine_ring_building_stops(df_operation)

    segments = load_and_process(df_operation)
    stats = compute_stats(segments)
    operation_summary = build_operation_context(
        df_operation,
        segments=segments,
        stats=stats,
        quality_report=quality_report,
    )

    df_state, _ = detect_excavation_state(df_operation)
    state_segments = excavation_state_segments(df_state)
    state_labels = explain_excavation_states(df_state)
    eff_df = excavation_state_efficiency(df_state)
    state_stats = excavation_state_stats(df_state, state_segments)
    cluster_summary = build_cluster_context(
        df_state,
        segments=state_segments,
        state_labels=state_labels,
        eff_df=eff_df,
        state_stats=state_stats,
    )

    gas_stats = compute_gas_stats(df_operation, df_state)
    gas_summary = build_gas_context(gas_stats, quality_report=quality_report)
    cell_response_df = project_plc_response_to_cells(df_operation, cell_length=cell_length)

    chainage_info = (quality_report or {}).get("chainage", {}) if isinstance(quality_report, dict) else {}
    current_chainage = chainage_info.get("end_chainage")
    day_start_chainage = chainage_info.get("start_chainage")
    day_end_chainage = chainage_info.get("end_chainage")

    return {
        "df_plc_annotated": df_operation,
        "quality_report": quality_report,
        "operation_summary": operation_summary,
        "cluster_summary": cluster_summary,
        "gas_summary": gas_summary,
        "cell_response_df": cell_response_df,
        "current_chainage": current_chainage,
        "day_start_chainage": day_start_chainage,
        "day_end_chainage": day_end_chainage,
        "warnings": warnings,
    }

