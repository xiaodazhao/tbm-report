# 后端范围与限制

当前后端是一个面向 TBM 日报生成、证据约束报告和可追溯核验的工程研究原型。

它的目标是：

- 稳定运行单主线 pipeline；
- 统一 `ConstructionStateCell` 字段契约；
- 导出可复现的中间结果；
- 用 Evidence Pack 约束报告生成；
- 用 Quality / Trace 核验报告文本；
- 为后续论文方法说明和实验复现提供工程基础。

## 当前系统不做什么

当前后端不做：

- 不重新解释 TSP/HSP 原始探测信号；
- 不构建 TBM 物理仿真数字孪生；
- 不预测地质灾害发生概率；
- 不把 `GRCI` 作为概率；
- 不把 LLM 作为核心数值推理器；
- 不在主流程中运行 Agent；
- 不自动完成论文实验或专家评价；
- 不恢复旧接口和旧多流程链路。

## 当前核心假设

- `RAI` 是基于 PLC 施工响应特征得到的工程近似异常指标。
- `GRS_geo_base` 来自标准化并融合后的地质证据。
- `GRCI` 是已掘 cell 的地质-施工响应耦合关注指标，只在同时存在地质证据和 PLC response evidence 时可解释。
- 前方关注使用 `forward_profile`、`GRS_geo_base`、主要 hazards 和 `source_trace`，不使用 `GRCI`。
- smoke test 验证的是工程稳定性和字段契约，不等同于科学有效性验证。

## 推荐使用方式

- 使用 no-LLM smoke test 验证 pipeline 可复现运行。
- 在论文实验前导出完整中间结果。
- 使用 Evidence Pack 和 Trace 人工复核报告中的 claim。
- 将 `_archive/` 仅作为历史参考，不要从中 import 代码进入当前主流程。
