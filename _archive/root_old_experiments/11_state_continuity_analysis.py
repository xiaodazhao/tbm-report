"""Build a lightweight CST state continuity case study from exported state snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
STATES_DIR = ROOT_DIR / "experiments" / "outputs" / "states"
METRICS_DIR = ROOT_DIR / "experiments" / "outputs" / "metrics"
TABLES_DIR = ROOT_DIR / "experiments" / "outputs" / "tables"


FORWARD_SCORE = {"none": 0, "low": 1, "medium": 2, "high": 3}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Summarize state continuity across exported CST cases.")
    parser.add_argument(
        "--summary",
        type=Path,
        default=STATES_DIR / "state_summary.csv",
        help="State summary CSV exported by 01_export_cst_states.py.",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=METRICS_DIR / "state_continuity_summary.csv",
        help="Output CSV for continuity metrics.",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=TABLES_DIR / "state_continuity_overview.md",
        help="Output markdown overview.",
    )
    return parser.parse_args()


def load_state_json(case_id: str) -> dict[str, Any]:
    """Load a single exported CST state json."""
    path = STATES_DIR / f"{case_id}_state.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def hazard_set(state: dict[str, Any]) -> set[str]:
    """Extract a compact hazard set from geological state."""
    hazards = state.get("geological_state", {}).get("hazards") or []
    return {str(item).strip() for item in hazards if str(item).strip()}


def forward_level(state: dict[str, Any]) -> str:
    """Return the first forward attention level if available."""
    windows = state.get("spatial_state", {}).get("forward_window") or []
    if not windows:
        return "none"
    return str(windows[0].get("advice_level") or "none").lower()


def main() -> None:
    """Build pairwise continuity summaries across cases ordered by date."""
    args = parse_args()
    df = pd.read_csv(args.summary, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "case_id"]).reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    md_lines = ["# State Continuity Overview", ""]

    previous_state: dict[str, Any] | None = None
    previous_case: pd.Series | None = None
    for _, current in df.iterrows():
        current_state = load_state_json(current["case_id"])
        if previous_state is None or previous_case is None:
            previous_state = current_state
            previous_case = current
            continue

        prev_hazards = hazard_set(previous_state)
        curr_hazards = hazard_set(current_state)
        shared_hazards = sorted(prev_hazards & curr_hazards)
        prev_forward = forward_level(previous_state)
        curr_forward = forward_level(current_state)

        row = {
            "prev_case_id": previous_case["case_id"],
            "prev_date": previous_case["date"].strftime("%Y-%m-%d"),
            "curr_case_id": current["case_id"],
            "curr_date": current["date"].strftime("%Y-%m-%d"),
            "delta_GRS": round(float(current["GRS"]) - float(previous_case["GRS"]), 4),
            "delta_RAI": round(float(current["RAI"]) - float(previous_case["RAI"]), 4),
            "delta_GRCI": round(float(current["GRCI"]) - float(previous_case["GRCI"]), 4),
            "prev_main_state": previous_case["main_state"],
            "curr_main_state": current["main_state"],
            "prev_forward_level": prev_forward,
            "curr_forward_level": curr_forward,
            "forward_level_shift": FORWARD_SCORE.get(curr_forward, 0) - FORWARD_SCORE.get(prev_forward, 0),
            "shared_hazard_count": len(shared_hazards),
            "shared_hazards": "、".join(shared_hazards),
        }
        rows.append(row)

        md_lines.extend(
            [
                f"## {row['prev_case_id']} -> {row['curr_case_id']}",
                "",
                f"- 日期：{row['prev_date']} -> {row['curr_date']}",
                f"- GRS 变化：{row['delta_GRS']:+.4f}",
                f"- RAI 变化：{row['delta_RAI']:+.4f}",
                f"- GRCI 变化：{row['delta_GRCI']:+.4f}",
                f"- 主导工况：{row['prev_main_state']} -> {row['curr_main_state']}",
                f"- 前方关注等级：{row['prev_forward_level']} -> {row['curr_forward_level']}",
                f"- 共有风险标签（{row['shared_hazard_count']}）：{row['shared_hazards'] or '无'}",
                "",
            ]
        )

        previous_state = current_state
        previous_case = current

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out_csv, index=False, encoding="utf-8-sig")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Wrote continuity csv: {args.out_csv}")
    print(f"Wrote continuity overview: {args.out_md}")


if __name__ == "__main__":
    main()
