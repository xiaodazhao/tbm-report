"""Generate ablation prompts and reports for selected experiment cases."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    CASES_DIR,
    DEFAULT_METHODS,
    METRICS_DIR,
    REPORTS_ABLATION_DIR,
    build_cst_llm_prompt,
    build_cst_llm_prompt_wo_geo,
    build_cst_llm_prompt_wo_alignment,
    build_cst_llm_prompt_wo_constraints,
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
    "full": build_cst_llm_prompt,
    "wo_geo": build_cst_llm_prompt_wo_geo,
    "wo_alignment": build_cst_llm_prompt_wo_alignment,
    "wo_constraints": build_cst_llm_prompt_wo_constraints,
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate ablation experiment reports.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=METRICS_DIR / "ablation_plan_core.csv",
        help="CSV file describing ablation variants to run.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPORTS_ABLATION_DIR,
        help="Directory for generated ablation prompts and reports.",
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
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPORTS_ABLATION_DIR / "ablation_manifest.csv",
        help="Output CSV manifest describing generated ablation artifacts.",
    )
    return parser.parse_args()


def load_ablation_plan(path: Path) -> list[dict[str, str]]:
    """Load the ablation plan CSV."""
    return load_case_csv(path)  # compatible column loader for basic string rows


def load_plan_rows(path: Path) -> list[dict[str, str]]:
    """Load ablation rows while preserving all plan-specific columns."""
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def main() -> None:
    """Generate prompts and optional reports for each ablation row."""
    args = parse_args()
    ensure_experiment_dirs()
    cases = {row["case_id"]: row for row in load_case_csv(args.case_list)}
    plan_rows = load_plan_rows(args.plan)
    manifest_rows = []

    for row in plan_rows:
        case_id = row["case_id"]
        variant_id = row["variant_id"]
        case = cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} from ablation plan is missing in {args.case_list}")
        builder = VARIANT_BUILDERS.get(variant_id)
        if builder is None:
            raise KeyError(f"Unsupported ablation variant: {variant_id}")

        context = load_case_context(case)
        state = build_cst_state(case, context)
        write_json(args.out_dir / f"{case_id}_{variant_id}_state_snapshot.json", state)

        prompt = builder(context)
        prompt_path = args.out_dir / f"{case_id}_{variant_id}.prompt.txt"
        write_text(prompt_path, prompt)
        report_text = maybe_call_llm(prompt, mode=args.mode, provider=args.provider)
        if report_text:
            report_path = args.out_dir / f"{case_id}_{variant_id}.txt"
            write_text(report_path, report_text)
            output_path = report_path
        else:
            output_path = prompt_path

        manifest_rows.append(
            {
                "case_id": case_id,
                "date": case["date"],
                "variant_id": variant_id,
                "variant_name": row.get("variant_name", variant_id),
                "path": str(output_path),
                "mode": args.mode,
            }
        )

    write_rows_csv(args.manifest, manifest_rows)
    print(f"Wrote ablation manifest: {args.manifest}")


if __name__ == "__main__":
    main()
