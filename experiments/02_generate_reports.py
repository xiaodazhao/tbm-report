"""Generate baseline and CST-driven reports for experiment cases."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    CASES_DIR,
    DEFAULT_METHODS,
    REPORTS_DIR,
    build_cst_llm_prompt,
    build_cst_state,
    build_direct_llm_prompt,
    build_template_report,
    ensure_experiment_dirs,
    load_case_context,
    load_case_csv,
    maybe_call_llm,
    write_json,
    write_rows_csv,
    write_text,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate experiment reports.")
    parser.add_argument(
        "--case-list",
        type=Path,
        default=CASES_DIR / "case_list.csv",
        help="CSV file describing experiment cases.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory for generated reports and prompts.",
    )
    parser.add_argument(
        "--methods",
        nargs="*",
        default=DEFAULT_METHODS,
        choices=["template", "direct_llm", "cst_llm"],
        help="Methods to generate.",
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
        default=REPORTS_DIR / "report_manifest.csv",
        help="Output CSV manifest describing generated artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate reports or prompts for each experiment case."""
    args = parse_args()
    ensure_experiment_dirs()
    cases = load_case_csv(args.case_list)
    manifest_rows = []
    for case in cases:
        context = load_case_context(case)
        state = build_cst_state(case, context)
        write_json(args.out_dir / f"{case['case_id']}_state_snapshot.json", state)

        if "template" in args.methods:
            report = build_template_report(case, state)
            report_path = args.out_dir / f"{case['case_id']}_template.txt"
            write_text(report_path, report)
            manifest_rows.append({"case_id": case["case_id"], "method": "template", "path": str(report_path), "mode": "local"})

        if "direct_llm" in args.methods:
            prompt = build_direct_llm_prompt(case, context)
            prompt_path = args.out_dir / f"{case['case_id']}_direct_llm.prompt.txt"
            write_text(prompt_path, prompt)
            report_text = maybe_call_llm(prompt, mode=args.mode, provider=args.provider)
            if report_text:
                report_path = args.out_dir / f"{case['case_id']}_direct_llm.txt"
                write_text(report_path, report_text)
                manifest_rows.append({"case_id": case["case_id"], "method": "direct_llm", "path": str(report_path), "mode": args.mode})
            else:
                manifest_rows.append({"case_id": case["case_id"], "method": "direct_llm", "path": str(prompt_path), "mode": args.mode})

        if "cst_llm" in args.methods:
            prompt = build_cst_llm_prompt(context)
            prompt_path = args.out_dir / f"{case['case_id']}_cst_llm.prompt.txt"
            write_text(prompt_path, prompt)
            report_text = maybe_call_llm(prompt, mode=args.mode, provider=args.provider)
            if report_text:
                report_path = args.out_dir / f"{case['case_id']}_cst_llm.txt"
                write_text(report_path, report_text)
                manifest_rows.append({"case_id": case["case_id"], "method": "cst_llm", "path": str(report_path), "mode": args.mode})
            else:
                manifest_rows.append({"case_id": case["case_id"], "method": "cst_llm", "path": str(prompt_path), "mode": args.mode})

    write_rows_csv(args.manifest, manifest_rows)
    print(f"Wrote report manifest: {args.manifest}")


if __name__ == "__main__":
    main()
