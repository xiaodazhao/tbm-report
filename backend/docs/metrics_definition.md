# 指标定义

本文档说明当前后端主流程中主要指标的定义、输入、计算位置、输出位置和语义边界。

## 1. `GRS_geo_base`

- 定义：cell 级地质证据关注度基础分。
- 输入字段：`geo_states_df` 中的围岩等级、hazard、置信度、证据支持等地质融合字段。
- 计算位置：`geology_v2/fusion_engine.py::fuse_geo_states`。
- 输出位置：`ConstructionStateCell.GRS_geo_base`。
- 语义：表示该 cell 的地质证据关注程度。
- 不应误解为：灾害概率、事故概率、现场已经揭露的事实。

## 2. `RAI`

- 定义：Response Anomaly Index，施工响应异常度。
- 输入字段：PLC 推进速度、推力、刀盘扭矩、停机时长、异常响应等。
- 计算位置：`plc/cell_response.py::project_plc_response_to_cells`。
- 输出位置：`cell_response_df.RAI`、`ConstructionStateCell.RAI`。
- 语义：表示该 cell 内当日 PLC 施工响应的异常程度。
- 不应误解为：地质风险本身、灾害概率。

## 3. `GRCI`

- 定义：Geology Response Coupling Index，地质-施工响应耦合关注度。
- 输入字段：`GRS_geo_base`、`RAI`、`has_plc_response`。
- 计算位置：`coupling/grs_rai_grci.py::compute_cell_grci`。
- 计算公式：

```text
GRCI = 0.55 * GRS_geo_base + 0.35 * RAI + 0.10 * GRS_geo_base * RAI
```

- 输出位置：`ConstructionStateCell.GRCI`。
- 语义：用于已掘区段复核，表示地质证据关注与施工响应异常的耦合关注程度。
- 不应误解为：灾害概率、前方风险、TSP/HSP 结论真实性。

重要规则：

- 没有 RAI 不计算正式 GRCI。
- 没有 PLC response evidence 不计算正式 GRCI。
- forward cell 不使用 GRCI。

## 4. `GRCI_available`

- 定义：正式 GRCI 是否可用。
- 输入字段：`GRS_geo_base` 是否存在、`RAI` 是否存在、`has_plc_response` 是否为真。
- 计算位置：`coupling/grs_rai_grci.py::build_construction_state_cells`。
- 输出位置：`ConstructionStateCell.GRCI_available`。
- 语义：为 `True` 时，`GRCI` 才可解释为正式耦合关注指标。
- 不应误解为：报告质量分或工程安全等级。

## 5. `quality_score`

- 定义：报告质量检查分。
- 输入字段：报告文本、Evidence Pack、Twin State。
- 计算位置：`llm/report_quality_checker.py::check_report_quality`。
- 输出位置：`quality_summary.quality_score`。
- 语义：衡量报告是否符合结构、禁用表述、grounding 等规则。
- 不应误解为：施工安全评分、地质风险评分。

## 6. `grounding_rate`

- 定义：有结构化证据支撑的 claim 数量 / 被检查 claim 数量。
- 输入字段：报告 claim、Evidence Pack、source trace。
- 计算位置：`llm/report_quality_checker.py::check_report_quality`，内部调用 grounding checker。
- 输出位置：`quality_summary.grounding_rate`。
- 语义：报告文本被证据支撑的比例。
- 不应误解为：报告绝对正确率。

## 7. `unsupported_claim_count`

- 定义：未找到结构化证据支撑的 claim 数量。
- 输入字段：报告 claim、Evidence Pack。
- 计算位置：`llm/report_quality_checker.py::check_report_quality`。
- 输出位置：`quality_summary.unsupported_claim_count`。
- 语义：报告中可能需要人工复核或删改的未支撑表述数量。

## 8. `trace_coverage`

- 定义：trace 中可追溯 claim 的覆盖率。
- 输入字段：报告 claim、Evidence Pack、source trace。
- 计算位置：`llm/report_trace_builder.py::build_report_trace`。
- 输出位置：`trace_summary.trace_coverage`。
- 语义：报告 claim 与结构化证据追溯关系的覆盖程度。
- 不应误解为：工程准确率。

## 9. `high_grci_cell_count`

- 定义：`high_grci_cells` 中 cell 数量。
- 输入字段：`ConstructionStateCell` 列表。
- 计算位置：`coupling/grs_rai_grci.py::high_grci_cells`。
- 输出位置：`DailyReportResult.high_grci_cells`、smoke summary、export summary。
- 语义：已掘区段中可解释的高耦合关注 cell 数量。
- 不应误解为：前方风险 cell 数量、灾害数量。

筛选规则：

- `GRCI_available=True`；
- `GRCI is not None`；
- `is_excavated_today=True`；
- `is_forward_cell=False`。

## 10. `forward_cell_count`

- 定义：当前掌子面前方关注 cell 数量。
- 输入字段：`ConstructionStateCell.is_forward_cell`、`forward_profile`。
- 计算位置：`pipeline/daily_report_pipeline.py` 和 `llm/evidence_pack.py`。
- 输出位置：smoke summary、export summary、Evidence Pack。
- 语义：前方地质关注提示涉及的 cell 数量。
- 不应误解为：高 GRCI cell 数量。

## 11. 总体语义边界

- `GRCI` 不是灾害概率。
- `GRCI` 不是前方风险。
- 前方 cell 不使用 GRCI。
- 没有 RAI 不计算正式 GRCI。
- Quality / Trace 是报告文本核验指标，不是工程安全评价指标。
