from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PLCPreprocessingConfig:
    eps_thrust: float = 0.0
    eps_torque: float = 0.0
    eps_speed: float = 0.0
    eps_rpm: float = 0.0
    chainage_reverse_tolerance: float = 0.01
    chainage_jump_threshold: float = 5.0
    min_outlier_sample_count: int = 30
    min_interval_sample_count: int = 20
    min_interval_duration_seconds: float = 30.0
    steady_window: int = 20
    steady_min_periods: int = 5
    steady_threshold_factor: float = 0.8
    min_steady_sample_count: int = 20
    min_steady_duration_seconds: float = 30.0
    cv_eps: float = 1e-6


NUMERIC_SIGNALS = {
    "__speed": "speed",
    "__thrust": "thrust",
    "__torque": "torque",
    "__rpm": "rpm",
    "__penetration": "penetration",
}


def apply_paper_based_preprocessing(
    df: pd.DataFrame,
    *,
    cell_length: float = 10.0,
    config: PLCPreprocessingConfig | None = None,
) -> dict[str, Any]:
    """Add paper-inspired PLC preprocessing labels and cell-level steady metrics.

    The implementation borrows only data cleaning and steady-state feature
    extraction ideas from TBM operation-parameter studies. It does not build a
    prediction model and does not change RAI/GRS/GRCI formulas.
    """
    config = config or PLCPreprocessingConfig()
    if df is None or df.empty:
        samples = pd.DataFrame()
        return {
            "samples": samples,
            "intervals": pd.DataFrame(),
            "cell_metrics": pd.DataFrame(),
            "daily_summary": _empty_daily_summary(),
        }

    work = df.copy()
    if "__time" in work.columns:
        work["__time"] = pd.to_datetime(work["__time"], errors="coerce")
        work = work.sort_values(["__time", "chainage"], na_position="last").copy()
    else:
        work = work.sort_values("chainage", na_position="last").copy()

    work = _ensure_numeric_columns(work)
    work["__paper_original_index"] = work.index
    _annotate_quality_audit(work, config)
    _annotate_shutdown(work, config)
    _annotate_outliers(work, config)
    _annotate_valid_excavation(work, config)
    intervals = _annotate_working_intervals(work, config)
    _annotate_steady_state(work, intervals, config)
    _ensure_cell_columns(work, cell_length)
    cell_metrics = _build_cell_metrics(work, config)
    daily_summary = _build_daily_summary(work, intervals)
    return {
        "samples": work,
        "intervals": intervals,
        "cell_metrics": cell_metrics,
        "daily_summary": daily_summary,
    }


def _ensure_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in ["chainage", "__speed", "__thrust", "__torque", "__rpm", "__penetration"]:
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if "__duration_sec" not in df.columns:
        df["__duration_sec"] = 1.0
    df["__duration_sec"] = pd.to_numeric(df["__duration_sec"], errors="coerce").fillna(1.0)
    return df


def _annotate_quality_audit(df: pd.DataFrame, config: PLCPreprocessingConfig) -> None:
    chainage_diff = pd.to_numeric(df["chainage"], errors="coerce").diff()
    df["__paper_chainage_reverse"] = chainage_diff.lt(-abs(config.chainage_reverse_tolerance)).fillna(False)
    df["__paper_chainage_jump"] = chainage_diff.abs().gt(config.chainage_jump_threshold).fillna(False)
    df["__paper_chainage_valid"] = ~df["__paper_chainage_reverse"] & df["chainage"].notna()

    if "__time" in df.columns:
        time_diff = pd.to_datetime(df["__time"], errors="coerce").diff().dt.total_seconds()
        valid_dt = time_diff[(time_diff > 0) & time_diff.notna()]
        median_dt = float(valid_dt.median()) if not valid_dt.empty else None
        threshold = max(3.0 * median_dt, 10.0) if median_dt is not None else None
        df["__paper_time_gap"] = time_diff.gt(threshold).fillna(False) if threshold is not None else False
        df["__paper_time_gap_threshold_sec"] = threshold
    else:
        df["__paper_time_gap"] = False
        df["__paper_time_gap_threshold_sec"] = None


