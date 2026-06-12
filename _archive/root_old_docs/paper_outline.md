# 论文大纲建议

## 1. 文档目的

这份文档给出一版面向英文论文撰写的结构化大纲，帮助项目从“系统实现”收敛为“方法 + 实验”的论文形式。

本大纲服务于以下目标：

- 明确每一章写什么；
- 区分“已实现系统”和“最终版方法主张”；
- 为后续插图、实验和补材料留位置；
- 避免全文写成项目说明书。

## 2. 建议题目方向

可以围绕以下题目风格展开：

**Construction State Twin-Driven Large Language Model Framework for Automated TBM Construction Reporting**

也可以采用更稳妥的表达：

**A Construction State Twin-Based Framework for Automated TBM Construction Reporting with Large Language Models**

如果后续“可追溯性”实验做得足够强，再考虑把 `traceable` 写进题目。

## 3. 全文主线

论文的核心主张应是：

1. 原始 TBM 工程数据异构、分散，不适合直接供 LLM 生成正式报告；
2. 因此需要一个中间状态层，即 `Construction State Twin`；
3. Twin 通过统一时间-里程状态空间组织多源施工信息；
4. Twin 为 LLM 提供 state-aware prompt；
5. 由此得到更完整、更一致、更可追溯的自动化施工报告。

为了避免主线发散，全文建议只收敛为三个主贡献：

1. `Construction State Twin`
2. `GRS / RAI / GRCI` 状态指标
3. `State-aware Prompt + Traceability Evaluation`

`Agent` 不作为主贡献，只作为 `an interactive extension of CST` 出现在方法扩展或系统扩展部分。

## 4. 建议章节结构

### Abstract

摘要需要回答四件事：

- 研究问题是什么；
- 提出了什么方法；
- 方法由哪些核心模块组成；
- 实验结果说明了什么。

推荐结构：

1. 背景：TBM 报告编写依赖多源异构数据；
2. 问题：原始数据不适合直接驱动 LLM；
3. 方法：提出 `Construction State Twin + state-aware prompt + LLM` 框架；
4. 结果：相较 baseline 提升了完整性、一致性、可追溯性；
5. 结论：Twin 是自动报告生成的有效中间层。

### 1. Introduction

建议分成五段。

#### 1.1 背景

说明 TBM 施工报告需要整合：

- 日运行数据；
- 超前地质预报；
- 掌子面揭示；
- 安全监测；
- 历史施工信息。

#### 1.2 现有问题

说明当前做法存在的问题：

- 人工整合成本高；
- 原始数据异构；
- 直接 LLM 生成不稳定；
- 普通检索或模板方法缺乏状态组织。

#### 1.3 核心思路

引入 `Construction State Twin` 的必要性：

- 不是让 LLM 直接读原始数据；
- 先构造状态，再基于状态生成。

#### 1.4 主要贡献

建议列 3 点：

1. 提出一个 Construction State Twin 驱动的 TBM 报告自动生成框架；
2. 构建一套区段关注、响应异常和耦合验证的状态表征机制；
3. 设计一套围绕完整性、一致性和可追溯性的实验验证方案。

#### 1.5 文章结构

简要交代各章节内容。

### 2. Related Work

建议分 4 个子方向。

#### 2.1 TBM construction data analysis

讨论 TBM 工况分析、施工参数分析、地质-施工耦合研究。

#### 2.2 Digital twin in underground construction

讨论数字孪生在施工、隧道或设备监测中的应用。  
这里要强调你做的是**状态数字孪生**，不是几何孪生。

#### 2.3 LLM-based report generation

讨论大语言模型在工程文本生成、工业文档生成、结构化数据到文本方面的工作。

#### 2.4 Traceable and constrained generation

讨论受控生成、事实一致性、可追溯生成等方向。

最后指出空缺：

现有工作缺少一个将多源 TBM 工程数据统一成状态层、并服务于可追溯报告生成的框架。

### 3. Method

这是全文最关键的一章。

#### 3.1 Problem Formulation

定义输入、输出和目标：

- 输入：`PLC_t, Geo_t, Face_t, Gas_t`
- 中间状态：`CST_t`
- 输出：`Report_t`

给出形式化关系：

\[
CST_t = U(CST_{t-1}, PLC_t, Geo_t, Face_t, Gas_t)
\]

\[
Report_t = G(CST_t, Prompt_t)
\]

这里建议在写作中明确：

- 递推更新公式属于方法主张；
- 第一轮实验中，动态更新优先以 `case study` 和 `state continuity analysis` 呈现；
- 不必一开始就将其写成最重的量化主实验。

#### 3.2 Multi-Source Data Structuring

写：

- CSV 数据字段与清洗；
- PDF 解析与证据标准化；
- SQLite 证据存储。

#### 3.3 Construction State Twin Modeling

这节展开写 Twin：

