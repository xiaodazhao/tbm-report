"""Export Construction State Twin payloads for experiment cases."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    CASES_DIR,
    STATES_DIR,
    build_cst_state,
    ensure_experiment_dirs,
    flatten_state_summary,
    load_case_context,
    load_case_csv,
    write_json,
    write_rows_csv,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Export CST states for all experiment cases.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=STATES_DIR,
        help="Output directory for state JSON files.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=STATES_DIR / "state_summary.csv",
        help="Output CSV for compact state summaries.",
    )
    return parser.parse_args()


def main() -> None:
    """Export case-level CST states."""
    args = parse_args()
    ensure_experiment_dirs()
    cases = load_case_csv(args.case_list)
    summary_rows = []
    for case in cases:
        context = load_case_context(case)
        state = build_cst_state(case, context)
        out_path = args.out_dir / f"{case['case_id']}_state.json"
        write_json(out_path, state)
        summary_rows.append(flatten_state_summary(state))
        print(f"Exported CST state: {out_path}")
    write_rows_csv(args.summary_csv, summary_rows)
    print(f"Wrote state summary CSV: {args.summary_csv}")


if __name__ == "__main__":
    main()
