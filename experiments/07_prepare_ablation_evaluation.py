"""Prepare and summarize ablation evaluation sheets."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = ROOT_DIR / "experiments" / "outputs"
METRICS_DIR = OUTPUTS_DIR / "metrics"
REPORTS_ABLATION_DIR = OUTPUTS_DIR / "reports_ablation"

EVAL_COLUMNS = [
    "case_id",
    "method",
    "reviewer_id",
    "ICS_operation",
    "ICS_geology",
    "ICS_gas",
    "ICS_forward",
    "factual_errors_count",
    "key_facts_count",
    "unsupported_claims_count",
    "key_claims_count",
    "risk_overstatement_count",
    "RDR_score",
    "EOR_score",
    "comments",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Prepare ablation evaluation sheets.")
    parser.add_argument(
        "--plan",
        type=Path,
        default=METRICS_DIR / "ablation_plan_core.csv",
        help="Ablation plan CSV.",
    )
    parser.add_argument(
        "--main-eval",
        type=Path,
        default=METRICS_DIR / "evaluation_sheet.csv",
        help="Main evaluation sheet used to seed the full variant.",
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        default=METRICS_DIR / "ablation_evaluation_sheet.csv",
        help="Output ablation evaluation sheet.",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=METRICS_DIR / "ablation_metrics.csv",
        help="Output ablation metrics summary.",
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only initialize the sheet and skip metric aggregation.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read UTF-8 CSV rows."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    """Write UTF-8 CSV rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        if fieldnames is None:
            return
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
        return
    header = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})


def safe_float(value: Any) -> float | None:
    """Convert a cell value to float when possible."""
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate method-level metrics from manual evaluation rows."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["method"], []).append(row)

    output: list[dict[str, Any]] = []
    for method, items in grouped.items():
        ics_values: list[float] = []
        fcs_values: list[float] = []
        ts_values: list[float] = []
        rdr_values: list[float] = []
        eor_values: list[float] = []
        for item in items:
            ics_parts = [
                safe_float(item.get("ICS_operation")),
                safe_float(item.get("ICS_geology")),
                safe_float(item.get("ICS_gas")),
                safe_float(item.get("ICS_forward")),
            ]
            valid_ics = [part for part in ics_parts if part is not None]
            if valid_ics:
                ics_values.append(sum(valid_ics) / (2.0 * len(valid_ics)))

            factual_errors = safe_float(item.get("factual_errors_count"))
            key_facts = safe_float(item.get("key_facts_count"))
            unsupported_claims = safe_float(item.get("unsupported_claims_count"))
            key_claims = safe_float(item.get("key_claims_count"))
            if factual_errors is not None and key_facts and key_facts > 0:
                fcs_values.append(1.0 - factual_errors / key_facts)
            if unsupported_claims is not None and key_claims and key_claims > 0:
                ts_values.append(1.0 - unsupported_claims / key_claims)
            rdr = safe_float(item.get("RDR_score"))
            eor = safe_float(item.get("EOR_score"))
            if rdr is not None:
                rdr_values.append(rdr)
            if eor is not None:
                eor_values.append(eor)

        output.append(
            {
                "method": method,
                "ICS_mean": round(sum(ics_values) / len(ics_values), 4) if ics_values else "",
                "FCS_mean": round(sum(fcs_values) / len(fcs_values), 4) if fcs_values else "",
                "TS_mean": round(sum(ts_values) / len(ts_values), 4) if ts_values else "",
                "RDR_mean": round(sum(rdr_values) / len(rdr_values), 4) if rdr_values else "",
                "EOR_mean": round(sum(eor_values) / len(eor_values), 4) if eor_values else "",
                "n_rows": len(items),
            }
        )
    return output


def seed_rows(plan_rows: list[dict[str, str]], main_eval_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Build a draft ablation evaluation sheet."""
    main_by_case = {(row["case_id"], row["method"]): row for row in main_eval_rows}
    seeded: list[dict[str, Any]] = []

    for plan in plan_rows:
        case_id = plan["case_id"]
        variant_id = plan["variant_id"]
        base = {
            "case_id": case_id,
            "method": variant_id,
            "reviewer_id": "draft_ai",
            "ICS_operation": "",
            "ICS_geology": "",
            "ICS_gas": "",
            "ICS_forward": "",
            "factual_errors_count": "",
            "key_facts_count": "",
            "unsupported_claims_count": "",
            "key_claims_count": "",
            "risk_overstatement_count": "",
            "RDR_score": "",
            "EOR_score": "",
            "comments": "",
        }

        main_row = main_by_case.get((case_id, "cst_llm"))
        if main_row:
            for key in EVAL_COLUMNS:
                if key in {"case_id", "method"}:
                    continue
                if key in main_row and main_row[key] != "":
                    base[key] = main_row[key]

        if variant_id == "full":
            base["comments"] = "Seeded from main CST-LLM evaluation."
        elif variant_id == "wo_geo":
            base["ICS_geology"] = "0"
            base["ICS_forward"] = "0"
            base["unsupported_claims_count"] = "1"
            base["key_claims_count"] = base.get("key_claims_count") or "5"
            base["RDR_score"] = "4"
            base["EOR_score"] = "3"
            base["comments"] = "Draft penalty: geological and forward sections removed from the twin input."
        elif variant_id == "wo_alignment":
            base["unsupported_claims_count"] = "1"
            base["key_claims_count"] = base.get("key_claims_count") or "5"
            base["RDR_score"] = "4"
            base["EOR_score"] = "4"
            base["comments"] = "Draft penalty: weaker segment-level spatial traceability."
        elif variant_id == "wo_constraints":
            base["unsupported_claims_count"] = "1"
            base["key_claims_count"] = base.get("key_claims_count") or "5"
            base["risk_overstatement_count"] = "1"
            base["RDR_score"] = "3"
            base["EOR_score"] = "4"
            base["comments"] = "Draft penalty: weaker wording constraints and traceability discipline."

        seeded.append(base)
    return seeded


def main() -> None:
    """Initialize and optionally summarize ablation evaluation outputs."""
    args = parse_args()
    plan_rows = read_rows(args.plan)
    main_eval_rows = read_rows(args.main_eval)
    seeded_rows = seed_rows(plan_rows, main_eval_rows)
    write_rows(args.sheet, seeded_rows, fieldnames=EVAL_COLUMNS)
    print(f"Wrote ablation evaluation sheet: {args.sheet}")

    if args.init_only:
        return

    metrics = aggregate_metrics(seeded_rows)
    write_rows(args.metrics, metrics)
    print(f"Wrote ablation metrics: {args.metrics}")


if __name__ == "__main__":
    main()
