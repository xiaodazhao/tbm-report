from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline
from scripts.batch_io import dates_from_file, parse_dates, resolve_output_dir, write_csv, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 5m/10m cell size sensitivity without changing default pipeline.")
    parser.add_argument("--date")
    parser.add_argument("--dates")
    parser.add_argument("--date-file")
    parser.add_argument("--cell-sizes", default="5,10", help="Comma-separated cell sizes. Defaults to 5,10.")
    parser.add_argument("--out-dir", default="outputs/analysis/cell_size")
    args = parser.parse_args()

    dates = parse_dates(args.date, args.dates)
    if args.date_file:
        dates.extend(dates_from_file(_backend_path(args.date_file)))
    dates = list(dict.fromkeys(dates))
    if not dates:
        raise SystemExit("Provide --date, --dates, or --date-file.")
    cell_sizes = [float(item.strip()) for item in args.cell_sizes.split(",") if item.strip()]
    payload = analyze_cell_size_sensitivity(dates=dates, cell_sizes=cell_sizes, out_dir=resolve_output_dir(args.out_dir))
    print(payload["summary"])


def analyze_cell_size_sensitivity(*, dates: list[str], cell_sizes: list[float], out_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for date in dates:
        for cell_size in cell_sizes:
            if cell_size > 10.0:
                rows.append(_warning_row(date, cell_size, "cell_size_m larger than recommended maximum for daily report review"))
                continue
            try:
                result = run_daily_report_pipeline(date, use_llm=False, generation_mode="template", cell_size_m=cell_size)
                rows.append(_result_row(date, cell_size, result, passed=True, error_message=None))
            except Exception as exc:
                rows.append(_warning_row(date, cell_size, str(exc), passed=False))
    comparison = _comparison_rows(rows)
    summary = {
        "date_count": len(dates),
        "cell_sizes": cell_sizes,
        "passed_count": sum(1 for row in rows if row.get("passed")),
        "failed_count": sum(1 for row in rows if row.get("passed") is False),
        "note": "daily_plc_range should remain unchanged; daily_excavated_scope may change with cell alignment.",
    }
    write_csv(out_dir / "cell_size_sensitivity_summary.csv", rows)
    write_json(out_dir / "cell_size_sensitivity_summary.json", {"summary": summary, "rows": rows})
    write_csv(out_dir / "cell_size_comparison_by_date.csv", comparison)
    return {"summary": summary, "rows": rows, "comparison": comparison}


def _result_row(date: str, cell_size: float, result: Any, *, passed: bool, error_message: str | None) -> dict[str, Any]:
    scope = result.scope_summary or {}
    daily_plc = scope.get("daily_plc_range") or {}
    daily_scope = scope.get("daily_excavated_scope") or {}
    return {
        "date": date,
        "cell_size_m": cell_size,
        "passed": passed,
        "error_message": error_message,
        "daily_plc_range_start": daily_plc.get("start_chainage") or scope.get("daily_chainage_min"),
        "daily_plc_range_end": daily_plc.get("end_chainage") or scope.get("daily_chainage_max"),
        "daily_advance_m": scope.get("daily_advance_m"),
        "daily_excavated_scope_start": daily_scope.get("start"),
        "daily_excavated_scope_end": daily_scope.get("end"),
        "construction_state_cell_count": len(result.construction_state_cells),
        "GRCI_available_count": result.method_metrics.get("GRCI_available_count"),
        "high_attention_cell_count": len(result.high_grci_cells),
        "grounding_rate": result.quality_summary.get("grounding_rate"),
        "unsupported_claim_count": result.quality_summary.get("unsupported_claim_count"),
        "warnings": result.warnings,
    }


def _warning_row(date: str, cell_size: float, message: str, *, passed: bool = False) -> dict[str, Any]:
    return {"date": date, "cell_size_m": cell_size, "passed": passed, "error_message": message, "warnings": [message]}


def _comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_date.setdefault(str(row.get("date")), []).append(row)
    for date, items in by_date.items():
        if len(items) < 2:
            continue
        base = sorted(items, key=lambda item: float(item.get("cell_size_m") or 0))[0]
        for row in items:
            out.append(
                {
                    "date": date,
                    "base_cell_size_m": base.get("cell_size_m"),
                    "cell_size_m": row.get("cell_size_m"),
                    "daily_plc_range_stable": (
                        row.get("daily_plc_range_start") == base.get("daily_plc_range_start")
                        and row.get("daily_plc_range_end") == base.get("daily_plc_range_end")
                    ),
                    "construction_state_cell_delta": _num(row.get("construction_state_cell_count")) - _num(base.get("construction_state_cell_count")),
                    "GRCI_available_delta": _num(row.get("GRCI_available_count")) - _num(base.get("GRCI_available_count")),
                    "unsupported_claim_delta": _num(row.get("unsupported_claim_count")) - _num(base.get("unsupported_claim_count")),
                }
            )
    return out


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _backend_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


if __name__ == "__main__":
    main()
