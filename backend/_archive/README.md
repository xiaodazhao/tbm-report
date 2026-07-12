# 后端历史代码归档

`_archive/` 只保存历史版本代码和旧实验脚本，不参与当前后端主流程。

根目录也存在 `_archive/`，二者分工如下：

- 根目录 `_archive/`：旧前端、旧根目录文档、旧实验脚本和本地快照。
- `backend/_archive/`：后端旧 route、旧 Agent、旧 services、旧 schema、旧地质链路、旧测试和旧调试脚本。

更完整的当前项目说明见根目录 `PROJECT_FULL_EXPLANATION.md`。

当前主流程仍然是：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

## 目录说明

- `legacy_previous/`：此前瘦身时已经从主目录剥离的旧代码统一归档。
- `legacy_analysis/`：从主目录归档的旧分析辅助代码。目前包括旧版 PLC cell response 构建逻辑；当前主流程使用 `plc/cell_response.py`。
- `legacy_schemas/`：从主目录归档的旧 API / CST / twin contract schema。当前主流程使用 `schemas/api.py`、`schemas/pipeline.py` 和 `schemas/twin.py`。
- `legacy_services/`：从主目录归档的旧 cache、run metadata、twin diff/event/store/builder 服务。当前主流程不从这些服务读取或写入。
- `legacy_llm/`：从主目录归档的旧 LLM API 兼容调用封装。当前主流程使用 `llm/llm_provider.py`、`llm/llm_report_generator.py` 等新链路。
- `legacy_utils/`：从主目录归档的旧 API response / time-window 工具。当前 API 直接由 `routes/report.py` 返回新字段契约。
- `legacy_configs/`：从主目录归档的旧 prompt / report 配置。当前活动代码只保留 `configs/quality_checker_policy.json`。

`legacy_previous/` 中包括：

- 旧 Agent 问答模块；
- 旧 `routes/tbm.py`；
- 旧 services 主流程；
- 旧 history memory；
- 旧 digital twin 展示快照；
- 旧 geology 融合链路；
- 旧 segment 级 GRCI；
- 旧 prompt builder；
- 旧测试和调试脚本。

## 使用约束

- 当前主流程不能从 `_archive/` import 任何内容。
- `_archive/` 仅用于历史参考、代码追溯或以后人工迁移参考。
- 如果未来确实需要恢复某段历史能力，应先复制到新的主流程模块，并重新补测试；不要直接从 `_archive/` 接回生产路径。
