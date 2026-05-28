# TBM Digital Twin Refactor Package

本包是在原后端代码基础上做的数字孪生层重构版本。目标：

- 分层清晰：分析结果、Twin/CST 结构状态、LLM summary、Prompt 文本适配分离。
- 契约稳定：新增 `schemas/twin_contract.py` 作为唯一 TwinState/TwinEvent/TwinDiff 契约层。
- 语义唯一：current_face、excavated_segment、forward_window、operation_mode、cluster_state、response_anomaly 分离。
- 文本输出单独适配：结构化 TwinState 不存自然语言报告段落；`summarize_cst_for_prompt()` 和 `summary_contract.py` 负责文本化。

## 新增文件

- `schemas/twin_contract.py`
- `services/twin_event_service.py`
- `services/twin_diff_service.py`
- `services/twin_store_service.py`
- `services/twin_query_service.py`

## 修改文件

- `schemas/cst_state.py`
- `services/cst_update_service.py`
- `services/digital_twin_state.py`
- `services/tbm_analysis_service.py`
- `llm/summary_contract.py`
- `routes/tbm.py`
- `schemas/responses.py`
- `agent/tbm_tools.py`
- `utils/serialization.py`

## 新增 API

- `GET /api/tbm/twin/events?date=YYYY-MM-DD`
- `GET /api/tbm/twin/segment?date=YYYY-MM-DD&chainage=...`
- `GET /api/tbm/twin/event_explain?date=YYYY-MM-DD&event_id=...`
- `GET /api/tbm/twin/diff?date1=YYYY-MM-DD&date2=YYYY-MM-DD`

## 关键原则

1. `cst_state` 不再嵌入完整 `llm_summary`，只保留 `llm_summary_ref`。
2. `TwinEvent` 是 Agent 解释“为什么值得注意”的主依据。
3. `forward_state` 只表示前方窗口证据提示，不包含 RAI/GRCI。
4. `attention_state` 只表示已开挖区段回顾性 GRS/RAI/GRCI 耦合关注。
5. `face_state` 只表示当前掌子面直接揭示资料，资料不足时不会被前方预报替代。
6. 兼容旧字段的内容只放进 `legacy_aliases`，canonical 层不再混用旧名。

## 验证

本包已执行：

```bash
python -m py_compile $(find . -name '*.py' -not -path './tests/*')
```

并对 `build_or_update_cst()` 做了最小样例 smoke test。
