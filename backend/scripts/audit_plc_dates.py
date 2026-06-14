from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from analysis.plc_contract import resolve_plc_columns  # noqa: E402
from config import CONFIG_WARNINGS, DATA_DIR  # noqa: E402
from scripts.batch_io import parse_date_from_name, resolve_output_dir, safe_float, write_csv, write_json  # noqa: E402


PREFERRED_CHAINAGE_COLUMNS = [
    "\u5bfc\u5411\u76fe\u9996\u91cc\u7a0b",
    "chainage",
    "\u5f53\u524d\u91cc\u7a0b",
    "\u5f00\u7d2f\u8fdb\u5c3a",
    "\u91cc\u7a0b",
]
MOTION_FALLBACKS = {
    "advance_speed": ["\u63a8\u8fdb\u901f\u5ea6", "advance_speed", "speed", "actual_speed"],
    "torque": ["\u5200\u76d8\u626d\u77e9", "\u626d\u77e9", "cutter_torque", "torque"],
    "thrust": ["\u63a8\u529b", "\u603b\u63a8\u529b", "thrust", "total_thrust"],
}
GAS_FALLBACKS = [
    "CH4\u68c0\u6d4b",
    "CO2\u68c0\u6d4b",
    "H2S\u68c0\u6d4b",
    "SO2\u68c0\u6d4b",
    "NO2\u68c0\u6d4b",
    "NO\u68c0\u6d4b",
    "CH4",
    "CO2",
    "H2S",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit available daily PLC CSV files.")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Directory containing tbm_data_YYYYMMDD.csv files.")
    parser.add_argument("--out-dir", default="outputs/audit")
    args = parser.parse_args()

    payload = audit_plc_dates(data_dir=Path(args.data_dir))
    out_dir = resolve_output_dir(args.out_dir)
    write_csv(out_dir / "plc_date_audit.csv", payload["rows"])
    write_json(out_dir / "plc_date_audit.json", payload)
    print(f"PLC audit written to {out_dir}")
    print(payload["summary"])


def audit_plc_dates(*, data_dir: Path) -> dict[str, Any]:
    rows = []
    paths = sorted(data_dir.glob("*.csv")) if data_dir.exists() else []
    if not paths:
        rows.append(_empty_row(date=None, file_path=data_dir, reason="no_csv_files_found"))
    for path in paths:
        rows.append(_audit_one_file(path))
    summary = _summary(rows)
    return {
        "schema_version": "plc_date_audit_v1",
        "data_dir": str(data_dir),
        "config_warnings": list(CONFIG_WARNINGS),
        "rows": rows,
        "summary": summary,
    }


