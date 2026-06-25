# TBM 施工状态数字孪生底座架构

本文档说明当前后端在原有单日 pipeline 基础上新增的 `DailyConstructionTwin` 架构层。它不是新的数值模型，也不改变 RAI / GRS / GRCI 的计算公式，而是把已经形成的 `ConstructionStateCell` 组织成可查询、可治理、可解释、可导出的施工状态数字孪生底座。

## 1. 架构定位

当前后端的核心定位从“只生成施工日报”扩展为：

```text
TBM 施工状态数字孪生底座
+ 多源证据治理
+ 大模型可追溯认知接口
```

日报仍然是一个重要输出，但不再是唯一中心。系统现在先构建结构化的日施工状态孪生对象，然后从该对象派生 Evidence Pack、报告、质量核验、Trace 和调试导出。

## 2. 当前主链路

```text
PLC 日运行数据 + 正式 evidence_db
        |
        v
ConstructionStateCell
        |
        v
DailyConstructionTwin
        |
        +--> Evidence Governance
        |       - role rules
        |       - metric boundaries
        |       - allowed / forbidden claims
        |
        +--> Twin Query
        |       - daily_review cells
        |       - forward_attention cells
        |       - local_background cells
        |       - high GRCI review cells
        |
        +--> Twin Evidence Pack
        |       - evidence_pack_source = daily_construction_twin
        |       - key_cells / selected_cells
        |       - daily_review / forward_attention / local_background
        |
        +--> LLM Cognitive Interface
        |       - report prompt
        |       - template report
        |       - optional LLM generation / revision
        |       - template-only state interpreter
        |
        v
Quality / Grounding / Trace / Twin Boundary Check
        |
        v
Report / Debug API / Export
```

## 3. 新增核心文件

| 文件 | 作用 |
| --- | --- |
| `schemas/twin.py` | 定义 `TwinScope`、`TwinCellView`、`TwinStateSummary`、`TwinTraceIndex`、`EvidenceGovernanceContext`、`DailyConstructionTwin` |
| `twin/construction_twin.py` | 从 `ConstructionStateCell` 构建 `DailyConstructionTwin` |
| `twin/query.py` | 只读查询 daily_review、forward_attention、local_background、high GRCI 等 cell |
| `evidence_governance/` | 定义证据角色、指标边界、claim 允许/禁止规则 |
| `llm/evidence_pack.py` | 新增 `build_evidence_pack_from_twin()`，Evidence Pack 从 twin 派生 |
| `llm/state_interpreter.py` | 模板式 cell / twin 解释接口，不调用外部 LLM |
| `llm/twin_boundary_checker.py` | 检查报告是否违反 twin 边界，例如把 GRCI 写成概率、把前方关注写成事实 |

## 4. DailyConstructionTwin 结构

`DailyConstructionTwin` 是当前结构化状态底座，主要字段如下：

| 字段 | 含义 |
| --- | --- |
| `date` | 报告日期 |
| `scope` | 当日 PLC 实测范围、cell 对齐复核范围、前方范围、局部背景范围 |
| `cells` | 全部 `TwinCellView` |
| `daily_review_cells` | 已掘复核单元，可使用 RAI / GRS / GRCI |
| `forward_attention_cells` | 当前掌子面前方关注单元，只使用 GRS / source_trace，不使用 GRCI |
| `local_background_cells` | 局部背景单元，只作为上下文 |
| `high_grci_cells` | 已掘复核范围内的 high / top GRCI 单元，不包含 forward cell |
| `summaries` | operation、response、geology、forward、gas、coupling、quality 摘要 |
| `trace_index` | cell、PLC、geology、source evidence 的索引 |
| `governance` | 证据角色规则、指标边界、claim 约束 |
| `debug` | 运行时调试信息 |
| `warnings` | pipeline warnings |

## 5. TwinCellView 结构

每个 `TwinCellView` 按状态域组织字段：

