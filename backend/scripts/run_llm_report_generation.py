from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from llm.llm_report_generator import generate_llm_report  # noqa: E402
from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Evidence-Pack-constrained LLM report generation.")
    parser.add_argument("--date", help="Single YYYY-MM-DD date.")
    parser.add_argument("--dates", help="Comma-separated dates.")
    parser.add_argument("--generation-mode", choices=["evidence_pack_llm", "evidence_pack_llm_with_revision"], default="evidence_pack_llm")
    parser.add_argument("--provider", help="mock, openai_or_compatible, or disabled.")
    parser.add_argument("--model", help="LLM model name.")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock provider.")
    parser.add_argument("--enable-revision", action="store_true", help="Enable revision.")
    parser.add_argument("--max-revision-rounds", type=int, default=1)
    parser.add_argument("--out-dir", default="outputs/llm_exports")
    args = parser.parse_args()

    dates = _parse_dates(args.date, args.dates)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = BACKEND_DIR / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    results = [
        _run_one(
            date,
            out_dir=out_dir,
            generation_mode=args.generation_mode,
            provider=args.provider,
            model=args.model,
            mock_llm=args.mock_llm,
            enable_revision=args.enable_revision or args.generation_mode == "evidence_pack_llm_with_revision",
            max_revision_rounds=args.max_revision_rounds,
        )
        for date in dates
    ]
    payload = {"results": results, "summary": _summary(results), "out_dir": str(out_dir)}
    _write_json(out_dir / "llm_export_summary.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _run_one(
    date: str,
    *,
    out_dir: Path,
    generation_mode: str,
    provider: str | None,
    model: str | None,
    mock_llm: bool,
    enable_revision: bool,
    max_revision_rounds: int,
) -> dict[str, Any]:
    target = out_dir / date / generation_mode
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
            enable_revision=enable_revision,
            max_revision_rounds=max_revision_rounds,
            fallback_report=baseline.report_text,
        )
        _write_llm_outputs(target, llm_result)
        summary = dict(llm_result.get("summary") or {})
        summary.update({"date": baseline.date, "passed": bool(llm_result.get("passed")), "out_dir": str(target)})
        return summary
    except Exception as exc:
        error = {
            "date": date,
            "passed": False,
            "error_message": str(exc),
            "traceback_summary": traceback.format_exc(limit=3),
            "out_dir": str(target),
        }
        _write_json(target / "llm_summary.json", error)
        return error


def _parse_dates(date: str | None, dates: str | None) -> list[str]:
    out: list[str] = []
    if dates:
        out.extend(item.strip() for item in dates.split(",") if item.strip())
    if date:
        out.append(date.strip())
    if not out:
        raise SystemExit("Provide --date or --dates.")
    return list(dict.fromkeys(out))


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [item for item in results if item.get("passed")]
    failed = [item for item in results if not item.get("passed")]
    return {
        "passed_count": len(passed),
        "failed_count": len(failed),
        "dates": [item.get("date") for item in results],
    }


def _write_llm_outputs(target: Path, result: dict[str, Any]) -> None:
    _write_json(target / "llm_mode.json", {
        "generation_mode": result.get("generation_mode"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "revision_enabled": result.get("revision_enabled"),
        "revision_executed": result.get("revision_executed"),
        "passed": result.get("passed"),
        "error_message": result.get("error_message"),
    })
    (target / "llm_prompt.txt").write_text(result.get("prompt", "") or "", encoding="utf-8")
    _write_json(target / "llm_request.json", result.get("request", {}))
    (target / "llm_raw_response.txt").write_text(result.get("raw_response", "") or "", encoding="utf-8")
    (target / "llm_report_draft.txt").write_text(result.get("report_draft", "") or "", encoding="utf-8")
    _write_json(target / "llm_quality_before_revision.json", result.get("quality_before_revision", {}))
    _write_json(target / "llm_trace_before_revision.json", result.get("trace_before_revision", {}))
    (target / "llm_revision_prompt.txt").write_text(result.get("revision_prompt", "") or "", encoding="utf-8")
    _write_json(target / "llm_revision_request.json", result.get("revision_request", {}))
    (target / "llm_revision_response.txt").write_text(result.get("revision_response", "") or "", encoding="utf-8")
    (target / "llm_report_final.txt").write_text(result.get("report_final", "") or "", encoding="utf-8")
    _write_json(target / "llm_quality_after_revision.json", result.get("quality_after_revision", {}))
    _write_json(target / "llm_trace_after_revision.json", result.get("trace_after_revision", {}))
    _write_json(target / "llm_summary.json", result.get("summary", {}))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
