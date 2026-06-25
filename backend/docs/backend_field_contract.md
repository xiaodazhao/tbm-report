# 后端字段契约

本文定义当前单主线后端的稳定字段语义。适用范围：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

P3 sidecar 输出、批量审计输出和正式日报输出各有边界；`_archive/` 不参与字段契约。

## 1. 范围字段

| 字段 | 含义 | 注意 |
|---|---|---|
| `daily_plc_range` | PLC 实测当日推进范围，包含起点、终点和 `daily_advance_m` | 报告中实际推进量只能来自这里 |
| `daily_chainage_raw` | PLC 原始里程序列统计的别名语义 | 不应与 cell 对齐范围混用 |
| `daily_chainage_min` / `daily_chainage_max` | PLC 当日实测最小/最大里程 | 用于实际施工范围 |
| `daily_advance_m` | PLC 实测日推进量 | 不允许由 cell 对齐范围自行计算 |
| `daily_excavated_scope` | 10m cell 对齐后的已掘复核范围 | 不是实际推进范围 |
| `forward_scope` | 当前掌子面前方关注窗口 | 只用于前方关注提示 |
| `local_background_scope` | 已掘范围后方局部背景窗口 | 只作背景上下文 |
| `cell_size_m` | 当前运行使用的 cell 尺度，默认 10m | 10m 是最大推荐日报复核尺度；5m/10m 用于尺度敏感性分析 |

典型表达：

```text
PLC 实测推进范围为 1014601.0 至 1014616.0，日推进约 15.0 m；
系统按 10m cell 将已掘复核范围对齐为 1014600.0 至 1014620.0。
```

## 2. ConstructionStateCell

`ConstructionStateCell` 是当前日报系统的核心 cell 级对象，由 `coupling/grs_rai_grci.py::build_construction_state_cells` 构建。

| 字段 | 含义 |
|---|---|
| `cell_id` | 10m cell 标识 |
| `cell_start` / `cell_end` / `cell_center` | cell 空间范围 |
| `cell_role` | cell 在日报中的语义角色 |
| `daily_review` / `is_excavated_today` | 已掘复核 cell |
| `forward_attention` / `is_forward_cell` | 当前掌子面前方关注 cell |
| `local_background` | 局部背景 cell |
| `has_plc_response` | 该 cell 是否有当日 PLC response |
| `has_geology_evidence` | 该 cell 是否有空间相关地质证据 |
| `RAI` | PLC 施工响应异常关注指标 |
| `GRS_geo_base` | 地质证据关注度基础分 |
| `GRCI` | 地质-施工响应耦合关注度 |
| `GRCI_available` | 只有 GRS、RAI 和 PLC response 同时存在且 cell 属于已掘复核时为 true |
| `GRCI_unavailable_reason` | GRCI 不可用原因 |
| `main_hazards` | 主要地质关注类型 |
| `source_trace` | 支撑该 cell 的证据追溯信息 |
| `coupling_explanation` | 面向报告的耦合解释 |
| `evidence_overlap_length` | 代表性证据-cell 重叠长度 |
| `evidence_overlap_ratio` | 代表性证据-cell 重叠比例 |
| `max_overlap_ratio` / `mean_overlap_ratio` | 当前 cell 证据重叠比例摘要 |
| `total_overlap_length` | 当前 cell 证据重叠长度合计 |
| `evidence_count` / `evidence_ids` | 当前 cell 投影证据数量与 ID |
| `source_type_distribution` | 当前 cell 中证据来源类型分布 |
| `evidence_confidence` | 证据置信度摘要；来源缺失时为 null |
| `evidence_confidence_method` | 证据置信度来源说明 |
| `trace_completeness` | 追溯信息完整度 |
| `trace_completeness_method` | 追溯完整度计算方法 |
| `manual_review_status` | 人工复核状态 |
| `source_reliability` | 来源可靠性摘要；来源缺失时为 null |
| `source_reliability_method` | 来源可靠性来源说明 |
| `distance_to_face_m` | cell center 到当前掌子面的距离 |
| `forward_distance_band` | 前方距离分带 |
| `forward_distance_weight` | 前方 cell 选择分中的距离权重 |

上述 overlap、trace completeness、source reliability、selection 相关字段主要服务解释性导出、Evidence Pack selection 和论文实验分析；它们不改变 RAI / GRS / GRCI 的默认公式和语义边界。

forward 距离分层当前采用：

| 分层 | 语义 |
|---|---|
| `near_0_10m` | 当前掌子面前方 0-10m |
| `mid_10_20m` | 当前掌子面前方 10-20m |
| `far_20_30m` | 当前掌子面前方 20-30m |
| `beyond_30m` | 超出 30m 关注窗口 |
| `not_forward` | 非前方关注 cell |

