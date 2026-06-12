"""Generate multi-source contribution experiment reports."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from common import (
    CASES_DIR,
    METRICS_DIR,
    REPORTS_MULTISOURCE_DIR,
    build_cst_llm_prompt,
    build_cst_llm_prompt_plc_geo,
    build_cst_llm_prompt_wo_geo,
    build_cst_state,
    ensure_experiment_dirs,
    load_case_context,
    load_case_csv,
    maybe_call_llm,
    write_json,
    write_rows_csv,
    write_text,
)


VARIANT_BUILDERS = {
    "plc_only": build_cst_llm_prompt_wo_geo,
    "plc_geo": build_cst_llm_prompt_plc_geo,
    "full": build_cst_llm_prompt,
}

DEFAULT_VARIANTS = [
    {"variant_id": "plc_only", "variant_name": "PLC only"},
    {"variant_id": "plc_geo", "variant_name": "PLC + Geo"},
    {"variant_id": "full", "variant_name": "Full"},
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate multi-source contribution reports.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--core-cases",
        nargs="*",
        default=["C01", "C05", "C06"],
        help="Case ids to include in the multi-source experiment.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPORTS_MULTISOURCE_DIR,
        help="Directory for generated prompts and reports.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPORTS_MULTISOURCE_DIR / "multisource_manifest.csv",
        help="Output CSV manifest describing generated artifacts.",
    )
    parser.add_argument(
        "--mode",
        choices=["prompt_only", "call_llm"],
        default="prompt_only",
        help="Whether to only save prompts or also call the configured LLM.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Optional provider override passed to call_llm.",
    )
    return parser.parse_args()


def write_plan(path: Path, rows: list[dict[str, str]]) -> None:
    """Persist the generated multi-source plan."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "date", "variant_id", "variant_name"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    """Generate prompts and optional reports for each multi-source row."""
    args = parse_args()
    ensure_experiment_dirs()
    all_cases = {row["case_id"]: row for row in load_case_csv(args.case_list)}
    selected_cases = [all_cases[case_id] for case_id in args.core_cases if case_id in all_cases]
    if not selected_cases:
        raise ValueError("No matching cases found for the multi-source experiment.")

    plan_rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []

    for case in selected_cases:
        context = load_case_context(case)
        state = build_cst_state(case, context)
        for variant in DEFAULT_VARIANTS:
            variant_id = variant["variant_id"]
            builder = VARIANT_BUILDERS[variant_id]
            plan_rows.append(
                {
                    "case_id": case["case_id"],
                    "date": case["date"],
                    "variant_id": variant_id,
                    "variant_name": variant["variant_name"],
                }
            )

            write_json(args.out_dir / f"{case['case_id']}_{variant_id}_state_snapshot.json", state)
            prompt = builder(context)
            prompt_path = args.out_dir / f"{case['case_id']}_{variant_id}.prompt.txt"
            write_text(prompt_path, prompt)
            report_text = maybe_call_llm(prompt, mode=args.mode, provider=args.provider)
            if report_text:
                report_path = args.out_dir / f"{case['case_id']}_{variant_id}.txt"
                write_text(report_path, report_text)
                output_path = report_path
            else:
                output_path = prompt_path

            manifest_rows.append(
                {
                    "case_id": case["case_id"],
                    "date": case["date"],
                    "variant_id": variant_id,
                    "variant_name": variant["variant_name"],
                    "path": str(output_path),
                    "mode": args.mode,
                }
            )

    write_plan(METRICS_DIR / "multisource_plan.csv", plan_rows)
    write_rows_csv(args.manifest, manifest_rows)
    print(f"Wrote multi-source manifest: {args.manifest}")


if __name__ == "__main__":
    main()
