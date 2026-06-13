# TBM 日报后端研究原型

本后端当前只保留一条主流程：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

旧版 Agent、旧 `routes/tbm.py`、旧 segment 级 GRCI、旧 history memory、旧多流程报告链路均不参与当前主流程。

## 当前主流程目录说明

参与当前主流程的核心目录：

- `routes/report.py`：当前唯一报告 API。
- `pipeline/`：日报主 pipeline，入口为 `run_daily_report_pipeline(date, use_llm=False)`，默认 `generation_mode=template`。
- `plc/`：PLC 工况、气体、施工响应和 cell 响应聚合。
- `geology_v2/`：当前唯一地质证据结构化、投影、融合和 forward profile 链路。
- `coupling/`：cell 级 `GRS / RAI / GRCI` 计算。
- `twin/`：由 `ConstructionStateCell` 构建当前孪生状态摘要。
- `llm/`：Evidence Pack、prompt、模板报告、质量检查、grounding 和 trace。
- `schemas/`：API、pipeline、ConstructionStateCell 等数据结构。
- `analysis/`：当前仅保留 PLC response 仍依赖的基础分析函数，不是旧主流程。
- `utils/`、`contracts/`、`configs/`：当前主流程和质量检查使用的辅助定义。
- `scripts/`：smoke test、结果导出和证据导入辅助脚本。
- `tests/`：当前回归测试。
- `docs/`：字段契约、方法定义、指标定义、边界说明和归档计划。

归档目录：

- `_archive/`：历史代码归档，仅作参考，不参与当前主流程。
- 当前主流程禁止从 `_archive/` import 任何内容。

## 配置 DATA_ROOT

复制 `.env.example` 为 `.env`，至少配置：

```env
DATA_ROOT=G:/我的云端硬盘/TBM9
USE_LLM=false
```

也可以显式配置：

```env
DATA_DIR=
EVIDENCE_DB_PATH=
```

如果未设置 `DATA_ROOT`，系统会尝试旧路径自动探测，并在 pipeline warnings 中提示。对于只读数据目录，可以设置：

```env
ENSURE_DIRS_ON_IMPORT=false
```

## 运行 no-LLM smoke test

```bash
cd backend
python scripts/smoke_test_daily_pipeline.py --date 2023-12-30 --no-llm
python scripts/smoke_test_daily_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out outputs/smoke_summary.json
```

输出指标包括：

- 当日里程范围和推进量；
- `cell_response_df` 数量；
- `construction_state_cells` 数量；
- `GRCI_available` 数量；
- high GRCI cell 数量；
- forward cell 数量；
- Evidence Pack `key_cells` 数量；
- grounding、quality、unsupported claim 指标；
- warnings。

## 导出完整中间结果

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

## Evidence Pack 约束 LLM 生成

默认报告生成模式仍然是 `template`，即不调用外部 LLM。LLM 只允许接在 Evidence Pack 之后，用于文本生成和修订，不参与 PLC 处理、地质证据筛选、ConstructionStateCell 构建或 `RAI / GRS / GRCI` 计算。

支持的 `generation_mode`：

- `template`：稳定模板报告，默认模式。
- `evidence_pack_llm`：基于 Evidence Pack 构建约束 prompt，生成 LLM 初稿，并运行 Quality / Trace。
- `evidence_pack_llm_with_revision`：先生成初稿，再根据 Quality / Trace 反馈构建 revision prompt，修订后再次运行 Quality / Trace。

独立脚本：

```bash
cd backend
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_llm --mock-llm --out-dir outputs/llm_exports
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_llm_with_revision --mock-llm --out-dir outputs/llm_exports
```

真实 DeepSeek / OpenAI-compatible 调用使用：

```bash
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_llm --provider openai_or_compatible --model deepseek-chat --out-dir outputs/llm_exports
```

注意：真实 LLM 调用会把 Evidence Pack 派生内容发送到外部模型服务，应在确认数据可外发后再运行。

LLM 审计导出文件包括：

- `llm_mode.json`
- `llm_prompt.txt`
- `llm_request.json`
- `llm_raw_response.txt`
- `llm_report_draft.txt`
- `llm_quality_before_revision.json`
- `llm_trace_before_revision.json`
- `llm_revision_prompt.txt`
- `llm_revision_request.json`
- `llm_revision_response.txt`
- `llm_report_final.txt`
- `llm_quality_after_revision.json`
- `llm_trace_after_revision.json`
- `llm_summary.json`

## 启动 FastAPI

```bash
cd backend
uvicorn app:app --reload --port 8000
```

## 当前 API

### `GET /api/tbm/health`

健康检查。

### `GET /api/tbm/dates`

返回可用 PLC 日运行数据日期。

### `POST /api/tbm/report`

请求示例：

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

### `POST /api/tbm/report/debug`

返回完整中间结果，适合工程调试和论文实验复核：

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

## ConstructionStateCell

`ConstructionStateCell` 是当前系统的核心 cell 对象，定义在 `schemas/pipeline.py`，由 `pipeline/daily_report_pipeline.py` 构建。

它统一承载：

- cell 空间位置：`cell_id`、`cell_start`、`cell_end`、`cell_center`；
- PLC 响应：`has_plc_response`、`plc_metrics`、`RAI`；
- 地质融合：`has_geology_evidence`、`GRS_geo_base`、`main_hazards`、`supporting_evidence_ids`；
- 耦合结果：`GRCI`、`GRCI_available`、`GRCI_source`、`GRCI_unavailable_reason`、`coupling_level`；
- 空间语义：`is_excavated_today`、`is_current_face_cell`、`is_forward_cell`；
- 追溯信息：`source_trace`、`trace_refs`。

重要语义：

- `GRCI` 不是灾害概率；
- `GRCI` 不是前方风险；
- 只有同时存在 `GRS_geo_base`、`RAI` 和 PLC response evidence 时，`GRCI_available=True`；
- 缺少 RAI 的 cell 不计算正式 GRCI；
- forward cell 使用 `GRS_geo_base / forward_profile / source_trace`，不进入 `high_grci_cells`。

## Evidence Pack / Quality / Trace

Evidence Pack 是报告生成的证据约束输入，主要包含：

- `operation_evidence`
- `cluster_evidence`
- `gas_evidence`
- `geology_evidence`
- `coupling_evidence`
- `forward_evidence`
- `source_trace`
- `generation_constraints`

`geology_evidence.key_cells` 是正式字段；`selected_cells` 是短期兼容字段，两者当前内容一致。

Quality / Trace 用于核验报告：

- `quality_score`：报告质量分；
- `grounding_rate`：claim 可被 Evidence Pack 支撑的比例；
- `unsupported_claim_count`：未支撑 claim 数；
- `report_trace`：claim 到 evidence 的追溯结果。

## 当前边界

当前后端不做：

- 前端展示；
- Agent 问答；
- 旧接口兼容；
- 真实外部 LLM 调用；
- TSP/HSP 原始探测信号重新解释；
- TBM 物理仿真数字孪生；
- 地质灾害概率预测；
- 论文实验批量评价。

这些内容如需参考历史代码，请查看 `_archive/`。
