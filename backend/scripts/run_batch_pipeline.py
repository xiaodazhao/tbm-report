from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from scripts.batch_io import dates_from_file, parse_dates, resolve_output_dir, write_csv, write_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the current daily pipeline over many dates.")
    parser.add_argument("--date")
    parser.add_argument("--dates")
    parser.add_argument("--date-file")
    parser.add_argument("--class-filter", help="Comma-separated A/B/C/D/E labels.")
    parser.add_argument("--out-dir", default="outputs/batch_pipeline")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--max-dates", type=int)
    parser.add_argument("--no-llm", action="store_true", help="Use template/no-LLM mode. This is the default.")
    args = parser.parse_args()

    dates = _select_dates(args)
    out_dir = resolve_output_dir(args.out_dir)
    payload = run_batch_pipeline(
        dates=dates,
        out_dir=out_dir,
        use_llm=False,
        continue_on_error=args.continue_on_error,
    )
    write_csv(out_dir / "batch_summary.csv", payload["summary_rows"])
    write_json(out_dir / "batch_summary.json", payload["summary"])
    write_csv(out_dir / "batch_error_log.csv", payload["error_rows"])
    print(payload["summary"])


def run_batch_pipeline(
    *,
    dates: list[str],
    out_dir: Path,
    use_llm: bool = False,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    summary_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    for date in dates:
        try:
            result = run_daily_report_pipeline(date, use_llm=use_llm, generation_mode="template" if not use_llm else None)
            target = out_dir / date
            target.mkdir(parents=True, exist_ok=True)
            write_json(target / "scope_summary.json", result.scope_summary)
            write_json(target / "evidence_pack.json", result.prompt_evidence_pack)
            write_json(target / "quality.json", result.quality)
            write_json(target / "trace.json", result.trace)
            write_json(target / "method_metrics.json", result.method_metrics)
            summary_rows.append(_summary_row(date, result, passed=True, error_message=None))
        except Exception as exc:
            error = {
                "date": date,
                "passed": False,
                "error_message": str(exc),
                "traceback_summary": traceback.format_exc(limit=3),
            }
            summary_rows.append(_failed_summary_row(date, error))
            error_rows.append(error)
            if not continue_on_error:
                break
    summary = {
        "date_count": len(dates),
        "passed_count": sum(1 for row in summary_rows if row.get("passed")),
        "failed_count": sum(1 for row in summary_rows if not row.get("passed")),
        "out_dir": str(out_dir),
    }
    return {"summary_rows": summary_rows, "error_rows": error_rows, "summary": summary}


def _summary_row(date: str, result: Any, *, passed: bool, error_message: str | None) -> dict[str, Any]:
    errors = result.quality.get("error_type_counts", {}) if isinstance(result.quality, dict) else {}
    return {
        "date": date,
        "passed": passed,
        "error_message": error_message,
        "construction_state_cells": len(result.construction_state_cells),
        "daily_review_cell_count": len(result.daily_review_cells),
        "forward_attention_cell_count": len(result.forward_attention_cells),
        "local_background_cell_count": len(result.local_background_cells),
        "GRCI_available_count": sum(1 for cell in result.construction_state_cells if cell.GRCI_available),
        "quality_score": result.quality_summary.get("quality_score"),
        "grounding_rate": result.quality_summary.get("grounding_rate"),
        "unsupported_claim_count": result.quality_summary.get("unsupported_claim_count"),
        "numeric_error_count": int(errors.get("E10_NUMERIC_VALUE_UNGROUNDED", 0) or 0) + int(errors.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0) or 0),
        "role_violation_count": sum(int(errors.get(key, 0) or 0) for key in ["E4_FORWARD_AS_EXCAVATED_REVIEW", "E5_BACKGROUND_AS_DAILY_RESPONSE", "E9_SOURCE_ROLE_CONFUSION"]),
        "forbidden_expression_count": int(errors.get("E1_UNSUPPORTED_CLAIM", 0) or 0),
    }


def _failed_summary_row(date: str, error: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": date,
        "passed": False,
        "error_message": error.get("error_message"),
        "construction_state_cells": 0,
        "daily_review_cell_count": 0,
        "forward_attention_cell_count": 0,
        "local_background_cell_count": 0,
        "GRCI_available_count": 0,
        "quality_score": None,
        "grounding_rate": None,
        "unsupported_claim_count": None,
        "numeric_error_count": None,
        "role_violation_count": None,
        "forbidden_expression_count": None,
    }


def _select_dates(args: argparse.Namespace) -> list[str]:
    selected = parse_dates(args.date, args.dates)
    if args.date_file:
        class_filter = set(item.strip() for item in args.class_filter.split(",") if item.strip()) if args.class_filter else None
        selected.extend(dates_from_file(_resolve_backend_path(args.date_file), class_filter=class_filter))
    selected = list(dict.fromkeys(selected))
    if args.max_dates:
        selected = selected[: max(int(args.max_dates), 0)]
    if not selected:
        raise SystemExit("Provide --date, --dates, or --date-file.")
    return selected


def _resolve_backend_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_DIR / path


if __name__ == "__main__":
    main()
