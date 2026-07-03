from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


BASE = Path("experiments/exp03_indicator_robustness/outputs")
FIG_DIR = BASE / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

summary = pd.read_csv(BASE / "indicator_variant_summary.csv")
topk = pd.read_csv(BASE / "topk_jaccard_grci.csv")
spearman = pd.read_csv(BASE / "spearman_rank_correlation.csv")
high_dates = pd.read_csv(BASE / "variant_high_attention_dates.csv")
leakage = pd.read_csv(BASE / "forward_grci_leakage_check.csv")

variant_cn = {
    "V0_current": "V0 当前主流程公式",
    "V1_percentile_equal": "V1 分位数标准化 + 均权",
    "V2_percentile_interaction": "V2 分位数标准化 + 交互耦合",
    "V3_percentile_entropy": "V3 分位数标准化 + 熵权",
    "V4_percentile_critic": "V4 分位数标准化 + CRITIC",
    "V5_strict_min": "V5 严格 min 耦合",
}


def write_table(name: str, frame: pd.DataFrame, title: str) -> None:
    frame.to_csv(BASE / f"{name}.csv", index=False, encoding="utf-8-sig")
    (BASE / f"{name}.md").write_text(f"# {title}\n\n" + frame.to_markdown(index=False) + "\n", encoding="utf-8")


variant_table = summary.copy()
variant_table.insert(1, "variant 中文解释", variant_table["variant"].map(variant_cn))
variant_table = variant_table[
    [
        "variant",
        "variant 中文解释",
        "available_cell_count",
        "mean_grci",
        "max_grci",
        "uses_forward_attention_grci",
    ]
]
write_table("publication_table_exp03_variant_summary", variant_table, "Exp03 指标变体概览")

topk_table = topk.copy()
topk_table["variant 中文解释"] = topk_table["variant"].map(variant_cn)
topk_table = topk_table[
    [
        "variant",
        "variant 中文解释",
        "k",
        "baseline_topk_count",
        "variant_topk_count",
        "overlap_count",
        "jaccard",
    ]
]
write_table("publication_table_exp03_topk_jaccard", topk_table, "Exp03 Top-K high GRCI cell Jaccard 重合度")

spearman_table = spearman.copy()
spearman_table["variant 中文解释"] = spearman_table["variant"].map(variant_cn)
spearman_table = spearman_table[["variant", "variant 中文解释", "common_cell_count", "spearman_correlation"]]
write_table("publication_table_exp03_spearman", spearman_table, "Exp03 GRCI 排序 Spearman 相关性")

high_dates_table = high_dates.copy()
high_dates_table["variant 中文解释"] = high_dates_table["variant"].map(variant_cn)
high_dates_table = high_dates_table[
    [
        "variant",
        "variant 中文解释",
        "top_n_dates",
        "overlap_count",
        "jaccard",
        "baseline_dates",
        "variant_dates",
    ]
]
write_table("publication_table_exp03_high_attention_dates", high_dates_table, "Exp03 高关注日期重合度")

leakage_table = leakage.copy()
leakage_table["variant 中文解释"] = leakage_table["variant"].map(variant_cn)
leakage_table = leakage_table[["variant", "variant 中文解释", "forward_cell_with_grci_count", "passed"]]
write_table("publication_table_exp03_forward_leakage", leakage_table, "Exp03 forward_attention GRCI 泄漏检查")

# Figures.
plt.rcParams["font.family"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
plot = spearman_table.copy()
plot["short"] = plot["variant"].str.replace("_percentile", "", regex=False).str.replace("_", "\n")
bars = ax.bar(plot["variant"].str.replace("_GRCI", "", regex=False), plot["spearman_correlation"], color="#4c78a8", edgecolor="black", linewidth=0.5)
ax.set_ylim(0, 1.05)
ax.set_ylabel("Spearman correlation with V0")
ax.set_title("GRCI ranking correlation between V0 and variants")
ax.grid(axis="y", linestyle="--", alpha=0.35)
ax.tick_params(axis="x", labelrotation=25)
for bar in bars:
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width() / 2, h, f"{h:.3f}", ha="center", va="bottom", fontsize=8)
fig.tight_layout()
fig.savefig(FIG_DIR / "fig_exp03_spearman_correlation.png", bbox_inches="tight")
fig.savefig(FIG_DIR / "fig_exp03_spearman_correlation.pdf", bbox_inches="tight")
plt.close(fig)

fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=160)
for variant, part in topk.groupby("variant"):
    ax.plot(part["k"], part["jaccard"], marker="o", label=variant.replace("_percentile", "").replace("_", " "))
ax.set_xlabel("Top-K cells")
ax.set_ylabel("Jaccard similarity with V0")
ax.set_title("Top-K high-attention cell overlap")
ax.set_ylim(0, 1.0)
ax.grid(True, linestyle="--", alpha=0.35)
ax.legend(fontsize=7, ncol=2)
fig.tight_layout()
fig.savefig(FIG_DIR / "fig_exp03_topk_jaccard.png", bbox_inches="tight")
fig.savefig(FIG_DIR / "fig_exp03_topk_jaccard.pdf", bbox_inches="tight")
plt.close(fig)

fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
x = range(len(summary))
width = 0.36
ax.bar([i - width / 2 for i in x], summary["mean_grci"], width, label="mean GRCI", color="#59a14f", edgecolor="black", linewidth=0.5)
ax.bar([i + width / 2 for i in x], summary["max_grci"], width, label="max GRCI", color="#f28e2b", edgecolor="black", linewidth=0.5)
ax.set_xticks(list(x))
ax.set_xticklabels(summary["variant"], rotation=25, ha="right")
ax.set_ylabel("GRCI score")
ax.set_title("GRCI scale under indicator variants")
ax.grid(axis="y", linestyle="--", alpha=0.35)
ax.legend()
fig.tight_layout()
fig.savefig(FIG_DIR / "fig_exp03_variant_grci_scale.png", bbox_inches="tight")
fig.savefig(FIG_DIR / "fig_exp03_variant_grci_scale.pdf", bbox_inches="tight")
plt.close(fig)

best_topk = topk.pivot(index="variant", columns="k", values="jaccard").reset_index()
report = f"""# Exp03 RAI / GRS / GRCI 指标稳健性分析（论文材料）

## 1. 实验目的

Exp03 用于检查当前 RAI / GRS / GRCI 启发式关注指标在不同标准化、权重和耦合形式下的排序稳健性。本实验不修改主流程，不替换 Exp02 中已经冻结的 V0 指标结果，也不运行 LLM。所有结果仅用于说明指标敏感性和论文方法边界。

## 2. 数据范围

- 日期数：91 天。
- 全部 ConstructionStateCell 数：1264。
- 可复算 GRCI 的 daily_review cell 数：175。
- forward_attention cell 不参与 GRCI 复算。

## 3. 指标变体

{variant_table.to_markdown(index=False)}

## 4. 排序稳健性结果

### 4.1 Spearman 排序相关性

{spearman_table.to_markdown(index=False)}

Spearman 结果显示，V1 与 V0 的相关性最高，为 0.9317；V2、V3、V4 与 V0 的相关性约为 0.877-0.889；最严格的 V5 与 V0 的相关性为 0.8168。整体看，V0 与主要变体之间仍保持较高排序相关，说明当前启发式指标在整体排序层面具有一定稳定性。

### 4.2 Top-K 高关注 cell 重合度

{best_topk.to_markdown(index=False)}

Top-K Jaccard 结果显示，V1 与 V0 的高关注 cell 重合度最高，Top-50 Jaccard 为 0.7241。交互耦合类变体 V2/V3/V4 的 Top-50 Jaccard 约为 0.538-0.587。V5 strict_min 的重合度最低，说明当耦合公式要求 RAI 与 GRS 同时较高时，高关注 cell 的精确选择会发生较明显变化。

### 4.3 高关注日期重合度

{high_dates_table.to_markdown(index=False)}

高关注日期层面，V1 与 V0 的 Top-10 日期重合 8 天，Jaccard 为 0.6667；V2/V3/V4 重合 6 天；V5 重合 4 天。说明在日期级别，当前 V0 与多数变体仍保留一定一致性，但严格耦合形式会改变部分高关注日期排序。

## 5. forward_attention 泄漏检查

{leakage_table.to_markdown(index=False)}

所有指标变体中，forward_attention cell 的 GRCI 计数均为 0，说明 Exp03 复算没有破坏“GRCI 只用于已掘 daily_review 复核，不用于前方提示”的语义边界。

## 6. 论文解释建议

1. 当前 V0 指标可以作为工程启发式关注指标使用，但不应表述为灾害概率或预测模型。
2. 排序相关性结果表明，V0 与均权、分位数、熵权和 CRITIC 等变体整体相关性较高，支持“当前指标具有一定排序稳健性”的保守结论。
3. Top-K 结果显示，高关注 cell 的精确选择对耦合形式仍有敏感性，尤其是 V5 strict_min。这一现象应写入局限性，说明后续需要专家标定、标签校准或更大规模工程验证。
4. 本实验不建议替换主流程公式，适合作为论文中的指标敏感性/稳健性补充实验。

## 7. 结论

Exp03 表明，当前 RAI / GRS / GRCI V0 公式在整体排序层面具有一定稳定性，尤其与分位数均权版本 V1 高度一致；但在 Top-K 高关注 cell 精确选择上，不同耦合形式会带来一定差异。因此，本文可以保留 V0 作为工程启发式关注指标，同时在论文中明确其非概率、非预测性质，并将权重和耦合形式敏感性作为研究边界。
"""

(BASE / "paper_exp03_indicator_robustness_analysis.md").write_text(report, encoding="utf-8")

print("Exp03 publication materials generated.")
