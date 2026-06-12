from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analysis.plc_contract import resolve_plc_columns


def project_plc_response_to_cells(
    df_plc: pd.DataFrame,
    cell_length: float = 10.0,
) -> pd.DataFrame:
    """Aggregate PLC operation and response metrics to 10 m chainage cells."""
    if df_plc is None or df_plc.empty:
        return _empty_cell_response_df()

    resolved = resolve_plc_columns(df_plc)
    chainage_col = resolved.get("chainage_col") or "chainage"
    if chainage_col not in df_plc.columns:
        return _empty_cell_response_df()

    df = df_plc.copy()
    df["chainage"] = pd.to_numeric(df[chainage_col], errors="coerce")
    df = df.dropna(subset=["chainage"]).copy()
    if df.empty:
        return _empty_cell_response_df()

    time_col = resolved.get("time_col")
    if time_col and time_col in df.columns:
        df["__time"] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.sort_values(["__time", "chainage"]).copy()
    else:
        df = df.sort_values("chainage").copy()

    _copy_numeric(df, resolved.get("speed_col"), "__speed")
    _copy_numeric(df, resolved.get("thrust_col"), "__thrust")
    _copy_numeric(df, resolved.get("torque_col"), "__torque")
    _copy_numeric(df, resolved.get("rpm_col"), "__rpm")

    df["__duration_sec"] = _infer_row_duration_seconds(df)
    if "is_working" not in df.columns:
        df["is_working"] = _numeric_series(df, resolved.get("state_col")).fillna(1).ne(0)
    if "is_stopped" not in df.columns:
        state = _numeric_series(df, resolved.get("state_col"))
        speed = df.get("__speed", pd.Series(0.0, index=df.index)).fillna(0.0)
        df["is_stopped"] = state.fillna(1).eq(0) | speed.abs().le(1e-8)
    if "is_abnormal" not in df.columns:
        speed = df.get("__speed", pd.Series(0.0, index=df.index)).fillna(0.0)
        torque = df.get("__torque", pd.Series(0.0, index=df.index)).fillna(0.0)
        thrust = df.get("__thrust", pd.Series(0.0, index=df.index)).fillna(0.0)
        df["is_abnormal"] = speed.abs().le(1e-8) & torque.abs().gt(0) & thrust.abs().le(1e-8)

    df["cell_start"] = np.floor(df["chainage"] / float(cell_length)) * float(cell_length)
    df["cell_end"] = df["cell_start"] + float(cell_length)
    df["cell_center"] = (df["cell_start"] + df["cell_end"]) / 2.0
    df["cell_id"] = df.apply(
        lambda row: f"cell_{_number_key(row['cell_start'])}_{_number_key(row['cell_end'])}",
        axis=1,
    )

    records: list[dict[str, Any]] = []
    for cell_id, group in df.groupby("cell_id", sort=True):
        duration_sec = float(group["__duration_sec"].sum() or 0.0)
        work_sec = _duration_for(group, "is_working")
        stop_sec = _duration_for(group, "is_stopped")
        abnormal_sec = _duration_for(group, "is_abnormal")
        speed_mean = _safe_mean(group.get("__speed"))
        speed_std = _safe_std(group.get("__speed"))
        thrust_mean = _safe_mean(group.get("__thrust"))
        torque_mean = _safe_mean(group.get("__torque"))
        torque_std = _safe_std(group.get("__torque"))
        rpm_mean = _safe_mean(group.get("__rpm"))

        stop_ratio = stop_sec / duration_sec if duration_sec > 0 else 0.0
        abnormal_ratio = abnormal_sec / duration_sec if duration_sec > 0 else 0.0
        speed_drop_score = _bounded(1.0 - (speed_mean or 0.0) / max(_safe_quantile(df.get("__speed"), 0.75), 1e-6))
        torque_volatility_score = _bounded((torque_std or 0.0) / max(abs(torque_mean or 0.0), 1.0))
        speed_volatility_score = _bounded((speed_std or 0.0) / max(abs(speed_mean or 0.0), 1.0))
        abnormal_score = _bounded(
            0.40 * stop_ratio
            + 0.25 * abnormal_ratio
            + 0.20 * speed_drop_score
            + 0.10 * torque_volatility_score
            + 0.05 * speed_volatility_score
        )

        operation_state = _dominant_operation_state(work_sec, stop_sec, abnormal_sec, duration_sec)
        cell_start = float(group["cell_start"].iloc[0])
        cell_end = float(group["cell_end"].iloc[0])
        records.append(
            {
                "cell_id": cell_id,
                "cell_start": cell_start,
                "cell_end": cell_end,
                "cell_center": float(group["cell_center"].iloc[0]),
                "operation_state": operation_state,
                "sample_count": int(len(group)),
                "duration_min": duration_sec / 60.0,
                "work_duration_min": work_sec / 60.0,
                "stop_duration_min": stop_sec / 60.0,
                "abnormal_duration_min": abnormal_sec / 60.0,
                "speed_mean": speed_mean,
                "speed_std": speed_std,
                "thrust_mean": thrust_mean,
                "torque_mean": torque_mean,
                "torque_std": torque_std,
                "rpm_mean": rpm_mean,
                "stop_ratio": stop_ratio,
                "abnormal_ratio": abnormal_ratio,
                "speed_drop_score": speed_drop_score,
                "torque_volatility_score": torque_volatility_score,
                "speed_volatility_score": speed_volatility_score,
                "abnormal_score": abnormal_score,
                "RAI": abnormal_score,
                "response_support_count": int(len(group)),
                "response_metrics": {
                    "duration_min": duration_sec / 60.0,
                    "work_duration_min": work_sec / 60.0,
                    "stop_duration_min": stop_sec / 60.0,
                    "abnormal_duration_min": abnormal_sec / 60.0,
                    "speed_drop_score": speed_drop_score,
                    "torque_volatility_score": torque_volatility_score,
                    "speed_volatility_score": speed_volatility_score,
                },
            }
        )

    return pd.DataFrame(records)


