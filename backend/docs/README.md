# TBM 日报后端文档索引

本目录只保留当前后端研究原型仍需要阅读和维护的文档。当前方法主线已经冻结，后续工作进入实验、复盘、论文写作和展示阶段；除明确说明为旁路脚本的内容外，不再把新方法模块接入默认主流程。当前后端主线为：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Planner / Generator / Revision
-> Quality / Trace
-> Report / Export
```

`_archive/`、旧 Agent、旧 `routes/tbm.py`、旧 segment 级 GRCI、旧 history memory 不参与当前主流程。

当前方法主线可以概括为：

```text
PLC 与多源地质证据
-> ConstructionStateCell 施工状态单元
-> RAI / GRS / GRCI 启发式关注指标
-> daily_review / forward_attention / local_background 证据角色分层
-> Evidence Pack 证据约束生成
-> Evidence Pack selection_score / selection_rank / selection_reason
-> Quality / Trace 语义边界校核
-> 批量实验、权重敏感性分析、cell 尺度敏感性分析、生成模式对比
```

关键边界：

- RAI / GRS / GRCI 是启发式关注指标，不是灾害预测模型。
- 当前没有灾害发生标签、异常原因标签或现场复核标签，因此不做监督学习式权重校准。
- GRCI 只用于已掘复核 `daily_review` cell，不用于 `forward_attention`。
- `forward_attention` 只写“当前掌子面前方关注提示”，不写已发生事实。
- forward 距离分层为 0-10m、10-20m、20-30m。
- cell 默认 10m，10m 是最大推荐日报复核尺度；5m/10m 用于尺度敏感性分析，不默认使用 20m。
- `daily_plc_range` / `daily_advance_m` 才是 PLC 实测推进范围和推进量；`daily_excavated_scope` 是 cell 对齐后的复核范围。
- `stop_ratio` 只是施工响应关注信号，不能直接解释为异常停机原因。
- P3 candidate evidence 仍然是旁路候选证据，不进入正式主 pipeline。
- claim-first generation 目前只做 `allowed_claims.json` 旁路导出，不接入默认生成流程。
- LLM 不直接读取原始 PLC CSV 或完整 evidence_db，只消费 Evidence Pack。

## 推荐阅读路径

1. [系统架构与执行路线](system_architecture.md)  
   面向首次阅读者，说明当前后端真实如何从 PLC 与地质证据生成日报，并包含主流程结构图。

2. [字段契约](backend_field_contract.md)  
   说明 `DailyReportResult`、`ConstructionStateCell`、Evidence Pack、Quality / Trace、API 与导出字段。

3. [方法与计算逻辑白皮书](method_calculation_whitepaper.md)  
   面向方法复盘和论文写作，详细解释 RAI、GRS、GRCI 作为启发式关注指标的语义、证据分层、字段来源和计算公式。

4. [LLM 生成模式](llm_generation_modes.md)  
   说明 `template`、`evidence_pack_llm`、`evidence_pack_llm_with_revision`、`evidence_pack_planner_llm`、`evidence_pack_planner_llm_with_revision` 的差异、约束和导出文件。

5. [批量审计与多日期运行](batch_pipeline.md)  
   说明 90 天数据审计、日期分类、批量 no-LLM pipeline、批量 LLM 生成脚本。

6. [实验与复盘脚本说明](experiment_scripts.md)  
   说明多日期 smoke、完整导出、批量指标统计、生成模式对比、GRCI 权重敏感性、cell size 敏感性和 allowed claims 旁路导出。

7. [方法增强说明](method_enhancement.md)  
   说明当前冻结方法中的 overlap、trace completeness、evidence confidence、forward distance、Evidence Pack 选择分，以及 claim-first 只旁路导出的边界。

8. [旁路式地质文本结构化](geology_text_extraction.md)  
   说明 P3 sidecar 模块如何把地质文本抽取成候选证据，以及为什么不进入正式主链路。

9. [论文写作上下文包](paper_writing_context.md)  
   给论文写作或外部 LLM 使用的项目上下文，强调当前系统已经实现什么、没有实现什么。

10. [LLM 简版上下文](llm_context_brief.md)  
   更短的上下文包，适合快速贴给外部模型。

11. [实验规划](experiment_plan.md)  
   说明后续论文实验可以如何基于当前导出结果展开。它是实验安排文档，不表示主流程继续新增方法模块。

## 当前主流程结构图

```mermaid
flowchart TD
    A[PLC daily CSV / PLC 日运行 CSV] --> B[PLC processing / PLC 处理]
    C[official evidence_db / 正式 evidence_db] --> D[Geology normalize / 地质标准化]
    D --> E[Time valid filter / 时间可用过滤]
    E --> F[Report scope filter / 日报范围筛选]
    B --> G[cell response / cell 响应]
    F --> H[geology state / 地质状态]
    G --> I[ConstructionStateCell]
    H --> I
    I --> J[RAI GRS GRCI / 三类核心指标]
    J --> K[Evidence Pack]
    K --> L[Template or LLM / 模板或 LLM]
    L --> M[Quality Grounding Trace / 质量核验追踪]
    M --> N[API and exports / API 与导出]
