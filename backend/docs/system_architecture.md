# TBM 日报后端系统架构

本文描述当前代码真实执行的后端架构。旧 Agent、旧 `routes/tbm.py`、旧 segment 级 GRCI、旧 history memory 和 `_archive/` 中的历史代码都不参与本文所述主流程。

相关文档：

- [字段契约](backend_field_contract.md)
- [方法与计算逻辑白皮书](method_calculation_whitepaper.md)
- [LLM 生成模式](llm_generation_modes.md)
- [批量审计与多日期运行](batch_pipeline.md)
- [方法增强说明](method_enhancement.md)
- [实验与复盘脚本说明](experiment_scripts.md)
- [旁路式地质文本结构化](geology_text_extraction.md)

当前方法主线已经冻结，后续工作进入实验与复盘阶段。旁路分析脚本、P3 candidate evidence 和 allowed claims 导出均不改变本文所述默认主流程。

## 1. 当前唯一日报主链路

```text
FastAPI routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> template / evidence_pack_llm / evidence_pack_llm_with_revision / evidence_pack_planner_llm
-> Quality / Trace
-> Report / Debug / Export
```

代码入口：

- API 注册：`backend/app.py`
- API 路由：`backend/routes/report.py`
- 主函数：`backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline`
- 核心 cell schema：`backend/schemas/pipeline.py::ConstructionStateCell`

## 2. 主流程结构图

```mermaid
flowchart TD
    in_date["input date<br/>输入日期"] --> load_inputs["load_daily_inputs<br/>读取输入"]
    load_inputs --> plc_data["PLC daily data<br/>PLC 日数据"]
    load_inputs --> evdb["official evidence_db<br/>正式 evidence_db"]

    plc_data --> plc_proc["PLC quality and operation<br/>质量与工况识别"]
    plc_proc --> gas_resp["Gas and response aggregation<br/>气体与响应聚合"]
    gas_resp --> cell_resp["cell_response_df"]

    evdb --> normalize["normalize_evidence_df"]
    normalize --> available["filter_available_evidence"]
    available --> scope_filter["Report scope filter<br/>日报范围筛选"]
    scope_filter --> projector["project_evidence_to_cells"]
    projector --> geo_states["geo_states_df"]

    cell_resp --> cs_cell["ConstructionStateCell"]
    geo_states --> cs_cell
    cs_cell --> metrics["RAI / GRS / GRCI<br/>核心指标"]
    metrics --> forward["Forward Profile<br/>前方画像"]
    metrics --> twin["Twin State<br/>孪生状态"]
    metrics --> pack["Prompt Evidence Pack<br/>证据包"]

    pack --> report_gen["Report Generation<br/>报告生成"]
    report_gen --> qtrace["Quality / Grounding / Trace<br/>质量核验追踪"]
    qtrace --> result["DailyReportResult"]
    result --> api_export["API and export scripts<br/>API 与导出脚本"]
```

## 3. 证据范围分层

当前日报不再保留全局地质 cell 作为主流程，而是围绕当日施工范围和当前掌子面构建局部日报 cell。

```mermaid
flowchart LR
    time_valid["time_valid evidence"] --> review["daily_review"]
    time_valid --> forward["forward_attention"]
    time_valid --> background["local_background"]
    time_valid --> excluded["excluded_by_distance"]

    review --> excavated["excavated review<br/>已掘复核"]
    excavated --> grci_ok["GRCI allowed<br/>可算 GRCI"]

    forward --> forward_tip["forward attention<br/>前方关注"]
    forward_tip --> grs_only["GRS / hazards / source_trace only<br/>仅用 GRS 与 trace"]

    background --> bg_use["local background<br/>局部背景"]
    excluded --> excluded_use["excluded from main report<br/>不进主报告"]
```

语义边界：

- `daily_review`：已掘区段复核，只有同时具备 GRS、RAI 和 PLC response 的 cell 才能计算正式 GRCI。
- `forward_attention`：当前掌子面前方关注提示，不使用 GRCI，不写成已发生事实。
- `local_background`：只提供局部背景上下文，不进入 high GRCI。
- `excluded_by_distance`：距离当日报告范围过远，不进入日报主链路。

## 4. LLM 生成链路

