from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from llm.llm_api import call_llm
from llm.prompt_builder import build_prompt
from llm.report_quality_checker import check_report_quality
from llm.report_trace_builder import build_report_trace, summarize_report_trace
from services.analysis_cache_service import clear_file_cache
from services.tbm_analysis_service import analyze_tbm_data
from utils.io_utils import get_all_csv_paths, load_csv_by_date, load_latest_csv
from utils.serialization import serialize_for_json


def _safe_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(serialize_for_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_dates(raw_dates: str | None, limit: int) -> list[str]:
    if raw_dates:
        return [item.strip() for item in raw_dates.split(",") if item.strip()]
    available: list[str] = []
    for path in get_all_csv_paths():
        raw = path.name.replace("tbm_data_", "").replace(".csv", "")
        if len(raw) == 8:
            available.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
    available = sorted(set(available), reverse=True)
    if available:
        return available[: max(limit, 1)]
    latest_path, _ = load_latest_csv()
    raw = latest_path.name.replace("tbm_data_", "").replace(".csv", "")
    return [f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"] if len(raw) == 8 else []


def _compact_analysis(result: dict[str, Any]) -> dict[str, Any]:
    llm_summary = result.get("llm_summary", {}) if isinstance(result.get("llm_summary"), dict) else {}
    return {
        "run_metadata": result.get("run_metadata", {}),
        "plc_quality_report": result.get("plc_quality_report", {}),
        "operation_context": result.get("operation_context", {}),
        "cluster_context": result.get("cluster_context", {}),
        "gas_context": result.get("gas_context", {}),
        "cell_response_summary": result.get("cell_response_summary", {}),
        "geology_v2_context": result.get("geology_v2_context", {}),
        "twin_state": result.get("twin_state", {}),
        "prompt_evidence_pack_summary": result.get("prompt_evidence_pack_summary", {}),
        "report_quality": result.get("report_quality", {}),
        "report_trace_summary": result.get("report_trace_summary", {}),
        "warnings": result.get("warnings", []),
        "llm_summary_keys": sorted(llm_summary.keys()),
    }


def _report_pipeline(result: dict[str, Any], *, no_llm: bool) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if no_llm:
        return "", result.get("report_quality", {}), result.get("report_trace_summary", {})

    llm_summary = result.get("llm_summary", {}) if isinstance(result.get("llm_summary"), dict) else {}
    prompt = build_prompt(
        seg_text=result.get("seg_text", ""),
        stats_text=result.get("stats_text", ""),
        state_text=result.get("state_text", ""),
        eff_text=result.get("eff_text", ""),
        state_stats_text=result.get("state_stats_text", ""),
        gas_text=result.get("gas_text", ""),
        geo_text=result.get("geo_text", ""),
        face_geo_text=result.get("face_geo_text", ""),
        llm_summary=llm_summary,
        risk_prob_text=result.get("risk_prob_text", ""),
    )
    report_text = call_llm(prompt)
    quality = check_report_quality(
        report_text,
        llm_summary=llm_summary,
        geology_context=result.get("geology_v2_context", {}),
        twin_state=result.get("twin_state", {}),
        prompt_evidence_pack=llm_summary.get("prompt_evidence_pack", {}),
        include_claim_results=False,
    )
    trace = build_report_trace(
        report_text,
        twin_state=result.get("twin_state", {}),
        geology_context=result.get("geology_v2_context", {}),
    )
    return report_text, quality, summarize_report_trace(trace)


def main() -> int:
    parser = argparse.ArgumentParser(description="SCI readiness architecture check for TBM report pipeline.")
    parser.add_argument("--dates", default="", help="Comma-separated dates like 2023-12-30,2023-12-29")
    parser.add_argument("--limit", type=int, default=1, help="Max number of dates when --dates is omitted")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM report generation")
    parser.add_argument("--output-dir", default="outputs/sci_readiness", help="Output directory")
    parser.add_argument("--clear-cache", action="store_true", help="Clear analysis cache before running")
    args = parser.parse_args()

    if args.clear_cache:
        clear_file_cache()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dates = _resolve_dates(args.dates, args.limit)
    rows: list[dict[str, Any]] = []

    for date in dates:
        started = perf_counter()
        row: dict[str, Any] = {
            "date": date,
            "ok": False,
            "has_run_metadata": False,
            "has_plc_quality_report": False,
            "has_operation_context": False,
            "has_cluster_context": False,
            "has_gas_context": False,
            "has_cell_response_summary": False,
            "has_geology_context": False,
            "has_twin_state": False,
            "has_prompt_evidence_pack": False,
            "has_report_quality": False,
            "has_report_trace_summary": False,
            "quality_score": 0,
            "grounding_rate": 0.0,
            "warning_count": 0,
            "duration_sec": 0.0,
        }
        try:
            path, df = load_csv_by_date(date)
            result = analyze_tbm_data(
                df,
                context={
                    "date": date,
                    "analysis_mode": "daily",
                    "source_path": str(path),
                    "source_name": path.name,
                    "persist_cst": False,
                },
            )
            llm_summary = result.get("llm_summary", {}) if isinstance(result.get("llm_summary"), dict) else {}
            prompt_pack = llm_summary.get("prompt_evidence_pack", {})
            report_text, quality, trace_summary = _report_pipeline(result, no_llm=args.no_llm)

            _safe_write_json(output_dir / f"analysis_{date}.json", _compact_analysis(result))
            _safe_write_json(output_dir / f"twin_state_{date}.json", result.get("twin_state", {}))
            _safe_write_json(output_dir / f"prompt_pack_{date}.json", prompt_pack)
            _safe_write_json(output_dir / f"quality_{date}.json", quality)
            _safe_write_json(output_dir / f"trace_summary_{date}.json", trace_summary)
            if report_text:
                (output_dir / f"report_{date}.txt").write_text(report_text, encoding="utf-8")

            row.update(
                {
                    "ok": True,
                    "has_run_metadata": bool(result.get("run_metadata")),
                    "has_plc_quality_report": bool(result.get("plc_quality_report")),
                    "has_operation_context": bool(result.get("operation_context")),
                    "has_cluster_context": bool(result.get("cluster_context")),
                    "has_gas_context": bool(result.get("gas_context")),
                    "has_cell_response_summary": bool(result.get("cell_response_summary")),
                    "has_geology_context": bool(result.get("geology_v2_context")),
                    "has_twin_state": bool(result.get("twin_state")),
                    "has_prompt_evidence_pack": bool(prompt_pack),
                    "has_report_quality": bool(quality),
                    "has_report_trace_summary": bool(trace_summary),
                    "quality_score": int((quality or {}).get("score", 0) or 0),
                    "grounding_rate": float(((quality or {}).get("grounding_summary", {}) or {}).get("grounding_rate", 0.0) or 0.0),
                    "warning_count": len(result.get("warnings", []) or []) + len((quality or {}).get("warnings", []) or []),
                }
            )
        except Exception as exc:
            row["warning_count"] = row.get("warning_count", 0) + 1
            _safe_write_json(output_dir / f"failure_{date}.json", {"date": date, "error": str(exc)})
        finally:
            row["duration_sec"] = round(perf_counter() - started, 3)
            rows.append(row)

    summary_path = output_dir / "summary.csv"
    with summary_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    print(f"[SCI readiness] wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
