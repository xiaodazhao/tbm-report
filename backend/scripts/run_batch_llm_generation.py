from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from llm.llm_report_generator import generate_llm_report  # noqa: E402
from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from scripts.batch_io import dates_from_file, parse_dates, resolve_output_dir, write_csv, write_json  # noqa: E402


SUPPORTED_MODES = [
    "evidence_pack_llm",
    "evidence_pack_llm_with_revision",
    "evidence_pack_planner_llm",
    "evidence_pack_planner_llm_with_revision",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM report generation over many dates.")
    parser.add_argument("--date")
    parser.add_argument("--dates")
    parser.add_argument("--date-file")
    parser.add_argument("--class-filter")
    parser.add_argument("--generation-mode", choices=SUPPORTED_MODES, default="evidence_pack_llm")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM. Default is true unless provider is explicitly allowed.")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--enable-planner", action="store_true")
    parser.add_argument("--enable-revision", action="store_true")
    parser.add_argument("--allow-external-llm", action="store_true")
    parser.add_argument("--out-dir", default="outputs/batch_llm")
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    parser.add_argument("--max-dates", type=int)
    args = parser.parse_args()

    if args.provider and args.provider != "mock" and not args.allow_external_llm:
        raise SystemExit("External LLM calls are refused unless --allow-external-llm is set.")

    dates = _select_dates(args)
    out_dir = resolve_output_dir(args.out_dir)
    payload = run_batch_llm_generation(
        dates=dates,
        out_dir=out_dir,
        generation_mode=args.generation_mode,
        provider=args.provider,
        model=args.model,
        mock_llm=True if not args.provider else bool(args.mock_llm or args.provider == "mock"),
        enable_planner=args.enable_planner or args.generation_mode.startswith("evidence_pack_planner"),
        enable_revision=args.enable_revision or args.generation_mode.endswith("_with_revision"),
        continue_on_error=args.continue_on_error,
    )
    write_csv(out_dir / "batch_llm_summary.csv", payload["summary_rows"])
    write_json(out_dir / "batch_llm_summary.json", payload["summary"])
    write_csv(out_dir / "batch_llm_error_log.csv", payload["error_rows"])
    print(payload["summary"])


def run_batch_llm_generation(
    *,
    dates: list[str],
    out_dir: Path,
    generation_mode: str,
    provider: str | None = None,
    model: str | None = None,
    mock_llm: bool = True,
    enable_planner: bool = False,
    enable_revision: bool = False,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    summary_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    for date in dates:
        target = out_dir / date
        target.mkdir(parents=True, exist_ok=True)
        try:
            baseline = run_daily_report_pipeline(date, use_llm=False, generation_mode="template")
            llm_result = generate_llm_report(
                date=baseline.date,
                prompt_evidence_pack=baseline.prompt_evidence_pack,
                twin_state=baseline.twin_state,
                generation_mode=generation_mode,
                provider_name=provider,
                model=model,
                mock_llm=mock_llm,
                enable_planner=enable_planner,
                enable_revision=enable_revision,
                fallback_report=baseline.report_text,
            )
            write_json(target / "llm_summary.json", llm_result.get("summary", {}))
            (target / "llm_report_final.txt").write_text(llm_result.get("report_final", "") or "", encoding="utf-8")
            summary_rows.append(_summary_row(date, llm_result))
        except Exception as exc:
            error = {
                "date": date,
                "passed": False,
                "error_message": str(exc),
                "traceback_summary": traceback.format_exc(limit=3),
            }
            summary_rows.append(_failed_summary_row(date, generation_mode, error))
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


def _summary_row(date: str, result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") or {}
    draft_errors = summary.get("draft_error_type_counts", {}) or {}
    final_errors = summary.get("final_error_type_counts", {}) or {}
    draft_quality = _num(summary.get("draft_quality_score"))
    final_quality = _num(summary.get("final_quality_score"))
    return {
        "date": date,
        "generation_mode": result.get("generation_mode"),
        "provider": result.get("provider"),
        "planner_enabled": summary.get("planner_enabled"),
        "revision_enabled": result.get("revision_enabled"),
        "passed": result.get("passed"),
        "error_message": result.get("error_message"),
        "draft_quality_score": draft_quality,
        "final_quality_score": final_quality,
        "draft_grounding_rate": summary.get("draft_grounding_rate"),
        "final_grounding_rate": summary.get("final_grounding_rate"),
        "draft_unsupported_claim_count": summary.get("draft_unsupported_claim_count"),
        "final_unsupported_claim_count": summary.get("final_unsupported_claim_count"),
        "draft_numeric_error_count": _numeric_count(draft_errors),
        "final_numeric_error_count": _numeric_count(final_errors),
        "draft_role_violation_count": _role_count(draft_errors),
        "final_role_violation_count": _role_count(final_errors),
        "revision_improved": bool(final_quality is not None and draft_quality is not None and final_quality >= draft_quality),
    }


def _failed_summary_row(date: str, generation_mode: str, error: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": date,
        "generation_mode": generation_mode,
        "provider": None,
        "planner_enabled": None,
        "revision_enabled": None,
        "passed": False,
        "error_message": error.get("error_message"),
        "draft_quality_score": None,
        "final_quality_score": None,
        "draft_grounding_rate": None,
        "final_grounding_rate": None,
        "draft_unsupported_claim_count": None,
        "final_unsupported_claim_count": None,
        "draft_numeric_error_count": None,
        "final_numeric_error_count": None,
        "draft_role_violation_count": None,
        "final_role_violation_count": None,
        "revision_improved": False,
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


def _numeric_count(errors: dict[str, Any]) -> int:
    return int(errors.get("E10_NUMERIC_VALUE_UNGROUNDED", 0) or 0) + int(errors.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0) or 0)


def _role_count(errors: dict[str, Any]) -> int:
    return sum(int(errors.get(key, 0) or 0) for key in ["E4_FORWARD_AS_EXCAVATED_REVIEW", "E5_BACKGROUND_AS_DAILY_RESPONSE", "E9_SOURCE_ROLE_CONFUSION"])


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _resolve_backend_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_DIR / path


if __name__ == "__main__":
    main()
