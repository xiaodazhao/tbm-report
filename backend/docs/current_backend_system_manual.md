# 当前后端系统说明书

本文档说明当前 TBM 施工日报后端的真实执行路线。它不是论文概念稿，也不是未来设计稿，而是基于当前代码和已导出的 `2023-12-30` 结果整理出的工程说明书。

## 相关文档

- [方法与计算逻辑白皮书](method_calculation_whitepaper.md)：公式、字段反向索引、配置常量、导出完整性检查。
- [后端字段契约](backend_field_contract.md)：API、schema 与 debug 输出字段。
- [方法定义文档](method_definition.md)：任务定义、核心对象与方法边界。
- [指标定义文档](metrics_definition.md)：GRS、RAI、GRCI、Quality、Trace 指标说明。
- [系统边界声明](scope_and_limitations.md)：当前系统不做什么。
- [2023-12-30 案例说明](case_2023-12-30.md)：典型日期案例。

## 1. 系统一句话说明

当前后端读取每日 PLC 运行数据和多源地质证据，按 10m 里程单元构建 `ConstructionStateCell`，计算 GRS / RAI / GRCI，生成 Evidence Pack、日报文本、Quality 与 Trace 结果，并通过精简后的报告 API 输出。

## 2. 当前总技术路线

```text
FastAPI 路由
│
└── routes/report.py
    │
    ▼
run_daily_report_pipeline(date, use_llm)
    │
    ├── load_daily_inputs(date)
    │   ├── PLC 日运行 CSV
    │   └── evidence_db.csv
    │
    ├── analyze_plc_response(df_plc)
    │   ├── PLC 质量检查
    │   ├── 工况识别
    │   ├── 施工状态聚类
    │   ├── 气体统计
    │   └── cell_response_df / RAI
    │
    ├── run_geology_v2_context(...)
    │   ├── normalize_evidence_df
    │   ├── filter_available_evidence
    │   ├── deduplicate_hsp_anomaly_points
    │   ├── build_chainage_cells
    │   ├── project_evidence_to_cells
    │   ├── fuse_geo_states
    │   └── build_forward_profile
    │
    ├── build_construction_state_cells(...)
    │   └── ConstructionStateCell[]
    │
    ├── high_grci_cells(...)
    ├── build_twin_state(...)
    ├── build_prompt_evidence_pack(...)
    ├── build_prompt(...)
    ├── call_llm_result 或 build_template_report
    ├── check_report_quality(...)
    ├── build_report_trace(...)
    │
    ▼
DailyReportResult
```

主线只有一条：`routes.report -> run_daily_report_pipeline -> ConstructionStateCell -> Evidence Pack -> Report -> Quality / Trace`。旧 Agent、旧 segment GRCI、旧 routes/tbm.py、旧 history memory 不参与当前主流程。

## 3. 主流程调用链

