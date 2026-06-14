# 后续实验计划

本文记录当前后端研究原型进入实验阶段后的推荐实验设计。当前方法主线已经冻结，后续实验不再默认新增方法模块，而是围绕稳定性、敏感性、生成模式和典型案例复盘展开。

## 1. 已有工程基础

当前已完成：

- 单日 pipeline 可运行；
- 三日期 no-LLM smoke 通过；
- 2023-12-30 `construction_state_cells = 14`；
- 91 天 PLC audit 可用；
- 91 天 batch pipeline 成功；
- 91 天 batch mock LLM 成功；
- P3 mock extraction 成功；
- 当前 pytest 持续通过。

当前指标口径：

- RAI / GRS / GRCI 是启发式关注指标，不是灾害预测模型；
- 当前没有灾害发生标签、异常原因标签或现场复核标签，因此不做监督学习式权重校准；
- GRCI 只用于 `daily_review`，不用于 `forward_attention`；
- `daily_plc_range` / `daily_advance_m` 是 PLC 实测范围和推进量，`daily_excavated_scope` 是 cell 对齐复核范围。

## 2. generation mode 对比

拟比较：

- `template`
- `evidence_pack_llm`
- `evidence_pack_llm_with_revision`
- `evidence_pack_planner_llm`
- `evidence_pack_planner_llm_with_revision`

评价指标：

- `quality_score`
- `grounding_rate`
- `unsupported_claim_count`
- E2 / E3 / E10 / E14 等错误数量
- report section completeness
- revision 前后差异

## 3. GRCI 权重敏感性

推荐脚本：

```powershell
python scripts/analyze_grci_weight_sensitivity.py --input-dir outputs/pipeline_exports --out-dir outputs/analysis/grci_weights
```

目标是分析不同启发式权重下 high attention cell 排序是否稳定。该实验不是灾害预测验证，也不使用监督标签。

## 4. cell 尺度敏感性

推荐脚本：

```powershell
python scripts/analyze_cell_size_sensitivity.py --dates 2023-12-30,2023-12-28 --cell-sizes 5,10 --out-dir outputs/analysis/cell_size
```

目标是比较 5m/10m 下 cell 数量、GRCI available 数、Quality / Trace 和 Evidence Pack selection 的变化。10m 是最大推荐日报复核尺度，不默认使用 20m。

## 5. generation mode 对比与 revision 效果

比较 revision 前后：

- unsupported claim 是否减少；
- 数值语义错误是否减少；
- GRCI 概率误用是否减少；
- 前方提示误写为事实是否减少；
- 文本结构是否保持完整。

## 6. P3 地质文本抽取准确率

P3 需要人工 gold standard：

- 从 TSP/HSP/sketch 原文中人工标注里程、围岩等级、hazard、evidence_role、original_text_span；
- 与 P3 candidate evidence 对比；
- 统计 chainage accuracy、hazard tag precision/recall、role accuracy、validation failure rate。

## 7. 人工评价

可邀请 TBM 施工或地质专家评价：

- 报告结构完整性；
- 证据引用可追溯性；
- 地质-施工响应复核合理性；
- 前方关注提示是否过度表达；
- 建议是否保守且有依据。

## 8. 典型案例导出

建议选择：

- GRCI available 且中高关注的日期；
- 前方关注证据较充分的日期；
- PLC 推进短、证据弱的日期；
- revision 改善明显的日期。

每个案例导出 Evidence Pack、Trace、报告和关键 cells。

## 9. 待补事项

```text
真实 DeepSeek 抽样验证
generation mode 批量统计
5m/10m cell 尺度敏感性
GRCI 权重敏感性
P3 gold standard
human evaluation
case studies
```
