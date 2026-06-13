from __future__ import annotations

import math
from typing import Any

import pandas as pd


DEFAULT_LOCAL_BACKGROUND_BACK_M = 100.0


def build_scope_summary(
    *,
    date: str,
    current_chainage: float | None,
    day_start_chainage: float | None,
    day_end_chainage: float | None,
    cell_length: float = 10.0,
    lookahead_m: float = 30.0,
    advance_direction: int = 1,
    local_background_back_m: float = DEFAULT_LOCAL_BACKGROUND_BACK_M,
) -> dict[str, Any]:
    """Build the report-local chainage scope used by the daily report pipeline."""
    cell = max(float(cell_length or 10.0), 1e-6)
    direction = 1 if float(advance_direction or 1) >= 0 else -1

    daily_min, daily_max = _bounds(day_start_chainage, day_end_chainage)
    current = _num(current_chainage)
    if current is None:
        current = daily_max

    daily_start = _floor_to_cell(daily_min, cell) if daily_min is not None else None
    daily_end = _ceil_to_cell(daily_max, cell) if daily_max is not None else None

    forward_start = None
    forward_end = None
    if current is not None:
        raw_forward_end = current + direction * float(lookahead_m or 0.0)
        f_min, f_max = min(current, raw_forward_end), max(current, raw_forward_end)
        if direction >= 0:
            forward_start = _ceil_to_cell(f_min, cell)
            forward_end = _ceil_to_cell(f_max, cell)
        else:
            forward_start = _floor_to_cell(f_min, cell)
            forward_end = _floor_to_cell(f_max, cell)
            forward_start, forward_end = min(forward_start, forward_end), max(forward_start, forward_end)

    background_start = None
    background_end = None
    if current is not None and daily_start is not None and local_background_back_m and local_background_back_m > 0:
        raw_background_start = current - direction * float(local_background_back_m)
        if direction >= 0:
            background_start = _floor_to_cell(raw_background_start, cell)
            background_end = daily_start
        else:
            background_start = daily_end
            background_end = _ceil_to_cell(raw_background_start, cell)
        background_start, background_end = min(background_start, background_end), max(background_start, background_end)
        if background_start == background_end:
            background_start = None
            background_end = None

    starts = [v for v in [background_start, daily_start, forward_start] if v is not None]
    ends = [v for v in [background_end, daily_end, forward_end] if v is not None]
    report_start = min(starts) if starts else None
    report_end = max(ends) if ends else None

    daily_advance = None
    if daily_min is not None and daily_max is not None:
        daily_advance = daily_max - daily_min

    return {
        "date": date,
        "cell_length_m": cell,
        "lookahead_m": float(lookahead_m or 0.0),
        "local_background_back_m": float(local_background_back_m or 0.0),
        "daily_chainage_min": daily_min,
        "daily_chainage_max": daily_max,
        "daily_advance_m": daily_advance,
        "current_chainage": current,
        "daily_excavated_scope": {"start": daily_start, "end": daily_end},
        "forward_scope": {"start": forward_start, "end": forward_end},
        "local_background_scope": {"start": background_start, "end": background_end},
        "report_scope": {"start": report_start, "end": report_end},
        "cell_scope_mode": "time_valid_and_spatial_relevant_report_scope",
    }