| 步骤 | 文件 / 函数 | 输入 | 输出 | 作用 |
|---|---|---|---|---|
| 1 | `app.py` | FastAPI 启动 | app | 注册当前报告路由 |
| 2 | `routes/report.py` | HTTP 请求 | API 响应 | 提供 `/api/tbm/health`、`/api/tbm/dates`、`/api/tbm/report`、`/api/tbm/report/debug` |
| 3 | `pipeline/daily_report_pipeline.py::run_daily_report_pipeline` | `date`, `use_llm` | `DailyReportResult` | 当前唯一日报主入口 |
| 4 | `pipeline/inputs.py::load_daily_inputs` | 日期 | PLC DataFrame、Evidence DataFrame | 按日期读取 PLC CSV 与证据库 |
| 5 | `plc/response.py::analyze_plc_response` | PLC DataFrame | operation / cluster / gas / cell_response | 完成 PLC 侧全部分析 |
| 6 | `geology_v2/pipeline.py::run_geology_v2_context` | PLC、evidence、当前里程、日期 | geology_v2 结构化结果 | 完成地质证据标准化、投影、融合与前方 profile |
| 7 | `coupling/grs_rai_grci.py::build_construction_state_cells` | cells、cell_response、geo_states、cell_evidence | `ConstructionStateCell[]` | 合并 PLC、地质、耦合、trace 字段 |
| 8 | `coupling/grs_rai_grci.py::high_grci_cells` | `ConstructionStateCell[]` | high GRCI cells | 只筛选已掘、GRCI 可用、非前方 cell |
| 9 | `twin/twin_state.py::build_twin_state` | summaries + cells | twin_state | 面向报告和 trace 的状态摘要 |
| 10 | `llm/evidence_pack.py::build_prompt_evidence_pack` | cells、summary、forward、constraints | Evidence Pack | 报告生成的唯一证据输入 |
| 11 | `llm/report_prompt.py::build_prompt` | Evidence Pack | prompt_text | 构建 LLM prompt |
| 12 | `llm/llm_api.py::call_llm_result` | prompt_text | LLM 结果 | 可选调用 LLM，失败时 fallback |
| 13 | `llm/evidence_pack.py::build_template_report` | Evidence Pack | report_text | no-LLM 或 LLM 失败时的模板报告 |
| 14 | `llm/report_quality_checker.py::check_report_quality` | report + Evidence Pack + twin_state | quality | 检查章节、禁用表述和 grounding |
| 15 | `llm/report_trace_builder.py::build_report_trace` | report + grounding + Evidence Pack | trace | 构建 claim 到 evidence 的追溯结果 |

## 4. 原始数据层

### 4.1 PLC 日运行数据

PLC 日运行数据由 `pipeline/inputs.py::load_daily_inputs` 调用 `utils/io_utils.py` 读取。当前按日期查找类似 `tbm_data_YYYYMMDD.csv` 的文件，实际目录由 `config.py` 中的 `DATA_ROOT` / `DATA_DIR` 决定。

当前实际使用字段包括：

- 时间：用于排序、采样间隔、工况持续时间。
- 里程 / 桩号：用于当日掘进范围和 10m cell 聚合。
- 推进速度：用于工况识别、速度统计、RAI。
- 推力：用于工况识别、聚类和响应统计。
- 刀盘扭矩：用于异常响应、聚类和 RAI。
- 刀盘转速：用于聚类和响应统计。
- 掘进状态 / 停机状态：用于工况识别和停机统计。
- 气体字段：用于气体统计和字段类型诊断。

缺字段时，PLC 模块会通过 `analysis/plc_contract.py` 做字段解析。关键字段缺失不会由前端处理，而是在后端 summary / warning 中表达。

### 4.2 多源地质证据

地质证据由 `config.py::EVIDENCE_DB_PATH` 指向的 `evidence_db.csv` 读取。证据类型在当前代码中主要通过 `source_type` / `source_type_norm` 表达：

- `TSP`：超前地质预报。
- `HSP`：水平声波等超前地质预报。
- `face_sketch`：掌子面素描，属于现场揭露类证据，但必须经过时间和里程可用性过滤。
- 其他扩展证据：仍可进入标准化流程，但是否参与报告取决于字段完整度和投影结果。

避免未来信息泄漏的关键规则在 `geology_v2.evidence_normalizer.filter_available_evidence` 和 `run_geology_v2_context(mode="online")` 中执行：

- 报告日期之后形成的 evidence 不进入当前 Evidence Pack。
- 当前掌子面之后才形成的掌子面素描不能用于当前日报。
- 前方地质证据只能写成“关注 / 提示 / 复核”，不能写成“已发生事实”。

## 5. PLC 施工响应分析路线

PLC 分析入口是 `plc/response.py::analyze_plc_response`。它内部组织以下结果：

- `operation_summary`：工况统计，包括工作、停机、过渡、异常段数和持续时间。
- `cluster_summary`：施工状态聚类与效率统计。
- `gas_summary`：气体字段诊断、浓度或报警字段统计、超限摘要。
- `cell_response_df`：按 10m cell 聚合的 PLC 响应表。
- `RAI`：施工响应异常度，当前由 `plc/cell_response.py::project_plc_response_to_cells` 计算。

`RAI` 当前是工程近似异常指标，不是灾害概率。它综合：

