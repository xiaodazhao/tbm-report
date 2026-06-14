# 后续实验计划

本文记录当前后端研究原型之后的实验设计，不表示这些实验已经完成。

## 1. 已有工程基础

当前已完成：

- 单日 pipeline 可运行；
- 三日期 no-LLM smoke 通过；
- 2023-12-30 `construction_state_cells = 14`；
- 91 天 PLC audit 可用；
- 91 天 batch pipeline 成功；
- 91 天 batch mock LLM 成功；
- P3 mock extraction 成功；
- 当前 pytest = 62 passed。

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

## 3. 消融实验

可设计消融：

1. 去掉 Evidence Pack 分层；
2. 去掉 planner；
3. 去掉 revision；
4. 去掉 Quality / Trace 反馈；
5. 去掉 GRCI，仅使用 GRS/RAI；
6. 不区分 daily_review / forward_attention / local_background。

目标是说明各模块对报告可追溯性、语义正确性和错误减少的贡献。

## 4. revision 效果分析

比较 revision 前后：

- unsupported claim 是否减少；
- 数值语义错误是否减少；
- GRCI 概率误用是否减少；
- 前方提示误写为事实是否减少；
- 文本结构是否保持完整。

## 5. P3 地质文本抽取准确率

P3 需要人工 gold standard：

- 从 TSP/HSP/sketch 原文中人工标注里程、围岩等级、hazard、evidence_role、original_text_span；
- 与 P3 candidate evidence 对比；
- 统计 chainage accuracy、hazard tag precision/recall、role accuracy、validation failure rate。

## 6. 人工评价

可邀请 TBM 施工或地质专家评价：

- 报告结构完整性；
- 证据引用可追溯性；
- 地质-施工响应复核合理性；
- 前方关注提示是否过度表达；
- 建议是否保守且有依据。

## 7. 典型案例导出

建议选择：

- GRCI available 且中高关注的日期；
- 前方关注证据较充分的日期；
- PLC 推进短、证据弱的日期；
- revision 改善明显的日期。

每个案例导出 Evidence Pack、Trace、报告和关键 cells。

## 8. 待补事项

```text
真实 DeepSeek 抽样验证
planner 模式批量统计
ablation
P3 gold standard
human evaluation
case studies
```
