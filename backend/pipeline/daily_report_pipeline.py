from __future__ import annotations

from typing import Any

import pandas as pd

from coupling.grs_rai_grci import build_construction_state_cells, high_grci_cells, priority_cell_groups
from geology_v2.evidence_projector import project_evidence_to_cells
from geology_v2.forward_profile import build_forward_profile
from geology_v2.fusion_engine import fuse_geo_states
from geology_v2.evidence_normalizer import summarize_normalized_evidence
from geology_v2.pipeline import run_geology_v2_context
from llm.evidence_pack import build_prompt_evidence_pack, build_template_report
from llm.llm_report_generator import generate_llm_report, normalize_generation_mode
from llm.report_prompt import build_prompt
from llm.report_quality_checker import check_report_quality
from llm.report_trace_builder import build_report_trace, summarize_report_trace
from pipeline.inputs import json_safe, load_daily_inputs
from pipeline.evidence_scope import (
    apply_spatial_relevance_filter,
    build_scope_cells,
    build_scope_summary,
)
from plc.response import analyze_plc_response
from schemas.pipeline import DailyReportResult
from twin.twin_state import build_twin_state


def run_daily_report_pipeline(
    date: str,
    use_llm: bool = False,
    *,
    generation_mode: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    mock_llm: bool = False,
    enable_revision: bool | None = None,
    enable_planner: bool | None = None,
    planner_provider: str | None = None,
    planner_model: str | None = None,
    max_revision_rounds: int = 1,
    cell_length: float = 10.0,
    cell_size_m: float | None = None,
    lookahead_m: float = 30.0,
    advance_direction: int = 1,
    local_background_back_m: float = 100.0,
) -> DailyReportResult:
    """Run the only retained daily TBM report pipeline."""
    warnings: list[str] = []
    if cell_size_m is not None:
        cell_length = float(cell_size_m)
    if float(cell_length or 10.0) > 10.0:
        warnings.append("cell_size_m larger than recommended maximum for daily report review")
    active_generation_mode = normalize_generation_mode(
        generation_mode or ("evidence_pack_llm" if use_llm else "template")
    )
    inputs = load_daily_inputs(date)
    warnings.extend(inputs.warnings)
    active_date = inputs.date or date

    plc_result = analyze_plc_response(
        inputs.df_plc,
        date=active_date,
        cell_length=cell_length,
    )
    warnings.extend(plc_result.get("warnings", []))
    current_chainage = _num(plc_result.get("current_chainage"))
    day_start_chainage = _num(plc_result.get("day_start_chainage"))
    day_end_chainage = _num(plc_result.get("day_end_chainage"))
    cell_response_df = plc_result.get("cell_response_df", pd.DataFrame())

    raw_geology_result = _run_geology_branch(
        df_plc=plc_result.get("df_plc_annotated", inputs.df_plc),
        evidence_df=inputs.evidence_df,
        current_chainage=current_chainage,
        analysis_date=active_date,
        cell_length=cell_length,
        lookahead_m=lookahead_m,
        advance_direction=advance_direction,
    )
    scope_summary = build_scope_summary(
        date=active_date,
        current_chainage=current_chainage,
        day_start_chainage=day_start_chainage,
        day_end_chainage=day_end_chainage,
        cell_length=cell_length,
        lookahead_m=lookahead_m,
        advance_direction=advance_direction,
        local_background_back_m=local_background_back_m,
    )
    geology_result = _rebuild_geology_branch_for_report_scope(
        raw_geology_result=raw_geology_result,
        scope_summary=scope_summary,
        current_chainage=current_chainage,
        cell_length=cell_length,
        lookahead_m=lookahead_m,
        advance_direction=advance_direction,
    )
    warnings.extend(geology_result.get("warnings", []))

    cells_df = _df(geology_result.get("cells_df"))
    if cells_df.empty and not cell_response_df.empty:
        cells_df = cell_response_df[["cell_id", "cell_start", "cell_end", "cell_center"]].copy()

    normalized_df = _df(geology_result.get("normalized_df"))
    cell_evidence_df = _df(geology_result.get("cell_evidence_df"))
    geo_states_df = _df(geology_result.get("geo_states_df"))
    forward_profile = geology_result.get("forward_profile") or {}

    construction_state_cells = build_construction_state_cells(
        cells_df=cells_df,
        cell_response_df=cell_response_df,
        geo_states_df=geo_states_df,
        cell_evidence_df=cell_evidence_df,
        normalized_evidence_df=normalized_df,
        current_chainage=current_chainage,
        day_start_chainage=day_start_chainage,
        day_end_chainage=day_end_chainage,
        lookahead_m=lookahead_m,
        advance_direction=advance_direction,
        scope_summary=scope_summary,
    )
    _update_scope_summary_with_cells(scope_summary, construction_state_cells)
    high_cells = high_grci_cells(construction_state_cells, limit=10)
    priority_cells = priority_cell_groups(construction_state_cells)
    forward_profile = _with_forward_attention_cells(forward_profile, construction_state_cells)

    normalized_evidence_summary = _normalized_summary(normalized_df, geology_result)
    operation_summary = json_safe(plc_result.get("operation_summary", {}))
    cluster_summary = json_safe(plc_result.get("cluster_summary", {}))
    gas_summary = json_safe(plc_result.get("gas_summary", {}))
    forward_profile = json_safe(forward_profile)

    prompt_evidence_pack = build_prompt_evidence_pack(
        date=active_date,
        current_chainage=current_chainage,
        operation_summary=operation_summary,
        cluster_summary=cluster_summary,
        gas_summary=gas_summary,
        construction_state_cells=construction_state_cells,
        forward_profile=forward_profile,
        high_grci_cells=high_cells,
        scope_summary=scope_summary,
        excluded_evidence_summary=_excluded_evidence_summary(_df(geology_result.get("excluded_evidence_df"))),
        priority_cells=priority_cells,
        quality_evidence=json_safe(plc_result.get("quality_report", {})),
        warnings=warnings,
    )
    prompt_text = build_prompt(prompt_evidence_pack)
    template_report = build_template_report(prompt_evidence_pack)

    twin_state = build_twin_state(
        date=active_date,
        current_chainage=current_chainage,
        operation_summary=operation_summary,
        cluster_summary=cluster_summary,
        gas_summary=gas_summary,
        construction_state_cells=construction_state_cells,
        forward_profile=forward_profile,
        high_grci_cells=high_cells,
        warnings=warnings,
    )

    llm_generation = {}
    if active_generation_mode == "template":
        report_text = template_report
    else:
        llm_generation = generate_llm_report(
            date=active_date,
            prompt_evidence_pack=prompt_evidence_pack,
            twin_state=twin_state,
            generation_mode=active_generation_mode,
            provider_name=llm_provider,
            model=llm_model,
            mock_llm=mock_llm,
            enable_revision=enable_revision,
            enable_planner=enable_planner,
            planner_provider_name=planner_provider,
            planner_model=planner_model,
            max_revision_rounds=max_revision_rounds,
            fallback_report=template_report,
        )
        warnings.extend(llm_generation.get("warnings", []))
        if llm_generation.get("prompt"):
            prompt_text = llm_generation.get("prompt", prompt_text)
        report_text = llm_generation.get("report_final") or template_report

    quality = (
        llm_generation.get("quality_after_revision")
        if llm_generation
        else None
    ) or check_report_quality(
        report_text,
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
        include_claim_results=True,
    )
    trace = (
        llm_generation.get("trace_after_revision")
        if llm_generation
        else None
    ) or build_report_trace(
        report_text,
        grounding_result={
            "claim_results": quality.get("claim_results") or [],
            **(quality.get("grounding_summary") or {}),
        },
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
    )

    quality_summary = _quality_summary(quality)
    trace_summary = summarize_report_trace(trace)

    return DailyReportResult(
        date=active_date,
        report_text=report_text,
        operation_summary=operation_summary,
        cluster_summary=cluster_summary,
        gas_summary=gas_summary,
        normalized_evidence_summary=json_safe(normalized_evidence_summary),
        construction_state_cells=construction_state_cells,
        forward_profile=forward_profile,
        prompt_evidence_pack=json_safe(prompt_evidence_pack),
        prompt_text=prompt_text,
        quality=json_safe(quality),
        quality_summary=json_safe(quality_summary),
        trace=json_safe(trace),
        trace_summary=json_safe(trace_summary),
        high_grci_cells=json_safe(high_cells),
        review_cells=json_safe(priority_cells.get("review_cells", [])),
        high_priority_cells=json_safe(priority_cells.get("high_priority_cells", [])),
        medium_priority_cells=json_safe(priority_cells.get("medium_priority_cells", [])),
        low_priority_cells=json_safe(priority_cells.get("low_priority_cells", [])),
        twin_state=json_safe(twin_state),
        scope_summary=json_safe(scope_summary),
        time_valid_evidence=json_safe(_df(geology_result.get("time_valid_evidence_df")).to_dict(orient="records")),
        spatial_relevant_evidence=json_safe(_df(geology_result.get("spatial_relevant_evidence_df")).to_dict(orient="records")),
        excluded_evidence=json_safe(_df(geology_result.get("excluded_evidence_df")).to_dict(orient="records")),
        cell_response_records=json_safe(_df(cell_response_df).to_dict(orient="records")),
        geo_state_records=json_safe(_df(geo_states_df).to_dict(orient="records")),
        cell_evidence_records=json_safe(_df(cell_evidence_df).to_dict(orient="records")),
        daily_review_cells=json_safe([cell.model_dump() for cell in construction_state_cells if cell.cell_role == "daily_review"]),
        forward_attention_cells=json_safe([cell.model_dump() for cell in construction_state_cells if cell.cell_role == "forward_attention"]),
        local_background_cells=json_safe([cell.model_dump() for cell in construction_state_cells if cell.cell_role == "local_background"]),
        method_metrics=json_safe(
            _method_metrics(
                construction_state_cells,
                scope_summary,
                geology_result,
                quality_summary=quality_summary,
                trace_summary=trace_summary,
                quality=quality,
                trace=trace,
                warnings=warnings,
                passed=True,
                priority_cells=priority_cells,
            )
        ),
        generation_mode=active_generation_mode,
        llm_generation=json_safe(llm_generation),
        warnings=list(dict.fromkeys(str(item) for item in warnings if item)),
    )


