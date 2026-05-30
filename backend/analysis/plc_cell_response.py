"""Build cell-level PLC response summaries without changing core RAI/GRCI logic."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from analysis.dataprocess import annotate_operation_mode, infer_sample_interval_sec
from utils.chainage_utils import format_chainage_range_dk

try:
    from analysis.plc_contract import resolve_plc_columns
except Exception:  # pragma: no cover
    resolve_plc_columns = None


def _safe_float(value: Any) -> float | None:
    """Convert values into finite floats."""
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _clean_json_value(value: Any) -> Any:
    """Recursively clean values for JSON-friendly summaries."""
    if isinstance(value, dict):
        return {str(key): _clean_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return _clean_json_value(value.item())
        except Exception:
            pass
    return value


def _resolve_columns(df: pd.DataFrame, chainage_col: str | None, time_col: str | None) -> tuple[str | None, str | None]:
    """Resolve chainage/time columns with plc_contract fallback."""
    resolved = resolve_plc_columns(df) if callable(resolve_plc_columns) else {}
    resolved_chainage = chainage_col or ("chainage" if "chainage" in df.columns else resolved.get("chainage_col"))
    resolved_time = time_col or resolved.get("time_col") or ("运行时间-time" if "运行时间-time" in df.columns else None)
    return resolved_chainage, resolved_time


def _estimate_duration_min(df: pd.DataFrame, time_col: str | None) -> tuple[pd.Series, list[str]]:
    """Estimate per-row duration minutes from time intervals or sample-count fallback."""
    warnings: list[str] = []
    if "duration_min" in df.columns:
        return pd.to_numeric(df["duration_min"], errors="coerce").fillna(0), warnings
    if "duration_sec" in df.columns:
        return pd.to_numeric(df["duration_sec"], errors="coerce").fillna(0) / 60.0, warnings

    if time_col and time_col in df.columns:
        times = pd.to_datetime(df[time_col], errors="coerce")
        diffs = times.diff().dt.total_seconds()
        sample_interval_sec = infer_sample_interval_sec(df.rename(columns={time_col: "运行时间-time"}), time_col=time_col)
        if sample_interval_sec <= 0:
            valid = diffs[(diffs > 0) & (diffs < 3600)]
            sample_interval_sec = float(valid.median()) if not valid.empty else 0.0
        durations = diffs.shift(-1)
        if sample_interval_sec > 0:
            durations = durations.fillna(sample_interval_sec)
            durations = durations.clip(lower=0, upper=max(sample_interval_sec * 5.0, 3600.0))
            return durations.fillna(0) / 60.0, warnings

    warnings.append("cell_response duration uses sample-count fallback because time interval estimation failed")
    return pd.Series(1.0, index=df.index, dtype=float), warnings


def _build_rai_proxy(row: pd.Series) -> float | None:
    """Build a lightweight PLC-only response anomaly preview score."""
    stop_ratio = _safe_float(row.get("stop_ratio"))
    abnormal_ratio = _safe_float(row.get("abnormal_ratio"))
    torque_std = _safe_float(row.get("torque_std"))
    speed_mean = _safe_float(row.get("speed_mean"))
    thrust_mean = _safe_float(row.get("thrust_mean"))
    torque_mean = _safe_float(row.get("torque_mean"))

    if all(value is None for value in [stop_ratio, abnormal_ratio, torque_std, speed_mean, thrust_mean, torque_mean]):
        return None

    score = 0.0
    score += 0.45 * min(max(stop_ratio or 0.0, 0.0), 1.0)
    score += 0.25 * min(max(abnormal_ratio or 0.0, 0.0), 1.0)
    if torque_std is not None:
        score += 0.15 * min(max(torque_std / 500.0, 0.0), 1.0)
    if speed_mean is not None:
        score += 0.15 * min(max((1.0 - min(max(speed_mean, 0.0), 1.0)), 0.0), 1.0)
    if (
        speed_mean is not None and speed_mean <= 0.05
        and ((thrust_mean or 0.0) > 0 or (torque_mean or 0.0) > 0)
    ):
        score = min(score + 0.15, 1.0)
    return round(min(max(score, 0.0), 1.0), 6)


def _classify_response_type(row: pd.Series) -> str:
    """Classify one cell's PLC response pattern."""
    stop_ratio = _safe_float(row.get("stop_ratio")) or 0.0
    abnormal_ratio = _safe_float(row.get("abnormal_ratio")) or 0.0
    speed_mean = _safe_float(row.get("speed_mean")) or 0.0
    thrust_mean = _safe_float(row.get("thrust_mean")) or 0.0
    torque_mean = _safe_float(row.get("torque_mean")) or 0.0

    if stop_ratio >= 0.45:
        return "stop_dominated"
    if abnormal_ratio >= 0.20:
        return "abnormal_torque"
    if speed_mean <= 0.05 and (thrust_mean > 0 or torque_mean > 0):
        return "high_load_low_speed"
    return "normal_or_unknown"


