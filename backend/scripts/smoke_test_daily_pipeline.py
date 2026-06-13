from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from statistics import mean
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import CONFIG_WARNINGS, DATA_DIR, DATA_ROOT, EVIDENCE_DB_PATH  # noqa: E402
from llm.report_grounding_checker import _get_key_cells  # noqa: E402
from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from pipeline.inputs import load_daily_inputs  # noqa: E402
from plc.response import analyze_plc_response  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the daily report pipeline.")
    parser.add_argument("--date", help="Single YYYY-MM-DD date.")
    parser.add_argument("--dates", help="Comma-separated dates, e.g. 2023-12-30,2023-12-28.")
    parser.add_argument("--no-llm", action="store_true", help="Use template report instead of LLM.")
    parser.add_argument("--out", help="Optional JSON output path.")
    args = parser.parse_args()

    dates = _parse_dates(args.date, args.dates)
    use_llm = not args.no_llm
    results = [_run_one(date, use_llm=use_llm) for date in dates]
    payload = {
        "config": _config_snapshot(),
        "results": results,
        "summary": _summary(results),
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = BACKEND_DIR / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


def _parse_dates(date: str | None, dates: str | None) -> list[str]:
    values: list[str] = []
    if dates:
        values.extend(item.strip() for item in dates.split(",") if item.strip())
    if date:
        values.append(date.strip())
    if not values:
        raise SystemExit("Provide --date or --dates.")
    return list(dict.fromkeys(values))


def _run_one(date: str, *, use_llm: bool) -> dict[str, Any]:
    try:
        inputs = load_daily_inputs(date)
        plc = analyze_plc_response(inputs.df_plc, date=date, cell_length=10.0)
        result = run_daily_report_pipeline(date, use_llm=use_llm)

        position = result.operation_summary.get("position", {})
        daily_min = position.get("start_chainage")
        daily_max = position.get("end_chainage")
        daily_advance = position.get("advance_length_m")
        response_df = plc.get("cell_response_df")
        cell_response_count = int(len(response_df)) if response_df is not None else 0
        cells = result.construction_state_cells
        key_cells = (result.prompt_evidence_pack.get("geology_evidence") or {}).get("key_cells") or []
        grounding_key_cells = _get_key_cells(result.twin_state, {}, result.prompt_evidence_pack)
        forward_ids = {cell.cell_id for cell in cells if cell.is_forward_cell}
        high_ids = {cell.get("cell_id") for cell in result.high_grci_cells}

        warnings = list(dict.fromkeys([*inputs.warnings, *result.warnings]))
        return {
            "date": result.date,
            "source_csv_path": str(inputs.plc_path),
            "evidence_path": str(inputs.evidence_path),
            "daily_chainage_min": daily_min,
            "daily_chainage_max": daily_max,
            "daily_advance_m": daily_advance,
            "cell_response_df_row_count": cell_response_count,
            "construction_state_cells_row_count": len(cells),
            "grci_available_count": sum(1 for cell in cells if cell.GRCI_available),
            "high_grci_cell_count": len(result.high_grci_cells),
            "review_cell_count": len(result.review_cells),
            "high_priority_cell_count": len(result.high_priority_cells),
            "medium_priority_cell_count": len(result.medium_priority_cells),
            "low_priority_cell_count": len(result.low_priority_cells),
            "forward_cell_count": sum(1 for cell in cells if cell.is_forward_cell),
            "daily_review_cell_count": len(result.daily_review_cells),
            "forward_attention_cell_count": len(result.forward_attention_cells),
            "local_background_cell_count": len(result.local_background_cells),
            "scope_summary": result.scope_summary,
            "key_cells_count": len(key_cells),
            "grounding_key_cells_seen": len(grounding_key_cells),
            "quality_score": result.quality_summary.get("quality_score"),
            "grounding_rate": result.quality_summary.get("grounding_rate"),
            "unsupported_claim_count": result.quality_summary.get("unsupported_claim_count"),
            "error_type_counts": result.quality.get("error_type_counts", {}),
            "support_type_distribution": result.trace.get("support_type_distribution", {}),
            "forward_profile_ok": bool(result.forward_profile.get("profile")) if isinstance(result.forward_profile, dict) else False,
            "high_grci_only_excavated": all(cell.get("is_excavated_today") for cell in result.high_grci_cells),
            "forward_cell_entered_high_grci_cells": bool(forward_ids & high_ids),
            "warnings": warnings,
            "passed": True,
        }
    except Exception as exc:
        return {
            "date": date,
            "passed": False,
            "error": str(exc),
            "traceback_summary": traceback.format_exc(limit=3),
            "warnings": list(CONFIG_WARNINGS),
        }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [item for item in results if item.get("passed")]
    failed = [item for item in results if not item.get("passed")]
    quality_values = [float(item.get("quality_score")) for item in passed if item.get("quality_score") is not None]
    grounding_values = [float(item.get("grounding_rate")) for item in passed if item.get("grounding_rate") is not None]
    return {
        "passed_count": len(passed),
        "failed_count": len(failed),
        "warning_count": sum(len(item.get("warnings") or []) for item in results),
        "average_quality_score": mean(quality_values) if quality_values else None,
        "average_grounding_rate": mean(grounding_values) if grounding_values else None,
    }


def _config_snapshot() -> dict[str, Any]:
    return {
        "DATA_ROOT": str(DATA_ROOT),
        "DATA_DIR": str(DATA_DIR),
        "EVIDENCE_DB_PATH": str(EVIDENCE_DB_PATH),
        "warnings": list(CONFIG_WARNINGS),
    }


if __name__ == "__main__":
    main()
