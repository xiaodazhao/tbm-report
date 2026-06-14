from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export daily pipeline outputs for review and experiments.")
    parser.add_argument("--date", help="Single YYYY-MM-DD date.")
    parser.add_argument("--dates", help="Comma-separated dates.")
    parser.add_argument("--no-llm", action="store_true", help="Keep LLM disabled. This is the default.")
    parser.add_argument("--use-llm", action="store_true", help="Allow LLM call; fallback remains enabled.")
    parser.add_argument(
        "--generation-mode",
        choices=[
            "template",
            "evidence_pack_llm",
            "evidence_pack_llm_with_revision",
            "evidence_pack_planner_llm",
            "evidence_pack_planner_llm_with_revision",
        ],
        help="Optional generation mode.",
    )
    parser.add_argument("--llm-provider", help="LLM provider, e.g. mock or openai_or_compatible.")
    parser.add_argument("--llm-model", help="LLM model name.")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic mock LLM.")
    parser.add_argument("--enable-revision", action="store_true", help="Enable LLM revision when generation mode supports it.")
    parser.add_argument("--enable-planner", action="store_true", help="Enable LLM report planner when generation mode supports it.")
    parser.add_argument("--planner-provider", help="Planner LLM provider, defaults to --llm-provider.")
    parser.add_argument("--planner-model", help="Planner LLM model, defaults to --llm-model.")
    parser.add_argument("--out-dir", default="outputs/pipeline_exports", help="Output directory.")
    args = parser.parse_args()

    dates = _parse_dates(args.date, args.dates)
    use_llm = bool(args.use_llm and not args.no_llm)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = BACKEND_DIR / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for date in dates:
        summary_rows.append(
            _export_one(
                date,
                out_dir=out_dir,
                use_llm=use_llm,
                generation_mode=args.generation_mode,
                llm_provider=args.llm_provider,
                llm_model=args.llm_model,
                mock_llm=args.mock_llm,
                enable_revision=args.enable_revision if args.enable_revision else None,
                enable_planner=args.enable_planner if args.enable_planner else None,
                planner_provider=args.planner_provider,
                planner_model=args.planner_model,
            )
        )

    summary_path = out_dir / "export_summary.json"
    _write_json(summary_path, {"results": summary_rows})
    print(json.dumps({"out_dir": str(out_dir), "results": summary_rows}, ensure_ascii=False, indent=2, default=str))


def _parse_dates(date: str | None, dates: str | None) -> list[str]:
    out: list[str] = []
    if dates:
        out.extend(item.strip() for item in dates.split(",") if item.strip())
    if date:
        out.append(date.strip())
    if not out:
        raise SystemExit("Provide --date or --dates.")
    return list(dict.fromkeys(out))