def build_cell_response_df(
    df: pd.DataFrame,
    cell_length: float = 10.0,
    chainage_col: str | None = None,
    time_col: str | None = None,
) -> pd.DataFrame:
    """Aggregate PLC responses into 10 m cells for structured downstream use."""
    warnings: list[str] = []
    frame = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
    if frame.empty:
        return pd.DataFrame(columns=["warnings"])

    if "operation_mode" not in frame.columns:
        frame = annotate_operation_mode(frame)

    resolved_chainage, resolved_time = _resolve_columns(frame, chainage_col, time_col)
    if resolved_chainage is None or resolved_chainage not in frame.columns:
        return pd.DataFrame([{"warnings": "missing chainage_col"}]).iloc[0:0]

    frame["__chainage"] = pd.to_numeric(frame[resolved_chainage], errors="coerce")
    frame = frame.dropna(subset=["__chainage"]).copy()
    if frame.empty:
        return pd.DataFrame()

    duration_min, duration_warnings = _estimate_duration_min(frame, resolved_time)
    warnings.extend(duration_warnings)
    frame["__duration_min"] = pd.to_numeric(duration_min, errors="coerce").fillna(0)
    frame["cell_start"] = (frame["__chainage"].floordiv(float(cell_length)) * float(cell_length)).astype(float)
    frame["cell_end"] = frame["cell_start"] + float(cell_length)
    frame["cell_center"] = (frame["cell_start"] + frame["cell_end"]) / 2.0
    frame["cell_id"] = frame["cell_start"].map(lambda value: f"cell_{int(value)}_{int(value + float(cell_length))}")

    for source_col, target_col in [
        ("推进速度", "__speed"),
        ("推力", "__thrust"),
        ("刀盘扭矩", "__torque"),
        ("刀盘实际转速", "__rpm"),
    ]:
        if source_col in frame.columns:
            frame[target_col] = pd.to_numeric(frame[source_col], errors="coerce")

    grouped = frame.groupby("cell_id", sort=True)
    rows = []
    for cell_id, group in grouped:
        row: dict[str, Any] = {
            "cell_id": cell_id,
            "cell_start": _safe_float(group["cell_start"].iloc[0]),
            "cell_end": _safe_float(group["cell_end"].iloc[0]),
            "cell_center": _safe_float(group["cell_center"].iloc[0]),
            "range_dk": format_chainage_range_dk(group["cell_start"].iloc[0], group["cell_end"].iloc[0]),
            "sample_count": int(len(group)),
            "work_sample_count": int(group.get("is_working", pd.Series(False, index=group.index)).fillna(False).astype(bool).sum()),
            "stop_sample_count": int(group.get("is_stopped", pd.Series(False, index=group.index)).fillna(False).astype(bool).sum()),
            "transition_sample_count": int(group.get("is_transition", pd.Series(False, index=group.index)).fillna(False).astype(bool).sum()),
            "abnormal_sample_count": int(group.get("is_abnormal", pd.Series(False, index=group.index)).fillna(False).astype(bool).sum()),
        }

        row["work_duration_min"] = _safe_float(group.loc[group.get("is_working", False).fillna(False), "__duration_min"].sum()) if "is_working" in group.columns else 0.0
        row["stop_duration_min"] = _safe_float(group.loc[group.get("is_stopped", False).fillna(False), "__duration_min"].sum()) if "is_stopped" in group.columns else 0.0
        row["transition_duration_min"] = _safe_float(group.loc[group.get("is_transition", False).fillna(False), "__duration_min"].sum()) if "is_transition" in group.columns else 0.0
        row["abnormal_duration_min"] = _safe_float(group.loc[group.get("is_abnormal", False).fillna(False), "__duration_min"].sum()) if "is_abnormal" in group.columns else 0.0

        total_duration = sum(value or 0.0 for value in [
            row["work_duration_min"],
            row["stop_duration_min"],
            row["transition_duration_min"],
            row["abnormal_duration_min"],
        ])
        if total_duration > 0:
            row["work_ratio"] = row["work_duration_min"] / total_duration
            row["stop_ratio"] = row["stop_duration_min"] / total_duration
            row["abnormal_ratio"] = row["abnormal_duration_min"] / total_duration
        else:
            row["work_ratio"] = None
            row["stop_ratio"] = None
            row["abnormal_ratio"] = None

        for source, prefix in [("__speed", "speed"), ("__thrust", "thrust"), ("__torque", "torque"), ("__rpm", "rpm")]:
            if source in group.columns:
                numeric = pd.to_numeric(group[source], errors="coerce")
                row[f"{prefix}_mean"] = _safe_float(numeric.mean())
                row[f"{prefix}_std"] = _safe_float(numeric.std())
                if prefix == "speed":
                    row[f"{prefix}_min"] = _safe_float(numeric.min())
                    row[f"{prefix}_max"] = _safe_float(numeric.max())
            else:
                row[f"{prefix}_mean"] = None
                row[f"{prefix}_std"] = None
                if prefix == "speed":
                    row[f"{prefix}_min"] = None
                    row[f"{prefix}_max"] = None

        if "routine_ring_building_candidate" in group.columns:
            routine_ratio = pd.to_numeric(group["routine_ring_building_candidate"], errors="coerce").fillna(0).clip(0, 1).mean()
            row["routine_stop_candidate_ratio"] = _safe_float(routine_ratio)
        else:
            row["routine_stop_candidate_ratio"] = None

        row["RAI_proxy"] = _build_rai_proxy(pd.Series(row))
        if row["RAI_proxy"] is None:
            warnings.append("RAI_proxy unavailable for some cells because required PLC fields are missing")
        row["response_anomaly_type"] = _classify_response_type(pd.Series(row))
        row["warnings"] = ""
        rows.append(row)

    out = pd.DataFrame(rows)
    if warnings:
        out["warnings"] = "; ".join(sorted(set(warnings)))
    return out


