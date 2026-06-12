# TBM 施工日报生成工作台

本仓库当前整理为一个以后端单主线 pipeline 为核心、配套干净前端工作台的 TBM 施工日报研究原型。

当前有效主线：

```text
backend/routes/report.py
-> backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline
-> ConstructionStateCell
-> Prompt Evidence Pack
-> Report
-> Quality / Trace
```

旧前端、旧论文实验脚本、旧顶层文档和旧后端模块均已归档，不参与当前主流程。

## 当前主目录

```text
tbm-report/
├── backend/      当前有效后端研究原型
├── frontend/     当前有效前端日报生成工作台
├── _archive/     历史材料归档，不参与当前主流程
├── README.md     当前说明
├── .gitignore
└── pytest.ini
```

## 后端主线

当前后端从 PLC 日运行数据和多源地质证据出发，完成：

1. 读取日运行 PLC CSV 与地质证据库；
2. 分析 PLC 工况、聚类施工状态、气体监测和施工响应；
3. 通过 `geology_v2` 完成地质证据标准化、online 过滤、cell 投影和融合；
4. 构建 10m `ConstructionStateCell`；
5. 计算 `GRS_geo_base / RAI / GRCI`；
6. 构建当前掌子面前方 `forward_profile`；
7. 构建 Prompt Evidence Pack；
8. 生成 no-LLM 模板报告或 LLM fallback 报告；
9. 执行 Quality / Trace 核验；
10. 通过 API 或导出脚本输出结果。

详细说明：

- [后端 README](backend/README.md)
- [字段契约](backend/docs/backend_field_contract.md)
- [方法定义](backend/docs/method_definition.md)
- [指标定义](backend/docs/metrics_definition.md)
- [范围与限制](backend/docs/scope_and_limitations.md)
- [目录归档计划](backend/docs/archive_plan.md)

## 前端工作台

当前前端是从头重做的 Vue 3 工作台，位于：

```text
frontend/
```

前端只调用当前后端四个 API：

```text
GET  /api/tbm/health
GET  /api/tbm/dates
POST /api/tbm/report
POST /api/tbm/report/debug
```

页面：

- `/report`：日报生成页；
- `/cells`：高关注区段页；
- `/forward`：前方关注提示页；
- `/debug`：调试与追溯页。

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

构建前端：

```powershell
cd frontend
npm run build
```

## 核心语义

- `ConstructionStateCell` 是当前系统的核心对象。
- `GRS_geo_base` 表示地质证据关注度。
- `RAI` 表示 PLC 施工响应异常度。
- `GRCI` 表示已掘 cell 的地质-施工响应耦合关注度。
- `GRCI` 不是灾害概率。
- `GRCI` 不是前方风险。
- 没有 PLC response 或没有 RAI 的 cell 不计算正式 GRCI。
- forward cell 使用 `forward_profile / GRS_geo_base / source_trace`，不进入 `high_grci_cells`。

## 当前 API

当前只维护以下核心接口：

```text
GET  /api/tbm/health
GET  /api/tbm/dates
POST /api/tbm/report
POST /api/tbm/report/debug
```

旧接口、Agent 接口、旧 `routes/tbm.py` 均已归档，不参与当前主流程。

## 配置后端

复制后端环境变量模板：

```powershell
copy backend\.env.example backend\.env
```

至少配置：

```env
DATA_ROOT=G:/我的云端硬盘/TBM9
USE_LLM=false
```

如果数据目录是只读环境，可设置：

```env
ENSURE_DIRS_ON_IMPORT=false
```

## 运行后端

```powershell
cd backend
uvicorn app:app --reload --port 8000
```

访问：

```text
http://127.0.0.1:8000/docs
```

## 后端回归测试

```powershell
cd backend
python -m pytest tests -q
```

## 多日期 no-LLM smoke test

```powershell
cd backend
python scripts/smoke_test_daily_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out outputs/smoke_summary.json
```

该脚本会输出：

- 当日里程范围；
- cell response 数量；
- `ConstructionStateCell` 数量；
- `GRCI_available` 数量；
- high GRCI cell 数量；
- forward cell 数量；
- Evidence Pack `key_cells` 数量；
- Quality / Trace 指标；
- warnings。

## 导出完整中间结果

```powershell
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

## 归档内容

根目录 `_archive/` 保存历史材料：

- `_archive/old_frontend/`：旧前端工程，仍依赖旧接口和 Agent，不参与当前主线；
- `_archive/root_old_docs/`：旧论文草稿、旧技术路线和旧说明文档；
- `_archive/root_old_experiments/`：旧论文实验脚本；
- `_archive/local_ignored_snapshots/`：本地代码快照，不建议提交到 GitHub。

后端内部 `_archive/` 保存旧后端模块：

- `backend/_archive/legacy_previous/`：旧 Agent、旧 routes、旧 services、旧 geology、旧 segment GRCI、旧 prompt builder 等。

当前主流程禁止从任何 `_archive/` 目录 import 代码。

## 当前边界

当前仓库不做：

- Agent 问答；
- 旧接口兼容；
- 真实外部 LLM 接入；
- TSP/HSP 原始探测信号重新解释；
- TBM 物理仿真数字孪生；
- 地质灾害概率预测；
- 正式论文实验批量评价。

这些能力如需参考历史版本，请查看 `_archive/`。
