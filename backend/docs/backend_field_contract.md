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

## 3. RAI / GRS / GRCI

| 指标 | 语义 | 不应误解为 |
|---|---|---|
| `RAI` | PLC 施工响应异常关注度 | 事故原因或停机原因 |
| `GRS_geo_base` | 地质证据关注度 | 地质灾害概率 |
| `GRCI` | 已掘 cell 的地质-施工响应耦合关注度 | 灾害概率、前方风险 |

GRCI 只在 daily review cell 中计算。forward attention 和 local background cell 必须视为 `GRCI_available=false`。

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
