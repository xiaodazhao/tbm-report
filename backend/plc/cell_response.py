from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analysis.plc_contract import resolve_plc_columns
from plc.paper_based_preprocessing import apply_paper_based_preprocessing


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

    motion_cols = resolved.get("motion_cols", {}) or {}
    advance_speed_col = motion_cols.get("advance_speed") or resolved.get("speed_col") or resolved.get("advance_speed_col")
    thrust_col = motion_cols.get("thrust") or resolved.get("thrust_col")
    torque_col = motion_cols.get("torque") or resolved.get("torque_col")
    rpm_col = motion_cols.get("rpm") or resolved.get("rpm_col")
    penetration_col = motion_cols.get("penetration") or resolved.get("penetration_col")

    _copy_numeric(df, advance_speed_col, "__speed")
    _copy_numeric(df, thrust_col, "__thrust")
    _copy_numeric(df, torque_col, "__torque")
    _copy_numeric(df, rpm_col, "__rpm")
    _copy_numeric(df, penetration_col, "__penetration")

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
    preprocessing = apply_paper_based_preprocessing(df, cell_length=cell_length)
    paper_samples = preprocessing.get("samples")
    if isinstance(paper_samples, pd.DataFrame) and not paper_samples.empty:
        for column in [
            "is_shutdown_segment",
            "shutdown_reason",
            "auxiliary_shutdown",
            "is_outlier",
            "outlier_reason",
            "valid_excavation_mask",
            "working_interval_id",
            "working_interval_is_valid",
            "paper_plc_stage",
            "steady_state_available",
            "steady_state_fallback_used",
            "steady_state_fallback_reason",
        ]:
            if column in paper_samples.columns:
                df[column] = paper_samples[column]
    paper_cell_metrics = {}
    paper_cell_df = preprocessing.get("cell_metrics")
    if isinstance(paper_cell_df, pd.DataFrame) and not paper_cell_df.empty and "cell_id" in paper_cell_df.columns:
        paper_cell_metrics = {
            str(row.get("cell_id")): {key: value for key, value in row.items() if key != "cell_id"}
            for _, row in paper_cell_df.iterrows()
        }

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
        paper_metrics = paper_cell_metrics.get(str(cell_id), {})
        working_metrics = _paper_based_working_aliases(paper_metrics, group_size=len(group))

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
        rai_components = _rai_components(
            stop_ratio=stop_ratio,
            abnormal_ratio=abnormal_ratio,
            speed_drop_score=speed_drop_score,
            torque_volatility_score=torque_volatility_score,
            speed_volatility_score=speed_volatility_score,
            rai=abnormal_score,
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
                **paper_metrics,
                "stop_ratio": stop_ratio,
                "abnormal_ratio": abnormal_ratio,
                "speed_drop_score": speed_drop_score,
                "torque_volatility_score": torque_volatility_score,
                "speed_volatility_score": speed_volatility_score,
                **working_metrics,
                **rai_components,
                "abnormal_score": abnormal_score,
                "RAI": abnormal_score,
                "RAI_formula_text": RAI_FORMULA_TEXT,
                "stop_reason_available": False,
                "planned_stop_distinguishable": False,
                "stop_interpretation_warning": STOP_INTERPRETATION_WARNING,
                "response_support_count": int(len(group)),
                "response_metrics": {
                    "duration_min": duration_sec / 60.0,
                    "work_duration_min": work_sec / 60.0,
                    "stop_duration_min": stop_sec / 60.0,
                    "abnormal_duration_min": abnormal_sec / 60.0,
                    "speed_drop_score": speed_drop_score,
                    "torque_volatility_score": torque_volatility_score,
                    "speed_volatility_score": speed_volatility_score,
                    **working_metrics,
                    **rai_components,
                    "RAI": abnormal_score,
                    "RAI_formula_text": RAI_FORMULA_TEXT,
                    "stop_reason_available": False,
                    "planned_stop_distinguishable": False,
                    "stop_interpretation_warning": STOP_INTERPRETATION_WARNING,
                    **paper_metrics,
                },
            }
        )

    out = pd.DataFrame(records)
    out.attrs["plc_preprocessing_daily_summary"] = preprocessing.get("daily_summary") or {}
    return out


