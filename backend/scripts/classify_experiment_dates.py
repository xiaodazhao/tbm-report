from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from scripts.batch_io import resolve_output_dir, safe_float, write_csv, write_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify dates for batch TBM report experiments.")
    parser.add_argument("--plc-audit", default="outputs/audit/plc_date_audit.csv")
    parser.add_argument("--evidence-audit", default="outputs/audit/evidence_db_audit.csv")
    parser.add_argument("--out-dir", default="outputs/audit")
    parser.add_argument("--max-dates", type=int)
    args = parser.parse_args()

    out_dir = resolve_output_dir(args.out_dir)
    plc_path = _resolve_backend_path(args.plc_audit)
    evidence_path = _resolve_backend_path(args.evidence_audit)
    payload = classify_experiment_dates(plc_audit_path=plc_path, evidence_audit_path=evidence_path, max_dates=args.max_dates)
    write_csv(out_dir / "date_classification.csv", payload["rows"])
    write_json(out_dir / "date_classification_summary.json", payload["summary"])
    print(f"Date classification written to {out_dir}")
    print(payload["summary"])


def classify_experiment_dates(
    *,
    plc_audit_path: Path,
    evidence_audit_path: Path,
    max_dates: int | None = None,
) -> dict[str, Any]:
    plc = pd.read_csv(plc_audit_path)
    evidence = pd.read_csv(evidence_audit_path) if evidence_audit_path.exists() else pd.DataFrame()
    evidence_by_date = {
        str(row.get("date")): row.to_dict()
        for _, row in evidence.iterrows()
        if row.get("date") is not None
    }
    rows = []
    candidates = plc.sort_values("date").to_dict(orient="records")
    if max_dates:
        candidates = candidates[: max(int(max_dates), 0)]
    for item in candidates:
        rows.append(_classify_one(item, evidence_by_date))
    summary = {
        "total_dates": len(rows),
        "class_counts": {str(key): int(value) for key, value in pd.Series([row["class_label"] for row in rows]).value_counts().to_dict().items()},
        "usable_for_batch_count": sum(1 for row in rows if row.get("usable_for_batch")),
        "usable_for_main_experiment_count": sum(1 for row in rows if row.get("usable_for_main_experiment")),
        "usable_for_case_study_count": sum(1 for row in rows if row.get("usable_for_case_study")),
    }
    return {"rows": rows, "summary": summary}


def _classify_one(plc_row: dict[str, Any], evidence_by_date: dict[str, Any]) -> dict[str, Any]:
    date = str(plc_row.get("date"))
    daily_advance = safe_float(plc_row.get("daily_advance_m"))
    has_plc = _truthy(plc_row.get("usable_for_report"))
    evidence_row = evidence_by_date.get(date)
    if evidence_row is None:
        evidence_row = evidence_by_date.get("unknown_date") or {}
    has_evidence = bool((safe_float(evidence_row.get("total_evidence_count")) or 0) > 0)
    base = {
        "date": date,
        "class_label": "D",
        "usable_for_batch": False,
        "usable_for_main_experiment": False,
        "usable_for_case_study": False,
        "reason": "",
        "daily_advance_m": daily_advance,
        "has_plc": has_plc,
        "has_evidence": has_evidence,
        "has_daily_review": False,
        "has_forward_attention": False,
        "has_GRCI": False,
        "construction_state_cells": 0,
        "warnings": [],
    }
    if not has_plc:
        base["reason"] = str(plc_row.get("exclude_reason") or "plc_not_usable")
        return base
    try:
        result = run_daily_report_pipeline(date, use_llm=False, generation_mode="template")
        scope = result.scope_summary or {}
        daily_review_count = int(scope.get("daily_review_cell_count") or len(result.daily_review_cells))
        forward_count = int(scope.get("forward_attention_cell_count") or len(result.forward_attention_cells))
        grci_count = int(scope.get("GRCI_available_count") or sum(1 for cell in result.construction_state_cells if cell.GRCI_available))
        spatial_count = int(scope.get("spatial_relevant_evidence_count") or 0)
        base.update(
            {
                "has_daily_review": daily_review_count > 0,
                "has_forward_attention": forward_count > 0,
                "has_GRCI": grci_count > 0,
                "construction_state_cells": len(result.construction_state_cells),
                "warnings": list(result.warnings),
            }
        )
        if daily_advance is not None and daily_advance > 0 and spatial_count > 0 and daily_review_count > 0 and forward_count > 0 and grci_count > 0:
            base.update(_label("A", True, True, True, "complete_plc_geology_review_forward_grci"))
        elif len(result.construction_state_cells) > 0 and (daily_review_count > 0 or forward_count > 0):
            base.update(_label("B", True, True, True, "reportable_with_partial_geology_support"))
        elif len(result.construction_state_cells) > 0:
            base.update(_label("C", True, False, False, "plc_usable_but_geology_support_is_weak"))
        else:
            base.update(_label("D", False, False, False, "pipeline_returned_no_cells"))
        return base
    except Exception as exc:
        base.update(_label("E", False, False, False, f"pipeline_failed:{exc}"))
        base["warnings"] = [traceback.format_exc(limit=3)]
        return base


def _label(label: str, batch: bool, main: bool, case: bool, reason: str) -> dict[str, Any]:
    return {
        "class_label": label,
        "usable_for_batch": batch,
        "usable_for_main_experiment": main,
        "usable_for_case_study": case,
        "reason": reason,
    }


def _resolve_backend_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_DIR / path


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    main()
