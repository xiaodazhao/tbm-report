# 论文写作用项目上下文

本文是给 GPT、Claude、DeepSeek 等大语言模型理解本项目并辅助撰写中文期刊论文使用的上下文包。它不是代码说明书，而是方法、数据、边界和论文写作口径的集中说明。

## 1. 项目一句话定义

本文面向 TBM 连续掘进过程中的施工日报自动生成问题，提出一种面向 TBM 施工日报的多源证据约束生成与可追溯校核方法。该方法将 PLC 施工参数、TSP/HSP 超前地质预报和掌子面素描等多源数据组织为可追溯的 ConstructionStateCell，并通过 RAI、GRS、GRCI 启发式关注指标、Prompt Evidence Pack 和 Quality / Trace 约束日报生成与核验。

## 2. 研究对象与数据来源

研究对象是 TBM 隧道施工日报自动生成。系统使用两类数据：

1. PLC 日运行数据：包括时间、导向盾首里程、推进速度、推力、刀盘扭矩、刀盘转速、停机/掘进状态、气体监测字段等；
2. 多源地质证据：包括 TSP 超前地质预报、HSP/sonic 超前地质资料、掌子面素描等。

当前工程数据基础：

```text
连续 PLC 日期数 = 91 天
PLC usable_dates = 91
evidence 总量 = 484 条
TSP = 139 条
HSP/sonic = 176 条
sketch = 169 条
A 类日期 = 83 天
B 类日期 = 8 天
batch pipeline = 91 / 91 passed
batch mock LLM = 91 / 91 passed
average_daily_advance_m = 13.8571
```

## 3. 本文不是做什么

本文不是简单调用大语言模型直接写施工日报；不是让 LLM 直接读取全部原始 PLC CSV 或完整 evidence_db 并自行判断地质风险；不是让 LLM 计算 RAI、GRS 或 GRCI；不是把 GRCI 解释为灾害概率；不是将前方超前预报写成现场已揭露事实；P3 地质文本结构化模块也不是替代正式 evidence_db 的解析器。

## 4. 核心方法链路

```text
PLC / 地质证据
-> 时空证据门控
-> ConstructionStateCell
-> RAI / GRS / GRCI 启发式关注指标
-> Prompt Evidence Pack
-> LLM Report Planner
-> Evidence-constrained Generator
-> Quality / Trace
-> Trace-guided Revision
-> TBM 施工日报
```

### 4.1 时空证据门控

系统首先根据报告日期进行 evidence online 过滤，避免使用报告日之后的信息；再根据当日 PLC 推进范围、当前掌子面位置、前方关注窗口和局部背景窗口筛选空间相关证据。这样可以避免旧远距离 TSP 或未来掌子面素描进入当前日报。

### 4.2 ConstructionStateCell

ConstructionStateCell 是 10m 里程单元下的施工状态表达对象。它把 PLC response、地质证据、source_trace、RAI、GRS、GRCI、cell_role 和报告追溯字段集中到同一个 cell 上，是 Evidence Pack、Twin State、Trace 和 debug 输出的核心对象。

### 4.3 RAI / GRS / GRCI

RAI 表示 PLC 施工响应启发式关注度。GRS 表示地质证据启发式关注度。GRCI 表示已掘 cell 的地质-施工响应耦合启发式关注度。GRCI 不是灾害概率，也不是前方风险。只有同时存在 GRS、RAI 和 PLC response 的 daily review cell 才计算正式 GRCI。当前没有灾害发生标签、异常原因标签或现场复核标签，因此不做监督学习式权重校准。

### 4.4 Prompt Evidence Pack

Evidence Pack 是 LLM 的唯一结构化报告输入，包括 operation evidence、gas evidence、geology evidence、excavated review evidence、forward attention evidence、background context evidence、coupling evidence、source trace 和 generation constraints。它的作用是约束 LLM 不做无证据推断。

### 4.5 Report Planner

Report Planner 在生成正文前先规划章节，明确每一节允许使用的证据角色和指标边界。Plan Validation 检查 planner 是否误用 GRCI、是否把 forward_attention 写成已掘复核、是否遗漏必要章节。

### 4.6 Quality / Trace / Revision

Quality / Trace 抽取报告 claim，并与 Evidence Pack 中的 evidence、key cells、source trace、policy constraints 匹配。错误 taxonomy 包括 GRCI 概率误用、前方提示事实误用、数值无支撑、E14 对齐范围误写为实际推进等。Revision 根据这些反馈修订报告。

