from __future__ import annotations

import ast
import json
from typing import Any

import pandas as pd

from schemas.pipeline import ConstructionStateCell


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
) -> list[ConstructionStateCell]:
    """Build the single cell-level state table used by the main report route."""
    base = _base_cells(cells_df, cell_response_df, geo_states_df)
    if base.empty:
        return []

    response_by_cell = _index_by_cell(cell_response_df)
    geo_by_cell = _index_by_cell(geo_states_df)
    evidence_lookup = _build_evidence_lookup(normalized_evidence_df)
    evidence_by_cell = _group_cell_evidence(cell_evidence_df)

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

        grs = _first_num(geo, ["GRS_geo_base", "GRS", "geo_risk_score", "GRS_base"])
        rai = _first_num(response, ["RAI", "response_anomaly_index", "abnormal_score"])
        has_plc_response = bool(response)
        has_geology_evidence = bool(geo) and (grs is not None or bool(geo.get("has_geology_evidence")))
        grci, grci_source, grci_unavailable_reason = compute_cell_grci(
            grs,
            rai,
            has_plc_response=has_plc_response,
        )
        grci_available = grci is not None
        coupling_level = classify_grci(grci) if grci_available else "unavailable"

        evidence_ids = _list_value(geo.get("supporting_evidence_ids"))
        if not evidence_ids:
            evidence_ids = evidence_by_cell.get(cell_id, [])
        source_trace = _source_trace_for_ids(evidence_ids, evidence_lookup)
        trace_refs = [str(item.get("evidence_id")) for item in source_trace if item.get("evidence_id")]

        main_hazards = _list_value(geo.get("main_hazards"))
        hazard_scores = _dict_float_value(geo.get("hazard_scores"))
        is_excavated_today = _cell_overlaps(cell_start, cell_end, day_min, day_max)
        is_current_face_cell = _is_current_face_cell(cell_start, cell_end, current_chainage)
        is_forward_cell = _is_strict_forward_cell(cell_start, forward_min, forward_max, current_chainage)

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
            geology_evidence_ids=evidence_ids,
            supporting_evidence_ids=evidence_ids,
            source_trace=source_trace,
            fused_grade=_text(geo.get("fused_grade")),
            main_hazards=main_hazards,
            hazard_scores=hazard_scores,
            confidence_score=_num(geo.get("confidence_score")),
            uncertainty_level=_text(geo.get("uncertainty_level")),
            conflict_level=_text(geo.get("conflict_level")),
            GRS_geo_base=grs,
            GRCI=grci,
            GRCI_available=grci_available,
            GRCI_source=grci_source,
            GRCI_unavailable_reason=grci_unavailable_reason,
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
    ranked = sorted(
        [
            cell
            for cell in cells
            if cell.GRCI_available
            and cell.GRCI is not None
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
                "RAI",
                "GRCI",
                "GRCI_available",
                "GRCI_source",
                "GRCI_unavailable_reason",
                "coupling_level",
                "main_hazards",
                "supporting_evidence_ids",
                "coupling_explanation",
                "has_plc_response",
                "has_geology_evidence",
                "is_excavated_today",
                "is_forward_cell",
            }
        )
        for cell in ranked[: max(limit, 0)]
    ]


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
                "spatial_type": _text(row.get("spatial_type")),
                "start_chainage": _num(row.get("start_chainage") or row.get("start_num")),
                "end_chainage": _num(row.get("end_chainage") or row.get("end_num")),
                "raw_text_excerpt": _excerpt(row.get("raw_text") or row.get("text") or row.get("description")),
            }
        )
    return traces


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
    ]:
        if key in response:
            out[key] = _num(response.get(key))
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
