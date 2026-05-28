# -*- coding: utf-8 -*-
"""Print TBM GRS/RAI/GRCI coupling-analysis details in the terminal.

Example:
    python backend/scripts/inspect_coupling_analysis.py --date 2023-12-30

This script reads the project's real TBM data, runs the existing backend
analysis pipeline, and prints the method parameters and segment-level result.
It does not call the LLM and does not modify source data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from services.tbm_analysis_service import analyze_tbm_data  # noqa: E402
from utils.io_utils import load_csv_by_date, load_latest_csv  # noqa: E402
from utils.serialization import serialize_for_json  # noqa: E402


DISPLAY_COLUMNS = [
    "segment",
    "segment_start_first",
    "segment_end_first",
    "geo_risk_score",
    "GRS",
    "GRS_base",
    "GRS_corrected",
    "GRS_smooth",
    "GRS_final",
    "correction",
    "correction_factor",
    "response_anomaly_index",
    "RAI",
    "stop_anomaly",
    "efficiency_anomaly",
    "param_anomaly",
    "anomaly_type",
    "anomaly_type_score",
    "delta_RAI",
    "delta_GRS",
    "sync_coupling",
    "lag_response",
    "response_change_coupling",
    "response_consistency",
    "coupling_index",
    "GRCI",
    "coupling_class",
    "coupling_type",
    "weak_anomaly_label",
    "weak_anomaly_reasons",
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Print TBM geology-response coupling analysis details."
    )
    parser.add_argument(
        "--date",
        help="Analysis date, for example 2023-12-30. If omitted, latest CSV is used.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of segment rows to print. Default: 20.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also print raw coupling_summary JSON.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the script entry point."""
    args = parse_args()
    path, df = load_csv_by_date(args.date) if args.date else load_latest_csv()
    loaded_date = args.date or _date_from_path(path)

    print_header("TBM 耦合分析终端检查")
    print(f"数据日期: {loaded_date or 'latest'}")
    print(f"CSV路径: {path}")
    print(f"记录行数: {len(df)}")

    result = analyze_tbm_data(df)
    coupling_summary = result.get("coupling_summary", {})
    coupling_validation = result.get("coupling_validation", {})
    output_paths = result.get("coupling_output_paths", {})
    high_attention = result.get("high_attention_segments", [])
    segment_df = result.get("segment_df", pd.DataFrame())

    print_header("方法版本与GRS参数")
    print(f"method: {coupling_summary.get('method', '-')}")
    print(f"grs_model_version: {coupling_summary.get('grs_model_version', '-')}")
    print(f"grs_weight_method: {coupling_summary.get('grs_weight_method', '-')}")
    print_mapping("engineering_weights", coupling_summary.get("engineering_weights", {}))
    print(f"correction_lambda: {format_value(coupling_summary.get('correction_lambda', '-'))}")
    print(f"min_grs: {format_value(coupling_summary.get('min_grs', '-'))}")
    print(f"grs_correction_mode: {coupling_summary.get('grs_correction_mode', '-')}")

    print_header("总体统计")
    summary_keys = [
        "segment_length_m",
        "segment_count",
        "GRS_mean",
        "GRS_max",
        "RAI_mean",
        "RAI_max",
        "GRCI_mean",
        "GRCI_max",
    ]
    for key in summary_keys:
        if key in coupling_summary:
            print(f"{key}: {format_value(coupling_summary.get(key))}")

    print_mapping("class_counts", coupling_summary.get("class_counts", {}))
    print_mapping("level_counts", coupling_summary.get("level_counts", {}))

    summary_text = coupling_summary.get("summary_text")
    if summary_text:
        print(f"summary_text: {summary_text}")

    print_header("弱标签验证")
    validation_keys = [
        "has_validation",
        "weak_label_count",
        "segment_count",
        "top_k",
        "top_k_hits",
        "top_k_hit_rate",
        "baseline_weak_label_rate",
        "threshold",
        "precision",
        "recall",
        "tp",
        "fp",
        "fn",
    ]
    for key in validation_keys:
        if key in coupling_validation:
            print(f"{key}: {format_value(coupling_validation.get(key))}")

    print_header("区段级结果表")
    if segment_df is None or segment_df.empty:
        print("没有区段级结果。")
    else:
        columns = [col for col in DISPLAY_COLUMNS if col in segment_df.columns]
        table = segment_df[columns].head(max(args.limit, 1)).copy()
        for col in table.columns:
            if pd.api.types.is_numeric_dtype(table[col]):
                table[col] = table[col].map(lambda value: round(float(value), 4) if pd.notna(value) else value)
        print(table.to_string(index=False))

    print_header("高关注区段")
    if high_attention:
        print(json.dumps(serialize_for_json(high_attention[: max(args.limit, 1)]), ensure_ascii=False, indent=2))
    else:
        print("没有高关注区段。")

    print_header("输出文件")
    print_mapping("coupling_output_paths", output_paths)

    warnings = coupling_summary.get("warnings") or result.get("warnings")
    if warnings:
        print_header("Warnings")
        for item in warnings:
            print(f"- {item}")

    if args.json:
        print_header("coupling_summary JSON")
        print(json.dumps(serialize_for_json(coupling_summary), ensure_ascii=False, indent=2))

    return 0


def print_header(title: str) -> None:
    """Print header."""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_mapping(title: str, mapping: Any) -> None:
    """Print mapping."""
    print(f"{title}:")
    if not mapping:
        print("  -")
        return
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            print(f"  {key}: {format_value(value)}")
        return
    print(f"  {format_value(mapping)}")


def format_value(value: Any) -> str:
    """Format value."""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _date_from_path(path: Path) -> str | None:
    """Internal helper for date from path."""
    try:
        raw = path.name.replace("tbm_data_", "").replace(".csv", "")
        if len(raw) == 8:
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    except Exception:
        return None
    return None


if __name__ == "__main__":
    raise SystemExit(main())