# TBM 施工日报生成研究原型

本项目是一个面向 TBM 连续掘进过程的施工日报生成研究原型。当前主线不是“直接让大语言模型自由写日报”，而是先把 PLC 运行数据、多源地质证据和报告约束组织成可追溯的结构化证据，再由模板或受约束 LLM 生成、核验和修订日报。

后端完整文档入口：[backend/docs/README.md](backend/docs/README.md)。

项目目录与归档边界说明：[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

## 当前主线

```text
backend/routes/report.py
-> backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline
-> ConstructionStateCell
-> DailyConstructionTwin
-> Prompt Evidence Pack
-> template / evidence_pack_llm / evidence_pack_planner_llm
-> Quality / Trace
-> Report / Export
```

## 当前目录边界

- `backend/`：当前后端主工程。
- `frontend/`：当前轻量日报生成工作台。
- `experiments/`：当前实验体系，包括 Exp01、Exp02、Exp03。
- `_archive/`：根目录旧前端、旧文档、旧实验和本地快照归档。
- `backend/_archive/`：后端旧 route、旧 Agent、旧 services、旧 schema、旧地质链路和旧测试归档。

当前主流程禁止从 `_archive/` 或 `backend/_archive/` import 代码。实验输出目录 `experiments/**/outputs*` 默认作为本地运行结果保存，不再作为 Git 常规提交内容。

## 项目目标

1. 从每日 PLC 数据和正式 `evidence_db.csv` 读取输入；
2. 通过时间合法性和空间相关性筛选地质证据；
3. 在日报局部 10m cell 上构建 `ConstructionStateCell`；
4. 计算 RAI、GRS、GRCI 等工程关注指标；
5. 构建 Prompt Evidence Pack 约束报告生成；
6. 支持 template、Evidence Pack LLM、planner LLM 和 revision 模式；
7. 通过 Quality / Trace / Error Taxonomy 检查报告是否有证据支撑；
8. 支持 91 天数据审计、日期分类、批量 pipeline 和批量 mock LLM 运行；
9. 提供 P3 sidecar 地质文本结构化候选模块，但不接入正式日报主链路。

## 核心文档

- [系统架构与执行路线](backend/docs/system_architecture.md)
- [字段契约](backend/docs/backend_field_contract.md)
- [方法与计算逻辑白皮书](backend/docs/method_calculation_whitepaper.md)
- [LLM 生成模式](backend/docs/llm_generation_modes.md)
- [批量审计与运行](backend/docs/batch_pipeline.md)
- [P3 地质文本结构化旁路模块](backend/docs/geology_text_extraction.md)
- [后续实验规划](backend/docs/experiment_plan.md)
- [论文写作上下文包](backend/docs/paper_writing_context.md)
- [LLM 简版上下文](backend/docs/llm_context_brief.md)

## 后端常用命令

进入后端：

```powershell
cd backend
```

运行测试：

```powershell
python -m pytest tests -q
```

三日期 no-LLM smoke：

```powershell
python scripts/smoke_test_daily_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out outputs/smoke_summary.json
```

完整中间结果导出：

```powershell
python scripts/export_daily_pipeline_outputs.py --dates 2023-12-30,2023-12-28 --no-llm --out-dir outputs/pipeline_exports
```

LLM planner mock：

```powershell
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_planner_llm_with_revision --mock-llm --enable-planner --enable-revision --out-dir outputs/llm_exports
```

数据审计：

```powershell
python scripts/audit_plc_dates.py --out-dir outputs/audit
python scripts/audit_evidence_db.py --out-dir outputs/audit
python scripts/classify_experiment_dates.py --plc-audit outputs/audit/plc_date_audit.csv --evidence-audit outputs/audit/evidence_db_audit.csv --out-dir outputs/audit
```

批量 pipeline：

```powershell
python scripts/run_batch_pipeline.py --date-file outputs/audit/date_classification.csv --class-filter A,B --no-llm --out-dir outputs/batch_pipeline --continue-on-error
```

批量 mock LLM：

```powershell
python scripts/run_batch_llm_generation.py --date-file outputs/audit/date_classification.csv --class-filter A,B --generation-mode evidence_pack_llm_with_revision --mock-llm --enable-revision --out-dir outputs/batch_llm --continue-on-error
```

P3 mock extraction：

```powershell
python scripts/run_geology_text_extraction.py --input-file outputs/geology_extraction/sample_geology_text.txt --source-type HSP --mock-llm --out-dir outputs/geology_extraction
```

## 后端 API

启动：

```powershell
cd backend
uvicorn app:app --reload --port 8000
```

当前外部调用只应使用：

```text
GET  /api/tbm/health
GET  /api/tbm/dates
POST /api/tbm/report
POST /api/tbm/report/debug
```

## 前端

当前前端是一个轻量 TBM 施工日报生成工作台，只消费后端新 API，不计算 GRCI、不处理 PLC 原始数据、不拼 Evidence Pack。

```powershell
cd frontend
npm install
npm run dev
npm run build
```

## 配置

复制模板：

```powershell
copy backend\.env.example backend\.env
```

至少配置：

```env
DATA_ROOT=G:/我的云端硬盘/TBM9
DATA_DIR=G:/我的云端硬盘/TBM9/TBM9_2023
EVIDENCE_DB_PATH=G:/我的云端硬盘/TBM9/DB/evidence_db.csv
USE_LLM=false
```

真实 DeepSeek / OpenAI-compatible 调用必须显式允许外发。不要在未确认数据脱敏和外发许可前把 Evidence Pack 发给外部模型。

## 关键语义边界

- `daily_plc_range` 是 PLC 实测推进范围。
- `daily_excavated_scope` 是 10m cell 对齐后的已掘复核范围，不是实际推进范围。
- `forward_attention` 是当前掌子面前方关注提示，不是已发生事实。
- `GRCI` 是地质-施工响应耦合关注度，不是灾害概率，也不是前方风险。
- 无 RAI 或无 PLC response 的 cell 不计算正式 GRCI。
- P3 是候选证据旁路模块，不进入正式 `evidence_db.csv` 和日报主链路。

## 归档内容

历史前端、旧接口、旧 Agent、旧 segment GRCI、旧实验草稿和旧文档已归档到 `_archive/` 或 `backend/_archive/`，不参与当前主流程。当前主流程禁止从 `_archive/` import。
