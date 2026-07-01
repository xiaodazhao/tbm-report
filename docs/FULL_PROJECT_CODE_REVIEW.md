# TBM 日报项目全项目代码审计与方法逻辑反向梳理

> 审计日期：2026-07-01  
> 审计状态：只读审计 + 新增本文档。未修改业务代码、未运行 LLM、未调用外部 API、未重跑实验、未移动或删除文件。  
> 审计对象：当前工作区状态，不仅是上一次 commit。当前工作区存在 Exp02/Exp03 相关未提交改动，见“当前 Git 状态”。

---

## 1. 项目一句话概括

当前项目是一个面向 TBM 施工日报/施工状态认知的后端研究原型：从 PLC 日运行数据和多源地质证据出发，构建 `ConstructionStateCell` 与 `DailyConstructionTwin`，计算 RAI / GRS / GRCI 等启发式关注指标，生成 Evidence Pack，并通过模板或 LLM 完成证据约束报告生成、Quality / Trace / Boundary 校核、自动修订和实验评估。

需要特别强调：代码中“日报生成”只是当前主要输出形态；更底层的真实结构是“施工状态单元 + 证据治理 + 可追溯文本接口”。但当前代码仍以日报 API、日报 Evidence Pack 和报告实验为主要组织方式。

---

## 2. 当前 Git 状态

审计时 `git status --short` 显示以下未提交改动：

```text
 M backend/configs/quality_checker_policy.json
 M backend/llm/report_grounding_checker.py
 M backend/llm/report_policy.py
 M backend/llm/report_quality_checker.py
 M backend/llm/twin_boundary_checker.py
 M backend/tests/test_exp02_llm_generation_modes_contract.py
 M backend/tests/test_quality_error_taxonomy_contract.py
 M backend/tests/test_twin_boundary_checker.py
 M experiments/exp02_llm_generation_modes/README.md
 M experiments/exp02_llm_generation_modes/prompts/M4_full_generation_prompt.md
 M experiments/exp02_llm_generation_modes/prompts/M4_revision_prompt.md
 M experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py
 ?? experiments/exp03_indicator_robustness/
```

因此本文审计的是“当前工作区最新状态”。如果论文或复现实验需要锁定版本，应先提交或打 tag。

---

## 3. 文件覆盖清单

本次索引扫描排除 `.git`、`node_modules`、`dist`、`__pycache__` 和大部分 `outputs*` 目录后，覆盖约：

| 类型 | 数量 |
|---|---:|
| 非输出文件总数 | 314 |
| Python 文件 | 183 |
| Markdown 文件 | 43 |
| JSON 文件 | 9 |

> 注：扫描过程中 `.pytest_cache` 有权限读取提示，但不影响项目代码审计。

### 3.1 主流程文件

- `backend/app.py`
- `backend/routes/report.py`
- `backend/pipeline/daily_report_pipeline.py`
- `backend/pipeline/inputs.py`
- `backend/pipeline/evidence_scope.py`
- `backend/config.py`
- `backend/utils/io_utils.py`
- `backend/utils/json_utils.py`

### 3.2 PLC 文件

- `backend/plc/response.py`
- `backend/plc/cell_response.py`
- `backend/plc/quality.py`
- `backend/plc/operation.py`
- `backend/plc/gas.py`
- `backend/analysis/dataprocess.py`
- `backend/analysis/excavation_state.py`
- `backend/analysis/gas_analysis.py`
- `backend/analysis/plc_quality_checker.py`

说明：`analysis/` 目录不是全部旧代码。当前 `plc/response.py` 仍依赖其中多个基础分析函数，因此不能整体归档。

### 3.3 地质证据文件

- `backend/geology_v2/pipeline.py`
- `backend/geology_v2/evidence_normalizer.py`
- `backend/geology_v2/evidence_dedup.py`
- `backend/geology_v2/cell_builder.py`
- `backend/geology_v2/evidence_projector.py`
- `backend/geology_v2/fusion_engine.py`
- `backend/geology_v2/forward_profile.py`
- `backend/geology_v2/config.py`
- `backend/geology_v2/schemas.py`
- `backend/geology_v2/text_builder.py`
- `backend/geology_v2/report_context_builder.py`
- `backend/geology_v2/report_renderer.py`
- `backend/geology_v2/explainability.py`
- `backend/geology_v2/coupling_adapter.py`

说明：`geology_v2/pipeline.py` 有动态函数解析 `_resolve_function()`，会通过模块名查找函数。因此不能只用静态 import 判断某些 geology_v2 文件未使用。

### 3.4 Coupling / Cell 文件

- `backend/coupling/grs_rai_grci.py`
- `backend/schemas/pipeline.py`
- `backend/schemas/twin.py`
- `backend/schemas/twin_state_schema.py`
- `backend/schemas/api.py`
- `backend/schemas/schemas.py`

### 3.5 DailyConstructionTwin 文件

- `backend/twin/construction_twin.py`
- `backend/twin/twin_state.py`
- `backend/twin/query.py`
- `backend/twin/interpretation.py`
- `backend/evidence_governance/governance_context.py`
- `backend/evidence_governance/roles.py`
- `backend/evidence_governance/boundaries.py`
- `backend/evidence_governance/claim_rules.py`

### 3.6 Evidence Pack / Prompt / Generation 文件

- `backend/llm/evidence_pack.py`
- `backend/llm/report_prompt.py`
- `backend/llm/llm_report_generator.py`
- `backend/llm/llm_provider.py`
- `backend/llm/llm_report_planner.py`
- `backend/llm/llm_revision.py`
- `backend/llm/prompts/report_generation_prompt.py`
- `backend/llm/prompts/report_revision_prompt.py`
- `backend/llm/prompts/report_plan_prompt.py`
- `backend/llm/prompts/geology_extraction_prompt.py`

### 3.7 Quality / Trace / Boundary 文件

- `backend/llm/report_quality_checker.py`
- `backend/llm/report_grounding_checker.py`
- `backend/llm/report_trace_builder.py`
- `backend/llm/report_claim_extractor.py`
- `backend/llm/report_error_taxonomy.py`
- `backend/llm/report_policy.py`
- `backend/llm/twin_boundary_checker.py`
- `backend/configs/quality_checker_policy.json`

### 3.8 P3 旁路地质文本结构化文件

- `backend/geology_text/__init__.py`
- `backend/geology_text/geology_extraction_schema.py`
- `backend/geology_text/geology_extraction_validator.py`
- `backend/geology_text/geology_extraction_writer.py`
- `backend/geology_text/llm_geology_extractor.py`
- `backend/scripts/run_geology_text_extraction.py`

说明：P3 是 sidecar candidate evidence module，不进入正式 evidence_db，不进入主 pipeline，不参与 GRS / RAI / GRCI。

### 3.9 API 路由清单

当前主 API 只确认 `backend/routes/report.py`：

- `GET /api/tbm/health`
- `GET /api/tbm/dates`
- `POST /api/tbm/report`
- `POST /api/tbm/report/debug`

旧 route 已在前序清理中归档，不应恢复。

### 3.10 脚本清单

主流程/导出：

- `backend/scripts/smoke_test_daily_pipeline.py`
- `backend/scripts/export_daily_pipeline_outputs.py`
- `backend/scripts/run_batch_pipeline.py`
- `backend/scripts/run_batch_llm_generation.py`
- `backend/scripts/batch_io.py`

数据审计：

- `backend/scripts/audit_plc_dates.py`
- `backend/scripts/audit_evidence_db.py`
- `backend/scripts/classify_experiment_dates.py`

P3：

- `backend/scripts/run_geology_text_extraction.py`

### 3.11 实验目录清单

- `experiments/exp01_twin_full_run/`
- `experiments/exp02_llm_generation_modes/`
- `experiments/exp03_indicator_robustness/`
- `backend/experiments/`：存在，但本次未发现它是主实验入口，建议后续单独核查是否可归档。

### 3.12 Exp02 关键文件

- `experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py`
- `experiments/exp02_llm_generation_modes/README.md`
- `experiments/exp02_llm_generation_modes/prompts/M1_direct_llm_prompt.md`
- `experiments/exp02_llm_generation_modes/prompts/M2_raw_evidence_llm_prompt.md`
- `experiments/exp02_llm_generation_modes/prompts/M3_twin_evidence_pack_llm_prompt.md`
- `experiments/exp02_llm_generation_modes/prompts/M4_full_generation_prompt.md`
- `experiments/exp02_llm_generation_modes/prompts/M4_revision_prompt.md`
- `experiments/exp02_llm_generation_modes/outputs_real_win_15dates_fixed_v31/`
- `experiments/exp02_llm_generation_modes/outputs_real_win_30dates_fixed_v31/`
- `experiments/exp02_llm_generation_modes/outputs_real_win_91dates_fixed_v31/`