def _audit_one_file(path: Path) -> dict[str, Any]:
    date = parse_date_from_name(path.name)
    row = _empty_row(date=date, file_path=path, reason="")
    try:
        if not path.exists():
            row["exclude_reason"] = "file_not_found"
            return row
        frame = pd.read_csv(path)
        row.update(
            {
                "file_exists": True,
                "row_count": int(len(frame)),
                "column_count": int(len(frame.columns)),
                "missing_rate": float(frame.isna().mean().mean()) if len(frame.columns) else None,
            }
        )
        resolved = resolve_plc_columns(frame)
        chainage_col = _find_preferred_chainage_col(frame, resolved.get("chainage_col"))
        time_col = resolved.get("time_col")
        motion_cols = resolved.get("motion_cols", {}) if isinstance(resolved, dict) else {}
        motion_cols = {
            key: motion_cols.get(key) or _find_col(frame, aliases)
            for key, aliases in MOTION_FALLBACKS.items()
        }
        gas_cols = resolved.get("gas_cols", {}) if isinstance(resolved, dict) else {}

        chainage = pd.to_numeric(frame[chainage_col], errors="coerce") if chainage_col in frame.columns else pd.Series(dtype=float)
        valid_chainage = chainage.dropna()
        valid_chainage_ratio = float(valid_chainage.shape[0] / max(len(frame), 1)) if len(frame) else 0.0
        daily_min = safe_float(valid_chainage.iloc[0]) if not valid_chainage.empty else None
        daily_max = safe_float(valid_chainage.iloc[-1]) if not valid_chainage.empty else None
        daily_advance = safe_float(float(valid_chainage.iloc[-1]) - float(valid_chainage.iloc[0])) if len(valid_chainage) else None

        duration_min = None
        if time_col in frame.columns:
            times = pd.to_datetime(frame[time_col], errors="coerce").dropna().sort_values()
            if len(times) >= 2:
                duration_min = safe_float((times.iloc[-1] - times.iloc[0]).total_seconds() / 60.0)

        required_missing = []
        for key in ["advance_speed", "torque", "thrust"]:
            if not motion_cols.get(key):
                required_missing.append(key)
        warnings = []
        if not chainage_col:
            required_missing.append("chainage")
        if row["row_count"] <= 0:
            warnings.append("empty plc file")
        if valid_chainage_ratio <= 0:
            warnings.append("no valid chainage values")

        usable = bool(row["row_count"] > 0 and chainage_col and valid_chainage_ratio > 0 and not required_missing)
        exclude_reason = ""
        if not usable:
            parts = []
            if row["row_count"] <= 0:
                parts.append("empty_file")
            if not chainage_col or valid_chainage_ratio <= 0:
                parts.append("missing_or_invalid_chainage")
            if required_missing:
                parts.append("missing_required_columns:" + ",".join(sorted(set(required_missing))))
            exclude_reason = ";".join(parts)

        row.update(
            {
                "chainage_col_exists": bool(chainage_col),
                "chainage_col_name": chainage_col,
                "daily_chainage_min": daily_min,
                "daily_chainage_max": daily_max,
                "daily_advance_m": daily_advance,
                "duration_min": duration_min,
                "valid_chainage_ratio": valid_chainage_ratio,
                "speed_col_exists": bool(motion_cols.get("advance_speed")),
                "torque_col_exists": bool(motion_cols.get("torque")),
                "thrust_col_exists": bool(motion_cols.get("thrust")),
                "gas_col_exists": any(bool(value) for value in gas_cols.values()) or bool(_find_col(frame, GAS_FALLBACKS)),
                "usable_for_report": usable,
                "exclude_reason": exclude_reason,
                "warnings": warnings,
            }
        )
        return row
    except Exception as exc:
        row["exclude_reason"] = f"read_or_audit_failed:{exc}"
        row["warnings"] = [traceback.format_exc(limit=2)]
        return row


def _empty_row(*, date: str | None, file_path: Path, reason: str) -> dict[str, Any]:
    return {
        "date": date,
        "file_path": str(file_path),
        "file_exists": bool(Path(file_path).exists()),
        "row_count": 0,
        "column_count": 0,
        "chainage_col_exists": False,
        "chainage_col_name": None,
        "daily_chainage_min": None,
        "daily_chainage_max": None,
        "daily_advance_m": None,
        "duration_min": None,
        "missing_rate": None,
        "valid_chainage_ratio": 0.0,
        "speed_col_exists": False,
        "torque_col_exists": False,
        "thrust_col_exists": False,
        "gas_col_exists": False,
        "usable_for_report": False,
        "exclude_reason": reason,
        "warnings": [],
    }


def _find_preferred_chainage_col(frame: pd.DataFrame, fallback: str | None) -> str | None:
    columns = {str(col).strip().lower(): col for col in frame.columns}
    for candidate in PREFERRED_CHAINAGE_COLUMNS:
        if candidate.strip().lower() in columns:
            return columns[candidate.strip().lower()]
    for candidate in PREFERRED_CHAINAGE_COLUMNS:
        for col in frame.columns:
            if candidate in str(col):
                return str(col)
    return fallback


def _find_col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(col).strip().lower(): col for col in frame.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower:
            return str(lower[key])
    for candidate in candidates:
        for col in frame.columns:
            if candidate in str(col):
                return str(col)
    return None


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if row.get("usable_for_report")]
    advances = [float(row["daily_advance_m"]) for row in usable if row.get("daily_advance_m") is not None]
    return {
        "total_dates": len([row for row in rows if row.get("date")]),
        "usable_dates": len(usable),
        "excluded_dates": len(rows) - len(usable),
        "average_daily_advance_m": mean(advances) if advances else None,
        "missing_chainage_dates": [row.get("date") for row in rows if not row.get("chainage_col_exists")],
        "missing_required_columns_dates": [
            row.get("date")
            for row in rows
            if "missing_required_columns" in str(row.get("exclude_reason", ""))
        ],
    }


if __name__ == "__main__":
    main()
