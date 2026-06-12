"""Create traceability review templates from generated reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    CASES_DIR,
    REPORTS_DIR,
    TABLES_DIR,
    DEFAULT_METHODS,
    ensure_experiment_dirs,
    extract_claim_candidates,
    load_case_csv,
    write_rows_csv,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate traceability review sheets from reports.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory containing generated report text files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=TABLES_DIR,
        help="Directory for traceability review CSV files.",
    )
    parser.add_argument(
        "--methods",
        nargs="*",
        default=DEFAULT_METHODS,
        choices=["template", "direct_llm", "cst_llm"],
        help="Methods to include.",
    )
    return parser.parse_args()


def main() -> None:
    """Build traceability review tables for each case and method."""
    args = parse_args()
    ensure_experiment_dirs()
    cases = load_case_csv(args.case_list)
    for case in cases:
        rows = []
        for method in args.methods:
            report_path = args.reports_dir / f"{case['case_id']}_{method}.txt"
            if not report_path.exists():
                continue
            report_text = report_path.read_text(encoding="utf-8")
            for claim_id, claim in enumerate(extract_claim_candidates(report_text), start=1):
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "method": method,
                        "claim_id": claim_id,
                        "report_claim": claim,
                        "claim_type": "",
                        "evidence_source": "",
                        "evidence_field": "",
                        "evidence_text": "",
                        "is_supported": "",
                        "error_type": "",
                    }
                )
        if rows:
            output_path = args.output_dir / f"traceability_{case['case_id']}.csv"
            write_rows_csv(output_path, rows)
            print(f"Wrote traceability sheet: {output_path}")


if __name__ == "__main__":
    main()
