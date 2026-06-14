from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.batch_io import json_safe, resolve_output_dir, safe_float, safe_int, write_csv, write_json


ERROR_COLUMNS = [
    "E3_GRCI_AS_PROBABILITY",
    "E10_NUMERIC_VALUE_UNGROUNDED",
    "E13_STOP_REASON_OVERINTERPRETATION",
    "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze exported batch pipeline method metrics.")
    parser.add_argument("--input-dir", default="outputs/batch_pipeline")
    parser.add_argument("--out-dir", default="outputs/analysis/batch_metrics")
    args = parser.parse_args()

    payload = analyze_batch_metrics(input_dir=_backend_path(args.input_dir), out_dir=resolve_output_dir(args.out_dir))
    print(payload["summary"])


def analyze_batch_metrics(*, input_dir: Path, out_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for date_dir in _date_dirs(input_dir):
        row, row_warnings = _read_date_metrics(date_dir)
        rows.append(row)
        warnings.extend(row_warnings)

    write_csv(out_dir / "batch_method_metrics_summary.csv", rows)
    write_json(out_dir / "batch_method_metrics_summary.json", {"rows": rows, "warnings": warnings})
    write_csv(out_dir / "quality_distribution.csv", _quality_distribution(rows))
    write_csv(out_dir / "error_type_distribution.csv", _error_type_distribution(rows))
    write_csv(out_dir / "grci_availability_distribution.csv", _availability_distribution(rows))
    write_csv(out_dir / "cell_role_distribution.csv", _cell_role_distribution(rows))

    summary = _summary(rows, warnings)
    write_json(out_dir / "batch_analysis_summary.json", summary)
    return {"rows": rows, "warnings": warnings, "summary": summary}


def _read_date_metrics(date_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    date = date_dir.name
    method = _read_json(date_dir / "method_metrics.json", warnings, date)
    quality = _read_json(date_dir / "quality.json", warnings, date)
    trace = _read_json(date_dir / "trace.json", warnings, date)
    summary = _read_json(date_dir / "summary.json", warnings, date)

    scope = _dict(method.get("scope_summary") or summary.get("scope_summary"))
    daily_plc_range = _dict(scope.get("daily_plc_range"))
    daily_scope = _dict(scope.get("daily_excavated_scope"))
    errors = _dict(method.get("error_type_counts") or quality.get("error_type_counts"))

    row = {
        "date": method.get("date") or summary.get("date") or date,
        "passed": _coalesce(method.get("passed"), summary.get("passed")),
        "cell_size_m": _coalesce(method.get("cell_size_m"), scope.get("cell_length_m"), summary.get("cell_size_m")),
        "daily_advance_m": _coalesce(method.get("daily_advance_m"), scope.get("daily_advance_m"), summary.get("daily_advance_m")),
        "daily_plc_range_start": _coalesce(daily_plc_range.get("start_chainage"), method.get("daily_chainage_min"), scope.get("daily_chainage_min")),
        "daily_plc_range_end": _coalesce(daily_plc_range.get("end_chainage"), method.get("daily_chainage_max"), scope.get("daily_chainage_max")),
        "daily_excavated_scope_start": daily_scope.get("start"),
        "daily_excavated_scope_end": daily_scope.get("end"),
        "construction_state_cell_count": _coalesce(method.get("construction_state_cell_count"), summary.get("construction_state_cells_row_count")),
        "daily_review_cell_count": _coalesce(method.get("daily_review_cell_count"), summary.get("daily_review_cell_count")),
        "forward_attention_cell_count": _coalesce(method.get("forward_attention_cell_count"), summary.get("forward_attention_cell_count")),
        "local_background_cell_count": _coalesce(method.get("local_background_cell_count"), summary.get("local_background_cell_count")),
        "RAI_available_count": method.get("RAI_available_count"),
        "GRS_available_count": method.get("GRS_available_count"),
        "GRCI_available_count": _coalesce(method.get("GRCI_available_count"), summary.get("grci_available_count")),
        "high_grci_cell_count": _coalesce(summary.get("high_grci_cell_count"), method.get("high_priority_cell_count")),
        "medium_grci_cell_count": method.get("medium_priority_cell_count"),
        "low_grci_cell_count": method.get("low_priority_cell_count"),
        "quality_score": _coalesce(method.get("quality_score"), _quality_score(quality), summary.get("quality_score")),
        "grounding_rate": _coalesce(method.get("grounding_rate"), _grounding_rate(quality), summary.get("grounding_rate")),
        "trace_coverage": _coalesce(method.get("trace_coverage"), trace.get("trace_coverage"), _dict(trace.get("summary")).get("trace_coverage")),
        "claim_count": _coalesce(method.get("claim_count"), _grounding_summary(quality).get("claim_count")),
        "grounded_claim_count": _coalesce(method.get("grounded_claim_count"), _grounding_summary(quality).get("grounded_claim_count")),
        "unsupported_claim_count": _coalesce(method.get("unsupported_claim_count"), _grounding_summary(quality).get("unsupported_claim_count"), summary.get("unsupported_claim_count")),
        "warning_count": len(method.get("warnings") or summary.get("warnings") or []),
    }
    for key in ERROR_COLUMNS:
        row[key] = safe_int(errors.get(key))
    for key, value in errors.items():
        row.setdefault(str(key), safe_int(value))
    return row, warnings


def _read_json(path: Path, warnings: list[dict[str, Any]], date: str) -> dict[str, Any]:
    if not path.exists():
        warnings.append({"date": date, "kind": "missing_file", "path": str(path)})
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append({"date": date, "kind": "read_failed", "path": str(path), "message": str(exc)})
        return {}
    return value if isinstance(value, dict) else {}


def _date_dirs(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(path for path in input_dir.iterdir() if path.is_dir())


def _summary(rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    quality = [safe_float(row.get("quality_score")) for row in rows if safe_float(row.get("quality_score")) is not None]
    grounding = [safe_float(row.get("grounding_rate")) for row in rows if safe_float(row.get("grounding_rate")) is not None]
    return {
        "date_count": len(rows),
        "passed_count": sum(1 for row in rows if bool(row.get("passed"))),
        "failed_count": sum(1 for row in rows if row.get("passed") is False),
        "warning_count": len(warnings),
        "average_quality_score": sum(quality) / len(quality) if quality else None,
        "average_grounding_rate": sum(grounding) / len(grounding) if grounding else None,
    }


def _quality_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_stats(rows, "quality_score"), _stats(rows, "grounding_rate"), _stats(rows, "trace_coverage")]


def _error_type_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({key for row in rows for key in row if str(key).startswith("E")})
    return [{"error_type": key, "count": sum(safe_int(row.get(key)) for row in rows)} for key in keys]


def _availability_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"metric": "RAI_available_count", "total": sum(safe_int(row.get("RAI_available_count")) for row in rows)},
        {"metric": "GRS_available_count", "total": sum(safe_int(row.get("GRS_available_count")) for row in rows)},
        {"metric": "GRCI_available_count", "total": sum(safe_int(row.get("GRCI_available_count")) for row in rows)},
    ]


def _cell_role_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"cell_role": "daily_review", "total": sum(safe_int(row.get("daily_review_cell_count")) for row in rows)},
        {"cell_role": "forward_attention", "total": sum(safe_int(row.get("forward_attention_cell_count")) for row in rows)},
        {"cell_role": "local_background", "total": sum(safe_int(row.get("local_background_cell_count")) for row in rows)},
    ]


def _stats(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [safe_float(row.get(key)) for row in rows if safe_float(row.get(key)) is not None]
    series = pd.Series(values, dtype=float)
    return {
        "metric": key,
        "count": int(len(values)),
        "mean": float(series.mean()) if not series.empty else None,
        "median": float(series.median()) if not series.empty else None,
        "min": float(series.min()) if not series.empty else None,
        "max": float(series.max()) if not series.empty else None,
    }


def _grounding_summary(quality: dict[str, Any]) -> dict[str, Any]:
    return _dict(quality.get("grounding_summary") or quality.get("stats"))


def _quality_score(quality: dict[str, Any]) -> Any:
    return _coalesce(quality.get("score"), _dict(quality.get("summary")).get("quality_score"))


def _grounding_rate(quality: dict[str, Any]) -> Any:
    return _grounding_summary(quality).get("grounding_rate")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _backend_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


if __name__ == "__main__":
    main()
