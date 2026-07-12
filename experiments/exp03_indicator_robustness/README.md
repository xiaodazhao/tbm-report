# Exp03 指标稳健性与改进分析

Exp03 用于评估当前 RAI / GRS / GRCI 启发式关注指标的排序稳健性。它是一个独立旁路实验，不修改后端主流程、不替换 Exp02 中已经冻结的指标结果，也不调用 LLM。

## 1. 实验目的

当前项目中的 RAI / GRS / GRCI 能够支撑日报生成和 Evidence Pack 选择，但其权重和公式具有工程启发式特征。Exp03 的目标是：

1. 将当前公式作为 `V0_current`；
2. 设计若干非主观或不同耦合形式的指标变体；
3. 比较不同版本下高关注 cell 和高关注日期是否稳定；
4. 判断当前 V0 指标是否可作为论文中的稳定启发式关注指标；
5. 明确后续是否需要专家标定、标签校准或更严格的权重敏感性分析。

## 2. 输入数据

默认读取：

```text
experiments/exp01_twin_full_run/outputs_fix02/date_exports/*/construction_state_cells.json
```

这些文件是已导出的 ConstructionStateCell 结果，包含：

```text
RAI / RAI components
GRS_geo_base / GRS components
GRCI / GRCI terms
cell_role
has_plc_response
has_geology_evidence
is_forward_cell
source_trace / evidence fields
```

## 3. 指标版本

| 版本 | 含义 | 说明 |
|---|---|---|
| `V0_current` | 当前主流程公式 | 不修改、不重算主流程，只读取已有 RAI/GRS/GRCI |
| `V1_percentile_equal` | 分位数标准化 + 均权 | 用作较弱主观性的基础对照 |
| `V2_percentile_interaction` | 分位数标准化 + 交互耦合 | `GRCI=sqrt(RAI*GRS)*C` |
| `V3_percentile_entropy` | 分位数标准化 + 熵权 | 权重由指标离散度自动计算 |
| `V4_percentile_critic` | 分位数标准化 + CRITIC | 权重由变异性与冲突性自动计算 |
| `V5_strict_min` | 严格耦合 | `GRCI=min(RAI,GRS)*C`，用于检验同时高响应和高地质关注时的稳定性 |

其中 `C` 为 coupling confidence。当前用可导出的 overlap、trace completeness、source reliability、evidence confidence 等字段的均值近似；若字段缺失则退化为 1。

## 4. 运行命令

在项目根目录运行：

```powershell
python experiments\exp03_indicator_robustness\run_exp03_indicator_robustness.py
```

可指定输入和输出目录：

```powershell
python experiments\exp03_indicator_robustness\run_exp03_indicator_robustness.py `
  --input-dir experiments\exp01_twin_full_run\outputs_fix02\date_exports `
  --out-dir experiments\exp03_indicator_robustness\outputs
```

## 5. 输出文件

```text
outputs/indicator_variant_summary.csv
outputs/topk_jaccard_grci.csv
outputs/spearman_rank_correlation.csv
outputs/high_grci_cell_comparison.csv
outputs/variant_high_attention_dates.csv
outputs/forward_grci_leakage_check.csv
outputs/indicator_variant_cell_scores.csv
outputs/exp03_indicator_robustness_report.md
```

## 6. 解释边界

- RAI 是施工响应关注度，不是故障概率；
- GRS 是地质证据关注度，不是灾害概率；
- GRCI 是已掘区段地质-施工响应耦合关注度，不用于前方预测；
- forward_attention cell 不计算 GRCI；
- 本实验结果只能说明排序稳健性，不能证明灾害预测准确率；
- 如果 V0 与多个变体排序相近，可在论文中说明当前启发式指标具有一定稳定性；
- 如果差异明显，应作为研究限制，说明后续需要专家权重标定或标签校准。