- 时间状态；
- 空间状态；
- 运行状态；
- 地质状态；
- 响应状态；
- 关注状态；
- 追溯与记忆状态。

#### 3.4 Unified Chainage Alignment and Geo-Construction Fusion

写：

- 为什么要统一里程轴；
- 区段型和点位型证据如何挂接；
- 事实型融合输出是什么。

#### 3.5 State Indicators: GRS, RAI, and GRCI

分三小节写：

- `GRS`：地质关注度表征
- `RAI`：施工响应异常度表征
- `GRCI`：地质-施工耦合验证

这里要明确：

- `GRS`：建议在论文中统一解释为 `Geological Attention Score`，并强调其不直接预测灾害真值
- `GRS`：归一化 + 平权聚合 + 高斯平滑 + 动态修正
- `RAI`：`Isolation Forest` + 辅助异常项 + 常规停顿折减
- `GRCI`：同步、滞后、变化、一致性、来源修正

#### 3.6 State-Aware Prompt Construction and LLM Report Generation

写：

- Twin 如何转成 prompt；
- prompt 如何形式化为 `Role Instruction + CST Summary + Writing Constraints + Output Schema`；
- 如何约束风险措辞；
- 如何避免混淆当前掌子面和前方预测；
- 如何生成日报和时段报告。

#### 3.7 Interactive Query and Traceability Extension

这一节可以简写为扩展模块：

- Agent 问答；
- 历史对比；
- 证据追溯。

### 4. Experimental Setup

#### 4.1 Dataset and Case Construction

写：

- 数据来源；
- 日期范围；
- 报告数量；
- case 筛选标准；
- case 类型分布。

#### 4.2 Baselines

写：

- Template
- Direct-LLM
- 可选 RAG-LLM
- CST-LLM

并说明：

- `w/o Spatial Alignment` 应是公平 baseline，即保留 PLC 和地质摘要，但不显式提供空间映射关系；
- 不应通过“故意删掉信息”来弱化 baseline。

#### 4.3 Evaluation Metrics

写：

- `ICS`
- `FCS`
- `RDR`
- `TS`
- `EOR`

同时在文中交代实验优先级：

- 第一阶段重点指标：`ICS / FCS / TS`
- 第二阶段补充指标：`RDR / EOR`

#### 4.4 Implementation Details

写：

- 模型提供方；
- prompt 约束策略；
- 主要算法实现；
- 超参数，如区段长度、平滑尺度、异常检测参数等。

### 5. Results and Analysis

#### 5.1 Main Comparison Results

比较各 baseline。

#### 5.2 Ablation Study

证明 Twin 关键模块的贡献。

#### 5.3 Multi-Source Contribution Analysis

分析不同输入组合的影响。

#### 5.4 Traceability Analysis

展示关键结论与证据映射结果。

#### 5.5 Dynamic State Update Analysis

建议定位为：

- `case study`
- `state continuity analysis`

证明 `CST_t` 是可递推更新的，而不是孤立快照。

### 6. Case Studies

建议选 3 个强案例：

- 稳定施工案例；
- 地质关注案例；
- 地质-施工耦合案例。

每个案例建议展示：

- 原始输入；
- Twin 状态摘要；
- 生成报告片段；
- 追溯表。

### 7. Discussion

讨论：

- Twin 相比直接 LLM 的意义；
- 为什么可追溯性重要；
- 当前方法的边界；
- 未来如何进一步提升。

这章适合写：

- 解析准确率仍需更强验证；
- 状态更新算子还可进一步形式化；
- 专家评分和大规模案例还可扩展。

### 8. Conclusion

总结全文：

- 提出了什么；
- 为什么需要 Twin；
- 实验说明了什么；
- 未来工作是什么。

## 5. 图表规划建议

### 图

建议准备以下图：

1. 总体方法框架图
2. Construction State Twin 分层图
3. 时间-里程对齐图
4. 主实验结果对比图
5. 消融实验图

### 表

建议准备以下表：

1. 数据集描述表
2. 指标定义表
3. 主实验结果表
4. 追溯性案例表

结果表默认建议采用：

- `mean ± std`

如 case 数量允许，可在补充实验中加入简单显著性检验。

## 6. 补充材料建议

如果后续投稿允许 supplementary material，可放：

- case list
- prompt 模板
- 追溯表样例
- 额外案例图
- 详细评分表

## 7. 当前写作顺序建议

建议不要先写全文，而是按下面顺序推进：

1. 先固定题目与方法主张；
2. 先写第 3 章 Method；
3. 再做实验并写第 4-6 章；
4. 最后补 Introduction、Related Work、Discussion、Conclusion。

## 8. 一句话总结

这篇论文最核心的写法不是“用了 LLM 生成 TBM 报告”，而是：

**提出了一个以 Construction State Twin 为中间状态层、以 state-aware prompt 为约束机制、以可追溯自动报告为目标的 TBM 施工报告生成框架。**