def _empty_cell_response_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "cell_id",
            "cell_start",
            "cell_end",
            "cell_center",
            "operation_state",
            "speed_mean",
            "thrust_mean",
            "torque_mean",
            "stop_duration_min",
            "abnormal_score",
            "RAI",
            "response_support_count",
            "response_metrics",
        ]
    )


def _copy_numeric(df: pd.DataFrame, source_col: str | None, target_col: str) -> None:
    if source_col and source_col in df.columns:
        df[target_col] = pd.to_numeric(df[source_col], errors="coerce")
    else:
        df[target_col] = np.nan


def _numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column and column in df.columns:
        return pd.to_numeric(df[column], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def _infer_row_duration_seconds(df: pd.DataFrame) -> pd.Series:
    if "__time" not in df.columns or df["__time"].dropna().shape[0] < 2:
        return pd.Series(1.0, index=df.index)
    times = pd.to_datetime(df["__time"], errors="coerce")
    diffs = times.diff().dt.total_seconds()
    valid = diffs[(diffs > 0) & (diffs < 3600)]
    median = float(valid.median()) if not valid.empty else 1.0
    return diffs.where((diffs > 0) & (diffs < 3600), median).fillna(median)


def _duration_for(group: pd.DataFrame, mask_col: str) -> float:
    mask = group.get(mask_col, pd.Series(False, index=group.index)).fillna(False).astype(bool)
    return float(group.loc[mask, "__duration_sec"].sum() or 0.0)


def _safe_mean(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    value = pd.to_numeric(series, errors="coerce").mean()
    return None if pd.isna(value) else float(value)


def _safe_std(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    value = pd.to_numeric(series, errors="coerce").std()
    return None if pd.isna(value) else float(value)


def _safe_quantile(series: pd.Series | None, q: float) -> float:
    if series is None:
        return 0.0
    value = pd.to_numeric(series, errors="coerce").dropna().quantile(q)
    return 0.0 if pd.isna(value) else float(value)


def _bounded(value: float) -> float:
    if pd.isna(value):
        return 0.0
    return float(max(0.0, min(1.0, value)))


def _dominant_operation_state(work_sec: float, stop_sec: float, abnormal_sec: float, duration_sec: float) -> str:
    if duration_sec <= 0:
        return "unknown"
    candidates = {
        "work": work_sec,
        "stop": stop_sec,
        "abnormal": abnormal_sec,
        "transition": max(duration_sec - work_sec - stop_sec - abnormal_sec, 0.0),
    }
    return max(candidates.items(), key=lambda item: item[1])[0]


def _number_key(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0").rstrip(".")