def _run_geology_branch(
    *,
    df_plc: pd.DataFrame,
    evidence_df: pd.DataFrame,
    current_chainage: float | None,
    analysis_date: str,
    cell_length: float,
    lookahead_m: float,
    advance_direction: int,
) -> dict[str, Any]:
    if evidence_df is None or evidence_df.empty:
        return {
            "warnings": ["empty evidence_df"],
            "cells_df": pd.DataFrame(),
            "normalized_df": pd.DataFrame(),
            "cell_evidence_df": pd.DataFrame(),
            "geo_states_df": pd.DataFrame(),
            "forward_profile": {},
        }
    result = run_geology_v2_context(
        df_plc=df_plc,
        evidence_df=evidence_df,
        current_chainage=current_chainage,
        analysis_date=analysis_date,
        mode="online",
        advance_direction=advance_direction,
        lookahead_m=lookahead_m,
        cell_length=cell_length,
        response_cell_df=None,
        coupled_df=None,
        build_report=False,
    )
    if not result.get("ok"):
        result.setdefault("warnings", []).append(result.get("message", "geology_v2 failed"))
    return result


def _rebuild_geology_branch_for_report_scope(
    *,
    raw_geology_result: dict[str, Any],
    scope_summary: dict[str, Any],
    current_chainage: float | None,
    cell_length: float,
    lookahead_m: float,
    advance_direction: int,
) -> dict[str, Any]:
    warnings = list(raw_geology_result.get("warnings", []))
    time_valid_df = _df(raw_geology_result.get("normalized_df"))
    spatial_df, excluded_df, counted_scope = apply_spatial_relevance_filter(time_valid_df, scope_summary)
    scope_summary.update(counted_scope)

    cells_df = build_scope_cells(scope_summary)
    if cells_df.empty:
        warnings.append("empty report scope cells")
        return {
            "warnings": warnings,
            "cells_df": pd.DataFrame(),
            "normalized_df": spatial_df,
            "time_valid_evidence_df": time_valid_df,
            "spatial_relevant_evidence_df": spatial_df,
            "excluded_evidence_df": excluded_df,
            "cell_evidence_df": pd.DataFrame(),
            "geo_states_df": pd.DataFrame(),
            "forward_profile": {},
        }

    if spatial_df.empty:
        cell_evidence_df = pd.DataFrame()
        geo_states_df = fuse_geo_states(
            cells_df=cells_df,
            cell_evidence_df=cell_evidence_df,
            normalized_evidence_df=spatial_df,
        )
    else:
        cell_evidence_df = project_evidence_to_cells(
            cells_df=cells_df,
            normalized_evidence_df=spatial_df,
        )
        geo_states_df = fuse_geo_states(
            cells_df=cells_df,
            cell_evidence_df=cell_evidence_df,
            normalized_evidence_df=spatial_df,
        )
    geo_states_df = _annotate_geo_states_availability(geo_states_df, cell_evidence_df)

    forward_profile = build_forward_profile(
        geo_states_df=geo_states_df,
        current_chainage=current_chainage,
        lookahead_m=lookahead_m,
        step_m=cell_length,
        advance_direction=advance_direction,
    )

    scope_summary.update(
        {
            "geo_states_cell_count": int(len(geo_states_df)),
            "construction_state_cell_count": int(len(cells_df)),
            "cell_evidence_row_count": int(len(cell_evidence_df)),
        }
    )
    return {
        "warnings": warnings,
        "cells_df": cells_df,
        "normalized_df": spatial_df,
        "time_valid_evidence_df": time_valid_df,
        "spatial_relevant_evidence_df": spatial_df,
        "excluded_evidence_df": excluded_df,
        "cell_evidence_df": cell_evidence_df,
        "geo_states_df": geo_states_df,
        "forward_profile": forward_profile,
        "raw_geology_result": raw_geology_result,
    }


