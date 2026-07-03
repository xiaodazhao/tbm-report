# Codex 可继续推进的工作清单

本文档记录当前 TBM 施工日报项目中，Codex 可以继续协助完成的工作范围。原则是：不替代人工工程判断，但可以承担代码实现、结果统计、论文材料整理、图表生成、实验复核和方法文档化工作。

## 1. 实验统计与显著性分析

- 基于 91 天 structured_trace_v1 结果，计算 M4 与 M1/M2/M3 的配对显著性检验。
- 输出 Wilcoxon signed-rank test、均值/中位数、效应量和 p 值。
- 生成 quality、grounding、unsupported、numeric 的箱线图和分布图。
- 写成论文“统计显著性分析”小节。

## 2. 典型案例分析

- 从 91 天结果中筛选代表性日期。
- 对比 M1/M2/M3/M4 的报告质量差异。
- 抽取典型 unsupported、numeric、boundary 或 trace mismatch 样本。
- 整理 claim 到 evidence 的追踪表。
- 写成论文 case study 草稿。

## 3. RAI / GRS / GRCI 稳健性分析

- 基于已有 ConstructionStateCell / DailyConstructionTwin 输出做旁路复算。
- 比较当前权重、均权、分位数、熵权、CRITIC、严格耦合等指标变体。
- 计算 Top-K overlap、Spearman rank correlation、高关注日期重合度。
- 输出指标稳健性报告，说明 GRCI 是启发式关注指标，不是灾害概率。

## 4. 自动评价体系审计

- 抽样整理 unsupported、numeric、boundary、grounded claim。
- 生成待人工复核表。
- 统计 checker 的疑似误伤类型。
- 分析自动评价指标的适用边界。
- 为人工评价准备标注表和说明文档。

## 5. 论文方法章节写作

- 写任务定义。
- 写多源证据治理流程。
- 写 ConstructionStateCell / DailyConstructionTwin 方法。
- 写 Evidence Pack 约束生成方法。
- 写 Structured Trace、Boundary Checker、Quality Checker、Reviser。
- 把代码逻辑抽象成论文方法，而不是项目说明书。

## 6. 论文实验章节写作

- 整理 M0-M4 生成模式对比。
- 整理 91 天真实 LLM 回归结果。
- 写 M4 修订前后分析。
- 写 M3 与 M4 差异分析。
- 写 M0 模板基线解释。
- 写 residual error 和局限性分析。

## 7. 论文图表生成

- 方法总框架图。
- Evidence Pack / Trace 流程图。
- M0-M4 对比流程图。
- 91 天指标箱线图。
- 修订前后对比图。
- case study 的 claim-evidence trace 图。

## 8. 人工评价辅助材料

- 生成报告抽样清单。
- 生成评分表。
- 生成评价说明。
- 合并人工评价结果。
- 计算评价者一致性和自动指标相关性。

## 9. 项目瘦身与复现整理

- 梳理论文主线代码。
- 归档旧实验、旧脚本和无关输出。
- 整理 README 和复现命令。
- 固化实验输入、输出和结果目录说明。
- 形成论文复现包。

## 10. 投稿前材料整理

- 整理论文三线表。
- 整理中英文摘要初稿。
- 整理创新点表述。
- 整理方法局限性。
- 整理投稿期刊候选和匹配方向。

## 当前最建议优先做的 5 件事

1. 基于 91 天结果做 M4 vs M1/M2/M3 的统计显著性检验。
2. 选 1-2 个典型日期做 case study。
3. 做 RAI / GRS / GRCI 稳健性分析。
4. 生成自动 checker 抽样复核表，为人工评价做准备。
5. 开始写论文方法章节，把项目逻辑抽象成方法论。

