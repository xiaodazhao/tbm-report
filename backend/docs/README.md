# TBM 日报后端文档索引

本目录记录当前单主线后端的字段契约、方法定义、指标解释、边界说明、案例说明和归档计划。当前主流程仍然是：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

## 推荐阅读顺序

1. [当前后端系统说明书](current_backend_system_manual.md)
   - 面向陌生读者的系统级说明，解释当前版本到底怎么跑。

2. [方法定义文档](method_definition.md)
   - 说明当前系统任务、PLC 和地质证据的作用、已掘复核与前方提示的区别。

3. [字段契约文档](backend_field_contract.md)
   - 说明 `DailyReportResult`、`ConstructionStateCell`、Evidence Pack、Quality / Trace 和 API 输出字段。

4. [指标定义文档](metrics_definition.md)
   - 解释 `GRS_geo_base`、`RAI`、`GRCI`、`quality_score`、`grounding_rate`、`trace_coverage` 等指标。

5. [方法与计算逻辑白皮书](method_calculation_whitepaper.md)
   - 更细的计算链路、字段来源、公式复盘和导出说明。

6. [Quality / Trace 方法边界句分类说明](quality_trace_boundary_update.md)
   - 说明 `method_boundary / policy_support / E12_METHOD_BOUNDARY_STATEMENT` 的最新分类规则。
   - 记录 2023-12-30 中“如无当日可用掌子面素描，不把前方证据写成已揭露事实。”这类句子的修正结果。

7. [范围与限制说明](scope_and_limitations.md)
   - 说明当前系统不做什么，例如不做灾害概率预测、不重新解释 TSP/HSP 原始信号、不接入 Agent 主流程。

8. [2023-12-30 案例说明](case_2023-12-30.md)
   - 用真实日期说明数据读取、cell 构建、Evidence Pack、报告、Quality / Trace 的完整流转。

9. [归档计划](archive_plan.md)
   - 说明哪些历史模块已归档，哪些目录参与当前主流程。

## 当前 Quality / Trace 关键语义

方法边界句不是普通技术 claim，也不是 unsupported 技术结论。当前会归为：

```text
claim_type = method_boundary
support_type = recommendation_policy
trace_support_type = policy_support
error_type = E12_METHOD_BOUNDARY_STATEMENT
```

真正无证据的技术判断不会因此被放宽。GRCI 概率误用仍归为 `E3_GRCI_AS_PROBABILITY`，把 `stop_ratio` 直接写成异常原因仍归为 `E13_STOP_REASON_OVERINTERPRETATION`。
