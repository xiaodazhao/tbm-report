# 后端方法定义

本文档描述当前单主线后端方法，范围限定为：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

`_archive/` 中保存的是旧版本代码，仅作历史参考，不参与当前方法定义、报告生成、质量核验或论文实验导出。

## 1. 系统任务定义

当前后端从 TBM 日运行 PLC 数据和多源地质证据出发，完成：

- PLC 施工状态与响应分析；
- 多源地质证据标准化、online 过滤、cell 投影和融合；
- cell 级 `ConstructionStateCell` 构建；
- `GRS / RAI / GRCI` 计算；
- 前方地质关注 profile 构建；
- Prompt Evidence Pack 构建；
- no-LLM 模板报告或 LLM fallback 报告生成；
- 报告质量检查和 claim-to-evidence trace；
- API 输出和中间结果导出。

## 2. PLC 的作用

PLC 数据提供当日实际施工响应证据，包括：

- 工况识别；
- 推进速度、推力、刀盘扭矩、刀盘转速；
- 停机和异常工况；
- 气体监测；
- cell 级施工响应指标；
- `RAI`。

PLC 不单独推断地质结论。PLC 的作用是描述施工状态，并在已掘 cell 中为 `GRCI` 提供施工响应证据。

## 3. TSP / HSP / 掌子面素描的作用

TSP、HSP、掌子面素描和其他地质资料在当前系统中都被视为“证据”，而不是绝对事实。

它们会经过：

- 文本和字段标准化；
- 里程化；
- online 可用性过滤；
- HSP 异常点去重；
- 投影到 10m chainage cell；
- cell 级地质融合。

报告中必须把这些内容写成“证据提示”“关注”“复核依据”，不能写成现场已经揭露或必然发生的事实。

## 4. 已掘区段复核与前方提示

已掘区段复核：

- 使用当日已掘范围内的 cell；
- 需要地质证据和 PLC response evidence；
- 可计算 `GRCI`；
- 用于复核地质证据与施工响应是否耦合。

前方关注提示：

- 使用当前掌子面前方可用地质证据；
- 使用 `GRS_geo_base`、主要 hazards、`source_trace` 和 `forward_profile`；
- 不使用 `GRCI`；
- 不进入 `high_grci_cells`；
- 只能表述为“前方关注提示”，不能写成已发生事实。

## 5. ConstructionStateCell 的设计原因

`ConstructionStateCell` 是 PLC 响应、地质融合、耦合计算、Evidence Pack、Twin State、API debug、Quality 和 Trace 之间的统一对象。

它的作用是：

- 避免报告层从零散 dict 中到处取字段；
- 固定 cell 级字段契约；
- 明确每个 cell 是否有 PLC response、是否有地质证据、是否可计算 GRCI；
- 支撑 Evidence Pack 和 Trace 的一致性。

## 6. GRS / RAI / GRCI 语义

- `GRS_geo_base`：cell 级地质证据关注度。
- `RAI`：cell 级施工响应异常度。
- `GRCI`：已掘 cell 中地质证据关注度与施工响应异常度的耦合关注度。

重要限制：

- `GRCI` 不是灾害概率；
- `GRCI` 不是前方风险；
- `GRCI` 不代表 TSP/HSP 结论一定真实；
- 只有同时存在 `GRS_geo_base`、`RAI` 和 PLC response evidence 时，才计算正式 GRCI；
- 没有 RAI 的 cell 不计算正式 GRCI；
- forward cell 不进入 `high_grci_cells`。

## 7. Evidence Pack 的作用

Evidence Pack 是报告生成的结构化证据边界。报告只能围绕 Evidence Pack 中的证据写结论。

Evidence Pack 包含：

- 施工运行证据；
- 聚类施工状态证据；
- 气体监测证据；
- 地质证据；
- 前方关注证据；
- 已掘区段耦合复核证据；
- source trace；
- generation constraints。

## 8. Quality / Trace 的作用

Quality 检查报告是否满足：

- 章节完整；
- 禁用表述未出现；
- 没有把 GRCI 写成概率；
- 没有把前方提示写成已发生事实；
- claim 尽量能被 Evidence Pack 支撑。

Trace 将报告中的 claim 连接到 Evidence Pack 和 source trace，用于人工复核和后续论文实验导出。

## 9. 当前方法不做什么

当前后端不做：

- TSP/HSP 原始探测信号重新解释；
- TBM 物理仿真数字孪生；
- 地质灾害概率预测；
- 专家评价；
- 前端展示；
- Agent 问答；
- 真实外部 LLM 数值推理。

LLM 在当前系统中不是核心数值推理器；no-LLM 模板报告也必须受 Evidence Pack 约束。
