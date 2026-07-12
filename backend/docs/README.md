# 后端文档索引

本目录只保留当前后端仍需要长期维护的少量文档。旧版方法说明、阶段性审计、失败过程记录和临时论文上下文已删除或迁入最终论文材料。

## 当前保留文档

| 文档 | 用途 |
|---|---|
| [`backend_field_contract.md`](backend_field_contract.md) | 后端核心 schema、API 返回字段、调试导出字段契约 |
| [`plc_preprocessing_method.md`](plc_preprocessing_method.md) | 当前 PLC 预处理与稳态施工响应证据构建方法 |
| [`README.md`](README.md) | 本索引 |

## 主流程位置

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> DailyConstructionTwin
-> Evidence Pack
-> Template / Optional LLM
-> Quality / Grounding / Boundary / Structured Trace
-> API / Export
```

主入口：

```text
backend/routes/report.py
backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline
```

## 当前有效目录

| 目录 | 说明 |
|---|---|
| `pipeline/` | 主 pipeline、输入、scope、输出组织 |
| `plc/` | PLC 质量检查、预处理、施工响应、气体摘要、cell response |
| `geology_v2/` | 正式地质证据标准化、时间/空间筛选、投影、融合、forward profile |
| `coupling/` | cell 级 RAI / GRS / GRCI |
| `twin/` | DailyConstructionTwin 构建和导出 |
| `evidence_governance/` | 证据角色和 claim 边界规则 |
| `llm/` | Evidence Pack、prompt、模板报告、可选 LLM、Quality、Grounding、Boundary、Trace |
| `schemas/` | API、pipeline、twin schema |
| `scripts/` | smoke、导出、批量、LLM、sidecar 工具 |
| `tests/` | 回归测试 |
| `_archive/` | 历史代码，仅作参考，主流程禁止 import |

## 方法边界

- RAI / GRS / GRCI 是启发式关注指标，不是灾害预测模型。
- GRCI 只用于已掘复核 `daily_review` cell，不用于 `forward_attention`。
- `forward_attention` 只能写当前掌子面前方关注提示，不写已发生事实。
- `daily_plc_range` / `daily_advance_m` 是 PLC 实测推进范围和推进量。
- `daily_excavated_scope` 是 cell 对齐后的复核范围，不是实际推进范围。
- `stop_ratio` 只是施工响应关注信号，不能直接解释为异常停机原因。
- PLC proxy 不是严格物理量，不能作为地质风险证明。
- P3 candidate evidence 是旁路候选证据，不进入正式主 pipeline。
- LLM 不直接读取原始 PLC CSV 或完整 evidence_db，只消费 Evidence Pack。

更完整的项目解释见根目录 [`PROJECT_FULL_EXPLANATION.md`](../../PROJECT_FULL_EXPLANATION.md)。