### 3.13 Exp03 关键文件

- `experiments/exp03_indicator_robustness/current_indicator_audit.md`
- `experiments/exp03_indicator_robustness/README.md`
- `experiments/exp03_indicator_robustness/indicator_variants.py`
- `experiments/exp03_indicator_robustness/weighting_methods.py`
- `experiments/exp03_indicator_robustness/ranking_metrics.py`
- `experiments/exp03_indicator_robustness/run_exp03_indicator_robustness.py`

### 3.14 文档与论文材料

根目录：

- `README.md`
- `PROJECT_STRUCTURE.md`
- `docs/agent_v2.md`
- `docs/FULL_PROJECT_CODE_REVIEW.md`（本文）

后端文档：

- `backend/README.md`
- `backend/docs/README.md`
- `backend/docs/backend_field_contract.md`
- `backend/docs/method_definition.md`
- `backend/docs/method_calculation_whitepaper.md`
- `backend/docs/method_enhancement.md`
- `backend/docs/metrics_definition.md`
- `backend/docs/scope_and_limitations.md`
- `backend/docs/experiment_scripts.md`
- `backend/docs/paper_writing_context.md`
- `backend/docs/current_backend_system_manual.md`
- `backend/docs/cleanup_audit.md`

Exp02 论文材料：

- `paper_exp02_91days_analysis.md`
- `paper_exp02_section_draft.md`
- `paper_exp02_case_study_draft.md`
- `EXP02_CURRENT_STATUS.md`
- `paper_table_*.csv`
- `quick_plots/`

### 3.15 归档/旧代码/疑似未使用文件

- `backend/_archive/`
- `backend/services/`：当前仍存在目录，已确认有未完全归档残留风险，需要进一步检查是否被 import。
- `backend/data/`
- `backend/parsers/`
- `backend/contracts/`
- `backend/experiments/`
- 根目录 `docs/`：含旧文档和本审计文档。

### 3.16 未完全审计说明

| 目录/内容 | 未完全审计原因 | 可能影响 | 建议后续检查 |
|---|---|---|---|
| `backend/_archive/` | 文件量较大，且明确为历史归档；本次只确认其不应参与主流程 | 若有主流程 import `_archive` 则是严重问题，本次未发现 | 用 `rg "_archive|legacy"` 做一次强制导入检查 |
| `frontend/` | 本次重点是后端方法与实验逻辑，仅确认其不应参与后端公式与实验 | 不影响后端论文方法，但影响演示系统完整性 | 前端另做 UI/API 契约审计 |
| 大量 `outputs*` | 结果文件体量较大；本次读取关键 summary 和论文表格 | 个别 case 文件可能未纳入审计 | 论文定稿前抽查 case/date 原始报告 |
| `backend/services/` | 前序清理后仍有目录残留，需要独立确认 import 状态 | 可能误导读者以为旧 service 仍参与主流程 | 若未使用，下一轮归档 |
| `backend/experiments/` | 与根 `experiments/` 并存，命名容易混淆 | 可能造成实验脚本入口混乱 | 检查是否仍被测试或文档引用 |

---

## 4. 项目目录地图

```text
tbm-report/
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── routes/report.py
│   ├── pipeline/
│   ├── plc/
│   ├── analysis/
│   ├── geology_v2/
│   ├── coupling/
│   ├── twin/
│   ├── evidence_governance/
│   ├── llm/
│   ├── schemas/
│   ├── scripts/
│   ├── tests/
│   ├── docs/
│   └── _archive/
├── frontend/
├── experiments/
│   ├── exp01_twin_full_run/
│   ├── exp02_llm_generation_modes/
│   └── exp03_indicator_robustness/
├── docs/
└── README.md
```

主流程核心目录是 `backend/routes`、`backend/pipeline`、`backend/plc`、`backend/geology_v2`、`backend/coupling`、`backend/twin`、`backend/evidence_governance`、`backend/llm`、`backend/schemas`。  
`experiments/` 是论文实验旁路，不应反向改变主流程。

---

## 5. 主流程调用关系图

### 5.1 API 到 pipeline

```text
backend/app.py
  → register_report_routes(app)

backend/routes/report.py
  GET /api/tbm/health
    → 返回服务状态、主入口说明

  GET /api/tbm/dates
    → list_available_dates()
    → 返回可用 PLC 日期

  POST /api/tbm/report
    → run_daily_report_pipeline(...)
    → 返回 report_text / quality_summary / trace_summary / forward_profile / high_grci_cells / warnings

  POST /api/tbm/report/debug
    → run_daily_report_pipeline(...)
    → 返回完整中间结果、daily_construction_twin、prompt_evidence_pack、quality、trace、method_metrics
```

### 5.2 `run_daily_report_pipeline()` 主链路

文件：`backend/pipeline/daily_report_pipeline.py`

```text
run_daily_report_pipeline(date, use_llm=False, generation_mode=None, ...)
  → normalize_generation_mode(...)
  → load_daily_inputs(date)
      输入：date
      输出：df_plc, evidence_df, plc_path, evidence_path, warnings
      fallback：DATA_ROOT 未设置时使用 legacy auto-detection，并写 CONFIG_WARNINGS

  → analyze_plc_response(df_plc, date, cell_length)
      输出：operation_summary, cluster_summary, gas_summary,
            cell_response_df, current_chainage,
            day_start_chainage, day_end_chainage, warnings

  → _run_geology_branch(...)
      → run_geology_v2_context(..., mode="online", build_report=False)
      输出：raw geology normalized/project/fuse/forward context
      fallback：evidence_df empty 时返回空结果 + warning

  → build_scope_summary(...)
      输入：current_chainage, day_start/end, lookahead_m, local_background_back_m, cell_length
      输出：日报局部范围、daily_review/forward/local_background 边界

  → _rebuild_geology_branch_for_report_scope(...)
      → apply_spatial_relevance_filter(time_valid_df, scope_summary)
      → build_scope_cells(scope_summary)
      → project_evidence_to_cells(cells_df, spatial_df)
      → fuse_geo_states(cells_df, cell_evidence_df, spatial_df)
      → _annotate_geo_states_availability(...)
      → build_forward_profile(...)
      输出：report-scope cells_df, spatial_relevant_evidence_df,
            excluded_evidence_df, cell_evidence_df, geo_states_df, forward_profile

  → build_construction_state_cells(...)
      输入：cells_df + cell_response_df + geo_states_df + cell_evidence_df + normalized_df
      输出：list[ConstructionStateCell]

  → high_grci_cells(...) / priority_cell_groups(...)
      输出：只基于 daily_review 且 GRCI_available 的复核 cell

  → _with_forward_attention_cells(...)
      输出：forward_profile.forward_attention_cells
      注意：只带 GRS / source_trace / forward fields，不带 GRCI

  → build_daily_construction_twin(...)
      输出：DailyConstructionTwin

  → build_evidence_pack_from_twin(...)
      输出：Prompt Evidence Pack

  → build_prompt(prompt_evidence_pack)
  → build_template_report(prompt_evidence_pack)

  → build_twin_state(...)
      输出：兼容旧质量/trace checker 的 twin_state dict

  分支：
    if generation_mode == "template":
        report_text = template_report
    else:
        generate_llm_report(...)
          支持 planner / revision / mock_llm / provider / fallback_report
        若 LLM 失败，fallback 到 template_report，并写 warnings

  → check_report_quality(...)
  → build_report_trace(...)
  → check_twin_boundary_violations(...)
  → _method_metrics(...)
  → DailyReportResult
```

### 5.3 关键 fallback

| 位置 | fallback 行为 |
|---|---|
| `config.py` | `.env` 未设置 `DATA_ROOT` 时走 legacy auto-detection，并加入 `CONFIG_WARNINGS` |
| `load_daily_inputs()` | evidence_db 缺失时使用空 `DataFrame` 并 warning |
| `_run_geology_branch()` | evidence_df 空时返回空 geology branch |
| `_rebuild_geology_branch_for_report_scope()` | report scope cells 空时返回空 geo_states/forward_profile |
| `project_plc_response_to_cells()` | 缺关键列时返回空 cell_response_df，而不是 crash |
| `compute_cell_grci()` | 缺 RAI/PLC 或缺 GRS 时不计算 GRCI，返回 unavailable reason |
| `generate_llm_report()` | LLM/provider/revision/planner 失败时 fallback 到模板报告 |
| Exp02 dry-run | 只检查 provider/date/out-dir，不发送请求，并显式 `api_key_value_logged=False` |
| Exp02 M4 section guard | 修订后缺章时补保底文本/章节，但 v3.1 已尽量避免补回初稿正文 |

