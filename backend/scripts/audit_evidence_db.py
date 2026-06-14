from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import EVIDENCE_DB_PATH  # noqa: E402
from scripts.batch_io import resolve_output_dir, safe_float, write_csv, write_json  # noqa: E402


DATE_COLUMNS = ["date", "source_date", "report_date", "available_date", "analysis_date", "created_date"]
SOURCE_COLUMNS = ["source_type_norm", "source_type", "source"]
ROLE_COLUMNS = ["evidence_report_role", "evidence_role", "role"]
START_COLUMNS = ["start_chainage", "start_num", "start"]
END_COLUMNS = ["end_chainage", "end_num", "end"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the multi-source geology evidence table.")
    parser.add_argument("--evidence-path", default=str(EVIDENCE_DB_PATH))
    parser.add_argument("--out-dir", default="outputs/audit")
    args = parser.parse_args()

    payload = audit_evidence_db(evidence_path=Path(args.evidence_path))
    out_dir = resolve_output_dir(args.out_dir)
    write_csv(out_dir / "evidence_db_audit.csv", payload["rows"])
    write_json(out_dir / "evidence_db_audit.json", payload)
    print(f"Evidence audit written to {out_dir}")
    print(payload["summary"])


def audit_evidence_db(*, evidence_path: Path) -> dict[str, Any]:
    if not evidence_path.exists():
        row = _empty_row("unknown_date")
        row["warnings"] = [f"evidence table not found: {evidence_path}"]
        return {
            "schema_version": "evidence_db_audit_v1",
            "evidence_path": str(evidence_path),
            "rows": [row],
            "summary": {"total_evidence_count": 0, "date_count": 0, "warnings": row["warnings"]},
        }
    try:
        frame = pd.read_csv(evidence_path)
    except Exception as exc:
        row = _empty_row("unknown_date")
        row["warnings"] = [f"read failed: {exc}", traceback.format_exc(limit=2)]
        return {
            "schema_version": "evidence_db_audit_v1",
            "evidence_path": str(evidence_path),
            "rows": [row],
            "summary": {"total_evidence_count": 0, "date_count": 0, "warnings": row["warnings"]},
        }

    date_col = _find_col(frame, DATE_COLUMNS)
    if date_col:
        dates = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        work = frame.copy()
        work["__audit_date"] = dates.fillna("unknown_date")
    else:
        work = frame.copy()
        work["__audit_date"] = "unknown_date"

    rows = [_audit_group(str(date), group.copy()) for date, group in work.groupby("__audit_date", dropna=False)]
    summary = {
        "total_evidence_count": int(len(frame)),
        "date_count": len(rows),
        "date_column": date_col,
        "global_source_type_counts": _source_counts(frame),
        "missing_date_count": int(work["__audit_date"].eq("unknown_date").sum()),
        "warnings": [] if date_col else ["no date-like evidence column found; grouped as unknown_date"],
    }
    return {
        "schema_version": "evidence_db_audit_v1",
        "evidence_path": str(evidence_path),
        "rows": rows,
        "summary": summary,
    }


def _audit_group(date: str, group: pd.DataFrame) -> dict[str, Any]:
    source_col = _find_col(group, SOURCE_COLUMNS)
    role_col = _find_col(group, ROLE_COLUMNS)
    start_col = _find_col(group, START_COLUMNS)
    end_col = _find_col(group, END_COLUMNS)
    source = group[source_col].astype(str) if source_col else pd.Series("", index=group.index)
    source_lower = source.str.lower()
    source_upper = source.str.upper()
    role = group[role_col].astype(str).str.lower() if role_col else pd.Series("", index=group.index)
    start = pd.to_numeric(group[start_col], errors="coerce") if start_col else pd.Series(float("nan"), index=group.index)
    end = pd.to_numeric(group[end_col], errors="coerce") if end_col else pd.Series(float("nan"), index=group.index)
    has_start_end = start.notna() & end.notna()
    valid_geometry = has_start_end & (start <= end)
    invalid_geometry = has_start_end & (start > end)
    missing_chainage = ~has_start_end

    return {
        "date": date or "unknown_date",
        "total_evidence_count": int(len(group)),
        "TSP_count": int(source_upper.str.contains("TSP", na=False).sum()),
        "HSP_count": int(source_lower.str.contains("hsp|sonic", regex=True, na=False).sum()),
        "sketch_count": int(source_lower.str.contains("sketch|face", regex=True, na=False).sum()),
        "forecast_count": int(role.str.contains("forecast|prediction|forward", regex=True, na=False).sum()),
        "observed_count": int(role.str.contains("observed|daily_review", regex=True, na=False).sum()),
        "background_count": int(role.str.contains("background|local_background", regex=True, na=False).sum()),
        "missing_chainage_count": int(missing_chainage.sum()),
        "missing_date_count": int(date == "unknown_date") * int(len(group)),
        "invalid_geometry_count": int(invalid_geometry.sum()),
        "valid_geometry_count": int(valid_geometry.sum()),
        "min_start_chainage": safe_float(start.min()) if start.notna().any() else None,
        "max_end_chainage": safe_float(end.max()) if end.notna().any() else None,
        "warnings": _warnings(date, source_col, role_col, start_col, end_col),
    }


def _empty_row(date: str) -> dict[str, Any]:
    return {
        "date": date,
        "total_evidence_count": 0,
        "TSP_count": 0,
        "HSP_count": 0,
        "sketch_count": 0,
        "forecast_count": 0,
        "observed_count": 0,
        "background_count": 0,
        "missing_chainage_count": 0,
        "missing_date_count": 0,
        "invalid_geometry_count": 0,
        "valid_geometry_count": 0,
        "min_start_chainage": None,
        "max_end_chainage": None,
        "warnings": [],
    }


def _find_col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(col).strip().lower(): col for col in frame.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower:
            return str(lower[key])
    for candidate in candidates:
        key = candidate.strip().lower()
        for col in frame.columns:
            if key and key in str(col).strip().lower():
                return str(col)
    return None


def _source_counts(frame: pd.DataFrame) -> dict[str, int]:
    source_col = _find_col(frame, SOURCE_COLUMNS)
    if not source_col:
        return {}
    return {str(key): int(value) for key, value in frame[source_col].astype(str).value_counts().to_dict().items()}


def _warnings(date: str, source_col: str | None, role_col: str | None, start_col: str | None, end_col: str | None) -> list[str]:
    warnings = []
    if date == "unknown_date":
        warnings.append("date column missing or value cannot be parsed")
    if not source_col:
        warnings.append("source type column missing")
    if not role_col:
        warnings.append("evidence role column missing")
    if not start_col or not end_col:
        warnings.append("start/end chainage columns missing")
    return warnings


if __name__ == "__main__":
    main()
