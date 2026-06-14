from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline
from scripts.batch_io import parse_dates, resolve_output_dir, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Export optional claim-first allowed_claims.json without changing report generation.")
    parser.add_argument("--date")
    parser.add_argument("--dates")
    parser.add_argument("--out-dir", default="outputs/allowed_claims")
    args = parser.parse_args()
    dates = parse_dates(args.date, args.dates)
    if not dates:
        raise SystemExit("Provide --date or --dates.")
    out_dir = resolve_output_dir(args.out_dir)
    results = []
    for date in dates:
        result = run_daily_report_pipeline(date, use_llm=False, generation_mode="template")
        claims = build_allowed_claims(result.prompt_evidence_pack)
        target = out_dir / date
        target.mkdir(parents=True, exist_ok=True)
        write_json(target / "allowed_claims.json", {"date": date, "enable_claim_first": False, "allowed_claims": claims})
        results.append({"date": date, "claim_count": len(claims), "out_dir": str(target)})
    write_json(out_dir / "allowed_claims_summary.json", {"results": results})
    print({"results": results})


def build_allowed_claims(pack: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    scope = pack.get("report_scope") or {}
    daily_plc = scope.get("daily_plc_range") or {}
    if daily_plc:
        claims.append(
            _claim(
                len(claims) + 1,
                section="今日施工运行概况",
                claim_type="actual_fact",
                text=(
                    f"PLC 实测推进范围为 {daily_plc.get('start_chainage')} 至 {daily_plc.get('end_chainage')}，"
                    f"日推进约 {daily_plc.get('daily_advance_m')} m。"
                ),
                fields=["report_scope.daily_plc_range"],
                allowed_usage="May describe actual daily PLC advance range.",
                forbidden_usage="Do not replace this with daily_excavated_scope.",
            )
        )
    for cell in (pack.get("excavated_review_evidence") or {}).get("high_grci_cells") or []:
        claims.append(
            _claim(
                len(claims) + 1,
                section="已掘区段地质-施工响应复核",
                claim_type="review_interpretation",
                text=f"{cell.get('cell_id')} 可作为已掘区段 GRCI 复核关注 cell，GRCI={cell.get('GRCI')}。",
                evidence_ids=cell.get("supporting_evidence_ids") or [],
                fields=["GRCI", "RAI", "GRS_geo_base", "source_trace"],
                allowed_usage="May describe review priority for excavated cells.",
                forbidden_usage="Do not describe GRCI as disaster probability or forward risk.",
                source_trace=cell.get("source_trace") or [],
            )
        )
    for cell in (pack.get("forward_attention_evidence") or {}).get("forward_attention_cells") or []:
        claims.append(
            _claim(
                len(claims) + 1,
                section="当前掌子面前方关注提示",
                claim_type="forward_attention",
                text=f"{cell.get('cell_id')} 属于前方关注 cell，可提示后续揭露复核。",
                evidence_ids=cell.get("supporting_evidence_ids") or [],
                fields=["GRS_geo_base", "main_hazards", "source_trace", "forward_distance_band"],
                allowed_usage="May describe forward attention or review suggestion.",
                forbidden_usage="Do not describe as occurred fact and do not use GRCI.",
                source_trace=cell.get("source_trace") or [],
            )
        )
    for text in pack.get("generation_constraints") or []:
        claims.append(
            _claim(
                len(claims) + 1,
                section="方法边界",
                claim_type="method_boundary",
                text=str(text),
                fields=["generation_constraints"],
                allowed_usage="May state method boundary or generation policy.",
                forbidden_usage="Do not convert policy into a technical finding.",
            )
        )
    return claims


def _claim(
    index: int,
    *,
    section: str,
    claim_type: str,
    text: str,
    evidence_ids: list[str] | None = None,
    fields: list[str] | None = None,
    allowed_usage: str,
    forbidden_usage: str,
    source_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "claim_id": f"C{index:03d}",
        "section": section,
        "claim_text": text,
        "claim_type": claim_type,
        "supporting_evidence_ids": evidence_ids or [],
        "supporting_fields": fields or [],
        "allowed_usage": allowed_usage,
        "forbidden_usage": forbidden_usage,
        "source_trace": source_trace or [],
    }


if __name__ == "__main__":
    main()