---

## 6. 数据流与字段流向表

| 字段 | 来源文件/函数 | 生成逻辑 | 中间传递 | 最终用途 | 进入报告 | 进入 LLM prompt | 风险 |
|---|---|---|---|---|---|---|---|
| `date` | API request / script args | 用户选择或脚本传入 | `load_daily_inputs`、pipeline、exports | 文件读取、报告日期、实验聚合 | 是 | 是 | 日期格式不一致会影响文件查找 |
| `daily_plc_range` | `llm/evidence_pack.py`、`twin/construction_twin.py` | 从 `daily_chainage_raw` / scope 中取 PLC 实测起止和 `daily_advance_m` | Evidence Pack scope | 防止 aligned scope 被写成实际进尺 | 是 | 是 | 必须和 `daily_excavated_scope` 区分 |
| `daily_advance_m` | `plc/response.py` + `evidence_scope.build_scope_summary()` | `day_end_chainage - day_start_chainage` | scope / Evidence Pack / prompt | 实际日推进量 | 是 | 是 | 不应由 cell 对齐范围自行计算 |
| `daily_excavated_scope` | `pipeline/evidence_scope.py` | 10m cell 对齐后的已掘复核范围 | scope / twin / Evidence Pack | daily_review cell 范围 | 可写，但要声明“对齐复核范围” | 是 | E14 风险：误写成实际推进 |
| `current_face` / `current_chainage` | `plc/response.py` | 当日 PLC 最大或导向里程推断 | scope / forward_profile / twin | 前方窗口边界 | 是 | 是 | 里程字段单位/列选择需稳定 |
| `cell_id` | `cell_builder` / `evidence_scope.build_scope_cells` / `cell_response` | `{start}_{end}` 数字 key | 全链路 | cell 索引、Trace | debug 中是 | 是 | 同里程精度变化会影响 join |
| `start_mileage/end_mileage` | cell_start/cell_end | cell 网格边界 | ConstructionStateCell / Twin | 报告复核区段 | 是 | 是 | 注意不是实际推进起止 |
| `RAI` | `plc/cell_response.py` | 施工响应异常/关注启发式指标 | cell_response_df → ConstructionStateCell | GRCI 输入、daily_review 解释 | 是 | 是 | 不是故障概率；stop_ratio 语义有限 |
| `GRS_geo_base` | `geology_v2/fusion_engine.py` | 地质证据融合关注度 | geo_states_df → ConstructionStateCell | GRCI 输入、forward_attention | 是 | 是 | 不是灾害概率 |
| `GRCI` | `coupling/grs_rai_grci.py` | 仅 GRS 与 RAI 可用且 daily_review 时计算 | ConstructionStateCell / Twin / Evidence Pack | high_grci_cells、复核重点 | 是 | 是 | 不能用于 forward，不是风险概率 |
| `high_grci_cells` | `coupling.high_grci_cells()` | daily_review + GRCI_available + 非 forward 排序 top | API / Evidence Pack / exports | 已掘复核高关注 | 是 | 是 | 不得包含 forward_attention |
| `daily_review` | `pipeline/evidence_scope.py` / `role_for_cell()` | 与当日已掘对齐范围重叠的 cell | cell_role | 已掘区段复核 | 是 | 是 | 与实际推进范围概念不同 |
| `forward_attention` | `role_for_cell()` / `build_forward_profile()` | 当前掌子面前方 0-30m 严格 forward cell | forward_profile / Twin | 前方关注提示 | 是 | 是 | 只能用 GRS/source_trace，不用 GRCI |
| `local_background` | `role_for_cell()` | 日报局部背景范围内但非 daily/forward | Twin / Evidence Pack | 背景 context | 可辅助 | 是 | 不能写成当日异常结论 |
| `gas_summary` | `analysis/gas_analysis.py` | CO2/H2S/SO2/NO2/NO/CH4 等统计 | plc_result → twin/pack | 气体监测章节 | 是 | 是 | 单位/报警阈值未必完整 |
| `quality_score` | `report_quality_checker.py` | 100 分起扣分 | quality_summary / experiments | 质量评价 | debug 是 | 否 | 自动指标，不等于人工质量 |
| `grounding_rate` | `report_grounding_checker.py` | grounded_claims / claims | trace/quality | 证据支撑率 | debug 是 | 否 | 受 claim 抽取粒度影响 |
| `unsupported_claims` | grounding checker | 未被 evidence/policy 支撑的 claim | Quality/Trace/Exp02 | 错误统计和 revision feedback | debug 是 | 修订 prompt 是 | 可能有 false positive |
| `numeric_errors` | quality checker | E10 + E14 等数值类错误 | Exp02 summary | 模式对比 | debug 是 | 修订 prompt 是 | 小数/日期/标题切分曾导致误伤 |
| `boundary_total` | twin_boundary_checker | boundary violation count | quality_summary/Exp02 | 边界安全评价 | debug 是 | 修订 prompt 是 | boundary statement 可能被误伤 |
| `E14` | `report_quality_checker.py` | aligned scope 被写成 actual advance | Exp02 numeric stats | 检查范围/进尺误写 | debug 是 | 修订 prompt 是 | 是关键论文安全指标 |
| `revision_feedback` | Exp02 script / `llm_report_generator` | 从 quality/trace/boundary 生成错误反馈 | M4 revision prompt | 自动修订 | 否 | 是 | 反馈太强可能压缩，太弱可能 no-op |
| `final_report` | template 或 LLM final | 模板 / draft / revision / fallback | API / exports / Exp02 | 最终报告 | 是 | 否 | LLM 模式有外部不确定性 |

---

## 7. PLC 处理逻辑

### 7.1 入口

文件：`backend/plc/response.py`  
函数：`analyze_plc_response(df_plc, date, cell_length)`

调用：

- `analysis.plc_quality_checker.check_plc_quality`
- `analysis.dataprocess.annotate_operation_mode`
- `analysis.dataprocess.annotate_routine_ring_building_stops`
- `analysis.dataprocess.compute_stats`
- `analysis.dataprocess.build_operation_context`
- `analysis.excavation_state.detect_excavation_state`
- `analysis.excavation_state.excavation_state_segments`
- `analysis.excavation_state.excavation_state_efficiency`
- `analysis.excavation_state.build_cluster_context`
- `analysis.gas_analysis.compute_gas_stats`
- `analysis.gas_analysis.build_gas_context`
- `plc.cell_response.project_plc_response_to_cells`

输出：

- `operation_summary`
- `cluster_summary`
- `gas_summary`
- `cell_response_df`
- `current_chainage`
- `day_start_chainage`
- `day_end_chainage`
- `warnings`

### 7.2 cell_response 聚合

文件：`backend/plc/cell_response.py`

主要字段：

- `speed_mean`
- `thrust_mean`
- `torque_mean`
- `rpm_mean`
- `penetration_mean`
- `stop_duration_min`
- `stop_ratio`
- `abnormal_ratio`
- `speed_drop_score`
- `torque_volatility_score`
- `speed_volatility_score`
- `RAI`
- `working_sample_count`
- `working_ratio`
- `working_speed_cv`
- `working_thrust_cv`
- `working_torque_cv`
- `cutterhead_power_proxy`
- `thrust_per_penetration`
- `torque_per_penetration`

working-only 规则：

```text
速度 > 0
推力 > 0
扭矩 > 0
刀盘实际转速 > 0
如果存在 is_working，则还要求 is_working == True
```

样本不足阈值：

```text
MIN_WORKING_SAMPLE_COUNT = 20
```

### 7.3 RAI 公式

```text
RAI = 0.40 * stop_ratio
    + 0.25 * abnormal_ratio
    + 0.20 * speed_drop_score
    + 0.10 * torque_volatility_score
    + 0.05 * speed_volatility_score
```

组件：