- 停机占比；
- 异常占比；
- 推进速度降低；
- 扭矩波动；
- 速度波动。

`cell_response_df` 有时只有 1-2 个 cell，是因为它只覆盖当日 PLC 实际掘进经过的里程单元。例如当日推进 15m，10m cell 粒度下通常只会覆盖 2 个 cell。这是正常现象，不表示地质证据只有 2 个 cell。

## 6. 地质证据处理路线

地质主链路只保留 `geology_v2`。入口是 `geology_v2/pipeline.py::run_geology_v2_context`。

| 函数 | 作用 |
|---|---|
| `normalize_evidence_df` | 把 TSP/HSP/掌子面素描等证据整理成统一字段，包含 evidence_id、source_type_norm、spatial_type、里程、hazard_tags、grade、置信字段等 |
| `filter_available_evidence` | 按报告日期、当前掌子面里程和 online 规则过滤不可用证据，避免未来信息泄漏 |
| `deduplicate_hsp_anomaly_points` | 对 HSP 异常点边界重复记录去重，防止同一异常点重复加权 |
| `build_chainage_cells` | 构建 10m 里程单元 |
| `project_evidence_to_cells` | 将标准化证据投影到 cell，计算空间距离、权重和 evidence-cell 关系 |
| `fuse_geo_states` | 融合 cell 级地质状态，生成 `geo_states_df` |
| `build_forward_profile` | 基于当前掌子面和前方窗口生成前方关注 profile |

`geo_states_df` 核心字段包括：

- `cell_id`, `cell_start`, `cell_end`, `cell_center`
- `has_geology_evidence`
- `fused_grade`
- `main_hazards`
- `hazard_scores`
- `confidence_score`
- `uncertainty_level`
- `conflict_level`
- `GRS_geo_base`
- `supporting_evidence_ids`

已掘区段的地质证据用于和 PLC 响应耦合复核；当前掌子面前方的地质证据用于 forward profile 和前方关注提示。前方 cell 不进入 high GRCI。

## 7. ConstructionStateCell

`ConstructionStateCell` 定义在 `schemas/pipeline.py`，由 `coupling/grs_rai_grci.py::build_construction_state_cells` 构建。它是当前系统最重要的 cell 级统一对象。

它的输入来自：

- `cells_df`：统一 10m cell 空间底板。
- `cell_response_df`：PLC 响应聚合结果和 RAI。
- `geo_states_df`：地质融合结果和 GRS。
- `cell_evidence_df`：cell 与 evidence 的投影关系。
- `normalized_evidence_df`：构建 source_trace 所需的证据详情。

关键字段语义：

| 字段 | 含义 |
|---|---|
| `cell_id` | 里程单元编号，例如 `cell_1014600_1014610` |
| `cell_start`, `cell_end`, `cell_center` | cell 的起止和中心里程 |
| `has_plc_response` | 当日 PLC 是否覆盖该 cell |
| `has_geology_evidence` | 该 cell 是否有地质证据或地质融合结果 |
| `is_excavated_today` | cell 是否与当日掘进范围重叠 |
| `is_current_face_cell` | 当前掌子面是否落在该 cell 内 |
| `is_forward_cell` | 是否为严格前方 cell |
| `GRS_geo_base` | 地质证据关注度，来自 `geo_states_df` |
| `RAI` | 施工响应异常度，来自 `cell_response_df` |
| `GRCI` | 地质-施工响应耦合关注度，只有 GRS 和 RAI 均可用时计算 |
| `GRCI_available` | 是否形成正式 GRCI |
| `GRCI_source` | GRCI 计算来源，当前为 `cell_grs_rai_formula_v1` 或 `unavailable` |
| `GRCI_unavailable_reason` | 不计算 GRCI 的原因，例如 `missing_plc_response` |
| `main_hazards` | cell 主要地质关注标签 |
| `supporting_evidence_ids` | 支撑该 cell 的证据 ID |
| `source_trace` | 证据来源、类型、角色、摘要等可追溯信息 |
| `coupling_explanation` | 该 cell 的耦合解释或不可用原因 |