def summarize_cell_response(
    cell_response_df: pd.DataFrame,
    top_k: int = 5,
) -> dict[str, Any]:
    """Summarize cell-level PLC response anomalies without exposing the full dataframe."""
    if cell_response_df is None or not isinstance(cell_response_df, pd.DataFrame) or cell_response_df.empty:
        return {
            "schema_version": "cell_response_summary_v1",
            "cell_count": 0,
            "high_response_cell_count": 0,
            "top_response_cells": [],
            "warnings": [],
        }

    frame = cell_response_df.copy()
    warnings = []
    if "warnings" in frame.columns:
        warnings = sorted(set(str(value) for value in frame["warnings"].dropna().tolist() if str(value).strip()))

    rai = pd.to_numeric(frame.get("RAI_proxy"), errors="coerce")
    high_count = int((rai.fillna(-1) >= 0.6).sum()) if "RAI_proxy" in frame.columns else 0
    sortable = frame.assign(__sort_rai=rai.fillna(-1)).sort_values("__sort_rai", ascending=False)
    top_cells = []
    for _, row in sortable.head(max(int(top_k), 0)).iterrows():
        top_cells.append(
            {
                "cell_id": row.get("cell_id"),
                "range_dk": row.get("range_dk"),
                "RAI_proxy": _safe_float(row.get("RAI_proxy")),
                "response_anomaly_type": row.get("response_anomaly_type"),
                "work_ratio": _safe_float(row.get("work_ratio")),
                "stop_ratio": _safe_float(row.get("stop_ratio")),
                "speed_mean": _safe_float(row.get("speed_mean")),
                "torque_mean": _safe_float(row.get("torque_mean")),
                "thrust_mean": _safe_float(row.get("thrust_mean")),
            }
        )

    return _clean_json_value(
        {
            "schema_version": "cell_response_summary_v1",
            "cell_count": int(len(frame)),
            "high_response_cell_count": high_count,
            "top_response_cells": top_cells,
            "warnings": warnings,
        }
    )