| 组件 | 公式 |
|---|---|
| `stop_component` | `0.40 * stop_ratio` |
| `abnormal_component` | `0.25 * abnormal_ratio` |
| `speed_drop_component` | `0.20 * speed_drop_score` |
| `torque_component` | `0.10 * torque_volatility_score` |
| `speed_volatility_component` | `0.05 * speed_volatility_score` |

语义边界：

- RAI 是施工响应关注度，不是设备故障概率。
- `stop_ratio` 权重较高，但当前 PLC 字段未区分计划停机与非计划停机。
- `cutterhead_power_proxy` 是 proxy，不是真实物理功率。
- `thrust_per_penetration`、`torque_per_penetration` 是负载—贯入关系 proxy，不是严格比能或地质强度。

---

## 8. 地质证据处理逻辑

### 8.1 geology_v2 入口

文件：`backend/geology_v2/pipeline.py`  
函数：`run_geology_v2_context(...)`

主步骤：

```text
normalize_evidence_df
→ filter_available_evidence(mode="online")
→ deduplicate_hsp_anomaly_points
→ build_chainage_cells / build_scope_cells
→ project_evidence_to_cells
→ fuse_geo_states
→ build_forward_profile
```

注意：主日报 pipeline 先运行一次 `run_geology_v2_context()` 获得 time-valid evidence，然后用 `pipeline/evidence_scope.py` 重建日报局部 scope，再重新 project/fuse。最终日报主范围不是全局 157 个 geo cell，而是 report-scope cells。

### 8.2 时间可用过滤

文件：`backend/geology_v2/evidence_normalizer.py`  
函数：`filter_available_evidence(...)`

主要目的：

- 防止报告日期之后形成的 evidence 进入日报。
- 防止当前掌子面之后才形成的掌子面素描泄漏。
- online 模式下，未来 evidence 不参与 Evidence Pack。

### 8.3 空间相关筛选

文件：`backend/pipeline/evidence_scope.py`

关键函数：

- `build_scope_summary()`
- `apply_spatial_relevance_filter()`
- `build_scope_cells()`
- `role_for_cell()`

Evidence roles：

| 角色 | 含义 | 报告用途 |
|---|---|---|
| `daily_review` | 当日已掘 cell 对齐范围 | 已掘区段地质-施工响应复核 |
| `forward_attention` | 当前掌子面前方 0-30m | 前方地质关注提示 |
| `local_background` | 局部背景证据 | 背景说明，不作当日结论 |
| `excluded_by_distance` | 距日报范围过远 | 不进入 Evidence Pack 主链路 |
| `excluded_by_missing_geometry` | 几何缺失 | 不进入空间融合 |

### 8.4 GRS 公式

文件：`backend/geology_v2/fusion_engine.py`

```text
GRS_geo_base = 0.45 * grade_score_component
             + 0.45 * hazard_component
             + 0.10 * confidence_component
```

其中：

- `grade_score_component`：围岩等级关注分。
- `hazard_component`：主要 hazard scores 的组合，代码中使用 `0.75 * max_hazard_score + 0.25 * avg_hazard_score`。
- `confidence_component`：融合置信度。

语义边界：

- GRS 是地质证据关注度，不是灾害概率。
- GRS=0 不能自动解释成“低风险”，必须看 `GRS_available`。
- 没有空间相关地质证据时，`GRS_available=False`，reason 为 `missing_spatial_relevant_geology_evidence`。

---

## 9. Evidence Role 划分逻辑

文件：`backend/pipeline/evidence_scope.py`

当前设计的关键点：

1. `daily_plc_range` 表示 PLC 实测当日推进范围。
2. `daily_excavated_scope` 表示 10m cell 对齐后的已掘复核范围。
3. `forward_attention` 使用当前掌子面前方严格 forward cell。
4. `local_background` 用于局部背景，不直接作为当日异常结论。

风险：

- `daily_excavated_scope` 命名容易被 LLM 或作者误解为实际掘进范围，已通过 E14 和 prompt 约束缓解。
- `local_background` 如果进入报告正文，需要非常谨慎，不能写成当日揭露事实。

---

## 10. ConstructionStateCell 逻辑

定义：`backend/schemas/pipeline.py::ConstructionStateCell`  
构建：`backend/coupling/grs_rai_grci.py::build_construction_state_cells`

输入：

- `cells_df`
- `cell_response_df`
- `geo_states_df`
- `cell_evidence_df`
- `normalized_evidence_df`
- `scope_summary`

核心字段分类：

| 类别 | 字段 |
|---|---|
| 空间位置 | `cell_id`, `cell_start`, `cell_end`, `cell_center`, `cell_role` |
| PLC 响应 | `has_plc_response`, `plc_metrics`, `speed_mean`, `thrust_mean`, `torque_mean`, `RAI`, RAI components |
| PLC enhanced | `working_sample_count`, `working_ratio`, `working_*_cv`, `penetration_mean`, `cutterhead_power_proxy`, `thrust_per_penetration`, `torque_per_penetration` |
| 地质 | `has_geology_evidence`, `GRS_geo_base`, `GRS_available`, `main_hazards`, `hazard_scores`, `source_trace` |
| 证据解释性 | `evidence_overlap_length`, `evidence_overlap_ratio`, `max_overlap_ratio`, `mean_overlap_ratio`, `source_reliability`, `trace_completeness` |
| 耦合 | `GRCI`, `GRCI_available`, `GRCI_source`, `GRCI_unavailable_reason`, `coupling_level`, `coupling_explanation` |
| 前方 | `is_current_face_cell`, `is_forward_cell`, `distance_to_face_m`, `forward_distance_band`, `forward_distance_weight` |
| Trace | `supporting_evidence_ids`, `trace_refs`, `source_trace` |

---

## 11. DailyConstructionTwin 逻辑

定义：`backend/schemas/twin.py::DailyConstructionTwin`  
构建：`backend/twin/construction_twin.py::build_daily_construction_twin`

结构：

- `scope`
- `cells`
- `daily_review_cells`
- `forward_attention_cells`
- `local_background_cells`
- `high_grci_cells`
- `summaries`
- `trace_index`
- `governance`

`TwinCellView` 将一个 `ConstructionStateCell` 拆为：

- `position_state`
- `operation_state`
- `response_state`
- `geology_state`
- `forward_state`
- `gas_state`
- `coupling_state`
- `quality_state`
- `trace_state`

边界保护：

- forward_attention cell 在 twin 中会把 `GRCI` 置空，`GRCI_available=False`。
- `coupling_state.boundary` 明确 GRCI 是已掘复核指标，不是灾害概率。
- `response_state.proxy_boundary` 明确 PLC enhanced metrics 是 proxy。

---

## 12. RAI / GRS / GRCI 完整公式

