# 后端目录清理归档计划

本文档说明本轮目录清理的边界和执行结果。目标是让当前主流程更清晰，同时不删除旧代码、不恢复旧接口、不改变现有单主线 pipeline。

## 1. 当前主流程文件清单

以下文件和目录直接参与当前主流程，必须保留在主目录：

- `app.py`
- `config.py`
- `routes/report.py`
- `pipeline/`
- `plc/`
- `geology_v2/`
- `coupling/`
- `twin/`
- `llm/evidence_pack.py`
- `llm/report_prompt.py`
- `llm/llm_api.py`
- `llm/report_quality_checker.py`
- `llm/report_grounding_checker.py`
- `llm/report_trace_builder.py`
- `schemas/`
- `scripts/smoke_test_daily_pipeline.py`
- `scripts/export_daily_pipeline_outputs.py`
- `tests/test_daily_pipeline_contracts.py`
- `docs/`
- `README.md`
- `.env.example`

当前主入口仍是：

```text
routes.report
-> pipeline.daily_report_pipeline.run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

## 2. 当前主流程依赖清单

静态 import 检查确认，当前主流程仍依赖以下辅助文件或目录，不能归档：

- `analysis/dataprocess.py`
- `analysis/excavation_state.py`
- `analysis/gas_analysis.py`
- `analysis/plc_contract.py`
- `analysis/plc_quality_checker.py`
- `utils/`
- `contracts/`
- `configs/`

说明：

- `plc/response.py` 依赖 `analysis/dataprocess.py`、`analysis/excavation_state.py`、`analysis/gas_analysis.py`、`analysis/plc_quality_checker.py`。
- `plc/cell_response.py` 依赖 `analysis/plc_contract.py`。
- `llm/report_quality_checker.py`、`llm/report_grounding_checker.py`、`llm/report_trace_builder.py` 依赖 `contracts/` 与 `llm/report_policy.py`。
- `geology_v2/` 多个模块依赖 `utils/chainage_utils.py`。

以下目录目前不属于报告主 pipeline，但仍作为证据导入、解析或测试支撑保留在主目录，暂不归档：

- `parsers/`
- `services/`
- `scripts/import_evidence_reports.py`
- `scripts/build_evidence_db.py`
- `tests/test_parsers.py`
- `tests/test_evidence_import_service.py`
- `tests/test_sqlite_storage_service.py`
- `tests/test_dataprocess.py`

风险原因：这些文件仍被当前测试集或证据导入工具 import。贸然移动会破坏测试或数据准备能力。

## 3. 准备归档文件清单

本轮准备归档的内容：

```text
backend/legacy/
```

该目录内包含此前已经从主目录剥离的旧模块：

- 旧 Agent 问答模块；
- 旧 `routes/tbm.py`；
- 旧 `services/tbm_analysis_service.py`、history memory、digital twin 快照服务；
- 旧 `geology/` 融合链路；
- 旧 segment 级 GRCI 分析；
- 旧 prompt builder / summary contract；
- 旧调试脚本和旧测试。

## 4. 为什么可以归档

`backend/legacy/` 当前不被以下主流程 import：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

主流程不应从归档目录 import 任何代码。归档目录仅作为历史参考。

## 5. 移动后新位置

采用统一归档方案：

```text
backend/legacy/
-> backend/_archive/legacy_previous/
```

并新增：

```text
backend/_archive/README.md
```

## 6. 风险提示

- 本轮只移动此前已经形成的旧代码归档目录，不移动当前主流程依赖文件。
- 不移动 `analysis/`，因为 PLC response 主流程仍依赖其中部分文件。
- 不移动 `services/` 和 `parsers/`，因为测试和证据导入工具仍依赖它们。
- 移动后必须运行 `pytest tests -q`、多日期 smoke test 和 export 脚本。
- 移动后必须确认主流程没有 import `_archive/`。

## 7. 执行结果

已执行统一归档：

```text
backend/legacy/
-> backend/_archive/legacy_previous/
```

说明：本轮先尝试使用 `git mv`，但该目录是此前瘦身时已经形成的未跟踪归档目录，Git 报告没有 tracked source 可移动。因此实际移动使用工作区目录移动完成；旧代码没有删除，也没有接回主流程。