def apply_spatial_relevance_filter(
    normalized_df: pd.DataFrame,
    scope_summary: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Annotate time-valid evidence with report-local spatial relevance and split it."""
    if normalized_df is None or normalized_df.empty:
        empty = pd.DataFrame()
        summary = _scope_count_summary(scope_summary, 0, 0, 0, 0)
        return empty, empty, summary

    out = normalized_df.copy()
    out["time_valid"] = True
    out["time_invalid_reason"] = None

    rows = []
    for _, row in out.iterrows():
        rows.append(_classify_evidence_row(row, scope_summary))
    anno = pd.DataFrame(rows, index=out.index)
    out = pd.concat([out, anno], axis=1)

    spatial = out[out["spatial_relevant"].fillna(False).astype(bool)].copy()
    excluded = out[~out["spatial_relevant"].fillna(False).astype(bool)].copy()
    summary = _scope_count_summary(
        scope_summary,
        time_valid_count=len(out),
        spatial_count=len(spatial),
        excluded_distance_count=int((excluded.get("evidence_report_role") == "excluded_by_distance").sum()) if not excluded.empty else 0,
        excluded_missing_count=int((excluded.get("evidence_report_role") == "excluded_by_missing_geometry").sum()) if not excluded.empty else 0,
    )
    return spatial, excluded, summary


def build_scope_cells(scope_summary: dict[str, Any]) -> pd.DataFrame:
    """Build 10 m cells strictly within the report scope."""
    scope = scope_summary.get("report_scope") or {}
    start = _num(scope.get("start"))
    end = _num(scope.get("end"))
    cell_length = float(scope_summary.get("cell_length_m") or 10.0)
    if start is None or end is None or end <= start:
        return pd.DataFrame(columns=["cell_id", "cell_start", "cell_end", "cell_center", "cell_length"])

    rows = []
    current = float(start)
    while current < float(end) - 1e-9:
        cell_start = current
        cell_end = current + cell_length
        rows.append(
            {
                "cell_id": f"cell_{_number_key(cell_start)}_{_number_key(cell_end)}",
                "cell_start": cell_start,
                "cell_end": cell_end,
                "cell_center": (cell_start + cell_end) / 2.0,
                "cell_length": cell_length,
            }
        )
        current += cell_length
    return pd.DataFrame(rows)


def role_for_cell(cell_start: float | None, cell_end: float | None, scope_summary: dict[str, Any]) -> str:
    daily = scope_summary.get("daily_excavated_scope") or {}
    forward = scope_summary.get("forward_scope") or {}
    background = scope_summary.get("local_background_scope") or {}
    if _overlaps(cell_start, cell_end, daily.get("start"), daily.get("end")):
        return "daily_review"
    if _overlaps(cell_start, cell_end, forward.get("start"), forward.get("end")):
        return "forward_attention"
    if _overlaps(cell_start, cell_end, background.get("start"), background.get("end")):
        return "local_background"
    return "outside_report_scope"


def _classify_evidence_row(row: pd.Series, scope_summary: dict[str, Any]) -> dict[str, Any]:
    ev_start, ev_end = _evidence_interval(row)
    current = _num(scope_summary.get("current_chainage"))
    daily = scope_summary.get("daily_excavated_scope") or {}
    forward = scope_summary.get("forward_scope") or {}
    background = scope_summary.get("local_background_scope") or {}
    report = scope_summary.get("report_scope") or {}

    if ev_start is None or ev_end is None:
        return {
            "spatial_relevant": False,
            "spatial_invalid_reason": "missing_geometry",
            "overlap_daily_excavated_scope": False,
            "overlap_forward_scope": False,
            "overlap_local_background_scope": False,
            "overlap_report_scope": False,
            "distance_to_current_chainage": None,
            "distance_to_daily_range": None,
            "evidence_report_role": "excluded_by_missing_geometry",
        }

    overlap_daily = _overlaps(ev_start, ev_end, daily.get("start"), daily.get("end"))
    overlap_forward = _overlaps(ev_start, ev_end, forward.get("start"), forward.get("end"))
    overlap_background = _overlaps(ev_start, ev_end, background.get("start"), background.get("end"))
    overlap_report = _overlaps(ev_start, ev_end, report.get("start"), report.get("end"))

    if overlap_daily:
        role = "daily_review_evidence"
    elif overlap_forward:
        role = "forward_attention_evidence"
    elif overlap_background:
        role = "local_background_evidence"
    elif overlap_report:
        role = "local_background_evidence"
    else:
        role = "excluded_by_distance"

    spatial_relevant = role not in {"excluded_by_distance", "excluded_by_missing_geometry"}
    return {
        "spatial_relevant": spatial_relevant,
        "spatial_invalid_reason": None if spatial_relevant else "outside_report_scope",
        "overlap_daily_excavated_scope": overlap_daily,
        "overlap_forward_scope": overlap_forward,
        "overlap_local_background_scope": overlap_background,
        "overlap_report_scope": overlap_report,
        "distance_to_current_chainage": _distance_to_point(ev_start, ev_end, current),
        "distance_to_daily_range": _distance_to_range(ev_start, ev_end, daily.get("start"), daily.get("end")),
        "evidence_report_role": role,
    }


def _evidence_interval(row: pd.Series) -> tuple[float | None, float | None]:
    start = _first_num(row, ["start_chainage", "start_num"])
    end = _first_num(row, ["end_chainage", "end_num"])
    if start is not None and end is not None:
        return min(start, end), max(start, end)
    point = _first_num(row, ["center_chainage", "face_chainage", "face_num"])
    if point is not None:
        return point, point
    return None, None


def _scope_count_summary(
    scope_summary: dict[str, Any],
    time_valid_count: int,
    spatial_count: int,
    excluded_distance_count: int,
    excluded_missing_count: int,
) -> dict[str, Any]:
    summary = dict(scope_summary)
    summary.update(
        {
            "time_valid_evidence_count": int(time_valid_count),
            "spatial_relevant_evidence_count": int(spatial_count),
            "excluded_by_distance_evidence_count": int(excluded_distance_count),
            "excluded_by_missing_geometry_evidence_count": int(excluded_missing_count),
            "excluded_by_time_evidence_count": 0,
        }
    )
    return summary


def _bounds(a: Any, b: Any) -> tuple[float | None, float | None]:
    x = _num(a)
    y = _num(b)
    if x is None or y is None:
        return None, None
    return min(x, y), max(x, y)


def _first_num(row: pd.Series, keys: list[str]) -> float | None:
    for key in keys:
        if key in row.index:
            value = _num(row.get(key))
            if value is not None:
                return value
    return None


def _overlaps(a_start: Any, a_end: Any, b_start: Any, b_end: Any) -> bool:
    a0 = _num(a_start)
    a1 = _num(a_end)
    b0 = _num(b_start)
    b1 = _num(b_end)
    if a0 is None or a1 is None or b0 is None or b1 is None:
        return False
    a0, a1 = min(a0, a1), max(a0, a1)
    b0, b1 = min(b0, b1), max(b0, b1)
    if a0 == a1:
        return b0 <= a0 < b1
    return max(a0, b0) < min(a1, b1)


def _distance_to_point(start: float, end: float, point: float | None) -> float | None:
    if point is None:
        return None
    if start <= point <= end:
        return 0.0
    return float(min(abs(point - start), abs(point - end)))


def _distance_to_range(start: float, end: float, range_start: Any, range_end: Any) -> float | None:
    b0 = _num(range_start)
    b1 = _num(range_end)
    if b0 is None or b1 is None:
        return None
    b0, b1 = min(b0, b1), max(b0, b1)
    if _overlaps(start, end, b0, b1):
        return 0.0
    if end < b0:
        return float(b0 - end)
    return float(start - b1)


def _floor_to_cell(value: float | None, cell_length: float) -> float | None:
    if value is None:
        return None
    return float(math.floor(float(value) / cell_length) * cell_length)


def _ceil_to_cell(value: float | None, cell_length: float) -> float | None:
    if value is None:
        return None
    return float(math.ceil(float(value) / cell_length) * cell_length)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number) or not math.isfinite(number):
        return None
    return number


def _number_key(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0").rstrip(".")
