# TBM 施工日报后端方法与计算逻辑白皮书

本文解释当前 TBM 日报后端“真实执行”的方法逻辑和计算链路。它不是论文实验结果，也不是理想设计稿，而是当前代码中已经落地的字段、公式、约束和导出说明。

配套阅读：

- [文档索引](README.md)
- [系统架构与执行路线](system_architecture.md)
- [字段契约](backend_field_contract.md)
- [LLM 生成模式](llm_generation_modes.md)
- [批量审计与多日期运行](batch_pipeline.md)
- [旁路式地质文本结构化](geology_text_extraction.md)
- [论文写作上下文包](paper_writing_context.md)

## 1. 方法定位

当前系统做的是：

```text
读取每日 PLC 施工数据和正式多源地质证据
-> 在日报局部 10m 里程单元上构建 ConstructionStateCell
-> 形成施工响应、地质证据关注、地质-施工响应耦合复核
-> 构建 Evidence Pack
-> 生成证据约束日报
-> 用 Quality / Trace 检查报告 claim 是否有证据支撑
```

当前系统不做：

- 不重新解释 TSP/HSP 原始探测信号；
- 不做 TBM 物理仿真数字孪生；
- 不做地质灾害概率预测；
- 不让 LLM 计算 RAI、GRS、GRCI；
- 不让 P3 旁路候选证据自动进入正式日报主链路。

## 2. 三条证据通道

### 2.1 PLC 事实统计通道

```text
PLC 日运行数据
-> 工况识别
-> 停机、工作、异常、气体统计
-> cell_response_df
-> operation_evidence / gas_evidence
```

该通道回答“当天 PLC 数据统计上发生了什么”。

### 2.2 已掘区段复核通道

```text
cell_response_df + geo_states_df
-> ConstructionStateCell
-> RAI / GRS / GRCI
-> high_grci_cells
```

该通道回答“已掘区段中哪些 cell 同时具有地质证据关注和施工响应关注，值得复核”。`GRCI` 只是耦合关注度，不是灾害概率。

### 2.3 当前掌子面前方关注通道

```text
time_valid + spatial_relevant 地质证据
-> forward_profile
-> forward_attention_cells
```

该通道回答“当前掌子面前方有哪些可用地质证据提示需要关注”。前方提示使用 `GRS_geo_base`、`main_hazards`、`source_trace`，不使用 GRCI。

## 3. 日报空间范围

当前日报只围绕当日施工范围和当前掌子面建立局部 cell。

核心字段：

- `daily_plc_range`：PLC 实测当日推进范围。
- `daily_advance_m`：PLC 实测推进量。
- `daily_excavated_scope`：10m cell 对齐后的已掘复核范围。
- `current_chainage`：当前掌子面/当日末端里程。

必须区分：

```text
PLC 实测推进范围 != 10m cell 对齐后的复核范围
```

例如 2023-12-30 中：

- PLC 实测范围为 `1014601.0 ~ 1014616.0`；
- 实测推进量为 `15.0 m`；
- 10m cell 对齐复核范围为 `1014600.0 ~ 1014620.0`；
- 报告不得把 `1014600.0 ~ 1014620.0` 写成实际推进 20m。

## 4. ConstructionStateCell

`ConstructionStateCell` 是当前系统的核心对象，定义在 `backend/schemas/pipeline.py`，由 `backend/pipeline/daily_report_pipeline.py` 构建。

它统一承载：

- 空间位置：`cell_id`、`cell_start`、`cell_end`、`cell_center`；
- PLC 响应：`has_plc_response`、`plc_metrics`、`RAI`、RAI components；
- 地质融合：`has_geology_evidence`、`GRS_geo_base`、GRS components、`main_hazards`；
- 耦合复核：`GRCI`、`GRCI_available`、GRCI terms、`coupling_level`；
- 空间语义：`is_excavated_today`、`is_current_face_cell`、`is_forward_cell`、`cell_role`；
- 追溯信息：`source_trace`、`supporting_evidence_ids`、`trace_refs`。

下游 Evidence Pack、Twin State、Trace、debug API 和导出文件都优先使用该对象，而不是从零散 dict 中重复取字段。

## 5. RAI 施工响应异常度

