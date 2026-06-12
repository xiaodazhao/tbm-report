"""Summarize traceability tables into a compact metrics CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT_DIR / "experiments" / "outputs" / "tables"
METRICS_DIR = ROOT_DIR / "experiments" / "outputs" / "metrics"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Summarize traceability CSV tables.")
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=TABLES_DIR,
        help="Directory containing traceability_*.csv files.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=METRICS_DIR / "traceability_summary.csv",
        help="Output summary CSV path.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read UTF-8 CSV rows."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def safe_int(value: Any) -> int:
    """Convert a cell value to int when possible."""
    if value in ("", None):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def main() -> None:
    """Aggregate traceability support counts by case and method."""
    args = parse_args()
    rows_out: list[dict[str, Any]] = []

    for path in sorted(args.tables_dir.glob("traceability_*.csv")):
        rows = read_rows(path)
        grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault((row.get("case_id", ""), row.get("method", "")), []).append(row)

        for (case_id, method), group_rows in grouped.items():
            filled_rows = [row for row in group_rows if row.get("report_claim", "").strip()]
            reviewed_rows = [
                row
                for row in filled_rows
                if row.get("claim_type", "").strip()
                or row.get("evidence_source", "").strip()
                or row.get("evidence_field", "").strip()
                or row.get("evidence_text", "").strip()
                or row.get("is_supported", "").strip()
                or row.get("error_type", "").strip()
            ]
            supported = sum(1 for row in reviewed_rows if safe_int(row.get("is_supported")) == 1)
            unsupported = sum(1 for row in reviewed_rows if safe_int(row.get("is_supported")) == 0)
            unresolved = sum(1 for row in reviewed_rows if row.get("is_supported", "") == "")
            support_ratio = round(supported / len(reviewed_rows), 4) if reviewed_rows else ""
            rows_out.append(
                {
                    "case_id": case_id,
                    "method": method,
                    "claim_count": len(filled_rows),
                    "reviewed_claim_count": len(reviewed_rows),
                    "supported_count": supported,
                    "unsupported_count": unsupported,
                    "unresolved_count": unresolved,
                    "support_ratio": support_ratio,
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as handle:
        if rows_out:
            writer = csv.DictWriter(handle, fieldnames=list(rows_out[0].keys()))
            writer.writeheader()
            writer.writerows(rows_out)
        else:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "case_id",
                    "method",
                    "claim_count",
                    "reviewed_claim_count",
                    "supported_count",
                    "unsupported_count",
                    "unresolved_count",
                    "support_ratio",
                ]
            )
    print(f"Wrote traceability summary: {args.out}")


if __name__ == "__main__":
    main()