RAI_FORMULA_TEXT = (
    "RAI = 0.40 * stop_ratio + 0.25 * abnormal_ratio "
    "+ 0.20 * speed_drop_score + 0.10 * torque_volatility_score "
    "+ 0.05 * speed_volatility_score"
)

STOP_INTERPRETATION_WARNING = (
    "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。"
)
MIN_WORKING_SAMPLE_COUNT = 20


def _rai_components(
    *,
    stop_ratio: float,
    abnormal_ratio: float,
    speed_drop_score: float,
    torque_volatility_score: float,
    speed_volatility_score: float,
    rai: float,
) -> dict[str, float | str]:
    components = {
        "stop_component": 0.40 * stop_ratio,
        "abnormal_component": 0.25 * abnormal_ratio,
        "speed_drop_component": 0.20 * speed_drop_score,
        "torque_component": 0.10 * torque_volatility_score,
        "speed_volatility_component": 0.05 * speed_volatility_score,
    }
    dominant_component = max(components.items(), key=lambda item: item[1])[0]
    return {
        **components,
        "dominant_component": dominant_component,
    }


def _paper_based_working_aliases(paper_metrics: dict[str, Any], *, group_size: int) -> dict[str, Any]:
    """Expose legacy working_* names from the single paper-based PLC source.

    Older code computed a second working-only feature set here. The current
    implementation keeps those public names as compatibility aliases only, so
    PLC cell evidence has one source of truth: paper_based_preprocessing.py.
    """
    raw_count = _int_value(paper_metrics.get("raw_sample_count"), default=group_size)
    working_count = _int_value(paper_metrics.get("working_sample_count_paper"), default=0)
    insufficient = working_count < MIN_WORKING_SAMPLE_COUNT
    steady_available = bool(paper_metrics.get("steady_state_available"))
    fallback_used = bool(paper_metrics.get("steady_state_fallback_used"))
    if steady_available:
        source = "paper_based_preprocessing_steady_state_alias"
    elif fallback_used:
        source = "paper_based_preprocessing_working_fallback_alias"
    else:
        source = "paper_based_preprocessing_valid_excavation_count"
    return {
        "working_sample_count": working_count,
        "working_ratio": working_count / raw_count if raw_count else 0.0,
        "insufficient_working_samples": insufficient,
        "working_speed_cv": None if insufficient else paper_metrics.get("steady_speed_cv"),
        "working_thrust_cv": None if insufficient else paper_metrics.get("steady_thrust_cv"),
        "working_torque_cv": None if insufficient else paper_metrics.get("steady_torque_cv"),
        "penetration_mean": None if insufficient else paper_metrics.get("steady_penetration_mean"),
        "cutterhead_power_proxy": None if insufficient else paper_metrics.get("steady_cutterhead_power_proxy"),
        "thrust_per_penetration": None if insufficient else paper_metrics.get("steady_thrust_per_penetration"),
        "torque_per_penetration": None if insufficient else paper_metrics.get("steady_torque_per_penetration"),
        "working_metrics_source": source,
    }


def _int_value(value: Any, *, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


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
            "working_sample_count",
            "working_ratio",
            "insufficient_working_samples",
            "working_speed_cv",
            "working_thrust_cv",
            "working_torque_cv",
            "penetration_mean",
            "cutterhead_power_proxy",
            "thrust_per_penetration",
            "torque_per_penetration",
            "working_metrics_source",
            "is_shutdown_segment",
            "shutdown_reason",
            "auxiliary_shutdown",
            "is_outlier",
            "outlier_reason",
            "valid_excavation_mask",
            "working_interval_id",
            "working_interval_is_valid",
            "paper_plc_stage",
            "steady_state_available",
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
            "steady_state_fallback_used",
            "steady_state_fallback_reason",
            "steady_detection_signal",
            "steady_threshold_value",
            "steady_median_signal_value",
            "steady_candidate_segment_count",
            "plc_preprocessing_quality_grade",
            "plc_preprocessing_quality_reason",
            "plc_preprocessing_method",
            "plc_preprocessing_boundary",
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