`RAI` 表示 PLC 施工响应关注度，是工程近似异常指标，不是灾害概率。

当前 components：

```text
stop_component = 0.40 * stop_ratio
abnormal_component = 0.25 * abnormal_ratio
speed_drop_component = 0.20 * speed_drop_score
torque_component = 0.10 * torque_volatility_score
speed_volatility_component = 0.05 * speed_volatility_score

RAI = stop_component
    + abnormal_component
    + speed_drop_component
    + torque_component
    + speed_volatility_component
```

导出字段包括：

- `stop_ratio`
- `abnormal_ratio`
- `speed_drop_score`
- `torque_volatility_score`
- `speed_volatility_score`
- 五个 component 字段
- `dominant_component`
- `RAI_formula_text`

停机语义边界：

```text
当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。
```

因此报告不能把“停机比例高”直接写成“异常停机原因明确”。

## 6. GRS 地质证据关注度

`GRS_geo_base` 表示地质证据融合后的关注度，不是灾害概率。

当前公式：

```text
GRS_geo_base = 0.45 * grade_score_component
             + 0.45 * hazard_component
             + 0.10 * confidence_component
```

导出字段包括：

- `grade_score_component`
- `hazard_component`
- `confidence_component`
- `GRS_geo_base`
- `GRS_formula_text`
- `GRS_component_method`
- `main_hazards`
- `hazard_scores`
- `confidence_score`
- `source_trace`

可用性字段：

- `GRS_available`
- `GRS_unavailable_reason`
- `has_geology_evidence`
- `GRS_component_method`

重要规则：

- `GRS_available=false` 表示没有可用空间相关地质证据或证据几何无效；
- `GRS_geo_base=0` 不能自动解释为“低关注”，必须同时看 `GRS_available`；
- 有证据但关注低，和没有证据，是两种不同语义。

## 7. GRCI 地质-施工响应耦合关注度

`GRCI` 表示地质证据关注与施工响应关注的耦合复核指标。它不是灾害概率，不是前方风险，也不能用于 forward cell。

只有满足以下条件才计算正式 GRCI：

- cell 属于 `daily_review` / 已掘复核范围；
- `GRS_geo_base` 存在且 `GRS_available=true`；
- `RAI` 存在；
- `has_plc_response=true`。

公式：

```text
grs_term = 0.55 * GRS_geo_base
rai_term = 0.35 * RAI
interaction_term = 0.10 * GRS_geo_base * RAI

GRCI = grs_term + rai_term + interaction_term
```

导出字段包括：

- `grs_term`
- `rai_term`
- `interaction_term`
- `GRCI`
- `GRCI_available`
- `GRCI_source`
- `GRCI_unavailable_reason`
- `GRCI_formula_text`
- `coupling_level`
- `coupling_explanation`

不可用规则：

- 缺少 PLC response：`GRCI_available=false`，reason 为 `missing_plc_response`；
- 缺少 RAI：不计算正式 GRCI；
- forward_attention 与 local_background cell 不计算 GRCI；
- high GRCI 只来自已掘区段。

## 8. Evidence Pack

Evidence Pack 是报告生成的唯一结构化证据输入。它至少包含：

- `report_scope`
- `operation_evidence`
- `cluster_evidence`
- `gas_evidence`
- `geology_evidence`
- `coupling_evidence`
- `forward_evidence`
- `quality_evidence`
- `source_trace`
- `generation_constraints`

证据分层：

- `excavated_review_evidence`：已掘区段复核，用于 GRCI 与 high_grci_cells。
- `forward_attention_evidence`：当前掌子面前方关注，只用 GRS / hazards / source_trace。
- `background_context_evidence`：局部背景，不作为强结论依据。

字段契约：

- 正式字段：`geology_evidence.key_cells`
- 短期兼容字段：`geology_evidence.selected_cells`
- 两者内容保持一致；
- grounding checker 优先读取 `key_cells`，其次 fallback 到 `selected_cells`。

## 9. 报告生成

当前支持：

- `template`：默认 no-LLM 模板报告；
- `evidence_pack_llm`：Evidence Pack 约束 LLM 生成；
- `evidence_pack_llm_with_revision`：LLM 初稿 + Quality/Trace 反馈修订；
- `evidence_pack_planner_llm`：先生成 Report Plan，验证后再生成报告。

