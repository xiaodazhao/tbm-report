# 实验与复盘脚本说明

本文说明当前后端可用于实验复盘、论文表格生成和工程验收的脚本。所有脚本默认服务“导出、统计、对比”，不改变主 pipeline，不接入 claim-first generation，不让 P3 candidate evidence 进入正式主链路。

## 1. 推荐输出目录结构

建议后续实验统一使用：

```text
outputs/
├── smoke_summary.json
├── pipeline_exports/
│   └── 2023-12-30/
│       ├── construction_state_cells.csv
│       ├── evidence_pack.json
│       ├── quality.json
│       ├── trace.json
│       └── method_metrics.json
├── analysis/
│   ├── batch_metrics/
│   ├── generation_modes/
│   ├── grci_weights/
│   └── cell_size/
└── allowed_claims/
```

## 2. analyze_batch_metrics.py

用途：

- 汇总多日期 pipeline 导出结果；
- 统计质量分、grounding rate、unsupported claim、error type；
- 统计 cell role、GRCI available、trace completeness 等方法指标。

输入：

```text
outputs/pipeline_exports/<date>/
```

要求每个日期目录尽量包含：

- `method_metrics.json`
- `quality.json`
- `trace.json`
- `summary.json`

命令：

```powershell
python scripts/analyze_batch_metrics.py `
  --input-dir outputs/pipeline_exports `
  --out-dir outputs/analysis/batch_metrics
```

输出：

- `batch_method_metrics_summary.csv`
- `batch_method_metrics_summary.json`
- `quality_distribution.csv`
- `error_type_distribution.csv`
- `grci_availability_distribution.csv`
- `cell_role_distribution.csv`
- `batch_analysis_summary.json`

可对应论文内容：

- 批量运行稳定性表；
- 报告质量与 grounding 统计表；
- 错误类型分布图；
- daily_review / forward_attention / local_background cell 数量分布图。

## 3. analyze_generation_modes.py

用途：

- 对比不同报告生成模式；
- 统计各模式的 quality score、grounding rate、trace coverage、unsupported claim、错误类型分布；
- 支撑 template、Evidence Pack LLM、planner、revision 等模式对比。

输入：

多个生成模式导出目录，每个目录下按日期组织：

```text
outputs/template_exports/<date>/
outputs/planner_exports/<date>/
```

命令：

```powershell
python scripts/analyze_generation_modes.py `
  --mode-dir template=outputs/template_exports `
  --mode-dir planner=outputs/planner_exports `
  --out-dir outputs/analysis/generation_modes
```

输出：

- `generation_mode_comparison.csv`
- `generation_mode_comparison_summary.json`
- `generation_mode_error_type_summary.csv`

可对应论文内容：

- 生成模式对比表；
- planner / revision 对 grounding 的影响；
- 不同模式下错误类型变化。

边界：

- 该脚本只读取已有导出；
- 不调用真实 LLM；
- 不改变生成流程。

## 4. analyze_grci_weight_sensitivity.py

用途：

- 在导出的 `construction_state_cells.csv` 上重算 GRCI；
- 比较不同启发式权重下的 GRCI 排序稳定性；
- 只做稳定性检验，不做灾害预测验证。

输入：

```text
outputs/pipeline_exports/<date>/construction_state_cells.csv
```

命令：

```powershell
python scripts/analyze_grci_weight_sensitivity.py `
  --input-dir outputs/pipeline_exports `
  --out-dir outputs/analysis/grci_weights
```

输出：

- `grci_weight_sensitivity_cells.csv`
- `grci_weight_sensitivity_summary.csv`
- `grci_weight_sensitivity_summary.json`
- `grci_topk_stability.csv`

默认权重方案包括：

- default；
- default +/- 10%；
- default +/- 20%；
- GRS-dominant；
- RAI-dominant；
- interaction-dominant。

可对应论文内容：

- GRCI 权重敏感性表；
- top-k high attention cell 稳定性图；
- 不同权重下排序变化分析。

边界：

- 只对 `daily_review` 且 `GRCI_available=true` 的 cell 重算；
- forward_attention 和 local_background 不计算正式 GRCI；
- 当前没有灾害发生标签、异常原因标签或现场复核标签，因此不做监督学习权重校准。

## 5. analyze_cell_size_sensitivity.py

用途：

- 运行不同 cell 尺度下的 pipeline；
- 比较 5m / 10m 下 construction_state_cells、GRCI available、high attention cell、Quality / Trace 等指标；
- 检查实际 PLC 推进范围是否保持稳定。

命令：

```powershell
python scripts/analyze_cell_size_sensitivity.py `
  --dates 2023-12-30,2023-12-28 `
  --cell-sizes 5,10 `
  --out-dir outputs/analysis/cell_size
```

输出：

- `cell_size_sensitivity_summary.csv`
- `cell_size_sensitivity_summary.json`
- `cell_size_comparison_by_date.csv`

可对应论文内容：

- cell 尺度敏感性表；
- 5m/10m 对 cell 数、GRCI 可用数和报告质量的影响；
- cell 对齐范围与 PLC 实测范围的区别说明。

边界：

- 默认只比较 5m / 10m；
- 10m 是最大推荐日报复核尺度；
- 不默认使用 20m；
- `daily_plc_range` / `daily_advance_m` 才是实际推进范围和推进量；
- `daily_excavated_scope` 是 cell 对齐后的复核范围，可能随 cell 尺度变化。

## 6. export_allowed_claims.py

用途：

- 从 Evidence Pack 旁路导出 allowed claims；
- 为后续 claim-first generation 研究保留材料；
- 当前不参与默认生成流程。

命令：

```powershell
python scripts/export_allowed_claims.py `
  --dates 2023-12-30 `
  --out-dir outputs/allowed_claims
```

输出：

- `outputs/allowed_claims/<date>/allowed_claims.json`
- `outputs/allowed_claims/allowed_claims_summary.json`

可对应论文内容：

- claim-level evidence grounding 案例；
- 后续 claim-first generation 的候选材料说明。

边界：

- `enable_claim_first=false`；
- 不接入默认报告生成；
- 不改变 template、LLM、planner 或 revision 行为。

## 7. 推荐实验命令清单

```powershell
python scripts/smoke_test_daily_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out outputs/smoke_summary.json

python scripts/export_daily_pipeline_outputs.py --dates 2023-12-30,2023-12-28 --no-llm --out-dir outputs/pipeline_exports

python scripts/analyze_batch_metrics.py --input-dir outputs/pipeline_exports --out-dir outputs/analysis/batch_metrics

python scripts/analyze_generation_modes.py --mode-dir template=outputs/pipeline_exports --out-dir outputs/analysis/generation_modes

python scripts/analyze_grci_weight_sensitivity.py --input-dir outputs/pipeline_exports --out-dir outputs/analysis/grci_weights

python scripts/analyze_cell_size_sensitivity.py --dates 2023-12-30,2023-12-28 --cell-sizes 5,10 --out-dir outputs/analysis/cell_size

python scripts/export_allowed_claims.py --dates 2023-12-30 --out-dir outputs/allowed_claims
```

