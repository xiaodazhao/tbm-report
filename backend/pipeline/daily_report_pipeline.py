from __future__ import annotations

from typing import Any

import pandas as pd

from coupling.grs_rai_grci import build_construction_state_cells, high_grci_cells
from geology_v2.evidence_normalizer import summarize_normalized_evidence
from geology_v2.pipeline import run_geology_v2_context
from llm.evidence_pack import build_prompt_evidence_pack, build_template_report
from llm.llm_api import call_llm_result
from llm.report_prompt import build_prompt
from llm.report_quality_checker import check_report_quality
from llm.report_trace_builder import build_report_trace, summarize_report_trace
from pipeline.inputs import json_safe, load_daily_inputs
from plc.response import analyze_plc_response
from schemas.pipeline import DailyReportResult
from twin.twin_state import build_twin_state


def run_daily_report_pipeline(
    date: str,
    use_llm: bool = True,
    *,
    cell_length: float = 10.0,
    lookahead_m: float = 30.0,
    advance_direction: int = 1,
) -> DailyReportResult:
    """Run the only retained daily TBM report pipeline."""
    warnings: list[str] = []
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

    geology_result = _run_geology_branch(
        df_plc=plc_result.get("df_plc_annotated", inputs.df_plc),
        evidence_df=inputs.evidence_df,
        current_chainage=current_chainage,
        analysis_date=active_date,
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
    )
    high_cells = high_grci_cells(construction_state_cells, limit=10)
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
        quality_evidence=json_safe(plc_result.get("quality_report", {})),
        warnings=warnings,
    )
    prompt_text = build_prompt(prompt_evidence_pack)

    llm_result = call_llm_result(prompt_text) if use_llm else {"ok": False, "text": "", "warnings": ["LLM disabled"]}
    warnings.extend(llm_result.get("warnings", []))
    report_text = llm_result.get("text") if llm_result.get("ok") else build_template_report(prompt_evidence_pack)

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

    quality = check_report_quality(
        report_text,
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
        include_claim_results=True,
    )
    trace = build_report_trace(
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
        twin_state=json_safe(twin_state),
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
                "supporting_evidence_ids",
                "source_trace",
                "is_current_face_cell",
                "is_forward_cell",
                "trace_refs",
            }
        )
        for cell in construction_state_cells
        if getattr(cell, "is_forward_cell", False)
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