def _export_one(
    date: str,
    *,
    out_dir: Path,
    use_llm: bool,
    generation_mode: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    mock_llm: bool = False,
    enable_revision: bool | None = None,
    enable_planner: bool | None = None,
    planner_provider: str | None = None,
    planner_model: str | None = None,
) -> dict[str, Any]:
    target = out_dir / date
    target.mkdir(parents=True, exist_ok=True)
    try:
        result = run_daily_report_pipeline(
            date,
            use_llm=use_llm,
            generation_mode=generation_mode,
            llm_provider=llm_provider,
            llm_model=llm_model,
            mock_llm=mock_llm,
            enable_revision=enable_revision,
            enable_planner=enable_planner,
            planner_provider=planner_provider,
            planner_model=planner_model,
        )
        cells = [cell.model_dump() for cell in result.construction_state_cells]
        summary = {
            "date": result.date,
            "construction_state_cells_row_count": len(cells),
            "grci_available_count": sum(1 for item in cells if item.get("GRCI_available")),
            "high_grci_cell_count": len(result.high_grci_cells),
            "review_cell_count": len(result.review_cells),
            "high_priority_cell_count": len(result.high_priority_cells),
            "medium_priority_cell_count": len(result.medium_priority_cells),
            "low_priority_cell_count": len(result.low_priority_cells),
            "forward_cell_count": sum(1 for item in cells if item.get("is_forward_cell")),
            "daily_review_cell_count": len(result.daily_review_cells),
            "forward_attention_cell_count": len(result.forward_attention_cells),
            "local_background_cell_count": len(result.local_background_cells),
            "key_cells_count": len((result.prompt_evidence_pack.get("geology_evidence") or {}).get("key_cells") or []),
            "quality_score": result.quality_summary.get("quality_score"),
            "grounding_rate": result.quality_summary.get("grounding_rate"),
            "unsupported_claim_count": result.quality_summary.get("unsupported_claim_count"),
            "error_type_counts": result.quality.get("error_type_counts", {}),
            "support_type_distribution": result.trace.get("support_type_distribution", {}),
            "warnings": result.warnings,
            "generation_mode": result.generation_mode,
            "llm_summary": (result.llm_generation or {}).get("summary", {}),
        }

        (target / "report.txt").write_text(result.report_text or "", encoding="utf-8")
        (target / "prompt.txt").write_text(result.prompt_text or "", encoding="utf-8")
        _write_json(target / "evidence_pack.json", result.prompt_evidence_pack)
        _write_json(target / "quality.json", result.quality)
        _write_json(target / "trace.json", result.trace)
        _write_json(target / "construction_state_cells.json", cells)
        _write_json(target / "forward_profile.json", result.forward_profile)
        _write_json(target / "high_grci_cells.json", result.high_grci_cells)
        _write_json(target / "review_cells.json", result.review_cells)
        _write_json(target / "daily_review_cells.json", result.daily_review_cells)
        _write_json(target / "forward_attention_cells.json", result.forward_attention_cells)
        _write_json(target / "local_background_cells.json", result.local_background_cells)
        _write_json(target / "scope_summary.json", result.scope_summary)
        _write_json(target / "method_metrics.json", result.method_metrics)
        _write_json(target / "cell_response_df.json", result.cell_response_records)
        _write_json(target / "geo_states_df.json", result.geo_state_records)
        _write_json(target / "cell_evidence_df.json", result.cell_evidence_records)
        _write_json(target / "warnings.json", result.warnings)
        _write_json(target / "summary.json", summary)
        _write_llm_outputs(target, result.llm_generation)

        csv_rows = [_csv_safe(item) for item in cells]
        pd.DataFrame(csv_rows).to_csv(target / "construction_state_cells.csv", index=False, encoding="utf-8-sig")
        _write_csv(target / "time_valid_evidence.csv", result.time_valid_evidence)
        _write_csv(target / "spatial_relevant_evidence.csv", result.spatial_relevant_evidence)
        _write_csv(target / "excluded_evidence.csv", result.excluded_evidence)
        _write_csv(target / "cell_response_df.csv", result.cell_response_records)
        _write_csv(target / "geo_states_df.csv", result.geo_state_records)
        _write_csv(target / "cell_evidence_df.csv", result.cell_evidence_records)
        return {"date": date, "passed": True, "out_dir": str(target), **summary}
    except Exception as exc:
        error = {
            "date": date,
            "passed": False,
            "error": str(exc),
            "traceback_summary": traceback.format_exc(limit=3),
        }
        _write_json(target / "summary.json", error)
        return error


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_llm_outputs(target: Path, llm_generation: dict[str, Any]) -> None:
    if not llm_generation:
        return
    _write_json(target / "llm_mode.json", {
        "generation_mode": llm_generation.get("generation_mode"),
        "provider": llm_generation.get("provider"),
        "model": llm_generation.get("model"),
        "passed": llm_generation.get("passed"),
        "error_message": llm_generation.get("error_message"),
        "planner_enabled": (llm_generation.get("summary") or {}).get("planner_enabled"),
        "planner_provider": (llm_generation.get("summary") or {}).get("planner_provider"),
        "plan_validation_passed": (llm_generation.get("summary") or {}).get("plan_validation_passed"),
        "plan_fallback_used": (llm_generation.get("summary") or {}).get("plan_fallback_used"),
    })
    (target / "llm_report_plan_prompt.txt").write_text(llm_generation.get("llm_report_plan_prompt", "") or "", encoding="utf-8")
    _write_json(target / "llm_report_plan_request.json", llm_generation.get("llm_report_plan_request", {}))
    (target / "llm_report_plan_raw_response.txt").write_text(llm_generation.get("llm_report_plan_raw_response", "") or "", encoding="utf-8")
    _write_json(target / "llm_report_plan.json", llm_generation.get("llm_report_plan", {}))
    _write_json(target / "llm_report_plan_validation.json", llm_generation.get("llm_report_plan_validation", {}))
    (target / "llm_prompt.txt").write_text(llm_generation.get("prompt", "") or "", encoding="utf-8")
    _write_json(target / "llm_request.json", llm_generation.get("request", {}))
    (target / "llm_raw_response.txt").write_text(llm_generation.get("raw_response", "") or "", encoding="utf-8")
    (target / "llm_report_draft.txt").write_text(llm_generation.get("report_draft", "") or "", encoding="utf-8")
    _write_json(target / "llm_quality_before_revision.json", llm_generation.get("quality_before_revision", {}))
    _write_json(target / "llm_trace_before_revision.json", llm_generation.get("trace_before_revision", {}))
    (target / "llm_revision_prompt.txt").write_text(llm_generation.get("revision_prompt", "") or "", encoding="utf-8")
    _write_json(target / "llm_revision_request.json", llm_generation.get("revision_request", {}))
    (target / "llm_revision_response.txt").write_text(llm_generation.get("revision_response", "") or "", encoding="utf-8")
    (target / "llm_report_final.txt").write_text(llm_generation.get("report_final", "") or "", encoding="utf-8")
    _write_json(target / "llm_quality_after_revision.json", llm_generation.get("quality_after_revision", {}))
    _write_json(target / "llm_trace_after_revision.json", llm_generation.get("trace_after_revision", {}))
    _write_json(target / "llm_summary.json", llm_generation.get("summary", {}))


def _write_csv(path: Path, rows: Any) -> None:
    if not rows:
        pd.DataFrame().to_csv(path, index=False, encoding="utf-8-sig")
        return
    pd.DataFrame([_csv_safe(dict(row)) for row in rows]).to_csv(path, index=False, encoding="utf-8-sig")


def _csv_safe(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple, set)):
            out[key] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            out[key] = value
    return out


if __name__ == "__main__":
    main()