| 名称 | 公式/规则 | 权重/阈值 | 文件 | 函数 | 主流程使用 | 论文风险 |
|---|---|---|---|---|---|---|
| RAI | `0.40*stop_ratio + 0.25*abnormal_ratio + 0.20*speed_drop_score + 0.10*torque_volatility_score + 0.05*speed_volatility_score` | 0.40/0.25/0.20/0.10/0.05 | `plc/cell_response.py` | `project_plc_response_to_cells()` | 是 | 权重启发式，stop_ratio 语义有限 |
| working CV | `std / mean` | `MIN_WORKING_SAMPLE_COUNT=20` | `plc/cell_response.py` | `_safe_cv()` | 是 | 样本不足时为空，不能过度解释 |
| cutterhead_power_proxy | `torque * rpm` 类 proxy | 仅 torque/rpm >0 | `plc/cell_response.py` | `_working_only_metrics()` | 是 | 不是实际功率，缺单位换算 |
| thrust_per_penetration | `thrust / penetration` proxy | penetration>0 | `plc/cell_response.py` | `_working_only_metrics()` | 是 | 不是严格物理比能 |
| torque_per_penetration | `torque / penetration` proxy | penetration>0 | `plc/cell_response.py` | `_working_only_metrics()` | 是 | 单位需谨慎 |
| GRS | `0.45*grade + 0.45*hazard + 0.10*confidence` | 0.45/0.45/0.10 | `geology_v2/fusion_engine.py` | `_grs_geo_base_components()` | 是 | 不是灾害概率 |
| hazard_component | `0.75*max_hazard + 0.25*avg_hazard` | 0.75/0.25 | `geology_v2/fusion_engine.py` | `_grs_geo_base_components()` | 是 | hazard 权重启发式 |
| confidence_score | `evidence_factor = min(1.0, 0.50 + 0.10 * evidence_count)` 等 | 0.50/0.10 | `geology_v2/fusion_engine.py` | `_confidence_score()` | 是 | 证据数量与置信度关系为规则化假设 |
| GRCI | `0.55*GRS + 0.35*RAI + 0.10*GRS*RAI` | 0.55/0.35/0.10 | `coupling/grs_rai_grci.py` | `compute_cell_grci()` | 是 | 不是灾害概率，权重启发式 |
| GRCI high | `>=0.75` | 0.75 | `coupling/grs_rai_grci.py` | `classify_grci()` / priority groups | 是 | 阈值来源需解释为工程分级 |
| GRCI medium | `>=0.50` | 0.50 | 同上 | 同上 | 是 | 同上 |
| GRCI low | `>=0.25` | 0.25 | 同上 | 同上 | 是 | 同上 |
| forward distance band | 0-10m / 10-20m / 20-30m | weights 1.0/0.7/0.4 | `coupling/grs_rai_grci.py` | `_forward_distance_band()` | 是 | 只能表示前方关注层级 |
| Evidence selection daily_review | GRCI/GRS/trace/reliability 等加权 | 见 `evidence_pack.py` | `llm/evidence_pack.py` | `_selection_score()` | 是 | selection_score 不是风险 |
| Evidence selection forward | `0.45*GRS + 0.25*forward_distance_weight + 0.20*evidence_confidence + 0.10*trace_completeness`，可用项重归一 | 0.45/0.25/0.20/0.10 | `llm/evidence_pack.py` | `_selection_score()` / `_twin_selection_score()` | 是 | 明确不使用 GRCI |
| Quality score | 100 起扣分 | forbidden 15, warning 5, missing section 3, low grounding 10, grounding<0.6 扣20 | `report_quality_checker.py`, `quality_checker_policy.json` | `_score_from_violations()` | 是 | 自动分数不是人工评分 |
| grounding_rate | `grounded_claim_count / claim_count` | 无 | `report_grounding_checker.py` | `check_claim_grounding()` | 是 | 受 claim 抽取影响 |
| E14 | aligned scope 被写成实际进尺/推进范围 | 规则匹配 | `report_quality_checker.py` | `_is_aligned_scope_as_actual_advance()` | 是 | 关键安全规则 |
| Boundary | regex 匹配 GRCI probability / forward fact / PLC proxy misuse 等 | 正则规则 | `twin_boundary_checker.py` | `check_twin_boundary_violations()` | 是 | 存在边界声明句误伤可能 |
| Exp02 revision reduction | `(pre - post) / pre`，实际用 unsupported+boundary | 无 | `run_exp02_llm_generation_modes.py` | `_reduction_rate()` | 实验 | 数值依赖 checker 口径 |
| Exp03 V1 | `0.5*RAI + 0.5*GRS` | 0.5/0.5 | `indicator_variants.py` | `compute_indicator_variants()` | 旁路 | 不改变主流程 |
| Exp03 V2/V3/V4 | `sqrt(RAI*GRS)*C` | C 为 coupling confidence | `indicator_variants.py` | `_interaction_grci()` | 旁路 | C 构造为启发式 |
| Exp03 V5 | `min(RAI, GRS)*C` | 严格耦合 | `indicator_variants.py` | `compute_indicator_variants()` | 旁路 | 仅敏感性分析 |

---

## 13. Evidence Pack 构建逻辑

文件：`backend/llm/evidence_pack.py`

当前主流程使用：

```text
build_evidence_pack_from_twin(...)
```

而不是旧的散乱字段拼接。Evidence Pack 主要包含：

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
- `evidence_governance`

证据分层：

- `daily_review_evidence`
- `forward_attention_evidence`
- `background_context_evidence`

字段契约：

- `geology_evidence.key_cells` 是正式字段。
- `geology_evidence.selected_cells` 是兼容字段，内容应与 key_cells 保持一致。
- grounding checker 优先读取 `key_cells`，fallback 到 `selected_cells`。

安全边界：

- daily_review 可使用 RAI/GRS/GRCI。
- forward_attention 只能使用 GRS/source_trace/forward distance，不使用 RAI/GRCI/PLC enhanced。
- local_background 只作背景，不作当日异常结论。
- `cutterhead_power_proxy` 等 proxy 带解释边界。

---

## 14. LLM 生成链路

### 14.1 主 pipeline LLM

文件：`backend/llm/llm_report_generator.py`

支持模式：

- `template`
- `evidence_pack_llm`
- `evidence_pack_llm_with_revision`
- `planned_evidence_pack_llm_with_revision`

主要逻辑：

```text
normalize_generation_mode
→ optional planner: generate_report_plan / validate_report_plan
→ build generation prompt
→ provider.generate()
→ clean_llm_report_text()
→ quality / trace evaluation
→ optional revise_llm_report()
→ fallback template_report if provider/revision fails
```

清洗规则包括删除对话式开场，例如：

- “好的，遵照您的指示”
- “好的，以下是”
- “遵照您的要求”

### 14.2 Provider

文件：`backend/llm/llm_provider.py`

支持：

- mock provider
- OpenAI-compatible provider
- 环境变量：`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`

风险：

- provider 配置错误会 fallback，但真实 LLM 输出不可完全复现。
- API key 不应打印；Exp02 dry-run 明确 `api_key_value_logged=False`。

### 14.3 Planner

文件：`backend/llm/llm_report_planner.py`

规则：

- forward section 不能允许 RAI/GRCI。
- plan 必须包含 GRCI 非概率边界。
- plan 必须包含 forward 非事实边界。
- plan 必须包含 aligned scope 边界。

Fallback：

- 解析失败或验证失败时可使用 rule-based plan。

---

## 15. Quality / Trace / Boundary 检查

### 15.1 Claim extraction

文件：`backend/llm/report_claim_extractor.py`

作用：

- 将报告文本拆成轻量规则 claim。
- 判断 claim type、空间范围、方法边界句。
- 过滤标题、表格分隔符等非技术 claim 的部分逻辑在 trace/quality 中实现。

风险：

- 中文标点、编号、小数、日期、表格会影响切分。

### 15.2 Grounding checker

文件：`backend/llm/report_grounding_checker.py`

支持来源：

- `geology_evidence.key_cells`
- `geology_evidence.selected_cells`
- forward segments/cells
- gas summary
- operation evidence
- cluster evidence
- coupling evidence
- policy/method boundary support

support_type：

- `observed_evidence`
- `prediction_evidence`
- `policy_support`
- `operation_evidence`
- `gas_evidence`
- `coupling_evidence`
- `none`

边界句支持：

- 方法边界句可归为 `policy_support`。
- 停机解释边界句可归为 `policy_support`。

### 15.3 Quality checker

文件：`backend/llm/report_quality_checker.py`

错误类型来自 `report_error_taxonomy.py`：

- `E1_UNSUPPORTED_CLAIM`
- `E2_FORECAST_AS_FACT`
- `E3_GRCI_AS_PROBABILITY`
- `E4_FORWARD_AS_EXCAVATED_REVIEW`
- `E5_BACKGROUND_AS_DAILY_RESPONSE`
- `E6_GAS_FIELD_MISUSE`
- `E7_UNSUPPORTED_RECOMMENDATION`
- `E8_MISSING_REQUIRED_SECTION`
- `E9_SOURCE_ROLE_CONFUSION`
- `E10_NUMERIC_VALUE_UNGROUNDED`
- `E11_HEADING_FALSE_POSITIVE`
- `E12_METHOD_BOUNDARY_STATEMENT`
- `E13_STOP_REASON_OVERINTERPRETATION`
- `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE`

计分：

```text
score = 100
- forbidden / error violation penalty
- warning penalty
- missing section penalty
- low grounding penalty
- grounding_rate < 0.6 时额外扣 20
score >= 0
minimum_ok_score = 80
```

重要风险：

`backend/configs/quality_checker_policy.json` 当前显示为明显乱码（例如 `鐏惧...`），但代码中也存在默认规则和上下文白名单。这个配置文件不一定导致运行失败，但会显著影响可读性和论文复现说明，应作为 P0/P1 风险确认。

### 15.4 Boundary checker

文件：`backend/llm/twin_boundary_checker.py`

检测类型：

- `grci_probability_misuse`
- `forward_fact_misuse`
- `plc_proxy_misuse`
- `stop_causality_misuse`
- `local_background_scope_misuse`

safe boundary statements：

- 明确“不是/不表示/不得写成”等否定语境会被排除为安全边界声明。

---

## 16. 自动修订机制

