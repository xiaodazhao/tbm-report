# 后端清理审计记录

本审计用于支持代码瘦身和归档整理。审计结论基于当前静态 import、主流程入口和目录扫描；本轮不删除业务代码，不改变主 pipeline。

## 1. 当前主流程入口

```text
backend/app.py
-> routes/report.py
-> pipeline/daily_report_pipeline.py::run_daily_report_pipeline
-> plc.response.analyze_plc_response
-> geology_v2.pipeline.run_geology_v2_context
-> coupling.grs_rai_grci.build_construction_state_cells
-> twin.construction_twin.build_daily_construction_twin
-> llm.evidence_pack / report_quality_checker / report_trace_builder / twin_boundary_checker
```

## 2. 必须保留在主目录的模块

| 模块 | 保留原因 |
|---|---|
| `app.py` | FastAPI 入口 |
| `routes/report.py` | 当前唯一业务 API |
| `pipeline/` | 单日主流程和证据范围筛选 |
| `plc/` | PLC 响应分析入口和 cell response |
| `analysis/` | 当前 PLC 分析仍依赖质量检查、工况识别、气体分析和字段契约 |
| `geology_v2/` | 当前正式地质证据链路 |
| `coupling/` | ConstructionStateCell 与 RAI/GRS/GRCI |
| `twin/` | DailyConstructionTwin |
| `llm/` | Evidence Pack、模板/LLM 生成、Quality、Trace、Boundary |
| `evidence_governance/` | Twin 证据治理上下文 |
| `contracts/` | claim/grounding 使用的数据字典 |
| `schemas/` | API、pipeline、twin schema |
| `utils/` | 输入读取、里程工具、序列化工具 |
| `scripts/` | smoke/export/batch/LLM/P3 工具 |
| `tests/` | 回归测试 |

## 3. 不应整体归档但需标注用途的目录

| 目录 | 原因 | 建议 |
|---|---|---|
| `backend/analysis/` | 名称像旧模块，但 `plc/response.py` 仍直接依赖 | 保留，并在 README 中说明它是 PLC 基础分析依赖 |
| `backend/services/` | 不进入日报主 pipeline，但 evidence 导入脚本和测试依赖 | 保留为“数据导入/SQLite 工具服务” |
| `backend/parsers/` | 不进入日报运行主线，但 `build_evidence_db.py` 和 evidence import 使用 | 保留为 evidence_db 构建工具 |
| `backend/geology_text/` | P3 sidecar，不进入正式 evidence_db 和日报主链路 | 保留，标注为候选证据旁路模块 |
| `backend/scripts/` | 包含生产 smoke，也包含实验/批处理工具 | 暂不拆分；后续可按 `runtime/experiment/import` 分类 |

## 4. 已归档或正在归档的旧模块

当前后端归档目录为：

```text
backend/_archive/
```

其中包括：

| 归档目录 | 内容 |
|---|---|
| `legacy_previous/` | 旧 Agent、旧 route、旧 services、旧 geology、旧 segment GRCI、旧 prompt、旧测试 |
| `legacy_analysis/` | 旧 PLC cell response 辅助代码 |
| `legacy_schemas/` | 旧 API / CST / twin contract schema |
| `legacy_services/` | 旧 cache、run metadata、twin diff/event/store/builder 服务 |
| `legacy_llm/` | 旧 LLM API 兼容调用封装，当前主流程使用 `llm_provider` / `llm_report_generator` |
| `legacy_utils/` | 旧 API response 与 time-window 工具，当前 report route 不再使用 |
| `legacy_configs/` | 旧 prompt / report 配置，当前活动代码只使用 `configs/quality_checker_policy.json` |

这些内容不参与当前主流程，不应被当前代码 import。

## 5. 可优先清理的非代码噪音

| 位置 | 问题 | 处理建议 |
|---|---|---|
| `experiments/**/outputs*` | 大量实验输出会污染 Git 状态 | 已加入 `.gitignore`，保留本地文件 |
| `outputs/` | pytest 和临时输出 | 已由 `.gitignore` 忽略 |
| `backend/outputs/` | smoke/export 输出 | 已由 `.gitignore` 忽略 |
| `__pycache__/` | Python 缓存 | 已由 `.gitignore` 忽略 |
| `.pytest_cache/` | pytest 缓存 | 已由 `.gitignore` 忽略 |

## 6. 后续可考虑的代码瘦身方向

这些不是本轮直接移动对象，需要逐项验证测试后再处理：

1. 将 `backend/scripts/` 按用途拆为：
   - runtime smoke/export；
   - evidence import；
   - batch experiment；
   - LLM generation；
   - sidecar geology text。
2. 将 `backend/services/` 明确标注为 evidence import / SQLite 工具，不再让人误解为日报主服务层。
3. 将 `backend/geology_v2/pipeline.py` 中的历史注释和乱码注释清理为 UTF-8 中文说明，但不改函数逻辑。
4. 对文档进行一次编码和标题统一，避免中文显示异常。
5. 如果某些旧 experiment outputs 需要提交，应只提交轻量 summary、表格和论文图，不提交完整逐日 prompt/report/trace 大目录。

## 7. 本轮清理边界

本轮只做安全整理：

- 不改 RAI / GRS / GRCI；
- 不改 Evidence Pack；
- 不改 prompt/checker；
- 不改 Exp02 结果；
- 不删除旧代码；
- 不恢复旧接口；
- 不从归档目录接回旧逻辑。
