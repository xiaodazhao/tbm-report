# TBM 后端文档索引

当前后端的主线已经从“只生成日报”升级为：

```text
TBM 施工状态数字孪生底座
+ 多源证据治理
+ 大模型可追溯认知接口
```

日报仍然是一个重要输出，但当前代码的核心对象已经是 `ConstructionStateCell` 和 `DailyConstructionTwin`。所有报告、Evidence Pack、Quality、Trace、调试导出都应围绕这个结构化状态底座展开。

## 推荐阅读路径

1. [施工状态数字孪生底座架构](construction_twin_architecture.md)  
   说明本轮架构升级后的 `DailyConstructionTwin`、Evidence Governance、Twin Query、Twin Evidence Pack、边界检查和导出结构。

2. [系统架构与执行路线](system_architecture.md)  
   说明当前后端主流程如何从 PLC 和正式 evidence_db 构建日报与可追溯输出。

3. [字段契约](backend_field_contract.md)  
   说明 `DailyReportResult`、`ConstructionStateCell`、Evidence Pack、Quality / Trace、API 和导出字段。

4. [方法与计算逻辑白皮书](method_calculation_whitepaper.md)  
   说明 RAI / GRS / GRCI 的计算语义、证据分层、cell 尺度、overlap、selection、trace completeness 等方法细节。

5. [方法增强说明](method_enhancement.md)  
   说明 overlap、source reliability、Evidence Pack selection、claim-first 旁路导出等增强项的用途和边界。

6. [实验脚本说明](experiment_scripts.md)  
   说明批量运行、生成模式对比、GRCI 权重敏感性、cell 尺度敏感性、allowed claims 导出等脚本。

7. [LLM 生成模式](llm_generation_modes.md)  
   说明 template、Evidence Pack LLM、revision、Report Planner 等生成模式。

8. [批量 Pipeline](batch_pipeline.md)  
   说明多日期审计、批量 no-LLM pipeline 和批量 LLM 生成脚本。

9. [旁路式地质文本结构化](geology_text_extraction.md)  
   说明 P3 sidecar 模块。它只生成候选证据，不写入正式 evidence_db，不进入主 pipeline。

10. [论文写作用上下文包](paper_writing_context.md)  
    给论文写作或外部 LLM 使用的项目背景说明。

11. [简版 LLM 上下文](llm_context_brief.md)  
    更短的上下文摘要，便于快速粘贴给外部模型。

## 当前主流程

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

## 当前核心边界

- RAI / GRS / GRCI 是启发式关注指标，不是灾害预测模型。
- GRCI 只用于已掘复核 `daily_review` cell，不用于 `forward_attention`。
- `forward_attention` 只写当前掌子面前方关注提示，不写已发生事实。
- `daily_plc_range` / `daily_advance_m` 是 PLC 实测推进范围和推进量。
- `daily_excavated_scope` 是 cell 对齐后的复核范围，不是实际推进范围。
- `stop_ratio` 只是施工响应关注信号，不能直接解释为异常停机原因。
- PLC enhanced proxy 不是严格物理量，不能作为地质风险证明。
- P3 candidate evidence 仍然是旁路候选证据，不进入正式主 pipeline。
- claim-first generation 目前只做 allowed claims 旁路导出，不接入默认生成流程。
- LLM 不直接读取原始 PLC CSV 或完整 evidence_db，只消费 Evidence Pack。

## 当前有效目录

- `pipeline/`：主 pipeline、输入、scope、输出组织。
- `plc/`：PLC 工况、气体、响应和 cell response。
- `geology_v2/`：正式地质证据标准化、过滤、投影、融合、forward profile。
- `coupling/`：cell 级 RAI / GRS / GRCI。
- `twin/`：`DailyConstructionTwin` 构建、查询和旧兼容摘要。
- `evidence_governance/`：证据角色和 claim 边界规则。
- `llm/`：Evidence Pack、prompt、模板报告、LLM 可选生成、Quality、Trace、边界检查。
- `schemas/`：API、pipeline、twin schema。
- `scripts/`：smoke、导出、批量、LLM、sidecar 工具。
- `tests/`：回归测试。
- `_archive/`：历史代码，仅作参考，主流程禁止 import。

