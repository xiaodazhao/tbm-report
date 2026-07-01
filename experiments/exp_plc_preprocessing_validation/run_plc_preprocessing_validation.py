from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from utils.io_utils import get_all_csv_paths  # noqa: E402


STEADY_FIELDS = [
    "steady_state_available",
    "steady_sample_count",
    "steady_ratio",
    "steady_to_working_ratio",
    "steady_speed_mean",
    "steady_thrust_mean",
    "steady_torque_mean",
    "steady_rpm_mean",
    "steady_penetration_mean",
    "steady_cutterhead_power_proxy",
    "steady_thrust_per_penetration",
    "steady_torque_per_penetration",
    "steady_state_fallback_used",
    "steady_state_fallback_reason",
    "plc_preprocessing_quality_grade",
    "plc_preprocessing_quality_reason",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate paper-based PLC preprocessing outputs.")
    parser.add_argument("--dates", help="Comma-separated dates. Defaults to all available PLC CSV dates.")
    parser.add_argument("--out-dir", default="experiments/exp_plc_preprocessing_validation/outputs")
    parser.add_argument("--max-dates", type=int)
    args = parser.parse_args()

    dates = _parse_dates(args.dates) or _all_dates()
    if args.max_dates:
        dates = dates[: max(args.max_dates, 0)]
    out_dir = _resolve(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    daily_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for date in dates:
        try:
            result = run_daily_report_pipeline(date, use_llm=False, generation_mode="template")
            cells = [cell.model_dump() for cell in result.construction_state_cells]
            cell_response = result.cell_response_records
            daily_rows.append(_daily_summary(date, result, cell_response))
            for row in cell_response:
                cell = _matching_cell(row.get("cell_id"), cells)
                cell_rows.append(_cell_summary(date, row, cell))
        except Exception as exc:  # pragma: no cover - script safety
            errors.append(
                {
                    "date": date,
                    "error": str(exc),
                    "traceback_summary": traceback.format_exc(limit=3),
                }
            )

    coverage = _coverage_summary(dates, daily_rows, cell_rows, errors)
    _write_csv(out_dir / "plc_preprocessing_daily_summary.csv", daily_rows)
    _write_csv(out_dir / "plc_preprocessing_cell_summary.csv", cell_rows)
    _write_csv(out_dir / "plc_preprocessing_coverage_summary.csv", [coverage])
    _write_csv(out_dir / "plc_preprocessing_quality_grade_summary.csv", _grade_summary(cell_rows))
    _write_json(out_dir / "plc_preprocessing_overall_summary.json", coverage)
    _write_text(out_dir / "plc_preprocessing_report.md", _report(coverage, errors))
    if errors:
        _write_csv(out_dir / "plc_preprocessing_error_log.csv", errors)
    print(json.dumps(coverage, ensure_ascii=False, indent=2))


def _daily_summary(date: str, result: Any, cell_response: list[dict[str, Any]]) -> dict[str, Any]:
    raw_count = sum(int(row.get("raw_sample_count") or row.get("sample_count") or 0) for row in cell_response)
    shutdown_count = sum(int(row.get("shutdown_sample_count") or 0) for row in cell_response)
    outlier_count = sum(int(row.get("outlier_sample_count") or 0) for row in cell_response)
    steady_available = sum(1 for row in cell_response if row.get("steady_state_available"))
    fallback_count = sum(1 for row in cell_response if row.get("steady_state_fallback_used"))
    return {
        "date": date,
        "raw_sample_count": raw_count,
        "shutdown_sample_count": shutdown_count,
        "shutdown_ratio": _ratio(shutdown_count, raw_count),
        "outlier_sample_count": outlier_count,
        "outlier_ratio": _ratio(outlier_count, raw_count),
        "cell_response_count": len(cell_response),
        "steady_state_available_cell_count": steady_available,
        "steady_state_fallback_cell_count": fallback_count,
        "warnings": "; ".join(result.warnings or []),
    }


def _cell_summary(date: str, row: dict[str, Any], cell: dict[str, Any] | None) -> dict[str, Any]:
    out = {
        "date": date,
        "cell_id": row.get("cell_id"),
        "cell_start": row.get("cell_start"),
        "cell_end": row.get("cell_end"),
        "cell_role": (cell or {}).get("cell_role"),
        "RAI": row.get("RAI"),
        "GRCI": (cell or {}).get("GRCI"),
        "GRCI_available": (cell or {}).get("GRCI_available"),
        "raw_sample_count": row.get("raw_sample_count") or row.get("sample_count"),
        "working_sample_count": row.get("working_sample_count"),
    }
    for field in STEADY_FIELDS:
        out[field] = row.get(field)
    return out


def _coverage_summary(
    dates: list[str],
    daily_rows: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    total_cells = len(cell_rows)
    steady_cells = sum(1 for row in cell_rows if row.get("steady_state_available"))
    fallback_cells = sum(1 for row in cell_rows if row.get("steady_state_fallback_used"))
    return {
        "total_dates": len(dates),
        "success_count": len(daily_rows),
        "failed_count": len(errors),
        "total_daily_review_cell_count": sum(1 for row in cell_rows if row.get("cell_role") == "daily_review"),
        "steady_state_available_cell_count": steady_cells,
        "steady_state_fallback_cell_count": fallback_cells,
        "steady_state_unavailable_cell_count": total_cells - steady_cells - fallback_cells,
        "steady_metrics_coverage_rate": _ratio(steady_cells, total_cells),
        "fallback_rate": _ratio(fallback_cells, total_cells),
        "quality_grade_A_count": _grade_count(cell_rows, "A"),
        "quality_grade_B_count": _grade_count(cell_rows, "B"),
        "quality_grade_C_count": _grade_count(cell_rows, "C"),
        "quality_grade_D_count": _grade_count(cell_rows, "D"),
    }


def _grade_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for grade in ["A", "B", "C", "D"]:
        out.append({"grade": grade, "count": _grade_count(rows, grade)})
    return out


def _grade_count(rows: list[dict[str, Any]], grade: str) -> int:
    return sum(1 for row in rows if str(row.get("plc_preprocessing_quality_grade")) == grade)


def _matching_cell(cell_id: Any, cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    for cell in cells:
        if str(cell.get("cell_id")) == str(cell_id):
            return cell
    return None


def _all_dates() -> list[str]:
    dates = []
    for path in get_all_csv_paths():
        raw = path.stem.replace("tbm_data_", "")
        try:
            dates.append(pd.to_datetime(raw, format="%Y%m%d").strftime("%Y-%m-%d"))
        except Exception:
            continue
    return sorted(dates)


def _parse_dates(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return None if not denominator else float(numerator) / float(denominator)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _report(summary: dict[str, Any], errors: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# PLC preprocessing validation report",
            "",
            f"- total_dates: {summary.get('total_dates')}",
            f"- success_count: {summary.get('success_count')}",
            f"- failed_count: {summary.get('failed_count')}",
            f"- steady_metrics_coverage_rate: {summary.get('steady_metrics_coverage_rate')}",
            f"- fallback_rate: {summary.get('fallback_rate')}",
            "",
            "This validation reads the current daily pipeline outputs and does not run LLM.",
            "The steady-state fields are PLC response evidence for excavated review cells only.",
            "",
            "## Errors",
            *(f"- {item.get('date')}: {item.get('error')}" for item in errors),
        ]
    )


if __name__ == "__main__":
    main()