def _normalized_summary(normalized_df: pd.DataFrame, geology_result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(normalized_df, pd.DataFrame) and not normalized_df.empty:
        try:
            return summarize_normalized_evidence(normalized_df)
        except Exception as exc:
            return {"ok": False, "warning": str(exc), "row_count": int(len(normalized_df))}
    for step in (geology_result.get("diagnostics") or {}).get("steps", []):
        if isinstance(step, dict) and step.get("name") == "hsp_anomaly_point_dedup":
            return step.get("summary") or {}
    return {"row_count": 0}


def _quality_summary(quality: dict[str, Any]) -> dict[str, Any]:
    stats = quality.get("stats", {}) if isinstance(quality, dict) else {}
    grounding = quality.get("grounding_summary", {}) if isinstance(quality, dict) else {}
    return {
        "ok": bool(quality.get("ok")) if isinstance(quality, dict) else False,
        "quality_score": quality.get("score", 0) if isinstance(quality, dict) else 0,
        "grounding_rate": grounding.get("grounding_rate", stats.get("grounding_rate", 0.0)),
        "claim_count": grounding.get("claim_count", stats.get("claim_count", 0)),
        "grounded_claim_count": grounding.get("grounded_claim_count", stats.get("grounded_claim_count", 0)),
        "unsupported_claim_count": grounding.get("unsupported_claim_count", stats.get("unsupported_claim_count", 0)),
        "error_count": stats.get("error_count", 0),
        "warning_count": stats.get("warning_count", 0),
    }


def _update_scope_summary_with_cells(scope_summary: dict[str, Any], cells: list) -> None:
    scope_summary.update(
        {
            "construction_state_cell_count": len(cells),
            "daily_review_cell_count": sum(1 for cell in cells if getattr(cell, "cell_role", None) == "daily_review"),
            "forward_attention_cell_count": sum(1 for cell in cells if getattr(cell, "cell_role", None) == "forward_attention"),
            "local_background_cell_count": sum(1 for cell in cells if getattr(cell, "cell_role", None) == "local_background"),
            "GRCI_available_count": sum(1 for cell in cells if getattr(cell, "GRCI_available", False)),
        }
    )


def _excluded_evidence_summary(excluded_df: pd.DataFrame) -> dict[str, Any]:
    if excluded_df is None or excluded_df.empty:
        return {
            "excluded_evidence_count": 0,
            "excluded_by_distance_evidence_count": 0,
            "excluded_by_missing_geometry_evidence_count": 0,
            "examples": [],
        }
    role = excluded_df.get("evidence_report_role", pd.Series(dtype=str)).astype(str)
    examples = []
    for _, row in excluded_df.head(10).iterrows():
        examples.append(
            {
                "evidence_id": row.get("evidence_id"),
                "report_id": row.get("report_id"),
                "source_type_norm": row.get("source_type_norm"),
                "evidence_report_role": row.get("evidence_report_role"),
                "spatial_invalid_reason": row.get("spatial_invalid_reason"),
                "start_chainage": row.get("start_chainage"),
                "end_chainage": row.get("end_chainage"),
                "distance_to_current_chainage": row.get("distance_to_current_chainage"),
            }
        )
    return {
        "excluded_evidence_count": int(len(excluded_df)),
        "excluded_by_distance_evidence_count": int(role.eq("excluded_by_distance").sum()),
        "excluded_by_missing_geometry_evidence_count": int(role.eq("excluded_by_missing_geometry").sum()),
        "examples": json_safe(examples),
    }


def _annotate_geo_states_availability(geo_states_df: pd.DataFrame, cell_evidence_df: pd.DataFrame) -> pd.DataFrame:
    if geo_states_df is None or geo_states_df.empty:
        return geo_states_df
    out = geo_states_df.copy()
    evidence_counts = {}
    if isinstance(cell_evidence_df, pd.DataFrame) and not cell_evidence_df.empty and "cell_id" in cell_evidence_df.columns:
        evidence_counts = cell_evidence_df.groupby("cell_id").size().to_dict()
    out["has_geology_evidence"] = out["cell_id"].map(lambda cell_id: int(evidence_counts.get(cell_id, 0)) > 0)
    method = out.get("GRS_component_method", pd.Series("unavailable", index=out.index)).astype(str)
    grs = pd.to_numeric(out.get("GRS_geo_base"), errors="coerce") if "GRS_geo_base" in out.columns else pd.Series(float("nan"), index=out.index)
    out["GRS_available"] = out["has_geology_evidence"].astype(bool) & grs.notna() & method.ne("empty")
    out["GRS_unavailable_reason"] = out["GRS_available"].map(
        lambda available: None if bool(available) else "missing_spatial_relevant_geology_evidence"
    )
    if "GRS_formula_text" not in out.columns:
        out["GRS_formula_text"] = "GRS = 0.45 * grade_score_component + 0.45 * hazard_component + 0.10 * confidence_component"
    return out


def _method_metrics(
    cells: list,
    scope_summary: dict[str, Any],
    geology_result: dict[str, Any],
    *,
    quality_summary: dict[str, Any] | None = None,
    trace_summary: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    passed: bool | None = None,
    priority_cells: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    spatial_df = _df(geology_result.get("spatial_relevant_evidence_df"))
    excluded_df = _df(geology_result.get("excluded_evidence_df"))
    quality_summary = quality_summary or {}
    trace_summary = trace_summary or {}
    quality = quality or {}
    trace = trace or {}
    priority_cells = priority_cells or {}
    return {
        "date": scope_summary.get("date"),
        "daily_chainage_min": scope_summary.get("daily_chainage_min"),
        "daily_chainage_max": scope_summary.get("daily_chainage_max"),
        "daily_advance_m": scope_summary.get("daily_advance_m"),
        "current_chainage": scope_summary.get("current_chainage"),
        "scope_summary": scope_summary,
        "time_valid_evidence_count": scope_summary.get("time_valid_evidence_count", 0),
        "spatial_relevant_evidence_count": scope_summary.get("spatial_relevant_evidence_count", 0),
        "excluded_by_distance_evidence_count": scope_summary.get("excluded_by_distance_evidence_count", 0),
        "excluded_by_time_evidence_count": scope_summary.get("excluded_by_time_evidence_count", 0),
        "excluded_by_missing_geometry_evidence_count": scope_summary.get("excluded_by_missing_geometry_evidence_count", 0),
        "construction_state_cell_count": len(cells),
        "daily_review_cell_count": sum(1 for cell in cells if cell.cell_role == "daily_review"),
        "forward_attention_cell_count": sum(1 for cell in cells if cell.cell_role == "forward_attention"),
        "local_background_cell_count": sum(1 for cell in cells if cell.cell_role == "local_background"),
        "cell_size_m": scope_summary.get("cell_length_m"),
        "RAI_available_count": sum(1 for cell in cells if cell.RAI is not None),
        "GRS_available_count": sum(1 for cell in cells if cell.GRS_available),
        "GRCI_available_count": sum(1 for cell in cells if cell.GRCI_available),
        "review_cell_count": len(priority_cells.get("review_cells", [])),
        "high_priority_cell_count": len(priority_cells.get("high_priority_cells", [])),
        "medium_priority_cell_count": len(priority_cells.get("medium_priority_cells", [])),
        "low_priority_cell_count": len(priority_cells.get("low_priority_cells", [])),
        "claim_count": quality_summary.get("claim_count"),
        "grounded_claim_count": quality_summary.get("grounded_claim_count"),
        "unsupported_claim_count": quality_summary.get("unsupported_claim_count"),
        "grounding_rate": quality_summary.get("grounding_rate"),
        "trace_coverage": trace_summary.get("trace_coverage"),
        "quality_score": quality_summary.get("quality_score"),
        "mean_trace_completeness": _mean([cell.trace_completeness for cell in cells if cell.trace_completeness is not None]),
        "min_trace_completeness": _min([cell.trace_completeness for cell in cells if cell.trace_completeness is not None]),
        "low_trace_completeness_count": sum(1 for cell in cells if cell.trace_completeness is not None and cell.trace_completeness < 0.7),
        "evidence_without_trace_count": sum(1 for cell in cells if cell.evidence_count and not cell.source_trace),
        "error_type_counts": quality.get("error_type_counts", {}),
        "support_type_distribution": trace.get("support_type_distribution", {}),
        "trace_support_none_count": (trace.get("support_type_distribution", {}) or {}).get("none", 0),
        "role_consistency_violation_count": sum(
            1 for item in (quality.get("violations") or [])
            if isinstance(item, dict) and item.get("error_type") in {
                "E4_FORWARD_AS_EXCAVATED_REVIEW",
                "E5_BACKGROUND_AS_DAILY_RESPONSE",
                "E9_SOURCE_ROLE_CONFUSION",
            }
        ),
        "warnings": list(warnings or []),
        "passed": passed,
        "spatial_relevant_role_counts": (
            spatial_df.get("evidence_report_role", pd.Series(dtype=str)).astype(str).value_counts().to_dict()
            if not spatial_df.empty and "evidence_report_role" in spatial_df.columns
            else {}
        ),
        "excluded_role_counts": (
            excluded_df.get("evidence_report_role", pd.Series(dtype=str)).astype(str).value_counts().to_dict()
            if not excluded_df.empty and "evidence_report_role" in excluded_df.columns
            else {}
        ),
        "RAI_components": [_rai_components(cell) for cell in cells],
        "GRS_components": [_grs_components(cell) for cell in cells],
        "GRCI_components": [_grci_components(cell) for cell in cells],
    }


def _rai_components(cell) -> dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "cell_role": cell.cell_role,
        "stop_ratio": cell.stop_ratio,
        "abnormal_ratio": cell.abnormal_ratio,
        "speed_drop_score": cell.speed_drop_score,
        "torque_volatility_score": cell.torque_volatility_score,
        "speed_volatility_score": cell.speed_volatility_score,
        "stop_component": cell.stop_component,
        "abnormal_component": cell.abnormal_component,
        "speed_drop_component": cell.speed_drop_component,
        "torque_component": cell.torque_component,
        "speed_volatility_component": cell.speed_volatility_component,
        "dominant_component": cell.dominant_component,
        "RAI": cell.RAI,
        "RAI_formula_text": cell.RAI_formula_text,
        "stop_reason_available": cell.stop_reason_available,
        "planned_stop_distinguishable": cell.planned_stop_distinguishable,
        "stop_interpretation_warning": cell.stop_interpretation_warning,
    }


def _grs_components(cell) -> dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "cell_role": cell.cell_role,
        "grade_score_component": cell.grade_score_component,
        "hazard_component": cell.hazard_component,
        "confidence_component": cell.confidence_component,
        "GRS_geo_base": cell.GRS_geo_base,
        "GRS_formula_text": cell.GRS_formula_text,
        "GRS_component_method": cell.GRS_component_method,
        "GRS_available": cell.GRS_available,
        "GRS_unavailable_reason": cell.GRS_unavailable_reason,
        "main_hazards": cell.main_hazards,
        "hazard_scores": cell.hazard_scores,
        "confidence_score": cell.confidence_score,
        "source_trace": cell.source_trace,
    }