### 4.7 P3 sidecar geology extraction

P3 从 raw_text/source_text/original_text_span 旁路抽取 candidate evidence。输出 `candidate_evidence_db.csv`，但必须标记 `candidate_only=true`、`requires_manual_review=true`、`not_used_by_main_pipeline=true`。P3 不进入正式日报主链路。

## 5. 关键概念

- `daily_plc_range`：PLC 实测推进范围和推进量。
- `daily_excavated_scope`：10m cell 对齐后的已掘复核范围，不是实际推进范围。
- `daily_review`：已掘区段复核 cell，可使用 GRCI。
- `forward_attention`：当前掌子面前方关注提示，只使用 GRS/source_trace，不使用 GRCI。
- `forward_distance_band`：当前采用 0-10m、10-20m、20-30m 三个前方距离分层。
- `selection_score` / `selection_rank` / `selection_reason`：Evidence Pack 中 key cells 的选择分、排序和选择原因。
- `local_background`：局部背景 cell，只作上下文。
- `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE`：检查是否把 cell 对齐范围误写成实际推进范围。

## 6. 方法创新点

1. 面向 TBM 日报生成构建时空证据门控机制；
2. 提出 ConstructionStateCell 作为里程空间下的施工状态表达单元；
3. 将已掘复核、前方关注和局部背景分层为不同证据角色；
4. 设计 RAI / GRS / GRCI 启发式关注指标表达施工响应、地质证据和耦合复核；
5. 构建 Prompt Evidence Pack 约束 LLM 生成过程；
6. 引入 Report Planner，实现章节级证据角色和指标使用控制；
7. 构建 Quality / Trace / Error Taxonomy，实现生成结果可追溯核验；
8. 设计 P3 旁路式地质文本结构化模块，为候选证据扩展提供支持。

## 7. 当前实验基础

已完成：

```text
单日 pipeline 可运行
三日期 no-LLM smoke 通过
2023-12-30 construction_state_cells = 14
91 天 PLC audit 可用
91 天 batch pipeline 成功
91 天 batch mock LLM 成功
P3 mock extraction 成功
当前 pytest 持续通过
```

## 8. 后续论文实验

当前方法主线已经冻结，后续论文实验建议围绕稳定性、敏感性、生成模式和案例复盘展开：

1. 91 天批量运行稳定性；
2. 5m/10m cell 尺度敏感性；
3. GRCI 权重敏感性；
4. generation mode 对比；
5. 典型日期案例复盘；
6. 可选人工评价。

这些实验评价的是方法稳定性、证据约束能力、报告 grounding 和可追溯性，不是灾害预测准确率。

## 9. 论文建议结构

```text
摘要
1 引言
2 相关研究
3 方法
  3.1 总体框架
  3.2 数据输入与日报生成任务定义
  3.3 时空证据门控
  3.4 ConstructionStateCell 施工状态单元
  3.5 RAI、GRS 与 GRCI 指标
  3.6 Prompt Evidence Pack 构建
  3.7 LLM Report Planner
  3.8 Evidence-constrained Report Generation
  3.9 Trace-guided Revision
  3.10 Quality / Trace / Error Taxonomy
  3.11 旁路式地质文本结构化候选模块
4 实验与结果
5 讨论
6 结论
```

## 10. 写作口径

中文论文中的主角是“多源证据约束生成、ConstructionStateCell 施工状态单元和可追溯校核”。LLM 是 Evidence Pack 约束下的工程语义生成模块，不是唯一贡献，也不是地质风险判断器。91 天数据是单工程连续过程验证，不要夸大成多工程泛化。GRCI 不能写成灾害概率，forward_attention 不能写成已发生灾害，daily_excavated_scope 不能写成实际推进。

P3 只能写成旁路候选模块，不应写成正式主链路的一部分。

## 11. 可直接给 GPT 的摘要提示

如果你是大语言模型，请基于以上上下文帮助我撰写中文期刊论文。注意：本文不是直接用 LLM 写日报，而是提出时空证据门控、施工状态孪生与证据约束生成框架。请始终区分 PLC 实测推进范围与 cell 对齐复核范围，区分已掘复核与前方关注，避免将 GRCI 写成灾害概率。P3 地质文本结构化模块仅为旁路候选证据模块，不进入正式日报主链路。