```

## 证据分层结构图

```mermaid
flowchart LR
    A[time_valid evidence] --> B[daily_review]
    A --> C[forward_attention]
    A --> D[local_background]
    A --> E[excluded_by_distance]

    B --> F[review cells with GRCI / 已掘复核 cell]
    C --> G[forward cells use GRS only / 前方 cell 只用 GRS]
    D --> H[local background context / 局部背景上下文]
    E --> I[excluded from main report / 不进入主报告]
```

## 方法增强旁路图

```mermaid
flowchart TD
    A[ConstructionStateCell / 统一 cell 对象] --> B[Evidence Pack / 证据包]
    B --> C[Report Quality Trace / 报告与核验]
    A -. statistics only / 仅统计 .-> D[Batch metrics / 批量指标]
    A -. sensitivity only / 仅敏感性分析 .-> E[GRCI and cell size sensitivity / GRCI 与 cell 尺寸敏感性]
    B -. export only / 仅导出 .-> F[Allowed claims / 允许 claim 清单]
```

## LLM 生成结构图

```mermaid
flowchart TD
    A[Evidence Pack] --> B[Report Planner]
    B --> C[Plan Validation / 计划校验]
    C --> D[Report Prompt / 报告提示词]
    D --> E[LLM Draft / 初稿]
    E --> F[Post-process / 后处理]
    F --> G[Quality Trace / 质量追踪]
    G --> H{Revision enabled / 启用修订}
    H -- No --> I[Final Report / 最终报告]
    H -- Yes --> J[Revision Prompt / 修订提示词]
    J --> K[Revised Report / 修订报告]
    K --> L[Final Quality Trace / 最终质量追踪]
    L --> I
```

## 已合并或移除的旧文档

以下文档属于阶段性说明或旧索引，内容已经合并到上述当前文档中，因此不再保留在 `backend/docs` 根目录：

- `current_backend_system_manual.md`：合并到 [系统架构与执行路线](system_architecture.md) 与 [方法与计算逻辑白皮书](method_calculation_whitepaper.md)。
- `case_2023-12-30.md`：真实案例信息合并到 [方法与计算逻辑白皮书](method_calculation_whitepaper.md) 的复盘说明与导出字段解释中。
- `quality_trace_boundary_update.md`：合并到 [字段契约](backend_field_contract.md)、[LLM 生成模式](llm_generation_modes.md) 与白皮书的 Quality / Trace 部分。
- `method_definition.md`、`metrics_definition.md`、`scope_and_limitations.md`：合并到 [方法与计算逻辑白皮书](method_calculation_whitepaper.md) 与 [论文写作上下文包](paper_writing_context.md)。
- `archive_plan.md`：归档说明合并到根 README、后端 README 和本文档。

后续如果新增文档，请优先放入上述阅读路径；不要再新增只记录单次修复过程的临时说明。
