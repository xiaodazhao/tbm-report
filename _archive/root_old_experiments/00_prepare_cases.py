"""Prepare candidate experiment cases from available TBM data."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    CASES_DIR,
    available_dates,
    build_cst_state,
    classify_case_type,
    draft_cases_from_dates,
    ensure_experiment_dirs,
    load_case_context,
    pick_balanced_cases,
    summarize_case_metrics,
    write_case_csv,
    write_rows_csv,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Prepare experiment case candidates from available TBM data.")
    parser.add_argument(
        "--output",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="Output CSV path for the selected case list.",
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=CASES_DIR / "case_candidates.csv",
        help="Output CSV path for all scored candidate dates.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum number of selected cases.",
    )
    parser.add_argument(
        "--dates",
        nargs="*",
        default=None,
        help="Optional explicit date list in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--draft-only",
        action="store_true",
        help="Skip analysis and only create a blank draft from the provided dates.",
    )
    return parser.parse_args()


def _draft_mode(args: argparse.Namespace) -> None:
    """Write a plain draft case list without running analysis."""
    dates = args.dates or available_dates(limit=args.limit)
    rows = draft_cases_from_dates(dates)
    write_case_csv(args.output, rows)
    print(f"Wrote {len(rows)} draft cases to {args.output}")


def main() -> None:
    """Generate a balanced candidate case list."""
    args = parse_args()
    ensure_experiment_dirs()

    if args.draft_only:
        _draft_mode(args)
        return

    dates = args.dates or available_dates()
    if not dates:
        write_case_csv(args.output, [])
        write_rows_csv(args.candidate_output, [])
        print(
            "No CSV dates were found in the current DATA_DIR. "
            f"Wrote an empty case list to {args.output}."
        )
        return

    candidate_rows = []
    for date in dates:
        base_case = {
            "case_id": "",
            "date": date,
            "time_start": "",
            "time_end": "",
            "chainage_start": None,
            "chainage_end": None,
            "case_type": "",
            "reason": "",
        }
        try:
            context = load_case_context(base_case)
            state = build_cst_state(base_case, context)
            metrics = summarize_case_metrics(base_case, context, state)
            case_type, reason, score = classify_case_type(metrics)
            row = {
                **base_case,
                "case_type": case_type,
                "reason": reason,
                "selection_score": round(float(score), 4),
                **metrics,
            }
            candidate_rows.append(row)
            print(
                f"[candidate] {date} -> {case_type} | "
                f"GRS={float(metrics.get('GRS_top') or 0):.2f}, "
                f"RAI={float(metrics.get('RAI_top') or 0):.2f}, "
                f"GRCI={float(metrics.get('GRCI_top') or 0):.2f}"
            )
        except Exception as exc:  # pragma: no cover - data-dependent path
            candidate_rows.append(
                {
                    **base_case,
                    "case_type": "error",
                    "reason": f"analysis failed: {exc}",
                    "selection_score": 0.0,
                }
            )
            print(f"[candidate] {date} -> error: {exc}")

    scored_rows = sorted(
        candidate_rows,
        key=lambda item: (str(item.get("case_type")), -float(item.get("selection_score") or 0)),
    )
    write_rows_csv(args.candidate_output, scored_rows)

    eligible_rows = [row for row in candidate_rows if row.get("case_type") != "error"]
    selected = pick_balanced_cases(eligible_rows, args.limit)
    write_case_csv(args.output, selected)

    print(f"Wrote {len(scored_rows)} scored candidates to {args.candidate_output}")
    print(f"Wrote {len(selected)} selected cases to {args.output}")


if __name__ == "__main__":
    main()