报告生成约束：

- 不得把 GRCI 写成概率；
- 不得把前方关注提示写成已发生事实；
- 不得把超前预报写成现场揭露事实；
- 不得根据 `daily_excavated_scope` 自行计算推进量；
- 实际推进范围只能使用 `daily_plc_range`；
- `stop_ratio` 高不能直接写成异常原因。

LLM 输出会经过后处理，删除“好的，以下是……”等客套开头和多余分隔符，最终只保留正式报告正文。

## 10. Quality / Trace

Quality / Trace 负责检查报告是否被 Evidence Pack 支撑。

关键指标：

- `quality_score`：报告质量分；
- `claim_count`：抽取到的 claim 数；
- `grounded_claim_count`：有证据支撑的 claim 数；
- `unsupported_claim_count`：未支撑 claim 数；
- `grounding_rate`：支撑率；
- `trace_coverage`：trace 覆盖率。

关键 error type：

- `E3_GRCI_AS_PROBABILITY`：把 GRCI 写成概率；
- `E10_NUMERIC_VALUE_UNGROUNDED`：数值无证据；
- `E12_METHOD_BOUNDARY_STATEMENT`：方法边界说明；
- `E13_STOP_REASON_OVERINTERPRETATION`：把停机直接解释成异常原因；
- `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE`：把 10m 对齐复核范围误写为实际推进范围或推进量。

方法边界句可以由 `policy_support` 支撑，但真正无证据的技术判断不能被放宽。

## 11. P3 旁路式地质文本结构化

P3 模块位于 `backend/geology_text/`，用于把原始地质文本抽取成候选证据。

它的输出必须满足：

- `candidate_only=true`
- `requires_manual_review=true`
- `not_used_by_main_pipeline=true`

P3 不写入正式 `evidence_db.csv`，不进入 time_valid / spatial_relevant，不参与 GRS/RAI/GRCI，不进入 Evidence Pack，也不影响报告生成。

## 12. 导出与复盘

`scripts/export_daily_pipeline_outputs.py` 会为每个日期导出：

- `report.txt`
- `prompt.txt`
- `evidence_pack.json`
- `quality.json`
- `trace.json`
- `construction_state_cells.json`
- `construction_state_cells.csv`
- `forward_profile.json`
- `high_grci_cells.json`
- `warnings.json`
- `summary.json`
- `method_metrics.json`

`method_metrics.json` 用于后续实验统计，包含：

- date 与里程范围；
- time_valid / spatial_relevant / excluded evidence 数量；
- construction_state_cell_count；
- daily_review / forward_attention / local_background 数量；
- RAI / GRS / GRCI available 数量；
- high / medium / low priority cell 数量；
- claim / grounding / quality / trace 指标；
- warnings 与 passed 状态。

## 13. 典型日期复盘方式

以 2023-12-30 为例，推荐复盘顺序：

1. 查看 `summary.json` 与 `method_metrics.json`，确认当日 PLC 范围、cell 数和 quality 指标；
2. 查看 `construction_state_cells.csv`，复算 RAI、GRS、GRCI components；
3. 查看 `high_grci_cells.json`，确认 high GRCI 只来自已掘区段；
4. 查看 `forward_profile.json`，确认前方提示未使用 GRCI；
5. 查看 `evidence_pack.json`，确认 `key_cells`、`excavated_review_evidence`、`forward_attention_evidence`；
6. 查看 `trace.json`，核对 report claim 与证据来源；
7. 查看 `report.txt`，确认报告没有把 GRCI 写成概率、没有把前方提示写成事实。

## 14. 方法边界总结

当前系统是一条证据约束日报生成与复核链路，而不是灾害概率预测系统。它的核心价值在于：

- 把 PLC 响应和地质证据统一到局部 10m cell；
- 把已掘复核、前方关注和背景上下文分层；
- 让每个 RAI、GRS、GRCI 分数可复盘；
- 让报告生成受 Evidence Pack 约束；
- 让 Quality / Trace 暴露无证据 claim 和语义误用；
- 为后续论文实验提供可复现导出。
