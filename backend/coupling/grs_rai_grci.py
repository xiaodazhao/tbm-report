from __future__ import annotations

import ast
import json
from typing import Any

import pandas as pd

from pipeline.evidence_scope import role_for_cell
from schemas.pipeline import ConstructionStateCell

RAI_FORMULA_TEXT = (
    "RAI = 0.40 * stop_ratio + 0.25 * abnormal_ratio "
    "+ 0.20 * speed_drop_score + 0.10 * torque_volatility_score "
    "+ 0.05 * speed_volatility_score"
)
GRCI_FORMULA_TEXT = "GRCI = 0.55 * GRS_geo_base + 0.35 * RAI + 0.10 * GRS_geo_base * RAI"
STOP_INTERPRETATION_WARNING = (
    "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。"
)


def build_construction_state_cells(
    cells_df: pd.DataFrame,
    cell_response_df: pd.DataFrame,
    geo_states_df: pd.DataFrame,
    cell_evidence_df: pd.DataFrame,
    normalized_evidence_df: pd.DataFrame,
    current_chainage: float | None,
    day_start_chainage: float | None,
    day_end_chainage: float | None,
    lookahead_m: float = 30.0,
    advance_direction: int = 1,
    scope_summary: dict[str, Any] | None = None,
) -> list[ConstructionStateCell]:
    """Build the single cell-level state table used by the main report route."""
    base = _base_cells(cells_df, cell_response_df, geo_states_df)
    if base.empty:
        return []

    response_by_cell = _index_by_cell(cell_response_df)
    geo_by_cell = _index_by_cell(geo_states_df)
    evidence_lookup = _build_evidence_lookup(normalized_evidence_df)
    evidence_by_cell = _group_cell_evidence(cell_evidence_df)
    evidence_summary_by_cell = _summarize_cell_evidence(cell_evidence_df)

    day_min, day_max = _range_bounds(day_start_chainage, day_end_chainage)
    forward_min, forward_max = _forward_bounds(current_chainage, lookahead_m, advance_direction)

    cells: list[ConstructionStateCell] = []
    for _, row in base.sort_values("cell_start").iterrows():
        cell_id = str(row.get("cell_id"))
        response = response_by_cell.get(cell_id, {})
        geo = geo_by_cell.get(cell_id, {})
        cell_start = _num(row.get("cell_start"))
        cell_end = _num(row.get("cell_end"))
        cell_center = _num(row.get("cell_center"))

        has_plc_response = bool(response)
        cell_role = role_for_cell(cell_start, cell_end, scope_summary) if scope_summary else None
        if cell_role is None or cell_role == "outside_report_scope":
            is_excavated_today = _cell_overlaps(cell_start, cell_end, day_min, day_max)
            is_current_face_cell = _is_current_face_cell(cell_start, cell_end, current_chainage)
            is_forward_cell = _is_strict_forward_cell(cell_start, forward_min, forward_max, current_chainage)
            if is_excavated_today:
                cell_role = "daily_review"
            elif is_forward_cell:
                cell_role = "forward_attention"
            else:
                cell_role = "local_background"
        else:
            is_excavated_today = cell_role == "daily_review"
            is_forward_cell = cell_role == "forward_attention"
            is_current_face_cell = _is_current_face_cell(cell_start, cell_end, current_chainage)

        evidence_ids = _list_value(geo.get("supporting_evidence_ids"))
        if not evidence_ids:
            evidence_ids = evidence_by_cell.get(cell_id, [])
        evidence_summary = evidence_summary_by_cell.get(cell_id, {})

        grs = _first_num(geo, ["GRS_geo_base", "GRS", "geo_risk_score", "GRS_base"])
        grade_score_component = _num(geo.get("grade_score_component"))
        hazard_component = _num(geo.get("hazard_component"))
        confidence_component = _num(geo.get("confidence_component"))
        grs_formula_text = _text(geo.get("GRS_formula_text")) or (
            "GRS = 0.45 * grade_score_component + 0.45 * hazard_component + 0.10 * confidence_component"
        )
        grs_component_method = _text(geo.get("GRS_component_method")) or "unavailable"
        raw_rai = _first_num(response, ["RAI", "response_anomaly_index", "abnormal_score"])
        rai = raw_rai if cell_role == "daily_review" else None
        has_geology_evidence = bool(evidence_ids) or bool(geo.get("has_geology_evidence"))
        grs_available = bool(has_geology_evidence and grs is not None and grs_component_method != "empty")
        grs_unavailable_reason = None if grs_available else "missing_spatial_relevant_geology_evidence"
        grci, grci_source, grci_unavailable_reason = compute_cell_grci(
            grs if grs_available else None,
            rai,
            has_plc_response=has_plc_response and cell_role == "daily_review",
        )
        grci_available = grci is not None
        coupling_level = classify_grci(grci) if grci_available else "unavailable"

        source_trace = _source_trace_for_ids(evidence_ids, evidence_lookup)
        trace_refs = [str(item.get("evidence_id")) for item in source_trace if item.get("evidence_id")]
        trace_completeness = _trace_completeness(source_trace, evidence_ids)
        distance_to_face = _distance_to_face(cell_center, current_chainage, advance_direction)
        forward_band, forward_weight = _forward_distance_band(distance_to_face) if cell_role == "forward_attention" else (None, None)

        main_hazards = _list_value(geo.get("main_hazards"))
        hazard_scores = _dict_float_value(geo.get("hazard_scores"))
        grs_term, rai_term, interaction_term = _grci_terms(grs if grs_available else None, rai)
        cell = ConstructionStateCell(
            cell_id=cell_id,
            cell_start=cell_start,
            cell_end=cell_end,
            cell_center=cell_center,
            operation_state=_text(response.get("operation_state")),
            plc_metrics=_response_metrics(response),
            speed_mean=_num(response.get("speed_mean")),
            thrust_mean=_num(response.get("thrust_mean")),
            torque_mean=_num(response.get("torque_mean")),
            stop_duration_min=_num(response.get("stop_duration_min")),
            abnormal_score=_num(response.get("abnormal_score")),
            RAI=rai,
            stop_ratio=_num(response.get("stop_ratio")),
            abnormal_ratio=_num(response.get("abnormal_ratio")),
            speed_drop_score=_num(response.get("speed_drop_score")),
            torque_volatility_score=_num(response.get("torque_volatility_score")),
            speed_volatility_score=_num(response.get("speed_volatility_score")),
            stop_component=_num(response.get("stop_component")),
            abnormal_component=_num(response.get("abnormal_component")),
            speed_drop_component=_num(response.get("speed_drop_component")),
            torque_component=_num(response.get("torque_component")),
            speed_volatility_component=_num(response.get("speed_volatility_component")),
            dominant_component=_text(response.get("dominant_component")),
            RAI_formula_text=_text(response.get("RAI_formula_text")) or (RAI_FORMULA_TEXT if has_plc_response else None),
            stop_reason_available=bool(response.get("stop_reason_available", False)),
            planned_stop_distinguishable=bool(response.get("planned_stop_distinguishable", False)),
            stop_interpretation_warning=_text(response.get("stop_interpretation_warning")) or (
                STOP_INTERPRETATION_WARNING if has_plc_response else None
            ),
            geology_evidence_ids=evidence_ids,
            supporting_evidence_ids=evidence_ids,
            source_trace=source_trace,
            evidence_overlap_length=_num(evidence_summary.get("total_overlap_length")),
            evidence_overlap_ratio=_num(evidence_summary.get("max_overlap_ratio")),
            max_overlap_ratio=_num(evidence_summary.get("max_overlap_ratio")),
            mean_overlap_ratio=_num(evidence_summary.get("mean_overlap_ratio")),
            total_overlap_length=_num(evidence_summary.get("total_overlap_length")),
            evidence_count=int(evidence_summary.get("evidence_count") or len(evidence_ids)),
            evidence_ids=evidence_ids,
            source_type_distribution=evidence_summary.get("source_type_distribution") or {},
            evidence_confidence=_num(evidence_summary.get("evidence_confidence")),
            evidence_confidence_method=_text(evidence_summary.get("evidence_confidence_method")) or "unavailable",
            trace_completeness=trace_completeness,
            trace_completeness_method="heuristic_by_trace_fields" if trace_completeness is not None else "unavailable",
            manual_review_status=_text(evidence_summary.get("manual_review_status")),
            source_reliability=_num(evidence_summary.get("source_reliability")),
            source_reliability_method=_text(evidence_summary.get("source_reliability_method")) or "unavailable",
            fused_grade=_text(geo.get("fused_grade")),
            main_hazards=main_hazards,
            hazard_scores=hazard_scores,
            confidence_score=_num(geo.get("confidence_score")),
            uncertainty_level=_text(geo.get("uncertainty_level")),
            conflict_level=_text(geo.get("conflict_level")),
            GRS_geo_base=grs,
            grade_score_component=grade_score_component,
            hazard_component=hazard_component,
            confidence_component=confidence_component,
            GRS_formula_text=grs_formula_text if grs_available else None,
            GRS_component_method=grs_component_method if grs_available else "unavailable",
            GRS_available=grs_available,
            GRS_unavailable_reason=grs_unavailable_reason,
            GRCI=grci,
            GRCI_available=grci_available,
            GRCI_source=grci_source,
            GRCI_unavailable_reason=grci_unavailable_reason,
            grs_term=grs_term,
            rai_term=rai_term,
            interaction_term=interaction_term,
            GRCI_formula_text=GRCI_FORMULA_TEXT if grci_available else None,
            coupling_level=coupling_level,
            coupling_explanation=explain_coupling(
                grs,
                rai,
                grci,
                coupling_level,
                main_hazards,
                unavailable_reason=grci_unavailable_reason,
            ),
            has_plc_response=has_plc_response,
            has_geology_evidence=has_geology_evidence,
            is_excavated_today=is_excavated_today,
            is_current_face_cell=is_current_face_cell,
            is_forward_cell=is_forward_cell,
            distance_to_face_m=distance_to_face,
            forward_distance_band=forward_band,
            forward_distance_weight=forward_weight,
            cell_role=cell_role,
            used_in_evidence_pack=False,
            trace_refs=trace_refs,
        )
        cells.append(cell)

    return cells