Evidence Pack、Twin State、Trace 和 `/api/tbm/report/debug` 都优先消费 `ConstructionStateCell`，不再从零散 dict 里重复拼主逻辑。

## 8. GRS / RAI / GRCI 当前语义

### GRS

`GRS_geo_base` 表示 cell 级地质证据关注度，来自地质证据融合。它反映围岩等级、hazard 标签、证据支持、置信度等地质侧信息。

### RAI

`RAI` 表示 cell 级施工响应异常度，来自 PLC 响应聚合。它反映停机、异常、速度下降和参数波动等施工侧表现。

### GRCI

`GRCI` 表示地质-施工响应耦合关注度，仅用于已掘区段复核。当前公式为：

```text
GRCI = 0.55 * GRS_geo_base + 0.35 * RAI + 0.10 * GRS_geo_base * RAI
```

必须满足：

- `GRS_geo_base` 存在；
- `RAI` 存在；
- `has_plc_response == True`。

否则：

```text
GRCI = None
GRCI_available = False
GRCI_source = "unavailable"
GRCI_unavailable_reason = "missing_plc_response" 或 "missing_geology_evidence"
coupling_level = "unavailable"
```

必须特别注意：

- GRCI 不是灾害概率。
- GRCI 不是前方风险。
- 没有 RAI 的 cell 不计算正式 GRCI。
- 前方 cell 使用 GRS / forward_profile / source_trace，不进入 high_grci_cells。

这些规则由 `compute_cell_grci` 和 `high_grci_cells` 共同保证。

## 9. Forward Profile 路线

`forward_profile` 由 `geology_v2.forward_profile.build_forward_profile` 构建，并在 `daily_report_pipeline._with_forward_attention_cells` 中补充 `forward_attention_cells`。

输入包括：

- `geo_states_df`
- 当前掌子面里程 `current_chainage`
- `lookahead_m`
- `advance_direction`

输出包括：

- 前方窗口列表，例如 `0-10m`, `10-20m`, `20-30m`
- 每个窗口对应的 supporting cell
- `attention_level`
- `fused_grade`
- `main_hazards`
- `forward_attention_cells`

前方提示只使用：

- `GRS_geo_base`
- `main_hazards`
- `source_trace`
- `forward_profile`

它不使用 GRCI。原因是前方 cell 没有当日 PLC response，因此不能形成地质-施工响应耦合复核。

## 10. Twin State 与 Evidence Pack

`twin/twin_state.py::build_twin_state` 构建面向报告和 trace 的状态摘要，包含：

- operation_state
- cluster_state
- gas_state
- geology_state
- response_state
- forward_state
- coupling_state
- provenance_state
- trace_state

`llm/evidence_pack.py::build_prompt_evidence_pack` 构建报告生成唯一证据包，主要包括：

- `report_scope`
- `operation_evidence`
- `cluster_evidence`
- `gas_evidence`
- `geology_evidence`
- `forward_evidence`
- `coupling_evidence`
- `quality_evidence`
- `source_trace`
- `generation_constraints`
- `warnings`

`geology_evidence.key_cells` 是正式字段；`geology_evidence.selected_cells` 是短期兼容字段，两者当前内容一致。Grounding checker 优先读 `key_cells`，再 fallback 到 `selected_cells`。

Evidence Pack 对报告的约束包括：

- 不得把 GRCI 写成灾害概率。
- 不得把前方提示写成已发生事实。
- 不得把既有超前预报写成现场揭露事实。
- 没有 source_trace 或 PLC 指标支持的内容不得写成确定性结论。
- TSP/HSP 结论不得被表述为一定真实。

## 11. 报告生成路线

当前报告生成有两种模式：

- `use_llm=False`：不调用真实 LLM，直接使用 `build_template_report` 生成模板报告。
- `use_llm=True`：调用 `call_llm_result`；如果失败或未配置，则回落到模板报告，并在 `warnings` 中写入原因。

无论哪种模式，报告都必须基于 Evidence Pack。LLM 不是数值推理器，也不负责计算 GRCI / RAI / forward cell。