| 状态域 | 来源 | 含义 |
| --- | --- | --- |
| `position_state` | `ConstructionStateCell` | cell 里程、是否已掘、是否当前掌子面 cell、是否前方 cell |
| `operation_state` | PLC 工况分析 | 停机、异常、停机语义边界 |
| `response_state` | PLC cell response | RAI、推进速度、推力、扭矩、working-only enhanced PLC proxy |
| `geology_state` | geology_v2 融合 | GRS、地质证据、hazards、source_trace |
| `forward_state` | report scope | forward distance band、forward boundary |
| `gas_state` | gas summary | 预留日级气体状态入口 |
| `coupling_state` | GRCI 结果 | GRCI、coupling_level、coupling explanation |
| `quality_state` | 字段可用性 | has_plc_response、has_geology_evidence、GRCI_available、warnings |
| `trace_state` | trace refs | supporting evidence ids、trace refs、source trace |

## 6. 证据角色边界

### daily_review

用于已掘区段复核。允许使用：

- RAI；
- GRS；
- GRCI；
- PLC enhanced proxy；
- 已掘范围内的地质证据；
- source_trace。

不得声称：

- GRCI 是灾害概率；
- PLC 指标单独证明地质异常；
- 前方状态已经发生。

### forward_attention

用于当前掌子面前方关注提示。允许使用：

- GRS；
- main_hazards；
- source_trace；
- forward_profile；
- forward distance band。

不得使用：

- GRCI；
- high_grci_cells；
- RAI 作为前方风险；
- 已掘 PLC 响应证明前方状态。

### local_background

只作为局部背景上下文，不作为当日复核结论或前方事实。

## 7. Evidence Pack 变化

新增入口：

```python
build_evidence_pack_from_twin(twin=DailyConstructionTwin, ...)
```

输出仍保留旧字段名，保证 Quality / Trace / API 兼容：

- `geology_evidence.key_cells`
- `geology_evidence.selected_cells`
- `daily_review_evidence`
- `excavated_review_evidence`
- `forward_attention_evidence`
- `background_context_evidence`
- `coupling_evidence`
- `source_trace`
- `generation_constraints`

新增或强化字段：

- `evidence_pack_source = "daily_construction_twin"`
- `evidence_governance`
- `source_role_boundaries`
- `metric_boundaries`
- `allowed_claims`
- `forbidden_claims`

## 8. 质量与边界检查

原有 Quality / Grounding / Trace 仍然保留。新增 `twin_boundary_check`，主要检查：

- 是否把 GRCI 写成灾害概率；
- 是否把 forward attention 写成已发生事实；
- 是否把 forward cell 和 GRCI 绑定；
- 是否把 PLC proxy 写成严格物理功率；
- 是否把 stop_ratio 直接解释为异常原因。

结果进入：

- `quality.twin_boundary_check`
- `quality_summary.twin_boundary_violation_count`
- `quality_summary.twin_boundary_has_violation`
- `DailyReportResult.twin_boundary_summary`

## 9. API 与导出

普通接口 `/api/tbm/report` 保持原有字段契约，不额外暴露完整 twin。

调试接口 `/api/tbm/report/debug` 新增：

- `daily_construction_twin`
- `twin_summary`
- `twin_boundary_summary`

导出脚本 `scripts/export_daily_pipeline_outputs.py` 新增：

- `daily_construction_twin.json`
- `twin_summary.json`
- `twin_boundary_summary.json`
- `twin_cell_views.json`
- `twin_cell_views.csv`

## 10. 重要边界

- 本次架构升级不改变 RAI / GRS / GRCI 公式。
- 本次架构升级不引入 RAI_v2、PPR、energy_load、relation_deviation_score 或复杂模型。
- `DailyConstructionTwin` 是结构化状态底座，不是物理仿真数字孪生。
- `state_interpreter.py` 是模板式解释接口，不默认调用外部 LLM。
- P3 地质文本结构化仍是 sidecar candidate evidence，不进入正式主链路。
- claim-first generation 仍是旁路导出能力，不进入默认报告生成流程。

