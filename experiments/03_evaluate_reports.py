"""Initialize and aggregate manual evaluation sheets."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from common import (
    CASES_DIR,
    DEFAULT_METHODS,
    METRICS_DIR,
    aggregate_metrics,
    ensure_experiment_dirs,
    evaluation_sheet_rows,
    load_case_csv,
    write_rows_csv,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Initialize or aggregate evaluation sheets.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        default=METRICS_DIR / "evaluation_sheet.csv",
        help="Path for the manual evaluation sheet.",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=METRICS_DIR / "report_metrics.csv",
        help="Path for aggregated metrics output.",
    )
    parser.add_argument(
        "--methods",
        nargs="*",
        default=DEFAULT_METHODS,
        choices=["template", "direct_llm", "cst_llm"],
        help="Methods included in the evaluation sheet.",
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize the evaluation sheet and skip aggregation.",
    )
    return parser.parse_args()


def main() -> None:
    """Create a manual evaluation sheet and optionally aggregate it."""
    args = parse_args()
    ensure_experiment_dirs()
    cases = load_case_csv(args.case_list)
    if not args.sheet.exists():
        rows = evaluation_sheet_rows(cases, args.methods)
        write_rows_csv(args.sheet, rows)
        print(f"Initialized evaluation sheet: {args.sheet}")
    elif args.init_only:
        print(f"Evaluation sheet already exists: {args.sheet}")

    if args.init_only:
        return

    with args.sheet.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    metrics = aggregate_metrics(rows)
    if metrics:
        write_rows_csv(args.metrics, metrics)
        print(f"Wrote aggregated metrics: {args.metrics}")
    else:
        print("No aggregate metrics were written because the evaluation sheet has no completed rows.")


if __name__ == "__main__":
    main()