def _annotate_shutdown(df: pd.DataFrame, config: PLCPreprocessingConfig) -> None:
    thrust_missing = df["__thrust"].isna()
    torque_missing = df["__torque"].isna()
    thrust_zero = df["__thrust"].le(config.eps_thrust).fillna(False)
    torque_zero = df["__torque"].le(config.eps_torque).fillna(False)
    df["is_shutdown_segment"] = thrust_zero | torque_zero

    reasons = []
    for thrust_is_zero, torque_is_zero, thrust_is_missing, torque_is_missing in zip(
        thrust_zero, torque_zero, thrust_missing, torque_missing
    ):
        if thrust_is_missing or torque_is_missing:
            reasons.append("missing_thrust_or_torque")
        elif thrust_is_zero and torque_is_zero:
            reasons.append("both_thrust_and_torque_zero_or_near_zero")
        elif thrust_is_zero:
            reasons.append("thrust_zero_or_near_zero")
        elif torque_is_zero:
            reasons.append("torque_zero_or_near_zero")
        else:
            reasons.append(None)
    df["shutdown_reason"] = reasons

    speed_zero = df["__speed"].le(config.eps_speed).fillna(False)
    rpm_zero = df["__rpm"].le(config.eps_rpm).fillna(False)
    df["auxiliary_shutdown"] = speed_zero | rpm_zero


def _annotate_outliers(df: pd.DataFrame, config: PLCPreprocessingConfig) -> None:
    non_shutdown = ~df["is_shutdown_segment"].fillna(False).astype(bool)
    outlier_mask = pd.Series(False, index=df.index)
    reasons: dict[Any, list[str]] = {idx: [] for idx in df.index}
    skipped_fields: list[str] = []

    for column, label in NUMERIC_SIGNALS.items():
        series = pd.to_numeric(df.loc[non_shutdown, column], errors="coerce").dropna()
        if len(series) < config.min_outlier_sample_count:
            skipped_fields.append(label)
            continue
        std = float(series.std())
        if np.isnan(std) or std <= config.cv_eps:
            skipped_fields.append(label)
            continue
        mean = float(series.mean())
        lower = mean - 3.0 * std
        upper = mean + 3.0 * std
        mask = non_shutdown & (df[column].lt(lower) | df[column].gt(upper))
        outlier_mask = outlier_mask | mask.fillna(False)
        for idx in df.index[mask.fillna(False)]:
            reasons[idx].append(f"{label}_outside_3sigma")

    df["is_outlier"] = outlier_mask
    df["outlier_reason"] = [";".join(reasons[idx]) if reasons[idx] else None for idx in df.index]
    df["outlier_filter_skipped_fields"] = ",".join(skipped_fields) if skipped_fields else None


def _annotate_valid_excavation(df: pd.DataFrame, config: PLCPreprocessingConfig) -> None:
    valid = (
        ~df["is_shutdown_segment"].fillna(False).astype(bool)
        & ~df["is_outlier"].fillna(False).astype(bool)
        & df["__paper_chainage_valid"].fillna(False).astype(bool)
        & df["__thrust"].gt(config.eps_thrust).fillna(False)
        & df["__torque"].gt(config.eps_torque).fillna(False)
    )
    if df["__speed"].notna().any():
        valid = valid & df["__speed"].gt(config.eps_speed).fillna(False)
    if df["__rpm"].notna().any():
        valid = valid & df["__rpm"].gt(config.eps_rpm).fillna(False)
    if "is_working" in df.columns:
        valid = valid & df["is_working"].fillna(False).astype(bool)
        df["used_existing_is_working"] = True
    else:
        df["used_existing_is_working"] = False
    df["valid_excavation_mask"] = valid


