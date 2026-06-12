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
        summary_rows.append(_export_one(date, out_dir=out_dir, use_llm=use_llm))

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


def _export_one(date: str, *, out_dir: Path, use_llm: bool) -> dict[str, Any]:
    target = out_dir / date
    target.mkdir(parents=True, exist_ok=True)
    try:
        result = run_daily_report_pipeline(date, use_llm=use_llm)
        cells = [cell.model_dump() for cell in result.construction_state_cells]
        summary = {
            "date": result.date,
            "construction_state_cells_row_count": len(cells),
            "grci_available_count": sum(1 for item in cells if item.get("GRCI_available")),
            "high_grci_cell_count": len(result.high_grci_cells),
            "forward_cell_count": sum(1 for item in cells if item.get("is_forward_cell")),
            "key_cells_count": len((result.prompt_evidence_pack.get("geology_evidence") or {}).get("key_cells") or []),
            "quality_score": result.quality_summary.get("quality_score"),
            "grounding_rate": result.quality_summary.get("grounding_rate"),
            "unsupported_claim_count": result.quality_summary.get("unsupported_claim_count"),
            "warnings": result.warnings,
        }

        (target / "report.txt").write_text(result.report_text or "", encoding="utf-8")
        (target / "prompt.txt").write_text(result.prompt_text or "", encoding="utf-8")
        _write_json(target / "evidence_pack.json", result.prompt_evidence_pack)
        _write_json(target / "quality.json", result.quality)
        _write_json(target / "trace.json", result.trace)
        _write_json(target / "construction_state_cells.json", cells)
        _write_json(target / "forward_profile.json", result.forward_profile)
        _write_json(target / "high_grci_cells.json", result.high_grci_cells)
        _write_json(target / "warnings.json", result.warnings)
        _write_json(target / "summary.json", summary)

        csv_rows = [_csv_safe(item) for item in cells]
        pd.DataFrame(csv_rows).to_csv(target / "construction_state_cells.csv", index=False, encoding="utf-8-sig")
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
