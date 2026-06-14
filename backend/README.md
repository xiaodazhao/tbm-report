# TBM 日报后端

当前后端是一个面向 TBM 施工日报生成、证据约束报告生成和方法复现实验的研究原型。主流程已经收束为单链路：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report Planner / Generator / Revision
-> Quality / Trace
-> API / Export
```

旧 Agent、旧 `routes/tbm.py`、旧 segment 级 GRCI、旧 history memory 和 `_archive/` 中的历史代码不参与当前主流程。

完整文档入口见：[docs/README.md](docs/README.md)。

## 1. 目录说明

当前主流程相关目录：

- `app.py`：FastAPI 应用入口。
- `routes/report.py`：当前唯一日报 API 路由。
- `pipeline/`：单日主 pipeline、输入读取、输出组织、evidence scope。
- `plc/`：PLC 工况识别、气体统计、施工响应与 cell response 聚合。
- `geology_v2/`：正式地质证据标准化、可用性过滤、投影、融合和 forward profile。
- `coupling/`：cell 级 RAI / GRS / GRCI 计算。
- `twin/`：基于 ConstructionStateCell 的状态摘要。
- `llm/`：Evidence Pack、prompt、模板报告、LLM 生成、planner、revision、Quality、Grounding、Trace。
- `schemas/`：API 与 pipeline 数据结构。
- `scripts/`：smoke test、导出、批量审计、批量运行、LLM 生成、P3 抽取。
- `tests/`：回归测试。
- `docs/`：当前有效文档。
- `geology_text/`：P3 旁路式 LLM 地质文本结构化，只生成候选证据，不进入正式主链路。

归档目录：

- `_archive/`：历史代码和旧流程，仅作参考。当前主流程禁止从 `_archive/` import。

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

如果没有配置 `DATA_ROOT`，系统会尝试旧路径自动探测，并在 pipeline warnings 中提示。生产或只读环境可设置：

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

`/api/tbm/report` 请求示例：

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
- `warnings`

`/api/tbm/report/debug` 返回完整中间结果，包括 operation、gas、normalized evidence、construction cells、Evidence Pack、prompt、quality、trace 等。

## 4. 单日与多日期 smoke test

```bash
cd backend
python scripts/smoke_test_daily_pipeline.py --date 2023-12-30 --no-llm
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
- `forward_profile.json`
- `high_grci_cells.json`
- `warnings.json`
- `summary.json`
- `method_metrics.json`

## 6. LLM 生成模式

默认模式仍为 `template`，不调用外部 LLM。

支持的 `generation_mode`：

- `template`：稳定模板报告，默认模式。
- `evidence_pack_llm`：基于 Evidence Pack 构建约束 prompt，生成 LLM 初稿，再运行 Quality / Trace。
- `evidence_pack_llm_with_revision`：初稿生成后，根据 Quality / Trace 反馈构建 revision prompt 并再次检查。
- `evidence_pack_planner_llm`：先生成结构化 Report Plan，验证后再生成报告。
- `evidence_pack_planner_llm_with_revision`：planner + generator + revision 的完整 LLM 链路。

示例：

```bash
cd backend
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_llm --mock-llm --out-dir outputs/llm_exports
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_planner_llm --mock-llm --enable-planner --out-dir outputs/llm_exports
```

真实 DeepSeek / OpenAI-compatible 调用示例：

```bash
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_planner_llm --provider openai_or_compatible --model deepseek-chat --enable-planner --out-dir outputs/llm_exports
```

真实 LLM 调用会把 Evidence Pack 派生内容发送到外部模型服务，应在确认数据可外发后再运行。

## 7. 批量审计与运行

```bash
cd backend
python scripts/audit_plc_dates.py --out outputs/audit/plc_dates.json
python scripts/audit_evidence_db.py --out outputs/audit/evidence_db.json
python scripts/classify_experiment_dates.py --out outputs/audit/date_classes.json
python scripts/run_batch_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out-dir outputs/batch_pipeline --continue-on-error
```

批量脚本只调用当前单日 pipeline，不改变单日逻辑。

## 8. P3 旁路式地质文本结构化

P3 是独立 sidecar 模块，输出候选地质证据，不写入正式 `evidence_db.csv`，不进入日报主链路。

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

测试覆盖字段契约、RAI/GRS/GRCI 公式项、Evidence Pack 字段、Quality / Trace 分类、E14 对齐范围误用、批量脚本契约和 P3 sidecar 契约。

## 10. 核心语义边界

- `GRCI` 是地质-施工响应耦合关注度，不是灾害概率。
- `GRCI` 只在已掘复核 cell 中可用；forward cell 不进入 high GRCI。
- `daily_plc_range` 是 PLC 实测推进范围。
- `daily_excavated_scope` 是 10m cell 对齐后的复核范围，不能写成实际推进量。
- 当前 PLC 字段未区分计划停机与非计划停机，`stop_ratio` 不能直接解释为异常原因。
- 前方关注提示只能写成关注/提示，不能写成已揭露事实。