### 16.1 主 pipeline 修订

文件：

- `backend/llm/llm_report_generator.py`
- `backend/llm/llm_revision.py`
- `backend/llm/prompts/report_revision_prompt.py`

逻辑：

```text
draft report
→ check_report_quality
→ build_report_trace
→ revision prompt
→ LLM revision
→ quality/trace after revision
→ fallback if failed
```

### 16.2 Exp02 M4 修订

文件：`experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py`

M4 是实验版闭环：

```text
initial_report
→ pre_eval quality/trace/boundary
→ build_revision_feedback
→ M4_revision_prompt
→ revised_report
→ section guard
→ post_eval
```

section guard：

- 目标是保留 9 个标准章节。
- v3.1 之前曾出现“补回初稿正文导致 unsupported/numeric 回流”的问题；v3.1 已做最小修复。
- 仍应视为实验脚本级保护，不是工程主 pipeline 核心方法。

---

## 17. 报告输出结构

### 17.1 API 输出

`/api/tbm/report`：

- `date`
- `report_text`
- `quality_summary`
- `trace_summary`
- `forward_profile`
- `high_grci_cells`
- `generation_mode`
- `llm_summary`
- `warnings`

`/api/tbm/report/debug`：

- 普通 report 字段
- `operation_summary`
- `cluster_summary`
- `gas_summary`
- `normalized_evidence_summary`
- `construction_state_cells`
- `prompt_evidence_pack`
- `prompt_text`
- `quality`
- `trace`
- `daily_construction_twin`
- `twin_summary`
- `twin_boundary_summary`
- `method_metrics`
- raw/intermediate evidence records

### 17.2 导出脚本输出

文件：`backend/scripts/export_daily_pipeline_outputs.py`

每日期导出：

- `report.txt`
- `prompt.txt`
- `evidence_pack.json`
- `quality.json`
- `trace.json`
- `construction_state_cells.json/csv`
- `daily_construction_twin.json`
- `twin_summary.json`
- `twin_boundary_summary.json`
- `twin_cell_views.json/csv`
- `forward_profile.json`
- `high_grci_cells.json`
- `method_metrics.json`
- `cell_response_df.csv`
- `geo_states_df.csv`
- `cell_evidence_df.csv`
- LLM plan/draft/revision/final files（LLM 模式下）

---

## 18. Exp02 完整审计

### 18.1 代码路径

文件：`experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py`

模式：

| 模式 | 输入 | 生成方式 | 是否修订 |
|---|---|---|---|
| M0_template_only | 主 pipeline template 报告 | 不调用 LLM | 否 |
| M1_direct_llm | 日期 + 基础统计 | 直接 LLM | 否 |
| M2_raw_evidence_llm | 粗略 PLC/地质/气体/前方摘要 | LLM | 否 |
| M3_twin_evidence_pack_llm | Twin Evidence Pack + governance | LLM | 否 |
| M4_full_twin_governance_trace_boundary_reviser | Twin Evidence Pack + governance + pre-eval feedback | LLM + revision | 是 |

M1 → M2 → M3 → M4 是递进式设计，可作为模块贡献/消融分析；M0 是非 LLM 模板基线。

### 18.2 与主流程关系

- Exp02 调用 `run_daily_report_pipeline(..., generation_mode="template")` 获得 baseline/twin/evidence pack。
- M1-M4 的 prompt 和修订逻辑在实验脚本中构造，不完全等同 `/api/tbm/report` 的普通 LLM 主流程。
- 因此论文要写为“实验生成模式对比脚本”，不要说 M4 完全就是线上 API 默认模式。

### 18.3 Dry-run / real / mock 分支

- `--llm-mode mock`：不调外部 API。
- `--llm-mode real`：构建 provider，按 date/mode 调真实 LLM。
- `--dry-run-real-config`：检查环境变量、输出目录、日期，不发送外部请求，写 `exp02_real_config_dry_run.json`。
- `api_key_value_logged=False` 明确写入 dry-run。

### 18.4 Summary 计算

主要输出：

- `exp02_generation_summary.csv/md`
- `exp02_mode_comparison_summary.csv/md`
- `exp02_revision_effect_summary.csv/md`
- `exp02_overall_summary.json`
- `exp02_boundary_violation_samples.csv`
- `exp02_unsupported_claim_samples.csv`
- `exp02_numeric_error_samples.csv`
- `exp02_failed_runs.csv`

聚合字段：

- `average_quality_score`
- `average_grounding_rate_effective`
- `unsupported_claim_count_effective_total`
- `numeric_error_count`
- `boundary_violation_count_total`
- `missing_sections`
- `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count`
- revision before/after unsupported/boundary

### 18.5 已完成结果

91 天全量：

```text
91 dates × 5 modes = 455 runs
failed_count = 0
```

91 天模式汇总：

| 模式 | 平均质量分 | 证据支撑率 | unsupported | numeric | boundary | E14 | 缺章 |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | 76.00 | 1.0000 | 0 | 0 | 0 | 0 | 273 |
| M1 | 69.99 | 0.7289 | 1129 | 431 | 8 | 0 | 182 |
| M2 | 72.79 | 0.7207 | 1257 | 340 | 30 | 0 | 182 |
| M3 | 72.04 | 0.7653 | 1248 | 185 | 4 | 0 | 188 |
| M4 | 93.02 | 0.9109 | 381 | 92 | 3 | 0 | 0 |

M4 revision：

```text
pre_revision_unsupported_total = 666
post_revision_unsupported_total = 381
reduction_count = 285
reduction_rate = 42.8%
```

15/30/91 稳定性：

| 样本规模 | M4 quality | grounding | unsupported | numeric | E14 | boundary | missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 天 | 96.67 | 0.9093 | 64 | 16 | 0 | 0 | 0 |
| 30 天 | 92.50 | 0.9205 | 118 | 22 | 0 | 1 | 0 |
| 91 天 | 93.02 | 0.9109 | 381 | 92 | 0 | 3 | 0 |

### 18.6 论文材料

91 天目录下已有：

- `paper_exp02_91days_analysis.md`
- `paper_exp02_section_draft.md`
- `paper_exp02_case_study_draft.md`
- `EXP02_CURRENT_STATUS.md`
- `paper_table_91days_mode_comparison.csv`
- `paper_table_15_30_91_trend.csv`
- `paper_table_m4_revision_effect.csv`
- `paper_table_m4_improvement_over_baselines.csv`
- `paper_table_boundary_review.csv`
- `paper_table_case_candidates.csv`
- `quick_plots/`

---

## 19. Exp03 完整审计

### 19.1 定位

目录：`experiments/exp03_indicator_robustness/`

目标：

- 不改变主流程。
- 不改变 Exp02。
- 不跑 LLM。
- 只复算指标和排序，评估 RAI / GRS / GRCI 启发式公式的稳健性。

### 19.2 输入

默认读取：

```text
experiments/exp01_twin_full_run/outputs/date_exports/
```

具体读取 `construction_state_cells.json/csv`，合并 91 天 cell。

### 19.3 指标版本

| 版本 | 公式 |
|---|---|
| V0_current | 读取主流程已有 `RAI`, `GRS_geo_base`, `GRCI` |
| V1_percentile_equal | RAI/GRS 子指标分位数标准化，`GRCI=0.5*RAI+0.5*GRS` |
| V2_percentile_interaction | `GRCI=sqrt(RAI*GRS)*C` |
| V3_percentile_entropy | 分位数标准化 + 熵权法，`sqrt(RAI*GRS)*C` |
| V4_percentile_critic | 分位数标准化 + CRITIC 权重，`sqrt(RAI*GRS)*C` |
| V5_strict_min | `GRCI=min(RAI, GRS)*C` |

`C` / coupling confidence：

- 由可用的 `max_overlap_ratio`、`evidence_overlap_ratio`、`trace_completeness`、`source_reliability`、`evidence_confidence` 等字段求平均。
- 缺失时填充为 1。
- 这是旁路敏感性分析的启发式置信项，不进入主流程。

### 19.4 比较指标

- Top-10 / Top-20 / Top-50 Jaccard overlap
- Spearman rank correlation
- high attention date overlap
- high_grci_cell_comparison
- forward_grci_leakage_check

### 19.5 已知结果

数据规模：

```text
91 dates
1264 cells
175 eligible daily_review cells
```

V0 与变体的排序相似性：