```mermaid
flowchart TD
    pack["Prompt Evidence Pack"] --> mode{"generation_mode"}
    mode -- "template" --> template["Template report<br/>模板报告"]
    mode -- "evidence_pack_llm" --> llm_prompt["Evidence Pack prompt<br/>证据包提示词"]
    mode -- "evidence_pack_llm_with_revision" --> llm_loop["Draft plus revision loop<br/>初稿加修订"]
    mode -- "evidence_pack_planner_llm" --> planner["Report Planner"]

    planner --> plan_check["Plan Validation<br/>计划校验"]
    plan_check --> generator["Generator<br/>生成器"]
    llm_prompt --> generator
    llm_loop --> generator
    generator --> post["LLM post process<br/>LLM 后处理"]
    post --> qtrace["Quality Trace<br/>质量追踪"]
    qtrace --> revision{"Revision<br/>修订"}
    revision -- "Yes" --> revision_prompt["Revision Prompt<br/>修订提示词"]
    revision_prompt --> final_trace["Final Quality Trace<br/>最终质量追踪"]
    revision -- "No" --> final_trace
    template --> final_trace
    final_trace --> audit["report quality trace audit<br/>报告与审计输出"]
```

LLM 只能消费 Evidence Pack 和经过验证的 planner 结果。LLM 不读取原始 PLC，不读取完整 evidence_db，不计算 RAI、GRS、GRCI，也不决定 forward cell。

## 5. 批量审计与多日期运行

```mermaid
flowchart TD
    plc_dir["PLC directory<br/>PLC 目录"] --> plc_audit["audit_plc_dates.py"]
    evdb["evidence_db.csv"] --> ev_audit["audit_evidence_db.py"]
    plc_audit --> classify["classify_experiment_dates.py"]
    ev_audit --> classify
    classify --> date_list["usable date list<br/>可运行日期"]
    date_list --> batch_pipeline["run_batch_pipeline.py"]
    date_list --> batch_llm["run_batch_llm_generation.py"]
```

批量脚本只调用现有单日 pipeline，不改变单日 pipeline 的计算逻辑。

## 6. P3 旁路式地质文本结构化

```mermaid
flowchart TD
    raw_text["raw geology text<br/>原始地质文本"] --> llm_extract["LLM geology extraction<br/>LLM 文本抽取"]
    llm_extract --> schema_check["schema validation<br/>schema 校验"]
    schema_check --> candidate["candidate evidence<br/>候选证据"]
    candidate --> candidate_db["candidate_evidence_db"]

    candidate_db -. "no write<br/>不写入" .-> evdb["official evidence_db"]
    candidate_db -. "no entry<br/>不进入" .-> scope_gate["time_valid / spatial_relevant"]
    candidate_db -. "no use<br/>不参与" .-> metrics["RAI / GRS / GRCI"]
    candidate_db -. "no entry<br/>不进入" .-> pack["Evidence Pack"]
```

P3 定位为 sidecar candidate evidence module：

- 不写入正式 `evidence_db.csv`；
- 不进入正式 `time_valid / spatial_relevant`；
- 不参与 GRS、RAI、GRCI；
- 不进入 Evidence Pack；
- 不影响 Report 生成；
- 输出必须标记 `candidate_only=true`、`requires_manual_review=true`、`not_used_by_main_pipeline=true`。

## 7. 目录职责

- `routes/`：当前 API，只保留日报与调试接口。
- `pipeline/`：单日主 pipeline、输入、输出和 evidence scope。
- `plc/`：PLC 工况、响应、气体和 cell response 聚合。
- `geology_v2/`：正式地质证据标准化、过滤、投影、融合和 forward profile。
- `coupling/`：cell 级 RAI / GRS / GRCI 计算和语义边界。
- `twin/`：从 ConstructionStateCell 构建孪生状态摘要。
- `llm/`：Evidence Pack、prompt、planner、模板报告、LLM 调用、质量检查、grounding 与 trace。
- `geology_text/`：P3 旁路候选地质文本结构化。
- `scripts/`：smoke、导出、批量审计、批量运行、LLM 生成、P3 抽取。
- `tests/`：字段契约、语义边界、质量检查、批量脚本和 P3 sidecar 的回归测试。
- `docs/`：当前有效文档。
- `_archive/`：历史代码归档，不允许主流程 import。

## 8. 关键语义边界

- `daily_plc_range` 是 PLC 实测当日推进范围。
- `daily_excavated_scope` 是 10m cell 对齐后的已掘复核范围，不能写成实际推进范围。
- `GRCI` 是地质-施工响应耦合关注度，不是灾害概率，也不是前方风险。
- 没有 RAI 或没有 PLC response 的 cell 不计算正式 GRCI。
- forward cell 不进入 high GRCI。
- `stop_ratio` 只是施工响应关注信号；当前 PLC 字段未区分计划停机与非计划停机，不能把停机直接写成异常原因。
- 前方关注提示来自当前掌子面前方可用地质证据，只能写成关注/提示，不得写成已揭露事实。
