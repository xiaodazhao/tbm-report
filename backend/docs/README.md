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
    plc["PLC daily CSV<br/>PLC 日运行 CSV"] --> plc_proc["PLC processing<br/>PLC 处理"]
    evdb["official evidence_db<br/>正式 evidence_db"] --> geo_norm["Geology normalize<br/>地质标准化"]
    geo_norm --> time_filter["Time valid filter<br/>时间可用过滤"]
    time_filter --> scope_filter["Report scope filter<br/>日报范围筛选"]
    plc_proc --> cell_resp["cell response<br/>cell 响应"]
    scope_filter --> geo_state["geology state<br/>地质状态"]
    cell_resp --> cs_cell["ConstructionStateCell"]
    geo_state --> cs_cell
    cs_cell --> core_metrics["RAI / GRS / GRCI<br/>三类核心指标"]
    core_metrics --> pack["Evidence Pack"]
    pack --> gen["Template or LLM<br/>模板或 LLM"]
    gen --> qtrace["Quality / Grounding / Trace<br/>质量核验追踪"]
    qtrace --> api_export["API and exports<br/>API 与导出"]
```

## 证据分层结构图

```mermaid
flowchart LR
    time_valid["time_valid evidence"] --> review["daily_review"]
    time_valid --> forward["forward_attention"]
    time_valid --> background["local_background"]
    time_valid --> excluded["excluded_by_distance"]

    review --> review_use["review cells with GRCI<br/>已掘复核 cell"]
    forward --> forward_use["forward cells use GRS only<br/>前方 cell 只用 GRS"]
    background --> background_use["local background context<br/>局部背景上下文"]
    excluded --> excluded_use["excluded from main report<br/>不进入主报告"]
```

## 方法增强旁路图

```mermaid
flowchart TD
    cs_cell["ConstructionStateCell<br/>统一 cell 对象"] --> pack["Evidence Pack<br/>证据包"]
    pack --> report_qt["Report / Quality / Trace<br/>报告与核验"]
    cs_cell -. "statistics only<br/>仅统计" .-> batch_metrics["Batch metrics<br/>批量指标"]
    cs_cell -. "sensitivity only<br/>仅敏感性分析" .-> sensitivity["GRCI and cell size sensitivity<br/>GRCI 与 cell 尺寸敏感性"]
    pack -. "export only<br/>仅导出" .-> allowed_claims["Allowed claims<br/>允许 claim 清单"]
```

## LLM 生成结构图

```mermaid
flowchart TD
    pack["Evidence Pack"] --> planner["Report Planner"]
    planner --> plan_check["Plan Validation<br/>计划校验"]
    plan_check --> prompt["Report Prompt<br/>报告提示词"]
    prompt --> draft["LLM Draft<br/>初稿"]
    draft --> post["Post-process<br/>后处理"]
    post --> qtrace["Quality Trace<br/>质量追踪"]
    qtrace --> revision{"Revision enabled<br/>启用修订"}
    revision -- "No" --> final_report["Final Report<br/>最终报告"]
    revision -- "Yes" --> revision_prompt["Revision Prompt<br/>修订提示词"]
    revision_prompt --> revised["Revised Report<br/>修订报告"]
    revised --> final_trace["Final Quality Trace<br/>最终质量追踪"]
    final_trace --> final_report
```

## 已合并或移除的旧文档

以下文档属于阶段性说明或旧索引，内容已经合并到上述当前文档中，因此不再保留在 `backend/docs` 根目录：

- `current_backend_system_manual.md`：合并到 [系统架构与执行路线](system_architecture.md) 与 [方法与计算逻辑白皮书](method_calculation_whitepaper.md)。
- `case_2023-12-30.md`：真实案例信息合并到 [方法与计算逻辑白皮书](method_calculation_whitepaper.md) 的复盘说明与导出字段解释中。
- `quality_trace_boundary_update.md`：合并到 [字段契约](backend_field_contract.md)、[LLM 生成模式](llm_generation_modes.md) 与白皮书的 Quality / Trace 部分。
- `method_definition.md`、`metrics_definition.md`、`scope_and_limitations.md`：合并到 [方法与计算逻辑白皮书](method_calculation_whitepaper.md) 与 [论文写作上下文包](paper_writing_context.md)。
- `archive_plan.md`：归档说明合并到根 README、后端 README 和本文档。

后续如果新增文档，请优先放入上述阅读路径；不要再新增只记录单次修复过程的临时说明。