def compute_cell_grci(
    grs: float | None,
    rai: float | None,
    *,
    has_plc_response: bool = True,
) -> tuple[float | None, str, str | None]:
    """Compute one cell-level geology-response coupling index."""
    if not has_plc_response or rai is None:
        return None, "unavailable", "missing_plc_response"
    if grs is None:
        return None, "unavailable", "missing_geology_evidence"
    g = _bounded(grs or 0.0)
    r = _bounded(rai or 0.0)
    return round(_bounded(0.55 * g + 0.35 * r + 0.10 * g * r), 4), "cell_grs_rai_formula_v1", None


def _grci_terms(grs: float | None, rai: float | None) -> tuple[float | None, float | None, float | None]:
    if grs is None or rai is None:
        return None, None, None
    g = _bounded(grs)
    r = _bounded(rai)
    return 0.55 * g, 0.35 * r, 0.10 * g * r


def classify_grci(grci: float | None) -> str:
    if grci is None:
        return "unknown"
    if grci >= 0.75:
        return "high"
    if grci >= 0.50:
        return "medium"
    if grci >= 0.25:
        return "low"
    return "none"


def explain_coupling(
    grs: float | None,
    rai: float | None,
    grci: float | None,
    level: str,
    hazards: list[str],
    unavailable_reason: str | None = None,
) -> str:
    hazard_text = "、".join(hazards[:3]) if hazards else "未识别明确主控地质标签"
    if grci is None:
        if unavailable_reason == "missing_plc_response":
            return "该里程单元缺少当日 PLC 施工响应证据，暂不计算地质-施工响应耦合关注度。"
        if unavailable_reason == "missing_geology_evidence":
            return "该里程单元缺少可用地质证据，暂不计算地质-施工响应耦合关注度。"
        return "该 cell 缺少可用 GRS/RAI 输入，未形成耦合关注度。"
    return (
        f"GRS={grs if grs is not None else 0:.2f}，RAI={rai if rai is not None else 0:.2f}，"
        f"GRCI={grci:.2f}，耦合等级={level}；主要地质关注：{hazard_text}。"
    )