def _annotate_working_intervals(df: pd.DataFrame, config: PLCPreprocessingConfig) -> pd.DataFrame:
    interval_ids: list[int | None] = []
    current_id = 0
    previous_valid = False
    previous_index = None
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}

    for idx, row in df.iterrows():
        valid = bool(row.get("valid_excavation_mask"))
        if not valid:
            interval_ids.append(None)
            previous_valid = False
            previous_index = idx
            continue

        new_interval = (
            not previous_valid
            or bool(row.get("__paper_time_gap"))
            or bool(row.get("__paper_chainage_reverse"))
        )
        if previous_index is None:
            new_interval = True
        if new_interval:
            current_id += 1
            starts[current_id] = idx
        ends[current_id] = idx
        interval_ids.append(current_id)
        previous_valid = True
        previous_index = idx

    df["working_interval_id"] = interval_ids
    rows = []
    for interval_id in sorted(set(item for item in interval_ids if item is not None)):
        part = df[df["working_interval_id"].eq(interval_id)]
        start_time = _first_non_null(part.get("__time"))
        end_time = _last_non_null(part.get("__time"))
        duration = float(part["__duration_sec"].sum() or 0.0)
        chainage_start = _safe_float(part["chainage"].iloc[0])
        chainage_end = _safe_float(part["chainage"].iloc[-1])
        chainage_length = None
        if chainage_start is not None and chainage_end is not None:
            chainage_length = abs(chainage_end - chainage_start)
        valid_interval = len(part) >= config.min_interval_sample_count and duration >= config.min_interval_duration_seconds
        rows.append(
            {
                "working_interval_id": int(interval_id),
                "interval_start_time": start_time,
                "interval_end_time": end_time,
                "interval_duration_seconds": duration,
                "interval_sample_count": int(len(part)),
                "interval_chainage_start": chainage_start,
                "interval_chainage_end": chainage_end,
                "interval_chainage_length": chainage_length,
                "interval_is_valid": bool(valid_interval),
                "interval_type": "valid_working_interval" if valid_interval else "short_transition_interval",
                **_trial_30s_metrics(part),
            }
        )
    intervals = pd.DataFrame(rows)
    if not intervals.empty:
        valid_map = intervals.set_index("working_interval_id")["interval_is_valid"].to_dict()
        df["working_interval_is_valid"] = df["working_interval_id"].map(valid_map).eq(True)
    else:
        df["working_interval_is_valid"] = False
    return intervals


def _annotate_steady_state(df: pd.DataFrame, intervals: pd.DataFrame, config: PLCPreprocessingConfig) -> None:
    df["steady_state_available"] = False
    df["steady_state_fallback_used"] = False
    df["steady_state_fallback_reason"] = None
    df["steady_detection_signal"] = None
    df["steady_threshold_value"] = np.nan
    df["steady_median_signal_value"] = np.nan
    df["steady_candidate_segment_count"] = 0
    df["paper_plc_stage"] = np.where(
        df["is_shutdown_segment"].fillna(False).astype(bool),
        "shutdown",
        np.where(df["is_outlier"].fillna(False).astype(bool), "abnormal_outlier", "non_excavation"),
    )

    if intervals.empty:
        return

    for _, interval in intervals[intervals["interval_is_valid"].astype(bool)].iterrows():
        interval_id = int(interval["working_interval_id"])
        part_index = df.index[df["working_interval_id"].eq(interval_id)].tolist()
        part = df.loc[part_index].copy()
        signal_col, signal_name = _choose_detection_signal(part)
        if signal_col is None:
            df.loc[part_index, "steady_state_fallback_used"] = True
            df.loc[part_index, "steady_state_fallback_reason"] = "no_detection_signal"
            df.loc[part_index, "paper_plc_stage"] = "working_only_fallback"
            continue

        signal = pd.to_numeric(part[signal_col], errors="coerce")
        min_periods = min(config.steady_min_periods, max(int(signal.notna().sum()), 1))
        rolling = signal.rolling(window=config.steady_window, min_periods=min_periods).mean()
        median_value = _safe_float(rolling.dropna().median())
        if median_value is None or median_value <= config.cv_eps:
            df.loc[part_index, "steady_state_fallback_used"] = True
            df.loc[part_index, "steady_state_fallback_reason"] = "invalid_detection_signal"
            df.loc[part_index, "steady_detection_signal"] = signal_name
            df.loc[part_index, "paper_plc_stage"] = "working_only_fallback"
            continue

        threshold = config.steady_threshold_factor * median_value
        candidate = rolling.ge(threshold).fillna(False)
        segments = _candidate_segments(part.index.tolist(), candidate.tolist(), df)
        df.loc[part_index, "steady_detection_signal"] = signal_name
        df.loc[part_index, "steady_threshold_value"] = threshold
        df.loc[part_index, "steady_median_signal_value"] = median_value
        df.loc[part_index, "steady_candidate_segment_count"] = len(segments)

        if not segments:
            df.loc[part_index, "steady_state_fallback_used"] = True
            df.loc[part_index, "steady_state_fallback_reason"] = "no_candidate_above_threshold"
            df.loc[part_index, "paper_plc_stage"] = "working_only_fallback"
            continue

        chosen = _choose_steady_segment(segments)
        if chosen["sample_count"] < config.min_steady_sample_count or chosen["duration_seconds"] < config.min_steady_duration_seconds:
            df.loc[part_index, "steady_state_fallback_used"] = True
            df.loc[part_index, "steady_state_fallback_reason"] = "steady_candidate_too_short"
            df.loc[part_index, "paper_plc_stage"] = "working_only_fallback"
            continue

        steady_indices = chosen["indices"]
        first_pos = part_index.index(steady_indices[0])
        last_pos = part_index.index(steady_indices[-1])
        before = part_index[:first_pos]
        after = part_index[last_pos + 1 :]
        df.loc[before, "paper_plc_stage"] = "ascending_or_startup"
        df.loc[steady_indices, "paper_plc_stage"] = "steady_state"
        df.loc[after, "paper_plc_stage"] = "end_or_deceleration"
        df.loc[steady_indices, "steady_state_available"] = True