## 3. RAI / GRS / GRCI 启发式关注指标

| 指标 | 语义 | 不应误解为 |
|---|---|---|
| `RAI` | PLC 施工响应启发式关注度 | 事故原因或停机原因 |
| `GRS_geo_base` | 地质证据启发式关注度 | 地质灾害概率 |
| `GRCI` | 已掘 cell 的地质-施工响应耦合启发式关注度 | 灾害概率、前方风险 |

GRCI 只在 daily review cell 中计算。forward attention 和 local background cell 必须视为 `GRCI_available=false`。

当前没有灾害发生标签、异常原因标签或现场复核标签，因此这些指标不进行监督学习式权重校准。

## 4. Evidence Pack

构建位置：`llm/evidence_pack.py::build_prompt_evidence_pack`。

| 字段 | 含义 |
|---|---|
| `report_scope` | 日期、当前里程、PLC 实测范围、cell 对齐范围等 |
| `operation_evidence` | PLC 工况统计 |
| `cluster_evidence` | 聚类施工状态和效率信息 |
| `gas_evidence` | 气体监测证据 |
| `geology_evidence` | 地质 key cells 和证据摘要 |
| `excavated_review_evidence` | 已掘区段地质-施工响应复核证据 |
| `forward_attention_evidence` | 当前掌子面前方关注提示证据 |
| `background_context_evidence` | 局部背景证据 |
| `coupling_evidence` | GRCI 可用 cell 与耦合复核证据 |
| `source_trace` | 原始 evidence 支撑链 |
| `generation_constraints` | 报告生成边界和禁用表述 |

`geology_evidence.key_cells` 是正式字段；`geology_evidence.selected_cells` 是短期兼容字段，当前与 `key_cells` 内容一致。

Evidence Pack 中 cell 可包含以下选择字段：

| 字段 | 含义 |
|---|---|
| `selection_score` | 当前角色下的选择分 |
| `selection_rank` | 当前角色下的排序 |
| `selection_reason` | 被选入 Evidence Pack 的原因 |
| `selection_method` | 选择分方法版本 |
| `selected_by_score` | 是否按选择分进入 Evidence Pack |

`daily_review` 的选择分可以使用 GRCI；`forward_attention` 的选择分不得使用 GRCI。

selection 字段只决定 Evidence Pack 中关键 cell 的排序和说明，不改变原始 cell 的 RAI / GRS / GRCI 数值。

## 5. Quality / Trace 字段

| 字段 | 含义 |
|---|---|
| `quality_score` | 报告质量检查分数 |
| `grounding_rate` | 有证据支撑 claim 的比例 |
| `unsupported_claim_count` | 未被结构化证据支撑的 claim 数量 |
| `trace_coverage` | claim trace 覆盖率 |
| `error_type_counts` | 各类错误数量 |
| `support_type_distribution` | 证据支撑类型分布 |
| `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE` | 将 10m 对齐复核范围误写为实际推进范围或实际推进量 |

## 5.1 method_metrics 新增字段

| 字段 | 含义 |
|---|---|
| `cell_size_m` | 当前运行使用的 cell 尺寸 |
| `mean_trace_completeness` | cell 追溯完整度均值 |
| `min_trace_completeness` | cell 追溯完整度最小值 |
| `low_trace_completeness_count` | 追溯完整度偏低的 cell 数量 |
| `evidence_without_trace_count` | 有证据但追溯信息缺失的 cell 数量 |

## 6. LLM Planner 字段

| 字段 | 含义 |
|---|---|
| `llm_report_plan` | LLM 或 mock planner 生成的章节计划 |
| `plan_validation` | plan 是否遵守章节、证据角色和指标使用约束 |
| `plan_fallback_used` | plan 不合法或生成失败时是否使用 fallback plan |

## 7. P3 candidate evidence 字段

P3 输出 `candidate_evidence_db.csv`，只作为候选证据：

| 字段 | 含义 |
|---|---|
| `candidate_id` | 候选证据 ID |
| `source_id` | 原始文本或文件 ID |
| `source_type` | TSP / HSP / sketch / unknown |
| `start_chainage` / `end_chainage` | 从原文抽取的里程范围 |
| `hazard_tags` | 标准化地质标签 |
| `original_text_span` | 支撑候选结果的原文片段 |
| `source_trace` | 文件名、路径、页码或行号等 |
| `candidate_only` | 必须为 true |
| `requires_manual_review` | 必须为 true |
| `not_used_by_main_pipeline` | 必须为 true |