## 12. Quality / Trace 路线

`llm/report_quality_checker.py::check_report_quality` 检查：

- 章节完整性；
- 禁用表述；
- GRCI 概率误用；
- 前方提示事实误用；
- claim grounding。

`llm/report_trace_builder.py::build_report_trace` 将报告中的 claim 和 Evidence Pack / Twin State 中的证据建立追溯关系。

关键指标：

- `quality_score`：报告质量分。
- `grounding_rate`：可追溯 claim 占比。
- `unsupported_claim_count`：未能找到证据支撑的 claim 数量。
- `trace_coverage`：trace 覆盖度。

当前字段契约已经统一：

```text
geology_evidence.key_cells      正式字段
geology_evidence.selected_cells 兼容字段
grounding checker: key_cells -> selected_cells
```

## 13. API 输出路线

当前后端只保留四个核心 API：

| API | 方法 | 作用 |
|---|---|---|
| `/api/tbm/health` | GET | 检查后端状态 |
| `/api/tbm/dates` | GET | 返回可用数据日期 |
| `/api/tbm/report` | POST | 返回普通报告结果 |
| `/api/tbm/report/debug` | POST | 返回完整中间结果 |

`/api/tbm/report` 适合普通前端展示，核心返回：

- `date`
- `report_text`
- `quality_summary`
- `trace_summary`
- `forward_profile`
- `high_grci_cells`
- `warnings`

`/api/tbm/report/debug` 适合研究和调试，额外返回：

- `operation_summary`
- `cluster_summary`
- `gas_summary`
- `normalized_evidence_summary`
- `construction_state_cells`
- `prompt_evidence_pack`
- `prompt_text`
- `quality`
- `trace`

## 14. 当前边界

当前系统不做以下事情：

- 不重新解释 TSP/HSP 原始探测信号。
- 不做 TBM 物理仿真数字孪生。
- 不做地质灾害概率预测。
- Agent 不参与当前主流程。
- LLM 不是核心数值推理器。
- 当前 smoke test 是工程回归验证，不是论文实验。

## 15. 2023-12-30 真实数据流案例

本节基于当前已导出的 no-LLM pipeline 结果：

```text
backend/outputs/pipeline_exports/2023-12-30/
```

以及多日期 smoke summary：

```text
backend/outputs/smoke_summary.json
```

### 15.1 输入

日期：

```text
2023-12-30
```

PLC 数据路径：

```text
G:/我的云端硬盘/TBM9/TBM9_2023/tbm_data_20231230.csv
```

地质证据库路径：

```text
G:/我的云端硬盘/TBM9/DB/evidence_db.csv
```

PLC 读取结果：

```text
PLC 行数：4098
当日最小里程：1014601.0
当日最大里程：1014616.0
当日推进量：15.0 m
当前掌子面里程：1014616.0
```

地质证据说明：

- 原始 `evidence_db.csv` 总行数没有在当前 export 文件中单独落盘，因此本文不虚构原始库总条数。
- 当前案例可直接复核的是进入 Evidence Pack 的关键地质证据引用：`key_cells` 去重 `supporting_evidence_ids` 共 `58` 条。
- 其中 high GRCI cells 使用的去重地质证据引用共 `6` 条。
- forward attention cells 使用的去重地质证据引用共 `5` 条。

### 15.2 PLC 施工响应

`cell_response_df` 行数：

```text
2
```

对应两个当日 PLC response cell：

| cell_id | 里程范围 | operation_state | stop_duration_min | RAI |
|---|---:|---|---:|---:|
| `cell_1014600_1014610` | 1014600.0 - 1014610.0 | stop | 837.3333 | 0.517548 |
| `cell_1014610_1014620` | 1014610.0 - 1014620.0 | stop | 236.5000 | 0.447116 |

这两个 cell 与当日推进范围 `1014601.0 - 1014616.0` 对齐。因为当日推进 15m，10m cell 粒度下覆盖两个 cell 是合理结果。

PLC 工况摘要：

