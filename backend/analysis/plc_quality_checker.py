"""PLC data quality checks for one daily TBM dataframe."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

try:
    from analysis.plc_contract import PLC_UNIT_ASSUMPTIONS, resolve_plc_columns
except Exception:  # pragma: no cover - keep checker usable even if contract import fails
    PLC_UNIT_ASSUMPTIONS = {}

    def resolve_plc_columns(df: pd.DataFrame) -> dict[str, Any]:
        """Fallback PLC column resolver."""
        columns = [str(col) for col in getattr(df, "columns", [])]
        lower_map = {col.strip().lower(): col for col in columns}

        def _find(candidates: list[str]) -> str | None:
            for candidate in candidates:
                key = candidate.strip().lower()
                if key in lower_map:
                    return lower_map[key]
            for candidate in candidates:
                key = candidate.strip().lower()
                for column in columns:
                    if key and key in column.strip().lower():
                        return column
            return None

        return {
            "time_col": _find(["运行时间-time", "timestamp", "time", "datetime", "date_time"]),
            "chainage_col": _find(["chainage", "当前里程", "导向盾首里程", "开累进尺", "里程"]),
            "state_col": _find(["掘进状态", "施工状态", "state", "excavation_state"]),
            "motion_cols": {
                "advance_speed": _find(["推进速度", "advance_speed", "speed", "actual_speed"]),
                "thrust": _find(["推力", "总推力", "thrust", "total_thrust"]),
                "torque": _find(["刀盘扭矩", "扭矩", "cutter_torque", "torque"]),
                "rpm": _find(["刀盘实际转速", "刀盘转速", "转速", "cutter_rpm", "rpm"]),
            },
            "gas_cols": {
                "CH4": _find(["CH4检测", "CH4", "甲烷"]),
                "CO2": _find(["CO2检测", "CO2"]),
                "H2S": _find(["H2S检测", "H2S"]),
                "SO2": _find(["SO2检测", "SO2"]),
                "NO2": _find(["NO2检测", "NO2"]),
                "NO": _find(["NO检测", "NO"]),
            },
        }


SCHEMA_VERSION = "plc_quality_v1"


def _safe_float(value: Any) -> float | None:
    """Convert values into finite floats for JSON serialization."""
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _safe_int(value: Any) -> int:
    """Convert values into safe ints with zero fallback."""
    try:
        return int(value)
    except Exception:
        return 0


def _clean_json_value(value: Any) -> Any:
    """Recursively convert pandas/numpy/timestamp values into JSON-safe values."""
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
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _to_datetime_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    """Return a parsed datetime series or an empty datetime series."""
    if column is None or column not in df.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(df[column], errors="coerce")


def _to_numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    """Return a numeric series or an empty float series."""
    if column is None or column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _missing_rate(df: pd.DataFrame, column: str | None) -> float:
    """Compute missing rate for a numeric PLC column."""
    if column is None or column not in df.columns:
        return 1.0
    series = pd.to_numeric(df[column], errors="coerce")
    if len(series) == 0:
        return 1.0
    return float(series.isna().mean())


def _guess_gas_value_type(series: pd.Series) -> str:
    """Guess whether a gas field behaves like concentration, alarm flag, or unknown."""
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return "unknown"

    unique_values = sorted(set(float(value) for value in numeric.unique().tolist()))
    unique_count = len(unique_values)
    if unique_count <= 3 and all(value in {0.0, 1.0} for value in unique_values):
        return "alarm_flag"
    if unique_count <= 4 and len(numeric) >= 10 and unique_count / max(len(numeric), 1) <= 0.05:
        return "alarm_flag"
    if unique_count >= 6:
        return "concentration"
    if numeric.max() > 5 and unique_count >= 4:
        return "concentration"
    return "unknown"


def check_plc_quality(
    df: pd.DataFrame,
    date: str | None = None,
) -> dict[str, Any]:
    """Check daily PLC data quality without producing engineering conclusions."""
    warnings: list[str] = []
    try:
        frame = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
        resolved = resolve_plc_columns(frame)
        time_col = resolved.get("time_col")
        chainage_col = "chainage" if "chainage" in frame.columns else resolved.get("chainage_col")
        motion_cols = resolved.get("motion_cols", {}) if isinstance(resolved, dict) else {}
        gas_cols = resolved.get("gas_cols", {}) if isinstance(resolved, dict) else {}

        time_series = _to_datetime_series(frame, time_col)
        valid_time = time_series.dropna().sort_values()
        duplicate_time_count = _safe_int(valid_time.duplicated().sum()) if not valid_time.empty else 0
        is_monotonic = bool(valid_time.is_monotonic_increasing) if not valid_time.empty else False
        time_diffs = valid_time.diff().dt.total_seconds().dropna()
        positive_diffs = time_diffs[time_diffs > 0]
        median_interval = _safe_float(positive_diffs.median()) if not positive_diffs.empty else None
        p95_interval = _safe_float(positive_diffs.quantile(0.95)) if not positive_diffs.empty else None
        large_gap_threshold = None
        if median_interval is not None:
            large_gap_threshold = max(5.0 * median_interval, 300.0)
        elif p95_interval is not None:
            large_gap_threshold = max(300.0, p95_interval)
        large_gap_count = 0
        if large_gap_threshold is not None and not positive_diffs.empty:
            large_gap_count = _safe_int((positive_diffs > large_gap_threshold).sum())

        chainage_series = _to_numeric_series(frame, chainage_col)
        valid_chainage = chainage_series.dropna()
        start_chainage = _safe_float(valid_chainage.iloc[0]) if not valid_chainage.empty else None
        end_chainage = _safe_float(valid_chainage.iloc[-1]) if not valid_chainage.empty else None
        advance_length = None
        negative_step_count = 0
        large_jump_count = 0
        zero_or_static_ratio = None
        if not valid_chainage.empty:
            advance_length = _safe_float(valid_chainage.iloc[-1] - valid_chainage.iloc[0])
            diffs = valid_chainage.diff().dropna()
            if not diffs.empty:
                negative_step_count = _safe_int((diffs < -1e-6).sum())
                large_jump_count = _safe_int((diffs.abs() > 10.0).sum())
                zero_or_static_ratio = _safe_float((diffs.abs() <= 1e-6).mean())

        missing_rate = {
            "推进速度": _missing_rate(frame, motion_cols.get("advance_speed")),
            "推力": _missing_rate(frame, motion_cols.get("thrust")),
            "刀盘扭矩": _missing_rate(frame, motion_cols.get("torque")),
            "刀盘实际转速": _missing_rate(frame, motion_cols.get("rpm")),
        }
        for field_name, rate in missing_rate.items():
            if rate >= 1.0:
                warnings.append(f"{field_name} 字段缺失或全空。")

        gas_field_diagnostics = {}
        for canonical_gas, column in gas_cols.items():
            column_name = column or (f"{canonical_gas}检测" if canonical_gas not in {"CH4", "CO2"} else f"{canonical_gas}检测")
            if column is None or column not in frame.columns:
                gas_field_diagnostics[column_name] = {
                    "exists": False,
                    "value_type_guess": "unknown",
                    "min": None,
                    "max": None,
                    "unique_count": 0,
                    "non_null_count": 0,
                    "unit_assumption": PLC_UNIT_ASSUMPTIONS.get(column_name),
                    "warning": "字段不存在。",
                }
                continue

            numeric = pd.to_numeric(frame[column], errors="coerce").dropna()
            guess = _guess_gas_value_type(frame[column])
            warning = None
            if guess == "alarm_flag":
                warning = "该字段疑似报警量，不宜直接按浓度值解释。"
            elif guess == "unknown":
                warning = "该字段单位或含义未确认，需谨慎解释。"

            gas_field_diagnostics[column] = {
                "exists": True,
                "value_type_guess": guess,
                "min": _safe_float(numeric.min()) if not numeric.empty else None,
                "max": _safe_float(numeric.max()) if not numeric.empty else None,
                "unique_count": _safe_int(numeric.nunique()) if not numeric.empty else 0,
                "non_null_count": _safe_int(numeric.shape[0]),
                "unit_assumption": PLC_UNIT_ASSUMPTIONS.get(column),
                "warning": warning,
            }
            if warning:
                warnings.append(f"{column}: {warning}")

        report = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "date": date,
            "row_count": _safe_int(len(frame)),
            "time": {
                "time_col": time_col,
                "valid_time_count": _safe_int(valid_time.shape[0]),
                "duplicate_time_count": duplicate_time_count,
                "is_monotonic": is_monotonic,
                "sample_interval_sec_median": median_interval,
                "sample_interval_sec_p95": p95_interval,
                "large_gap_count": large_gap_count,
                "large_gap_threshold_sec": _safe_float(large_gap_threshold),
            },
            "chainage": {
                "chainage_col": chainage_col,
                "valid_chainage_count": _safe_int(valid_chainage.shape[0]),
                "start_chainage": start_chainage,
                "end_chainage": end_chainage,
                "advance_length_m": advance_length,
                "negative_step_count": negative_step_count,
                "large_jump_count": large_jump_count,
                "large_jump_threshold_m": 10.0,
                "zero_or_static_ratio": zero_or_static_ratio,
            },
            "missing_rate": missing_rate,
            "gas_field_diagnostics": gas_field_diagnostics,
            "warnings": warnings,
        }
        return _clean_json_value(report)
    except Exception as exc:  # pragma: no cover - defensive runtime fallback
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "date": date,
            "row_count": _safe_int(len(df)) if isinstance(df, pd.DataFrame) else 0,
            "time": {},
            "chainage": {},
            "missing_rate": {},
            "gas_field_diagnostics": {},
            "warnings": [f"PLC 质量检查失败：{exc}"],
        }