P3 candidate evidence 不进入正式 `evidence_db`，不进入 GRS/GRCI，不进入 Evidence Pack。

## 8. API 返回字段

`POST /api/tbm/report` 返回：

- `date`
- `report_text`
- `quality_summary`
- `trace_summary`
- `forward_profile`
- `high_grci_cells`
- `warnings`

`POST /api/tbm/report/debug` 返回完整中间结果，包括：

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
# DailyConstructionTwin 字段补充

当前后端在 `ConstructionStateCell` 之上新增 `DailyConstructionTwin`，用于统一组织施工状态、证据治理、查询、Evidence Pack 和 Trace 导出。它不改变 RAI / GRS / GRCI 的计算公式。

## DailyReportResult 新增字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `daily_construction_twin` | `dict` | `DailyConstructionTwin` 的完整 JSON 结构，主要用于 debug 和导出 |
| `twin_summary` | `dict` | twin 的紧凑摘要，包括 cell 数量、分层数量、operation/response/geology/forward/coupling/quality 摘要 |
| `twin_boundary_summary` | `dict` | 报告文本是否违反 twin 语义边界的检查结果 |

## DailyConstructionTwin

| 字段 | 含义 |
| --- | --- |
| `date` | 日期 |
| `scope` | 当日 PLC 实测范围、cell 对齐复核范围、前方范围和背景范围 |
| `cells` | 全部 `TwinCellView` |
| `daily_review_cells` | 已掘复核 cell，可使用 RAI / GRS / GRCI |
| `forward_attention_cells` | 当前掌子面前方关注 cell，只使用 GRS / source_trace，不使用 GRCI |
| `local_background_cells` | 局部背景 cell，只提供上下文 |
| `high_grci_cells` | 已掘复核范围内的 high/top GRCI cell，不包含 forward cell |
| `summaries` | operation、response、plc、geology、forward、gas、coupling、quality 摘要 |
| `trace_index` | cell、PLC、geology、source evidence、warning 索引 |
| `governance` | 证据角色规则、指标边界、allowed/forbidden claims |
| `debug` | pipeline 调试信息 |
| `warnings` | warning 列表 |

## TwinCellView

| 字段 | 含义 |
| --- | --- |
| `cell_id` | cell 编号 |
| `mileage_start` / `mileage_end` | cell 起止里程 |
| `cell_role` | `daily_review` / `forward_attention` / `local_background` 等角色 |
| `distance_to_face_m` | 距当前掌子面的距离 |
| `position_state` | 里程位置、是否已掘、是否前方、forward distance band |
| `operation_state` | 工况、停机、异常和停机语义边界 |
| `response_state` | RAI、PLC 均值、working-only enhanced PLC proxy |
| `geology_state` | GRS、围岩等级、hazards、supporting evidence、source trace |
| `forward_state` | 前方关注边界。forward cell 的 `GRCI_available=false` |
| `gas_state` | 气体状态入口，当前以日级 gas summary 为主 |
| `coupling_state` | GRCI、coupling level、解释文本和边界说明 |
| `quality_state` | has_plc_response、has_geology_evidence、GRS/GRCI 可用性、warnings |
| `trace_state` | supporting evidence ids、trace refs、source trace、trace completeness |

## Evidence Pack 新增字段

当 Evidence Pack 从 `DailyConstructionTwin` 构建时，新增：

| 字段 | 含义 |
| --- | --- |
| `evidence_pack_source` | 固定为 `daily_construction_twin` |
| `evidence_governance` | 完整证据治理上下文 |
| `source_role_boundaries` | daily_review / forward_attention / local_background 的使用边界 |
| `metric_boundaries` | RAI / GRS / GRCI / proxy 指标语义边界 |
| `allowed_claims` | Evidence Pack 支撑的允许表达类型 |
| `forbidden_claims` | 报告中禁止表达的 claim 类型 |

兼容字段仍然保留：

| 字段 | 说明 |
| --- | --- |
| `geology_evidence.key_cells` | 正式关键 cell 字段 |
| `geology_evidence.selected_cells` | 短期兼容字段，内容与 `key_cells` 一致 |

## Twin Boundary Check

`twin_boundary_summary` 用于检查报告是否违反 twin 语义边界，重点包括：

- GRCI 被写成灾害概率；
- forward attention 被写成已发生事实；
- forward cell 使用 GRCI；
- PLC proxy 被写成严格物理功率；
- stop_ratio 被写成异常停机原因。

检查结果进入：

- `quality.twin_boundary_check`
- `quality_summary.twin_boundary_violation_count`
- `quality_summary.twin_boundary_has_violation`
- `DailyReportResult.twin_boundary_summary`
