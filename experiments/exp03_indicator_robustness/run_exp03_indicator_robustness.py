from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from indicator_variants import VARIANT_NAMES, compute_indicator_variants
from ranking_metrics import (
    compare_top_cells,
    high_attention_date_overlap,
    spearman_rank_correlation,
    topk_jaccard,
)


DEFAULT_INPUT_DIR = Path("experiments/exp01_twin_full_run/outputs/date_exports")
DEFAULT_OUTPUT_DIR = Path("experiments/exp03_indicator_robustness/outputs")
CASE_STUDY_DATES = ["2023-09-19", "2023-09-28", "2023-10-12"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Exp03 RAI/GRS/GRCI indicator robustness analysis.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory containing per-date pipeline exports.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for Exp03 tables and report.")
    parser.add_argument("--top-date-count", type=int, default=10)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = load_construction_state_cells(input_dir)
    if cells.empty:
        raise SystemExit(f"No construction_state_cells.json found under {input_dir}")

    variant_result = compute_indicator_variants(cells)
    variant_cells = variant_result.cells
    variant_cols = [f"{name}_GRCI" for name in VARIANT_NAMES]

    variant_result.summary.to_csv(out_dir / "indicator_variant_summary.csv", index=False, encoding="utf-8-sig")
    topk = topk_jaccard(
        variant_cells,
        baseline_col="V0_current_GRCI",
        variant_cols=[column for column in variant_cols if column != "V0_current_GRCI"],
    )
    topk.to_csv(out_dir / "topk_jaccard_grci.csv", index=False, encoding="utf-8-sig")

    spearman = spearman_rank_correlation(
        variant_cells,
        baseline_col="V0_current_GRCI",
        variant_cols=[column for column in variant_cols if column != "V0_current_GRCI"],
    )
    spearman.to_csv(out_dir / "spearman_rank_correlation.csv", index=False, encoding="utf-8-sig")

    top_cells = compare_top_cells(variant_cells, variant_cols=variant_cols, top_n=50)
    top_cells.to_csv(out_dir / "high_grci_cell_comparison.csv", index=False, encoding="utf-8-sig")

    high_dates = high_attention_date_overlap(
        variant_cells,
        baseline_col="V0_current_GRCI",
        variant_cols=[column for column in variant_cols if column != "V0_current_GRCI"],
        top_n_dates=args.top_date_count,
    )
    high_dates.to_csv(out_dir / "variant_high_attention_dates.csv", index=False, encoding="utf-8-sig")

    leakage = forward_grci_leakage_check(variant_cells, variant_cols)
    leakage.to_csv(out_dir / "forward_grci_leakage_check.csv", index=False, encoding="utf-8-sig")

    compact_cols = [
        "date",
        "global_cell_key",
        "cell_id",
        "cell_start",
        "cell_end",
        "cell_role",
        "RAI",
        "GRS_geo_base",
        "GRCI",
        "GRCI_available",
        *variant_cols,
    ]
    available_compact_cols = [column for column in compact_cols if column in variant_cells.columns]
    variant_cells[available_compact_cols].to_csv(out_dir / "indicator_variant_cell_scores.csv", index=False, encoding="utf-8-sig")

    report = build_report(
        input_dir=input_dir,
        cells=variant_cells,
        summary=variant_result.summary,
        topk=topk,
        spearman=spearman,
        high_dates=high_dates,
        leakage=leakage,
        warnings=variant_result.warnings,
    )
    (out_dir / "exp03_indicator_robustness_report.md").write_text(report, encoding="utf-8")
    print(f"Exp03 finished. date_count={cells['date'].nunique()} cell_count={len(cells)} output_dir={out_dir}")


def load_construction_state_cells(input_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*/construction_state_cells.json")):
        date = path.parent.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            rows.append({"date": date, "load_error": str(exc)})
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["date"] = date
            row["global_cell_key"] = f"{date}:{row.get('cell_id')}"
            rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for column in [
        "cell_start",
        "cell_end",
        "cell_center",
        "RAI",
        "GRS_geo_base",
        "GRCI",
        "stop_ratio",
        "abnormal_ratio",
        "speed_drop_score",
        "torque_volatility_score",
        "speed_volatility_score",
        "grade_score_component",
        "hazard_component",
        "confidence_component",
        "evidence_overlap_ratio",
        "max_overlap_ratio",
        "trace_completeness",
        "source_reliability",
        "evidence_confidence",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def forward_grci_leakage_check(frame: pd.DataFrame, variant_cols: list[str]) -> pd.DataFrame:
    role = frame.get("cell_role", pd.Series("", index=frame.index)).astype(str)
    is_forward = role.eq("forward_attention") | frame.get("is_forward_cell", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    rows = []
    for column in variant_cols:
        if column not in frame.columns:
            count = 0
        else:
            count = int(pd.to_numeric(frame.loc[is_forward, column], errors="coerce").notna().sum())
        rows.append(
            {
                "variant": column.removesuffix("_GRCI"),
                "forward_cell_with_grci_count": count,
                "passed": count == 0,
            }
        )
    return pd.DataFrame(rows)


def build_report(
    *,
    input_dir: Path,
    cells: pd.DataFrame,
    summary: pd.DataFrame,
    topk: pd.DataFrame,
    spearman: pd.DataFrame,
    high_dates: pd.DataFrame,
    leakage: pd.DataFrame,
    warnings: list[str],
) -> str:
    eligible = cells.get("eligible_for_grci_variant", pd.Series(False, index=cells.index)).fillna(False).astype(bool)
    case_rows = []
    for date in CASE_STUDY_DATES:
        date_rows = cells[cells["date"].astype(str).eq(date)]
        case_rows.append(
            {
                "date": date,
                "cell_count": len(date_rows),
                "eligible_cell_count": int(date_rows.get("eligible_for_grci_variant", pd.Series(False, index=date_rows.index)).sum()),
                "max_v0_grci": _fmt_float(date_rows.get("V0_current_GRCI", pd.Series(dtype=float)).max()),
                "max_v5_grci": _fmt_float(date_rows.get("V5_strict_min_GRCI", pd.Series(dtype=float)).max()),
            }
        )
    case_frame = pd.DataFrame(case_rows)

    topk_pivot = topk.pivot_table(index="variant", columns="k", values="jaccard", aggfunc="first").reset_index()
    lines = [
        "# Exp03 RAI / GRS / GRCI 指标稳健性与改进分析",
        "",
        "## 1. 实验边界",
        "",
        "- 本实验只读取已有 ConstructionStateCell / DailyConstructionTwin 导出，不修改主流程。",
        "- 本实验不运行 LLM，不改变 Exp02 的 15/30/91 天生成结果。",
        "- RAI 表示施工响应关注度，不是设备故障概率。",
        "- GRS 表示地质证据关注度，不是灾害概率。",
        "- GRCI 表示已掘区段地质-施工响应耦合关注度，不用于当前掌子面前方预测。",
        "- forward_attention cell 在所有变体中均不计算 GRCI。",
        "",
        "## 2. 数据来源",
        "",
        f"- 输入目录：`{input_dir.as_posix()}`",
        f"- 日期数：{cells['date'].nunique()}",
        f"- cell 总数：{len(cells)}",
        f"- 可复算 GRCI 的 daily_review cell 数：{int(eligible.sum())}",
        "",
        "## 3. 指标版本",
        "",
        _to_markdown(summary),
        "",
        "## 4. Top-K 高关注 cell 稳定性",
        "",
        _to_markdown(topk_pivot),
        "",
        "## 5. Spearman 排序相关性",
        "",
        _to_markdown(spearman),
        "",
        "## 6. 高关注日期重合情况",
        "",
        _to_markdown(high_dates),
        "",
        "## 7. forward_attention GRCI 泄漏检查",
        "",
        _to_markdown(leakage),
        "",
        "## 8. 典型案例日期位置",
        "",
        _to_markdown(case_frame),
        "",
        "## 9. 初步解释",
        "",
        "- 若 V1-V5 与 V0 的 Top-K Jaccard 和 Spearman 较高，说明当前启发式指标在排序层面具有一定稳健性。",
        "- 若某些变体，尤其 V5_strict_min，与 V0 差异较大，说明高关注 cell 对公式形式较敏感，后续需要专家标定或标签校准。",
        "- 本实验不能把任何 GRCI 结果解释为灾害发生概率，只能作为指标敏感性和证据选择稳定性的补充分析。",
        "",
    ]
    if warnings:
        lines.extend(["## 10. 计算警告", "", *[f"- {item}" for item in warnings], ""])
    return "\n".join(lines)


def _to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_无数据_"
    return frame.to_markdown(index=False)


def _fmt_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number):
        return None
    return round(number, 4)


if __name__ == "__main__":
    main()
