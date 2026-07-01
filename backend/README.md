# TBM 后端研究原型

当前后端是一个面向 TBM 施工状态复核、证据治理、报告生成和可追溯核验的研究原型。它的中心不再只是“日报生成”，而是：

```text
TBM 施工状态数字孪生底座
+ 多源证据治理
+ 大模型可追溯认知接口
```

日报是该底座上的一个输出。主流程仍然稳定为单链路：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> DailyConstructionTwin
-> Evidence Pack
-> Template / Optional LLM
-> Quality / Grounding / Trace / Twin Boundary Check
-> API / Export
```

旧 Agent、旧 `routes/tbm.py`、旧 segment 级 GRCI、旧 history memory 和 `_archive/` 中的历史代码不参与当前主流程。

完整文档入口见：[docs/README.md](docs/README.md)。

代码清理与归档边界见：[docs/cleanup_audit.md](docs/cleanup_audit.md)。其中需要特别注意：`analysis/` 当前仍是 PLC 响应分析依赖，不是可整体归档的旧目录。

## 1. 当前目录说明

参与当前主流程的核心目录：

- `app.py`：FastAPI 应用入口。
- `routes/report.py`：当前保留的 API 路由。
- `pipeline/`：单日主 pipeline、输入读取、scope 构建和输出组织。
- `plc/`：PLC 工况识别、气体统计、施工响应和 cell response。
- `geology_v2/`：正式地质证据标准化、online 过滤、投影、融合和 forward profile。
- `coupling/`：cell 级 RAI / GRS / GRCI。
- `twin/`：`DailyConstructionTwin` 构建、查询和兼容摘要。
- `evidence_governance/`：证据角色、指标边界和 claim 约束规则。
- `llm/`：Evidence Pack、prompt、模板报告、可选 LLM 生成、Quality、Grounding、Trace、Twin Boundary Check。
- `schemas/`：API、pipeline 和 twin schema。
- `scripts/`：smoke test、导出、批量运行、LLM 生成、sidecar 工具。
- `tests/`：回归测试。
- `docs/`：当前有效文档。
- `geology_text/`：P3 旁路式地质文本结构化，只生成候选证据，不进入正式主链路。

归档目录：

- `_archive/`：历史代码，仅作参考。当前主流程禁止从 `_archive/` import。
  - `legacy_previous/`：此前已经归档的旧 Agent、旧 route、旧服务、旧地质链路、旧测试和调试脚本。
  - `legacy_analysis/`：本轮归档的旧分析辅助代码；当前 PLC cell response 以 `plc/cell_response.py` 为准。
  - `legacy_schemas/`：本轮归档的旧 API / CST / twin contract schema；当前 schema 以 `schemas/api.py`、`schemas/pipeline.py`、`schemas/twin.py` 为准。
  - `legacy_services/`：本轮归档的旧 cache、run metadata、twin diff/event/store/builder 服务；当前主流程不依赖这些服务。

## 2. 环境配置

复制 `.env.example` 为 `.env`，至少配置：

```env
DATA_ROOT=G:/我的云端硬盘/TBM9
DATA_DIR=G:/我的云端硬盘/TBM9/TBM9_2023
EVIDENCE_DB_PATH=G:/我的云端硬盘/TBM9/DB/evidence_db.csv
USE_LLM=false
LLM_PROVIDER=
LLM_API_KEY=
```

如果运行环境只读，建议设置：

```env
ENSURE_DIRS_ON_IMPORT=false
```

## 3. 启动 API

```bash
cd backend
uvicorn app:app --reload --port 8000
```

当前 API：

- `GET /api/tbm/health`
- `GET /api/tbm/dates`
- `POST /api/tbm/report`
- `POST /api/tbm/report/debug`

`/api/tbm/report` 示例：

```json
{
  "date": "2023-12-30",
  "use_llm": false
}
```

核心返回：

- `date`
- `report_text`
- `quality_summary`
- `trace_summary`
- `forward_profile`
- `high_grci_cells`
- `generation_mode`
- `llm_summary`
- `warnings`

`/api/tbm/report/debug` 返回完整中间结果，包括：

- `operation_summary`
- `cluster_summary`
- `gas_summary`
- `normalized_evidence_summary`
- `construction_state_cells`
- `daily_construction_twin`
- `twin_summary`
- `twin_boundary_summary`
- `prompt_evidence_pack`
- `prompt_text`
- `quality`
- `trace`
- `forward_profile`
- `high_grci_cells`

## 4. Smoke Test

单日期：

```bash
cd backend
python scripts/smoke_test_daily_pipeline.py --date 2023-12-30 --no-llm
```

多日期：

```bash
python scripts/smoke_test_daily_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out outputs/smoke_summary.json
```

smoke 输出会记录：

- PLC 实测当日里程范围；
- `cell_response_df` 数量；
- `construction_state_cells` 数量；
- `GRCI_available` 数量；
- high GRCI cell 数量；
- forward cell 数量；
- Evidence Pack `key_cells` 数量；
- Quality / Grounding / Trace 指标；
- warnings。

## 5. 导出完整中间结果

```bash
cd backend
python scripts/export_daily_pipeline_outputs.py --dates 2023-12-30,2023-12-28 --no-llm --out-dir outputs/pipeline_exports
```

每个日期会导出：

- `report.txt`
- `prompt.txt`
- `evidence_pack.json`
- `quality.json`
- `trace.json`
- `construction_state_cells.json`
- `construction_state_cells.csv`
- `daily_construction_twin.json`
- `twin_summary.json`
- `twin_boundary_summary.json`
- `twin_cell_views.json`
- `twin_cell_views.csv`
- `forward_profile.json`
- `high_grci_cells.json`
- `method_metrics.json`
- `summary.json`

## 6. LLM 生成模式

默认模式仍为 `template`，不调用外部 LLM。

支持的 `generation_mode`：

- `template`
- `evidence_pack_llm`
- `evidence_pack_llm_with_revision`
- `evidence_pack_planner_llm`
- `evidence_pack_planner_llm_with_revision`

Mock LLM 示例：

```bash
cd backend
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_llm --mock-llm --out-dir outputs/llm_exports
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_planner_llm --mock-llm --enable-planner --out-dir outputs/llm_exports
```

真实 LLM 调用会把 Evidence Pack 派生内容发送到外部模型服务，应在确认数据可外发后再运行。

## 7. 批量运行与实验脚本

```bash
cd backend
python scripts/audit_plc_dates.py --out outputs/audit/plc_dates.json
python scripts/audit_evidence_db.py --out outputs/audit/evidence_db.json
python scripts/classify_experiment_dates.py --out outputs/audit/date_classes.json
python scripts/run_batch_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out-dir outputs/batch_pipeline --continue-on-error
```

批量脚本只调用当前单日 pipeline，不改变单日逻辑。

## 8. P3 旁路地质文本结构化

P3 是独立 sidecar 模块，只输出候选证据，不写入正式 `evidence_db.csv`，不进入日报主链路。

```bash
cd backend
python scripts/run_geology_text_extraction.py --input-file outputs/geology_extraction/sample_geology_text.txt --source-type HSP --mock-llm --out-dir outputs/geology_extraction
```

候选输出必须标记：

- `candidate_only=true`
- `requires_manual_review=true`
- `not_used_by_main_pipeline=true`

## 9. 回归测试

```bash
cd backend
python -m pytest tests -q
```

测试覆盖字段契约、RAI/GRS/GRCI 公式项、Evidence Pack、Quality / Trace、E14 对齐范围误用、批量脚本、P3 sidecar 和 DailyConstructionTwin 架构契约。

## 10. 核心语义边界

- RAI / GRS / GRCI 是启发式关注指标，不是灾害预测模型。
- GRCI 是地质-施工响应耦合关注度，不是灾害概率。
- GRCI 只在已掘复核 `daily_review` cell 中可用；forward cell 不进入 high GRCI。
- `daily_plc_range` 是 PLC 实测推进范围。
- `daily_excavated_scope` 是 10m cell 对齐后的复核范围，不是实际推进量。
- `stop_ratio` 不能直接解释为异常停机原因。
- PLC enhanced proxy 不是严格物理量，也不能单独证明地质异常。
- 当前掌子面前方关注提示只能写成关注/提示，不得写成已揭露事实。