def high_grci_cells(cells: list[ConstructionStateCell], limit: int = 10) -> list[dict[str, Any]]:
    """Legacy-compatible alias for top daily review cells by available GRCI."""
    return review_cells(cells, limit=limit)


def review_cells(cells: list[ConstructionStateCell], limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(
        [
            cell
            for cell in cells
            if cell.GRCI_available
            and cell.GRCI is not None
            and _is_daily_review_cell(cell)
            and cell.is_excavated_today
            and not cell.is_forward_cell
        ],
        key=lambda cell: cell.GRCI or 0.0,
        reverse=True,
    )
    return [
        cell.model_dump(
            include={
                "cell_id",
                "cell_start",
                "cell_end",
                "cell_center",
                "GRS_geo_base",
                "grade_score_component",
                "hazard_component",
                "confidence_component",
                "GRS_formula_text",
                "GRS_component_method",
                "GRS_available",
                "GRS_unavailable_reason",
                "RAI",
                "stop_ratio",
                "abnormal_ratio",
                "speed_drop_score",
                "torque_volatility_score",
                "speed_volatility_score",
                "stop_component",
                "abnormal_component",
                "speed_drop_component",
                "torque_component",
                "speed_volatility_component",
                "dominant_component",
                "RAI_formula_text",
                "stop_reason_available",
                "planned_stop_distinguishable",
                "stop_interpretation_warning",
                "GRCI",
                "GRCI_available",
                "GRCI_source",
                "GRCI_unavailable_reason",
                "grs_term",
                "rai_term",
                "interaction_term",
                "GRCI_formula_text",
                "coupling_level",
                "main_hazards",
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
                "coupling_explanation",
                "has_plc_response",
                "has_geology_evidence",
                "is_excavated_today",
                "is_current_face_cell",
                "is_forward_cell",
                "distance_to_face_m",
                "forward_distance_band",
                "forward_distance_weight",
                "cell_role",
            }
        )
        for cell in ranked[: max(limit, 0)]
    ]


def priority_cell_groups(cells: list[ConstructionStateCell]) -> dict[str, list[dict[str, Any]]]:
    reviews = review_cells(cells, limit=len(cells))
    return {
        "review_cells": reviews,
        "high_priority_cells": [cell for cell in reviews if _num(cell.get("GRCI")) is not None and _num(cell.get("GRCI")) >= 0.75],
        "medium_priority_cells": [
            cell for cell in reviews
            if _num(cell.get("GRCI")) is not None and 0.50 <= _num(cell.get("GRCI")) < 0.75
        ],
        "low_priority_cells": [
            cell for cell in reviews
            if _num(cell.get("GRCI")) is not None and 0.25 <= _num(cell.get("GRCI")) < 0.50
        ],
    }


def _is_daily_review_cell(cell: ConstructionStateCell) -> bool:
    return cell.cell_role == "daily_review" or (
        cell.cell_role == "outside_report_scope"
        and cell.is_excavated_today
        and not cell.is_forward_cell
    )


def _base_cells(cells_df: pd.DataFrame, cell_response_df: pd.DataFrame, geo_states_df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for df in [cells_df, cell_response_df, geo_states_df]:
        if isinstance(df, pd.DataFrame) and not df.empty and "cell_id" in df.columns:
            cols = [col for col in ["cell_id", "cell_start", "cell_end", "cell_center"] if col in df.columns]
            frames.append(df[cols].copy())
    if not frames:
        return pd.DataFrame()
    base = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["cell_id"], keep="first")
    for col in ["cell_start", "cell_end", "cell_center"]:
        if col not in base.columns:
            base[col] = None
    return base


def _index_by_cell(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if not isinstance(df, pd.DataFrame) or df.empty or "cell_id" not in df.columns:
        return {}
    return {
        str(row.get("cell_id")): row.to_dict()
        for _, row in df.drop_duplicates(subset=["cell_id"], keep="first").iterrows()
    }


def _group_cell_evidence(cell_evidence_df: pd.DataFrame) -> dict[str, list[str]]:
    if not isinstance(cell_evidence_df, pd.DataFrame) or cell_evidence_df.empty:
        return {}
    if "cell_id" not in cell_evidence_df.columns or "evidence_id" not in cell_evidence_df.columns:
        return {}
    out: dict[str, list[str]] = {}
    for cell_id, group in cell_evidence_df.groupby("cell_id"):
        ids = [str(value) for value in group["evidence_id"].dropna().tolist()]
        out[str(cell_id)] = list(dict.fromkeys(ids))
    return out


def _summarize_cell_evidence(cell_evidence_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if not isinstance(cell_evidence_df, pd.DataFrame) or cell_evidence_df.empty or "cell_id" not in cell_evidence_df.columns:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for cell_id, group in cell_evidence_df.groupby("cell_id"):
        evidence_ids = [str(value) for value in group.get("evidence_id", pd.Series(dtype=str)).dropna().tolist()]
        source_types = [str(value) for value in group.get("source_type_norm", pd.Series(dtype=str)).dropna().tolist()]
        overlap_lengths = pd.to_numeric(group.get("evidence_overlap_length"), errors="coerce") if "evidence_overlap_length" in group.columns else pd.Series(dtype=float)
        overlap_ratios = pd.to_numeric(group.get("evidence_overlap_ratio"), errors="coerce") if "evidence_overlap_ratio" in group.columns else pd.Series(dtype=float)
        reliabilities = pd.to_numeric(group.get("source_reliability"), errors="coerce") if "source_reliability" in group.columns else pd.Series(dtype=float)
        confidences = pd.to_numeric(group.get("evidence_confidence"), errors="coerce") if "evidence_confidence" in group.columns else pd.Series(dtype=float)
        out[str(cell_id)] = {
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "evidence_count": len(set(evidence_ids)),
            "source_type_distribution": {key: source_types.count(key) for key in sorted(set(source_types))},
            "total_overlap_length": _series_sum(overlap_lengths),
            "max_overlap_ratio": _series_max(overlap_ratios),
            "mean_overlap_ratio": _series_mean(overlap_ratios),
            "source_reliability": _series_mean(reliabilities),
            "source_reliability_method": "mean_projected_source_reliability" if not reliabilities.dropna().empty else "unavailable",
            "evidence_confidence": _series_mean(confidences),
            "evidence_confidence_method": "mean_projected_evidence_confidence" if not confidences.dropna().empty else "unavailable",
            "manual_review_status": _first_text(group, ["manual_review_status"]),
        }
    return out


def _build_evidence_lookup(normalized_evidence_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if not isinstance(normalized_evidence_df, pd.DataFrame) or normalized_evidence_df.empty:
        return {}
    if "evidence_id" not in normalized_evidence_df.columns:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in normalized_evidence_df.iterrows():
        evidence_id = _text(row.get("evidence_id"))
        if evidence_id:
            lookup[evidence_id] = row.to_dict()
    return lookup


def _source_trace_for_ids(evidence_ids: list[str], evidence_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    traces = []
    for evidence_id in evidence_ids[:20]:
        row = evidence_lookup.get(str(evidence_id), {})
        traces.append(
            {
                "evidence_id": str(evidence_id),
                "report_id": _text(row.get("report_id")),
                "source_type": _text(row.get("source_type_norm") or row.get("source_type")),
                "evidence_role": _text(row.get("evidence_role")),
                "evidence_report_role": _text(row.get("evidence_report_role")),
                "spatial_type": _text(row.get("spatial_type")),
                "start_chainage": _num(row.get("start_chainage") or row.get("start_num")),
                "end_chainage": _num(row.get("end_chainage") or row.get("end_num")),
                "evidence_confidence": _num(row.get("evidence_confidence") or row.get("confidence")),
                "evidence_confidence_method": _text(row.get("evidence_confidence_method")) or ("source_field" if _num(row.get("confidence")) is not None else "unavailable"),
                "manual_review_status": _text(row.get("manual_review_status")),
                "source_reliability": _num(row.get("source_reliability")),
                "source_reliability_method": _text(row.get("source_reliability_method")) or ("source_field" if _num(row.get("source_reliability")) is not None else "unavailable"),
                "raw_text_excerpt": _excerpt(row.get("raw_text") or row.get("text") or row.get("description")),
            }
        )
    return traces


def _trace_completeness(source_trace: list[dict[str, Any]], evidence_ids: list[str]) -> float | None:
    if not evidence_ids:
        return None
    if not source_trace:
        return 0.0
    scores = []
    for trace in source_trace:
        has_id = bool(trace.get("evidence_id"))
        has_source = bool(trace.get("source_type"))
        has_chainage = trace.get("start_chainage") is not None or trace.get("end_chainage") is not None
        has_trace_text = bool(trace.get("raw_text_excerpt") or trace.get("report_id"))
        if has_id and has_source and has_chainage and has_trace_text:
            scores.append(1.0)
        elif has_id and has_chainage:
            scores.append(0.7)
        elif has_trace_text or has_source:
            scores.append(0.4)
        else:
            scores.append(0.0)
    return sum(scores) / len(scores) if scores else 0.0


def _distance_to_face(cell_center: float | None, current_chainage: float | None, direction: int) -> float | None:
    center = _num(cell_center)
    current = _num(current_chainage)
    if center is None or current is None:
        return None
    sign = 1 if float(direction or 1) >= 0 else -1
    return float((center - current) * sign)


def _forward_distance_band(distance_to_face_m: float | None) -> tuple[str, float | None]:
    distance = _num(distance_to_face_m)
    if distance is None:
        return "unknown", None
    if 0.0 <= distance <= 10.0:
        return "near_forward", 1.0
    if 10.0 < distance <= 20.0:
        return "short_forward", 0.7
    if 20.0 < distance <= 30.0:
        return "extended_forward", 0.4
    return "outside_forward_window", None


def _response_metrics(response: dict[str, Any]) -> dict[str, Any]:
    metrics = response.get("response_metrics")
    if isinstance(metrics, dict):
        out = dict(metrics)
    else:
        out = {}
    for key in [
        "sample_count",
        "duration_min",
        "work_duration_min",
        "stop_duration_min",
        "abnormal_duration_min",
        "stop_ratio",
        "abnormal_ratio",
        "speed_drop_score",
        "torque_volatility_score",
        "speed_volatility_score",
        "stop_component",
        "abnormal_component",
        "speed_drop_component",
        "torque_component",
        "speed_volatility_component",
        "working_sample_count",
        "working_ratio",
        "working_speed_cv",
        "working_thrust_cv",
        "working_torque_cv",
        "penetration_mean",
        "cutterhead_power_proxy",
        "thrust_per_penetration",
        "torque_per_penetration",
        "raw_sample_count",
        "shutdown_sample_count",
        "outlier_sample_count",
        "working_sample_count_paper",
        "steady_sample_count",
        "steady_ratio",
        "steady_to_working_ratio",
        "steady_speed_mean",
        "steady_speed_std",
        "steady_speed_cv",
        "steady_thrust_mean",
        "steady_thrust_std",
        "steady_thrust_cv",
        "steady_torque_mean",
        "steady_torque_std",
        "steady_torque_cv",
        "steady_rpm_mean",
        "steady_rpm_std",
        "steady_rpm_cv",
        "steady_penetration_mean",
        "steady_penetration_std",
        "steady_penetration_cv",
        "steady_cutterhead_power_proxy",
        "steady_thrust_per_penetration",
        "steady_torque_per_penetration",
        "steady_threshold_value",
        "steady_median_signal_value",
        "steady_candidate_segment_count",
        "RAI",
    ]:
        if key in response:
            out[key] = _num(response.get(key))
    for key in [
        "dominant_component",
        "RAI_formula_text",
        "stop_interpretation_warning",
        "working_metrics_source",
        "steady_state_fallback_reason",
        "steady_detection_signal",
        "plc_preprocessing_quality_grade",
        "plc_preprocessing_quality_reason",
        "plc_preprocessing_method",
        "plc_preprocessing_boundary",
    ]:
        if key in response:
            out[key] = _text(response.get(key))
    for key in [
        "stop_reason_available",
        "planned_stop_distinguishable",
        "insufficient_working_samples",
        "steady_state_available",
        "steady_state_fallback_used",
    ]:
        if key in response:
            out[key] = bool(response.get(key))
    return {key: value for key, value in out.items() if value is not None}


def _range_bounds(start: float | None, end: float | None) -> tuple[float | None, float | None]:
    if start is None or end is None:
        return None, None
    a = _num(start)
    b = _num(end)
    if a is None or b is None:
        return None, None
    return min(a, b), max(a, b)


def _forward_bounds(current: float | None, lookahead_m: float, direction: int) -> tuple[float | None, float | None]:
    if current is None:
        return None, None
    center = _num(current)
    if center is None:
        return None, None
    end = center + (1 if direction >= 0 else -1) * float(lookahead_m)
    return min(center, end), max(center, end)


def _cell_overlaps(cell_start: float | None, cell_end: float | None, start: float | None, end: float | None) -> bool:
    if cell_start is None or cell_end is None or start is None or end is None:
        return False
    return max(cell_start, start) < min(cell_end, end)


def _is_current_face_cell(cell_start: float | None, cell_end: float | None, current_chainage: float | None) -> bool:
    current = _num(current_chainage)
    if cell_start is None or cell_end is None or current is None:
        return False
    return cell_start <= current < cell_end


def _is_strict_forward_cell(
    cell_start: float | None,
    forward_min: float | None,
    forward_max: float | None,
    current_chainage: float | None,
) -> bool:
    current = _num(current_chainage)
    if cell_start is None or forward_min is None or forward_max is None or current is None:
        return False
    return cell_start >= current and forward_min <= cell_start < forward_max


def _list_value(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return _list_value(parsed)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(text)
            return _list_value(parsed)
        except Exception:
            pass
        return [item.strip() for item in text.split(",") if item.strip()]
    return [str(value)]


def _dict_float_value(value: Any) -> dict[str, float]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            try:
                value = ast.literal_eval(value)
            except Exception:
                value = {}
    if not isinstance(value, dict):
        return {}
    out = {}
    for key, item in value.items():
        number = _num(item)
        if number is not None:
            out[str(key)] = number
    return out


def _first_num(row: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        number = _num(row.get(key))
        if number is not None:
            return _bounded(number)
    return None


def _series_mean(series: pd.Series) -> float | None:
    if series is None:
        return None
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.mean())


def _series_max(series: pd.Series) -> float | None:
    if series is None:
        return None
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.max())


def _series_sum(series: pd.Series) -> float | None:
    if series is None:
        return None
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.sum())


def _first_text(frame: pd.DataFrame, keys: list[str]) -> str | None:
    for key in keys:
        if key in frame.columns:
            for value in frame[key].dropna().tolist():
                text = _text(value)
                if text:
                    return text
    return None


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number):
        return None
    return number


def _bounded(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _excerpt(value: Any, limit: int = 180) -> str | None:
    text = _text(value)
    if not text:
        return None
    text = " ".join(text.split())
    return text[:limit]