```text
主导工况：停机
稳定掘进时长：360.1667 min
停机时长：1074.0 min
过渡时长：3.0 min
异常时长：2.3333 min
稳定掘进段数：15
停机段数：18
过渡段数：9
异常段数：5
```

气体摘要：

```text
has_exceedance: true
exceed_gases: CH4检测
exceed_event_count_total: 1
```

### 15.3 地质证据与 geo_states

当前案例中：

```text
geo_states_df cell 数：157
construction_state_cells 数：157
```

`geo_states_df` 的地质融合字段已经合入 `ConstructionStateCell`，包括：

- `GRS_geo_base`
- `fused_grade`
- `main_hazards`
- `hazard_scores`
- `confidence_score`
- `uncertainty_level`
- `conflict_level`
- `supporting_evidence_ids`

### 15.4 GRS / RAI / GRCI 结果

`GRCI_available_count`：

```text
2
```

缺 RAI 的 cell 数：

```text
155
```

缺正式 GRCI 的 cell 数：

```text
155
```

这说明当前语义已经生效：没有 PLC response / RAI 的 cell 不计算正式 GRCI。

两个 high GRCI cells：

| cell_id | GRS_geo_base | RAI | GRCI | coupling_level | forward? | 主要地质关注 |
|---|---:|---:|---:|---|---|---|
| `cell_1014600_1014610` | 0.575306 | 0.517548 | 0.5273 | medium | false | 围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常 |
| `cell_1014610_1014620` | 0.611930 | 0.447116 | 0.5204 | medium | false | 围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常 |

对应解释：

```text
cell_1014600_1014610:
GRS=0.58，RAI=0.52，GRCI=0.53，耦合等级=medium；主要地质关注：围岩极破碎、掉块、裂隙密集。

cell_1014610_1014620:
GRS=0.61，RAI=0.45，GRCI=0.52，耦合等级=medium；主要地质关注：围岩极破碎、掉块、裂隙密集。
```

### 15.5 Forward Profile

当前掌子面：

```text
1014616.0
```

前方窗口：

| range_label | 窗口范围 | supporting_cell_ids | attention_level | fused_grade | main_hazards |
|---|---:|---|---|---|---|
| `0-10m` | 1014616.0 - 1014626.0 | `cell_1014620_1014630` | medium | Ⅳ | 围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常 |
| `10-20m` | 1014626.0 - 1014636.0 | `cell_1014630_1014640` | medium | Ⅳ | 围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常 |
| `20-30m` | 1014636.0 - 1014646.0 | `cell_1014640_1014650` | low | Ⅳ | 围岩极破碎、明显反射异常、掉块、裂隙密集、围岩破碎 |

`forward_attention_cells`：

| cell_id | 里程范围 | GRS_geo_base | main_hazards |
|---|---:|---:|---|
| `cell_1014620_1014630` | 1014620.0 - 1014630.0 | 0.535269 | 围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常 |
| `cell_1014630_1014640` | 1014630.0 - 1014640.0 | 0.557462 | 围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常 |
| `cell_1014640_1014650` | 1014640.0 - 1014650.0 | 0.483092 | 围岩极破碎、明显反射异常、掉块、裂隙密集、围岩破碎 |

这些 forward cells 均不进入 high GRCI，因为它们没有当日 PLC response / RAI。

### 15.6 Evidence Pack key_cells

Evidence Pack 中：

```text
key_cells_count = 13
selected_cells_count = 13
grounding_key_cells_seen = 13
```

`key_cells` 列表：

| cell_id | GRCI_available | is_excavated_today | is_forward_cell | GRS_geo_base | RAI | GRCI |
|---|---|---|---|---:|---:|---:|
| `cell_1014600_1014610` | true | true | false | 0.575306 | 0.517548 | 0.5273 |
| `cell_1014610_1014620` | true | true | false | 0.611930 | 0.447116 | 0.5204 |
| `cell_1013180_1013190` | false | false | false | 0.898125 | null | null |
| `cell_1013540_1013550` | false | false | false | 0.894525 | null | null |
| `cell_1013670_1013680` | false | false | false | 0.891841 | null | null |
| `cell_1013220_1013230` | false | false | false | 0.870221 | null | null |
| `cell_1013120_1013130` | false | false | false | 0.869908 | null | null |
| `cell_1013130_1013140` | false | false | false | 0.868046 | null | null |
| `cell_1013570_1013580` | false | false | false | 0.862671 | null | null |
| `cell_1013110_1013120` | false | false | false | 0.861413 | null | null |
| `cell_1014620_1014630` | false | false | true | 0.535269 | null | null |
| `cell_1014630_1014640` | false | false | true | 0.557462 | null | null |
| `cell_1014640_1014650` | false | false | true | 0.483092 | null | null |

