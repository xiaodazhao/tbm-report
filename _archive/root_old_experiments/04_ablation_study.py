"""Create an ablation plan for CST-LLM experiments."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = ROOT_DIR / "experiments" / "outputs"
CASES_DIR = OUTPUTS_DIR / "cases"
METRICS_DIR = OUTPUTS_DIR / "metrics"


ABLATION_VARIANTS = [
    ("full", "Full CST-LLM", "Complete method with full CST, indicators, and prompt constraints."),
    ("wo_geo", "w/o Geo", "Remove geological evidence state and keep operation-side state only."),
    (
        "wo_alignment",
        "w/o Spatial Alignment",
        "Keep PLC and geology summaries but remove explicit chainage-level alignment.",
    ),
    (
        "wo_constraints",
        "w/o Prompt Constraints",
        "Keep CST but remove cautious wording and evidence boundary constraints.",
    ),
    (
        "wo_indicators",
        "w/o GRS/RAI/GRCI",
        "Keep CST base state but remove indicator-guided attention summarization.",
    ),
]


def ensure_experiment_dirs() -> None:
    """Create the local experiment output directories required by this script."""
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)


def load_case_csv(path: Path) -> list[dict[str, str]]:
    """Load experiment cases from CSV without importing backend-dependent helpers."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write rows to a UTF-8 CSV file."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate an ablation study plan.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=METRICS_DIR / "ablation_plan.csv",
        help="Path for the ablation plan CSV.",
    )
    return parser.parse_args()


def main() -> None:
    """Write a CSV describing ablation variants for each case."""
    args = parse_args()
    ensure_experiment_dirs()
    cases = load_case_csv(args.case_list)
    rows = []
    for case in cases:
        for variant_id, variant_name, description in ABLATION_VARIANTS:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "date": case["date"],
                    "variant_id": variant_id,
                    "variant_name": variant_name,
                    "description": description,
                }
            )
    write_rows_csv(args.output, rows)
    print(f"Wrote ablation plan: {args.output}")


if __name__ == "__main__":
    main()
