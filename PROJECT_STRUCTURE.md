# 项目结构与归档说明

本文档用于说明当前仓库中哪些目录属于主流程，哪些目录属于实验支撑，哪些目录只是历史归档。整理原则是：不删除旧代码，不从归档目录接回旧逻辑，当前主流程保持清晰可追踪。

## 1. 当前主流程

当前后端主流程为：

```text
backend/app.py
-> backend/routes/report.py
-> backend/pipeline/daily_report_pipeline.py
-> ConstructionStateCell
-> DailyConstructionTwin
-> Evidence Pack
-> Template / optional LLM
-> Quality / Grounding / Trace / Boundary Check
-> API / Export
```

当前主流程不从 `_archive/` 或 `backend/_archive/` import 任何代码。

## 2. 顶层目录

| 目录 | 当前角色 | 是否参与主流程 | 说明 |
|---|---|---:|---|
| `backend/` | 后端主工程 | 是 | FastAPI、pipeline、PLC、地质证据、Twin、Evidence Pack、Quality/Trace、脚本和测试 |
| `frontend/` | 当前前端工作台 | 是，作为展示端 | Vue 3 + Vite + TypeScript，只消费后端新 API |
| `experiments/` | 当前实验体系 | 否，独立调用主流程 | Exp01/Exp02/Exp03 等实验脚本和说明 |
| `_archive/` | 根目录历史归档 | 否 | 旧前端、旧根目录文档、旧实验脚本、本地快照 |
| `outputs/` | 本地运行输出 | 否 | 已在 `.gitignore` 中忽略 |

## 3. 后端核心目录

| 目录 | 当前职责 | 清理建议 |
|---|---|---|
| `backend/routes/` | 只保留当前 API：health、dates、report、report/debug | 保留 |
| `backend/pipeline/` | 单日主流程、输入读取、证据范围筛选 | 保留 |
| `backend/plc/` | PLC 响应分析与 cell 聚合 | 保留 |
| `backend/analysis/` | PLC 质量、工况、气体、基础统计依赖 | 保留，虽然名称像旧模块，但仍被 `plc/response.py` 使用 |
| `backend/geology_v2/` | 正式地质证据处理链路 | 保留 |
| `backend/coupling/` | cell 级 RAI / GRS / GRCI | 保留 |
| `backend/twin/` | DailyConstructionTwin 构建与查询 | 保留 |
| `backend/llm/` | Evidence Pack、prompt、LLM 接口、Quality/Trace/Boundary | 保留 |
| `backend/evidence_governance/` | 证据角色、边界、claim 规则 | 保留 |
| `backend/contracts/` | 字段字典和字段契约 | 保留 |
| `backend/schemas/` | API、pipeline、twin schema | 保留 |
| `backend/scripts/` | smoke、导出、批处理、LLM 生成、P3 工具 | 保留 |
| `backend/tests/` | 回归测试 | 保留 |
| `backend/_archive/` | 后端历史代码归档 | 不参与主流程 |

## 4. 实验目录

| 目录 | 当前用途 | 说明 |
|---|---|---|
| `experiments/exp01_twin_full_run/` | DailyConstructionTwin 全流程批量运行实验 | 脚本和 README 可保留，`outputs*` 为本地结果 |
| `experiments/exp02_llm_generation_modes/` | M0-M4 生成模式对比实验 | 脚本、prompts、README 保留，`outputs*` 为本地结果 |
| `experiments/exp03_indicator_robustness/` | RAI/GRS/GRCI 指标稳健性实验 | 旁路实验，不改主流程、不跑 LLM |

实验输出目录已通过 `.gitignore` 忽略：

```text
experiments/**/outputs*/
```

如果某些论文材料需要长期保留到 Git，建议从输出目录中复制到独立的、轻量的 `paper_materials/` 或 `docs/` 文件夹，而不是直接提交完整输出目录。

## 5. 归档目录

### `_archive/`

根目录历史归档，主要包括：

- 旧前端；
- 根目录旧文档；
- 根目录旧实验脚本；
- 本地快照文件。

### `backend/_archive/`

后端历史归档，主要包括：

- 旧 Agent；
- 旧 `routes/tbm.py`；
- 旧 services；
- 旧 geology 链路；
- 旧 segment 级 GRCI；
- 旧 schema；
- 旧测试和调试脚本。

## 6. 后续清理规则

1. 任何文件移动到归档前，先确认没有被当前主流程、实验脚本或测试 import。
2. 归档使用 `git mv`，不直接删除。
3. 归档目录只作历史参考，不允许主流程从归档目录 import。
4. 大体量运行结果默认不进 Git。
5. 论文需要引用的结果，应整理成轻量 CSV、Markdown 或图表后单独纳入文档目录。