def _choose_detection_signal(part: pd.DataFrame) -> tuple[str | None, str | None]:
    speed = pd.to_numeric(part.get("__speed"), errors="coerce")
    if speed.notna().any() and speed.gt(0).any():
        return "__speed", "advance_speed"
    # The project PLC field named "penetration" is the machine-reported
    # penetration value (typically mm/r), not a confirmed penetration-rate
    # signal. Use it only as a last-resort monotonic signal for steady-state
    # segmentation when advance speed is unavailable.
    penetration = pd.to_numeric(part.get("__penetration"), errors="coerce")
    if penetration.notna().any() and penetration.gt(0).any():
        return "__penetration", "penetration_value_fallback_not_rate"
    return None, None


def _candidate_segments(indices: list[Any], candidate_values: list[bool], df: pd.DataFrame) -> list[dict[str, Any]]:
    segments = []
    current: list[Any] = []
    for idx, is_candidate in zip(indices, candidate_values):
        if is_candidate:
            current.append(idx)
        elif current:
            segments.append(_segment_record(current, df))
            current = []
    if current:
        segments.append(_segment_record(current, df))
    return segments


def _segment_record(indices: list[Any], df: pd.DataFrame) -> dict[str, Any]:
    part = df.loc[indices]
    duration = float(part["__duration_sec"].sum() or 0.0)
    start = _safe_float(part["chainage"].iloc[0])
    end = _safe_float(part["chainage"].iloc[-1])
    length = abs(end - start) if start is not None and end is not None else 0.0
    return {
        "indices": indices,
        "sample_count": len(indices),
        "duration_seconds": duration,
        "chainage_length": length,
        "first_order": int(part.index.to_series().rank(method="first").iloc[0]) if len(part) else 0,
    }


def _choose_steady_segment(segments: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        segments,
        key=lambda item: (
            -int(item["sample_count"]),
            -float(item["duration_seconds"]),
            -float(item["chainage_length"]),
        ),
    )[0]


def _ensure_cell_columns(df: pd.DataFrame, cell_length: float) -> None:
    if "cell_id" in df.columns and "cell_start" in df.columns and "cell_end" in df.columns:
        return
    length = float(cell_length or 10.0)
    df["cell_start"] = np.floor(df["chainage"] / length) * length
    df["cell_end"] = df["cell_start"] + length
    df["cell_center"] = (df["cell_start"] + df["cell_end"]) / 2.0
    df["cell_id"] = df.apply(lambda row: f"cell_{_number_key(row['cell_start'])}_{_number_key(row['cell_end'])}", axis=1)