| 变体 | Spearman |
|---|---:|
| V1 | 0.9317 |
| V2 | 0.8772 |
| V3 | 0.8787 |
| V4 | 0.8886 |
| V5 | 0.8168 |

TopK Jaccard with V0：

| 变体 | Top10 | Top20 | Top50 |
|---|---:|---:|---:|
| V1 | 0.538 | 0.667 | 0.724 |
| V2 | 0.429 | 0.538 | 0.538 |
| V3 | 0.429 | 0.538 | 0.538 |
| V4 | 0.429 | 0.538 | 0.587 |
| V5 | 0.250 | 0.333 | 0.429 |

forward leakage：

```text
所有变体 forward_cell_with_grci_count = 0
```

解释：

- 当前 V0 与非主观权重/交互/熵权/CRITIC 版本总体排序相关较高，说明 V0 具有一定稳健性。
- 但 Top-10 高关注 cell 对公式形式较敏感，尤其 V5 严格耦合差异较大。
- 论文应写为“指标稳健性/敏感性分析”，不应写成“权重已被验证最优”。

---

## 20. 未使用代码与重复逻辑

| 文件/函数 | 当前状态 | 主流程调用 | 实验调用 | 建议保留 | 建议归档 | 原因 |
|---|---|---:|---:|---:|---:|---|
| `backend/_archive/` | 历史归档 | 否 | 否 | 否 | 已归档 | 不应从主流程 import |
| `backend/services/` | 清理后仍残留目录 | 未确认 | 未确认 | 待定 | 待定 | 可能是旧 service 残留，需要 import 检查 |
| `backend/geology_v2/coupling_adapter.py` | 旧/兼容耦合 adapter | 主日报不直接调用 | 可能被调试/旧文档引用 | 可保留为参考 | 可考虑归档 | 内含旧 GRCI 公式，易与当前 cell-level 耦合混淆 |
| `backend/geology_v2/report_context_builder.py` / `report_renderer.py` | geology_v2 自带报告上下文 | 主日报 pipeline `build_report=False` | 可能旧调试 | 可保留 | 可归档候选 | 当前主报告从 Evidence Pack 生成 |
| `backend/geology_text/` | P3 sidecar | 否 | P3 脚本 | 保留 | 否 | 明确旁路候选证据模块 |
| `backend/twin/interpretation.py` | Twin 解释辅助 | 未见主流程调用 | 可能可用于调试 | 保留 | 否 | 与 Twin 方法解释有关 |
| `backend/twin/query.py` | 查询工具 | 未见主流程调用 | 可能实验/调试 | 保留 | 否 | 小工具，不影响主流程 |
| `backend/experiments/` | 名称与根 experiments 重复 | 未确认 | 未确认 | 待定 | 待定 | 容易误导，建议单独核查 |
| Exp02 prompt logic vs 主 LLM prompt | 双套生成逻辑 | 主流程不用 Exp02 prompts | Exp02 使用 | 保留 | 否 | 论文实验需要，但文档要说明不是 API 默认模式 |
| Quality checker 与 Boundary checker | 有部分重叠规则 | 是 | 是 | 保留 | 否 | 两者职责不同，但规则重叠需维护一致 |

---

## 21. 分支逻辑与 fallback 审计

| 场景 | 文件/函数 | 行为 | 风险 |
|---|---|---|---|
| 缺 PLC 文件 | `utils/io_utils.py`, `pipeline/inputs.py` | 文件读取失败会异常或 warning，脚本捕获后记录 failed | 批量实验需保留 error log |
| 缺 evidence_db | `pipeline/inputs.py` | 空 evidence_df + warning | 报告仍能跑，但 GRS 不可用 |
| 缺地质空间证据 | `daily_report_pipeline._annotate_geo_states_availability` | `GRS_available=False`, reason `missing_spatial_relevant_geology_evidence` | 不能把 GRS=0 写成低风险 |
| 缺 PLC response | `compute_cell_grci()` | GRCI=None, reason `missing_plc_response` | forward/background 不应有 GRCI |
| gas 缺字段 | `analysis/gas_analysis.py` | 多数统计为空或 0，仍生成 gas_summary | 需要在报告中避免无根据报警结论 |
| LLM 调用失败 | `llm_report_generator.generate_llm_report` | fallback template_report + warning | 可用性好，但 LLM 实验需区分 fallback |
| Planner 失败 | `llm_report_planner` / generator | rule-based plan fallback | 不能说所有 plan 都来自 LLM |
| Revision 失败 | `llm_revision.py` / generator | 保留 draft 或 fallback | revision 效果需记录 applied |
| Exp02 单 run 失败 | `run_exp02_llm_generation_modes.py` | 写 failed_runs，继续其他 date/mode | 适合批量实验 |
| Exp02 dry-run | 同上 | 不发送外部请求 | 安全 |
| API key | `llm_provider.py`, Exp02 dry-run | dry-run 不打印 key | 仍需人工避免日志打印 env |
| checker 缺章 | quality checker | E8 + 扣分 | 标题格式识别仍可能影响分数 |

---

## 22. 代码真实逻辑 vs 论文可讲逻辑

| 模块 | 代码真实逻辑 | 论文可讲逻辑 | 不能这样讲 | 原因 |
|---|---|---|---|---|
| ConstructionStateCell | DataFrame join 后的 Pydantic cell 对象 | 统一里程单元状态表达 | 不能说是物理仿真单元 | 没有 TBM 物理仿真 |
| DailyConstructionTwin | cell view + governance + trace index | 日尺度施工状态数字孪生底座 | 不能说实时数字孪生完整闭环控制 | 当前是日尺度证据 twin |
| Evidence Pack | 从 Twin 选择 key cells / evidence roles / constraints | 证据治理后的 LLM 认知输入 | 不能说 LLM 直接读取全量原始数据 | LLM 只消费结构化包 |
| RAI | PLC 响应启发式分数 | 施工响应关注度 | 不能说异常原因概率 | 停机原因不可区分 |
| GRS | 地质证据融合启发式分数 | 地质证据关注度 | 不能说灾害概率 | 无灾害标签 |
| GRCI | 已掘 cell 的 GRS/RAI 耦合关注度 | 已掘复核优先级 | 不能说前方风险概率 | 仅 daily_review 且需 RAI |
| Planner | 生成/验证报告章节约束 | 报告结构规划 | 不能说工程决策规划器 | 只是文本结构约束 |
| Generator | Template 或 LLM 文本生成 | 证据约束报告生成 | 不能说 LLM 判断地质风险 | 风险来自 Evidence Pack 指标 |
| Quality | 规则 + grounding 检查 | 自动质量核验 | 不能说等同专家评价 | 自动规则有误伤 |
| Trace | claim 与 evidence/policy 匹配 | 可追溯核验 | 不能说完全语义理解 | 规则/字段匹配为主 |
| Boundary | 正则/规则边界检查 | 工程表达安全约束 | 不能说完全消除越界 | 91 天仍有 3 条 boundary |
| Reviser | LLM 根据反馈改写 | 质量反馈修订闭环 | 不能说保证无错误 | 修订仍可能残留 unsupported |
| Exp02 | 五模式真实 LLM 对比 | 生成模式对比与递进式消融 | 不能说跨工程验证 | 只基于本工程 91 天 |
| Exp03 | 指标变体旁路复算 | 指标稳健性/敏感性分析 | 不能说证明 V0 最优 | 无标签/专家标定 |

---

## 23. 论文表述风险

1. “灾害概率”风险：GRCI/GRS 不能写成灾害概率或风险概率。
2. “前方预测”风险：forward_attention 只提示关注，不代表已发生事实，不使用 GRCI。
3. “实际进尺”风险：`daily_excavated_scope` 不是实际推进范围，实际推进只能来自 `daily_plc_range`/`daily_advance_m`。
4. “停机异常原因”风险：`stop_ratio` 不能直接解释为异常停机原因。
5. “真实功率/比能”风险：`cutterhead_power_proxy` 等是 proxy，不是严格物理量。
6. “自动评价等同人工评价”风险：quality/trace/boundary 是规则评价，不替代人工复核。
7. “跨工程泛化”风险：当前 91 天是本工程可用日期全量，不代表跨工程验证。
8. “权重已标定”风险：RAI/GRS/GRCI 权重是启发式，Exp03 只能支持稳健性分析。

---

## 24. 疑点清单