这个列表同时包含：

- 已掘且有 GRCI 的复核 cell；
- 历史/背景地质高关注 cell；
- 当前掌子面前方 attention cell。

报告中的 high GRCI 只从前两行中取，因为只有它们满足 `GRCI_available == true`、`is_excavated_today == true`、`is_forward_cell == false`。

### 15.7 报告句子到证据的追溯示例

当前质量检查结果：

```text
quality_score = 100
grounding_rate = 1.0
unsupported_claim_count = 0
trace_coverage = 1.0
```

典型 claim 与证据关系：

| 报告 claim | grounding 来源 |
|---|---|
| 本日已形成 2 个可用的已开挖区段 GRCI 关注 cell。 | `coupling_evidence.high_grci_cells` 中两个 cell |
| GRCI 仅用于已开挖区段复核。 | `generation_constraints` 与 high GRCI 筛选规则 |
| 前方关注提示来自 forward_profile，共 3 个前方窗口，仅用于提示和复核。 | `forward_evidence.forward_profile.profile` |
| PLC 工况统计显示，主导工况为停机。 | `operation_evidence.operation_mode_summary.dominant_mode_cn` |
| PLC 统计记录中，稳定掘进段数量为 15，停机段数量为 18，异常段数量为 5。 | `operation_evidence.operation_mode_summary` |
| `cell_1014600_1014610` 的 GRCI 等级为 medium，GRCI 约 0.53。 | `coupling_evidence.high_grci_cells[0]` |
| `cell_1014610_1014620` 的 GRCI 等级为 medium，GRCI 约 0.52。 | `coupling_evidence.high_grci_cells[1]` |
| 主要地质关注标签为围岩极破碎、掉块、裂隙密集、软硬不均、明显反射异常。 | `geology_evidence.key_cells[*].main_hazards` 与对应 `source_trace` |
| 涉及气体为 CH4检测。 | `gas_evidence.exceed_summary.exceed_gases` |
| forward_attention_cells 数量为 3。 | `forward_profile.forward_attention_cells` |

其中地质 hazard 类 claim 可进一步追到 evidence：

```text
claim
-> geology_evidence.key_cells
-> supporting_evidence_ids
-> source_trace
```

示例支撑 evidence：

```text
DyK1014+545...20231224_hsp_2
DyK1014+591...sketch_0
DyK1014+545...20231224_hsp_3_collapse_point_0
```

这些 source_trace 会保留 evidence 类型，例如 `HSP` 或 `face_sketch`，并标注 evidence_role，例如 `prediction` 或 `observed`。因此报告可以区分“超前预报提示”和“现场素描证据”，避免把前方预报写成已揭露事实。

## 16. 本案例结论

`2023-12-30` 的真实数据流说明当前主线工作正常：

- PLC 读取 4098 行，当日推进 15m。
- `cell_response_df` 覆盖 2 个当日施工响应 cell。
- `geo_states_df` / `construction_state_cells` 覆盖 157 个地质 cell。
- 只有 2 个 cell 同时具备 GRS、RAI 和 PLC response，因此只有 2 个正式 GRCI。
- 前方 3 个 cell 使用 forward_profile 和 GRS，不进入 high GRCI。
- Evidence Pack 中 `key_cells` 与 `selected_cells` 数量一致，均为 13。
- Grounding checker 能识别全部 key_cells，`grounding_key_cells_seen = 13`。
- 模板报告质量检查通过，`unsupported_claim_count = 0`。