def _build_cell_metrics(df: pd.DataFrame, config: PLCPreprocessingConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if df.empty or "cell_id" not in df.columns:
        return pd.DataFrame()
    for cell_id, group in df.groupby("cell_id", sort=True):
        raw_count = int(len(group))
        working = group[group["valid_excavation_mask"].fillna(False).astype(bool)]
        steady = group[group["paper_plc_stage"].eq("steady_state")]
        working_count = int(len(working))
        steady_count = int(len(steady))
        base = {
            "cell_id": cell_id,
            "raw_sample_count": raw_count,
            "shutdown_sample_count": int(group["is_shutdown_segment"].fillna(False).sum()),
            "outlier_sample_count": int(group["is_outlier"].fillna(False).sum()),
            "working_sample_count_paper": working_count,
            "steady_state_available": steady_count > 0,
            "steady_sample_count": steady_count,
            "steady_ratio": _safe_ratio(steady_count, raw_count),
            "steady_to_working_ratio": _safe_ratio(steady_count, working_count),
        }
        for internal, label in NUMERIC_SIGNALS.items():
            stats = _series_stats(steady.get(internal), config)
            base[f"steady_{label}_mean"] = stats["mean"]
            base[f"steady_{label}_std"] = stats["std"]
            base[f"steady_{label}_cv"] = stats["cv"]

        torque_mean = base.get("steady_torque_mean")
        rpm_mean = base.get("steady_rpm_mean")
        penetration_mean = base.get("steady_penetration_mean")
        base["steady_cutterhead_power_proxy"] = (
            torque_mean * rpm_mean if torque_mean is not None and rpm_mean is not None else None
        )
        base["steady_thrust_per_penetration"] = (
            base.get("steady_thrust_mean") / penetration_mean
            if base.get("steady_thrust_mean") is not None and penetration_mean is not None and penetration_mean > config.cv_eps
            else None
        )
        base["steady_torque_per_penetration"] = (
            torque_mean / penetration_mean
            if torque_mean is not None and penetration_mean is not None and penetration_mean > config.cv_eps
            else None
        )
        base["steady_state_fallback_used"] = bool(
            steady_count == 0 and working_count >= config.min_interval_sample_count
        )
        base["steady_state_fallback_reason"] = _first_text(group.get("steady_state_fallback_reason"))
        base["steady_detection_signal"] = _first_text(group.get("steady_detection_signal"))
        base["steady_threshold_value"] = _first_number(group.get("steady_threshold_value"))
        base["steady_median_signal_value"] = _first_number(group.get("steady_median_signal_value"))
        base["steady_candidate_segment_count"] = int(pd.to_numeric(group.get("steady_candidate_segment_count"), errors="coerce").fillna(0).max())
        base["plc_preprocessing_quality_grade"], base["plc_preprocessing_quality_reason"] = _quality_grade(base)
        base["plc_preprocessing_method"] = "wang_shutdown_3sigma_shan_steady_state_v1"
        base["plc_preprocessing_boundary"] = (
            "Steady-state PLC metrics are excavated daily-review response evidence only; "
            "proxy metrics are not strict physical power, specific energy, geological proof, or risk probability."
        )
        rows.append(base)
    return pd.DataFrame(rows)


def _series_stats(series: pd.Series | None, config: PLCPreprocessingConfig) -> dict[str, float | None]:
    if series is None:
        return {"mean": None, "std": None, "cv": None}
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {"mean": None, "std": None, "cv": None}
    mean = float(numeric.mean())
    std = float(numeric.std()) if len(numeric) > 1 else 0.0
    cv = None if abs(mean) <= config.cv_eps else std / abs(mean)
    return {"mean": mean, "std": std, "cv": cv}


def _trial_30s_metrics(part: pd.DataFrame) -> dict[str, float | None]:
    if part.empty:
        return {}
    cumulative = pd.to_numeric(part["__duration_sec"], errors="coerce").fillna(1.0).cumsum()
    trial = part.loc[cumulative.le(30.0)].copy()
    if trial.empty:
        return {}
    out: dict[str, float | None] = {}
    for internal, label in NUMERIC_SIGNALS.items():
        numeric = pd.to_numeric(trial.get(internal), errors="coerce").dropna()
        out[f"trial_30s_{label}_mean"] = None if numeric.empty else float(numeric.mean())
        out[f"trial_30s_{label}_var"] = None if len(numeric) < 2 else float(numeric.var())
    return out


def _quality_grade(metrics: dict[str, Any]) -> tuple[str, str]:
    steady_available = bool(metrics.get("steady_state_available"))
    steady_sample_count = int(metrics.get("steady_sample_count") or 0)
    steady_to_working = metrics.get("steady_to_working_ratio")
    key_values = [
        metrics.get("steady_speed_mean"),
        metrics.get("steady_thrust_mean"),
        metrics.get("steady_torque_mean"),
    ]
    non_empty = sum(1 for value in key_values if value is not None)
    working_count = int(metrics.get("working_sample_count_paper") or 0)
    fallback_used = bool(metrics.get("steady_state_fallback_used"))
    if steady_available and steady_sample_count >= 50 and (steady_to_working or 0.0) >= 0.5 and non_empty >= 3:
        return "A", "steady_state_available_with_high_sample_count"
    if steady_available and steady_sample_count >= 20 and non_empty >= 2:
        return "B", "steady_state_available_with_sufficient_core_metrics"
    if not steady_available and fallback_used and working_count >= 20:
        return "C", "working_only_fallback_available"
    return "D", "insufficient_valid_plc_preprocessing_evidence"


def _build_daily_summary(df: pd.DataFrame, intervals: pd.DataFrame) -> dict[str, Any]:
    raw_count = int(len(df))
    return {
        "raw_sample_count": raw_count,
        "timestamp_missing_count": int(df.get("__time", pd.Series(index=df.index, dtype=object)).isna().sum()) if "__time" in df.columns else raw_count,
        "timestamp_missing_rate": _safe_ratio(int(df.get("__time", pd.Series(index=df.index, dtype=object)).isna().sum()), raw_count) if "__time" in df.columns else 1.0,
        "duplicate_timestamp_count": int(df["__time"].duplicated().sum()) if "__time" in df.columns else 0,
        "time_gap_count": int(df["__paper_time_gap"].fillna(False).sum()),
        "median_time_interval_seconds": _median_time_interval(df),
        "chainage_missing_count": int(df["chainage"].isna().sum()),
        "chainage_missing_rate": _safe_ratio(int(df["chainage"].isna().sum()), raw_count),
        "chainage_reverse_count": int(df["__paper_chainage_reverse"].fillna(False).sum()),
        "chainage_jump_count": int(df["__paper_chainage_jump"].fillna(False).sum()),
        "speed_missing_rate": _missing_rate(df, "__speed"),
        "thrust_missing_rate": _missing_rate(df, "__thrust"),
        "torque_missing_rate": _missing_rate(df, "__torque"),
        "rpm_missing_rate": _missing_rate(df, "__rpm"),
        "penetration_missing_rate": _missing_rate(df, "__penetration"),
        "shutdown_sample_count": int(df["is_shutdown_segment"].fillna(False).sum()),
        "shutdown_ratio": _safe_ratio(int(df["is_shutdown_segment"].fillna(False).sum()), raw_count),
        "outlier_sample_count": int(df["is_outlier"].fillna(False).sum()),
        "outlier_ratio": _safe_ratio(int(df["is_outlier"].fillna(False).sum()), raw_count),
        "working_interval_count": int(len(intervals)),
        "valid_working_interval_count": int(intervals.get("interval_is_valid", pd.Series(dtype=bool)).fillna(False).sum()) if not intervals.empty else 0,
        "short_transition_interval_count": int(intervals.get("interval_type", pd.Series(dtype=str)).astype(str).eq("short_transition_interval").sum()) if not intervals.empty else 0,
        "steady_interval_count": int(df["paper_plc_stage"].eq("steady_state").groupby(df["working_interval_id"]).any().sum()) if "working_interval_id" in df.columns else 0,
        "steady_state_available": bool(df["paper_plc_stage"].eq("steady_state").any()),
        "fallback_used": bool(df["steady_state_fallback_used"].fillna(False).any()),
        "fallback_reason": _first_text(df.get("steady_state_fallback_reason")),
    }


def _empty_daily_summary() -> dict[str, Any]:
    return {
        "raw_sample_count": 0,
        "shutdown_sample_count": 0,
        "shutdown_ratio": 0.0,
        "outlier_sample_count": 0,
        "outlier_ratio": 0.0,
        "working_interval_count": 0,
        "valid_working_interval_count": 0,
        "steady_state_available": False,
    }


def _median_time_interval(df: pd.DataFrame) -> float | None:
    if "__time" not in df.columns:
        return None
    diffs = pd.to_datetime(df["__time"], errors="coerce").diff().dt.total_seconds()
    valid = diffs[(diffs > 0) & diffs.notna()]
    return None if valid.empty else float(valid.median())


def _missing_rate(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or len(df) == 0:
        return 1.0
    return float(pd.to_numeric(df[column], errors="coerce").isna().sum() / len(df))


def _safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator) / float(denominator)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number):
        return None
    return number


def _first_non_null(series: pd.Series | None) -> Any:
    if series is None:
        return None
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    value = cleaned.iloc[0]
    return value.isoformat() if hasattr(value, "isoformat") else value


def _last_non_null(series: pd.Series | None) -> Any:
    if series is None:
        return None
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    value = cleaned.iloc[-1]
    return value.isoformat() if hasattr(value, "isoformat") else value


def _first_text(series: pd.Series | None) -> str | None:
    if series is None:
        return None
    for value in series.dropna().tolist():
        text = str(value).strip()
        if text and text.lower() != "nan":
            return text
    return None


def _first_number(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.iloc[0])


def _number_key(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0").rstrip(".")
