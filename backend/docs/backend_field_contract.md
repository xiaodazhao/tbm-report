# 后端字段契约

本文档描述当前单主线后端的稳定字段契约。适用范围是：

```text
routes.report
-> pipeline.daily_report_pipeline.run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

`_archive/` 中的旧代码不参与当前字段契约，不应作为 API、Evidence Pack 或 Trace 的字段来源。

## 1. DailyReportResult 字段

定义位置：`schemas/pipeline.py`

| 字段 | 含义 |
|---|---|
| `date` | 报告日期，格式为 `YYYY-MM-DD`。 |
| `report_text` | 最终报告文本；no-LLM 模式下由模板报告生成。 |
| `operation_summary` | PLC 工况统计和施工运行概况。 |
| `cluster_summary` | PLC 聚类施工状态与效率统计。 |
| `gas_summary` | 气体监测统计和字段解释提示。 |
| `normalized_evidence_summary` | online 过滤后的标准化地质证据摘要。 |
| `construction_state_cells` | `ConstructionStateCell` 列表，是当前系统核心 cell 级状态。 |
| `forward_profile` | 当前掌子面前方关注 profile 和 forward attention cells。 |
| `prompt_evidence_pack` | 注入 prompt、报告、质量检查和 trace 的结构化证据包。 |
| `prompt_text` | 由 Evidence Pack 构建的 prompt。 |
| `quality` | 完整报告质量检查结果。 |
| `quality_summary` | 报告质量核心指标摘要。 |
| `trace` | 完整 claim-to-evidence trace。 |
| `trace_summary` | trace 核心指标摘要。 |
| `high_grci_cells` | 已掘区段中 `GRCI_available=True` 的高关注 cell。 |
| `twin_state` | 由同一批 cell 和 evidence 构建的施工状态孪生摘要。 |
| `warnings` | pipeline warning 列表。 |

## 2. ConstructionStateCell 字段

定义位置：`schemas/pipeline.py`

构建位置：`coupling/grs_rai_grci.py::build_construction_state_cells`

| 字段 | 来源 | 含义 |
|---|---|---|
| `cell_id` | cell / geology / PLC | 稳定 10m cell 编号，例如 `cell_1014600_1014610`。 |
| `cell_start`、`cell_end`、`cell_center` | cell | cell 空间范围和中心里程。 |
| `operation_state` | PLC response | 该 cell 内主导工况。 |
| `plc_metrics` | PLC response | PLC 聚合指标、持续时间、样本数等。 |
| `speed_mean` | PLC response | cell 内平均推进速度。 |
| `thrust_mean` | PLC response | cell 内平均推力。 |
| `torque_mean` | PLC response | cell 内平均刀盘扭矩。 |
| `stop_duration_min` | PLC response | cell 内停机时长，单位分钟。 |
| `abnormal_score` | PLC response | 施工响应异常分。 |
| `RAI` | PLC response | Response Anomaly Index，目前与 `abnormal_score` 同源。 |
| `geology_evidence_ids` | geology projection | 投影到该 cell 的地质证据 id。 |
| `supporting_evidence_ids` | geology projection | 报告和 trace 使用的正式支撑证据 id 列表。 |
| `source_trace` | normalized evidence | 证据追溯记录，包括证据 id、来源、里程和文本摘录。 |
| `fused_grade` | geology fusion | 融合后的围岩等级。 |
| `main_hazards` | geology fusion | 主要地质关注类型。 |
| `hazard_scores` | geology fusion | 地质关注类型分数字典。 |
| `confidence_score` | geology fusion | 地质融合置信度。 |
| `uncertainty_level` | geology fusion | 不确定性等级。 |
| `conflict_level` | geology fusion | 多源证据冲突等级。 |
| `GRS_geo_base` | geology fusion | 地质证据关注度基础分。 |
| `GRCI` | coupling | cell 级地质-施工响应耦合关注度，可为空。 |
| `GRCI_available` | coupling | 只有同时存在 GRS、RAI 和 PLC response 时才为 `True`。 |
| `GRCI_source` | coupling | GRCI 公式来源；不可用时为 `unavailable`。 |
| `GRCI_unavailable_reason` | coupling | GRCI 不可用原因，例如 `missing_plc_response`。 |
| `coupling_level` | coupling | `high`、`medium`、`low`、`none` 或 `unavailable`。 |
| `coupling_explanation` | coupling | 面向报告的耦合解释。 |
| `has_plc_response` | PLC response | 该 cell 是否有当日 PLC response evidence。 |
| `has_geology_evidence` | geology fusion | 该 cell 是否有地质证据或融合结果。 |
| `is_excavated_today` | pipeline spatial logic | 该 cell 是否与当日已掘范围重叠。 |
| `is_current_face_cell` | pipeline spatial logic | 该 cell 是否包含当前掌子面里程。 |
| `is_forward_cell` | pipeline spatial logic | 该 cell 是否属于严格前方 cell。 |
| `used_in_evidence_pack` | Evidence Pack | 是否被 Evidence Pack 选为关键报告证据。 |
| `trace_refs` | Trace | 可供 trace 使用的引用标识。 |

## 3. Evidence Pack 字段

构建位置：`llm/evidence_pack.py::build_prompt_evidence_pack`

主要字段：

| 字段 | 含义 |
|---|---|
| `report_scope` | 报告日期、当前里程、当日里程范围等范围信息。 |
| `operation_evidence` | PLC 工况和施工运行证据。 |
| `cluster_evidence` | 聚类施工状态与效率证据。 |
| `gas_evidence` | 气体监测证据。 |
| `geology_evidence` | 地质 cell、证据摘要和地质关注信息。 |
| `forward_evidence` | 前方关注提示证据。 |
| `coupling_evidence` | 已掘区段 GRCI 复核证据。 |
| `quality_evidence` | 数据质量、warning、可用性信息。 |
| `source_trace` | 证据追溯信息。 |
| `generation_constraints` | 报告生成约束。 |

### key_cells / selected_cells 契约

- `geology_evidence.key_cells` 是正式字段。
- `geology_evidence.selected_cells` 是短期兼容字段。
- 当前两者内容一致。
- grounding checker 读取时优先使用 `key_cells`，缺失时 fallback 到 `selected_cells`。
- 后续如果所有调用方都切换到 `key_cells`，可以删除 `selected_cells`。

## 4. Quality / Trace 字段

| 字段 | 含义 |
|---|---|
| `quality_score` | 报告质量分，不是工程安全分。 |
| `grounding_rate` | 被结构化证据支撑的 claim 比例。 |
| `claim_count` | 抽取出的可检查 claim 数量。 |
| `grounded_claim_count` | 有证据支撑的 claim 数量。 |
| `unsupported_claim_count` | 未找到结构化证据支撑的 claim 数量。 |
| `trace_coverage` | trace 中可追溯 claim 的覆盖率。 |
| `report_trace` | claim 与 Evidence Pack / source trace 的匹配结果。 |

## 5. `/api/tbm/report` 返回字段

该接口面向前端或普通调用方，返回精简结果：

- `date`
- `report_text`
- `quality_summary`
- `trace_summary`
- `forward_profile`
- `high_grci_cells`
- `warnings`

## 6. `/api/tbm/report/debug` 返回字段

该接口面向调试、复核和论文实验导出，返回完整中间结果：

- `operation_summary`
- `cluster_summary`
- `gas_summary`
- `normalized_evidence_summary`
- `construction_state_cells`
- `prompt_evidence_pack`
- `prompt_text`
- `report_text`
- `quality`
- `trace`
- `warnings`

## 7. 关键语义约束

- `GRCI` 不是灾害概率。
- `GRCI` 不是前方风险。
- 没有 RAI 或没有 PLC response evidence 的 cell 不计算正式 GRCI。
- forward cell 使用 `GRS_geo_base`、`forward_profile` 和 `source_trace`，不进入 `high_grci_cells`。
- TSP/HSP/掌子面素描是证据来源，不应写成绝对事实。