def _grci_components(cell) -> dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "cell_role": cell.cell_role,
        "GRS_geo_base": cell.GRS_geo_base,
        "RAI": cell.RAI,
        "grs_term": cell.grs_term,
        "rai_term": cell.rai_term,
        "interaction_term": cell.interaction_term,
        "GRCI": cell.GRCI,
        "GRCI_available": cell.GRCI_available,
        "GRCI_unavailable_reason": cell.GRCI_unavailable_reason,
        "coupling_level": cell.coupling_level,
        "GRCI_formula_text": cell.GRCI_formula_text,
    }


def _with_forward_attention_cells(forward_profile: dict[str, Any], construction_state_cells: list) -> dict[str, Any]:
    profile = dict(forward_profile) if isinstance(forward_profile, dict) else {"profile": forward_profile}
    profile["forward_attention_cells"] = [
        cell.model_dump(
            include={
                "cell_id",
                "cell_start",
                "cell_end",
                "cell_center",
                "fused_grade",
                "main_hazards",
                "hazard_scores",
                "confidence_score",
                "uncertainty_level",
                "conflict_level",
                "GRS_geo_base",
                "grade_score_component",
                "hazard_component",
                "confidence_component",
                "GRS_formula_text",
                "GRS_component_method",
                "GRS_available",
                "GRS_unavailable_reason",
                "supporting_evidence_ids",
                "evidence_overlap_length",
                "evidence_overlap_ratio",
                "max_overlap_ratio",
                "mean_overlap_ratio",
                "total_overlap_length",
                "evidence_count",
                "evidence_ids",
                "source_type_distribution",
                "evidence_confidence",
                "evidence_confidence_method",
                "trace_completeness",
                "trace_completeness_method",
                "manual_review_status",
                "source_reliability",
                "source_reliability_method",
                "source_trace",
                "is_current_face_cell",
                "is_forward_cell",
                "distance_to_face_m",
                "forward_distance_band",
                "forward_distance_weight",
                "cell_role",
                "trace_refs",
            }
        )
        for cell in construction_state_cells
        if getattr(cell, "cell_role", None) == "forward_attention"
    ]
    return profile


def _df(value: Any) -> pd.DataFrame:
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number):
        return None
    return number


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _min(values: list[float]) -> float | None:
    if not values:
        return None
    return float(min(values))