| 疑点 | 涉及文件 | 为什么不确定 | 可能影响 | 建议如何确认 |
|---|---|---|---|---|
| `quality_checker_policy.json` 显示乱码 | `backend/configs/quality_checker_policy.json` | 文件内容疑似编码损坏 | forbidden terms / section titles 可读性和复现风险 | 检查实际读取后规则是否 fallback；重写为 UTF-8 中文 |
| `backend/services/` 是否仍被引用 | `backend/services/` | 清理后目录仍在 | 可能残留旧主链路概念 | `rg "from services|import services"` |
| `backend/experiments/` 与根 `experiments/` 关系 | `backend/experiments/` | 命名重复 | 实验入口混乱 | 列出目录内容并检查引用 |
| GRS 置信度公式来源 | `geology_v2/fusion_engine.py` | evidence_factor 等为启发式 | 论文方法合理性 | 在方法章节写明工程规则/敏感性分析 |
| source_reliability 权重来源 | `geology_v2/config.py` | 来源可靠性权重人为设定 | 论文审稿质疑 | 附录列出权重表，说明依据和边界 |
| RAI stop_ratio 权重 | `plc/cell_response.py` | 停机原因不可区分 | 可能被质疑为异常解释过强 | 保留 stop boundary，并在论文说明 |
| Exp02 M4 与 API LLM 模式差异 | Exp02 script vs backend llm generator | 实验脚本复刻闭环 | 论文若写“系统默认 M4”会不准确 | 写明为实验模式 |
| Exp03 输入来源 | `experiments/exp01_twin_full_run/outputs/date_exports` | 依赖已有导出而非实时 pipeline | 复现需先生成 Exp01 outputs | README 写清前置 |
| claim 抽取粒度 | `report_claim_extractor.py` | 规则切句 | unsupported 数量受切句影响 | 典型案例人工复核 |
| P3 candidate evidence | `backend/geology_text` | sidecar 存在但不入主链路 | 容易误写为已使用 LLM 结构化地质证据 | 论文中说明旁路候选，未进入正式实验 |

---

## 25. 后续提升优先级

| 优先级 | 问题 | 涉及文件 | 为什么重要 | 建议动作 | 是否需要改代码 |
|---|---|---|---|---|---|
| P0 | 修复/确认 quality policy JSON 乱码 | `backend/configs/quality_checker_policy.json` | 影响 checker 可读性和复现 | 重写 UTF-8 中文配置，并跑测试 | 是 |
| P0 | 明确当前论文实验所用 commit/tag | 全项目 | 当前有未提交改动 | 提交或打 tag，锁定 v3.1 + Exp03 状态 | 否/流程 |
| P0 | 确认 `services/` 残留是否无引用 | `backend/services/` | 防止旧主链路混入 | 只读 import 检查，必要时归档 | 可能 |
| P1 | 梳理 source_reliability / hazard weights 来源 | `geology_v2/config.py` | 审稿会问权重来源 | 文档列权重表，说明启发式 | 不一定 |
| P1 | 将 RAI/GRS/GRCI 权重定位固定为启发式 | docs / paper | 防止过度宣称 | 论文方法章节明确边界 | 否 |
| P1 | Exp02 M4 与主 API LLM 模式差异说明 | Exp02 README / paper | 防止复现实验误解 | 文档注明实验脚本闭环 | 否 |
| P1 | 典型案例人工复核 | Exp02 case files | 自动指标不足 | 做 1 主 1 辅人工复核表 | 否 |
| P2 | 减少 checker 重复规则 | `report_quality_checker.py`, `twin_boundary_checker.py`, `report_policy.py` | 降低维护成本 | 抽统一规则常量 | 是 |
| P2 | 清理 `backend/experiments/` | `backend/experiments/` | 目录混乱 | 确认后归档 | 是 |
| P2 | Exp03 图表与论文表格整理 | Exp03 outputs | 支撑指标稳健性 | 生成论文附表/图 | 否 |
| P3 | 引入监督学习权重标定 | RAI/GRS/GRCI | 当前无标签 | 暂不做，避免臃肿 | 是，但不建议 |
| P3 | 恢复 Agent / 前端大屏 | archived/old modules | 当前论文主线不需要 | 暂不做 | 是，但不建议 |

---

## 26. 最大 10 个风险或疑点

1. `quality_checker_policy.json` 乱码，需要立即确认是否影响实际 section/forbidden 规则。
2. 当前工作区有未提交 Exp02/Exp03 改动，论文复现版本未冻结。
3. RAI/GRS/GRCI 权重均为启发式，不能写成标定模型或概率模型。
4. `daily_excavated_scope` 与实际推进范围概念相近，仍是文本生成的高风险混淆点。
5. `stop_ratio` 高权重但停机原因不可区分，论文必须写边界。
6. Quality/Trace/Boundary 规则有重叠和误伤风险，自动指标不可替代人工评价。
7. Exp02 M4 是实验脚本中的闭环模式，不完全等同主 API 默认生成流程。
8. `geology_v2/pipeline.py` 使用动态函数解析，静态依赖不透明，重构时容易误删。
9. `backend/services/`、`backend/experiments/` 等残留目录可能误导项目结构理解。
10. P3 sidecar 地质文本结构化存在，但未进入正式 evidence_db 和主实验，论文中不要误写。

---

## 27. 最值得优先提升的 10 个点

1. 锁定当前实验版本 commit/tag。
2. 修复质量检查配置乱码并测试。
3. 做 `services/`、`backend/experiments/` 的只读 import 审计。
4. 在论文方法章中明确 RAI/GRS/GRCI 是启发式关注指标。
5. 将 Exp03 作为指标稳健性补充，而不是公式替代。
6. 给 1-2 个 Exp02 case 做人工复核。
7. 梳理 geology_v2 config 权重表作为附录。
8. 文档化 Exp02 M4 实验脚本与主 API 的差异。
9. 减少 Quality/Boundary 规则重复前，先冻结当前 checker 口径。
10. 保持 P3 sidecar，不要接入主链路，避免论文主线发散。

---

## 28. 建议冻结的代码

这些代码与论文当前实验结果强绑定，短期不建议再改：

- `backend/pipeline/daily_report_pipeline.py`
- `backend/pipeline/evidence_scope.py`
- `backend/plc/cell_response.py`
- `backend/coupling/grs_rai_grci.py`
- `backend/twin/construction_twin.py`
- `backend/llm/evidence_pack.py`
- `backend/llm/report_quality_checker.py`
- `backend/llm/report_grounding_checker.py`
- `backend/llm/twin_boundary_checker.py`
- `experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py`
- `experiments/exp02_llm_generation_modes/prompts/`

除非发现 P0 复现 bug，否则不要为了提高指标继续修改。

---

## 29. 建议归档/进一步核查的代码

| 路径 | 建议 |
|---|---|
| `backend/services/` | 优先核查 import；若无引用，归档 |
| `backend/experiments/` | 优先核查用途；与根 `experiments/` 合并或归档 |
| `backend/geology_v2/coupling_adapter.py` | 若仅旧链路使用，标注 legacy/compat，防止与当前 GRCI 混淆 |
| `backend/geology_v2/report_context_builder.py` / `report_renderer.py` | 若不再用于主报告，文档注明非主链路 |
| `docs/agent_v2.md` | 与当前主线无关，保留为历史/另线文档 |
| `_archive/` | 保持归档，不从主流程 import |

---

## 30. 普通读者版总结

这个项目现在真实做的事情可以理解为四层：

1. **把数据整理成 cell**：PLC 和地质证据都投到 10m 左右的里程单元上。
2. **给 cell 加证据角色**：已掘复核、前方关注、局部背景分开，防止混用。
3. **计算关注指标**：RAI 看施工响应，GRS 看地质证据，GRCI 只看已掘区段的地质—施工响应耦合关注。
4. **让 LLM 在证据约束下写报告**：LLM 不直接判断风险，而是用 Evidence Pack 写报告，再由 Quality/Trace/Boundary 检查和修订。

当前最强的实验结论来自 Exp02：在本工程 91 天可用日期上，完整闭环 M4 比直接 LLM、原始证据 LLM、结构化证据 LLM 更稳定，质量分更高，未支撑表述和数值错误更少，E14 为 0，缺章为 0。但这仍是单工程实验，且自动评价需要人工复核补充。

Exp03 说明：当前 RAI/GRS/GRCI 虽然是启发式公式，但与若干分位数、熵权、CRITIC 和严格耦合变体的排序相关较高，具有一定稳健性；不过 Top-10 cell 对公式形式仍敏感，因此论文不能声称权重最优，只能声称做了稳健性/敏感性分析。

