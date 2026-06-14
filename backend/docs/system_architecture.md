# TBM 日报后端系统架构

本文描述当前真实执行的后端架构。历史代码、旧 Agent、旧 routes 和旧 segment GRCI 均不参与本文所述主流程。

## 1. 正式日报生成主链路

```text
正式 evidence_db
-> time_valid filter
-> spatial_relevant filter
-> ConstructionStateCell
-> RAI / GRS / GRCI
-> Evidence Pack
-> template / LLM / planner LLM
-> Quality / Trace
-> Revision
-> Report
```

主入口是 `backend/routes/report.py` 调用 `backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline`。输入包括指定日期的 PLC CSV 和正式地质证据库 `EVIDENCE_DB_PATH`。地质证据必须先经过 online 时间合法性过滤和日报空间范围筛选，才能进入报告级 cell 建模。

## 2. LLM 生成链路

```text
Prompt Evidence Pack
-> Report Planner
-> Plan Validation
-> Generator
-> Quality / Trace
-> Revision
-> Final Report
```

LLM 不直接读取原始 PLC 或完整 evidence_db，也不计算 RAI、GRS、GRCI。LLM 只消费 Evidence Pack 和经过验证的 plan。Quality / Trace 会检查报告 claim 是否有结构化证据支撑，并识别前方提示误写、GRCI 概率误用、对齐范围误写为实际推进等错误。

## 3. 批量运行链路

```text
PLC audit
-> evidence audit
-> date classification
-> batch pipeline
-> batch LLM generation
```

对应脚本：

- `scripts/audit_plc_dates.py`
- `scripts/audit_evidence_db.py`
- `scripts/classify_experiment_dates.py`
- `scripts/run_batch_pipeline.py`
- `scripts/run_batch_llm_generation.py`

该链路用于后续实验准备，不改变单日主 pipeline 行为。

## 4. P3 旁路地质文本结构化链路

```text
raw_text / source_text / original_text_span
-> LLM geology extraction
-> candidate evidence
-> schema validation
-> candidate_evidence_db
```

P3 的定位是 sidecar candidate module：

- 不写入正式 `evidence_db`；
- 不进入 `time_valid / spatial_relevant`；
- 不进入 GRS、RAI、GRCI；
- 不进入 Evidence Pack；
- 不影响 Report 生成；
- 输出必须标记 `candidate_only=true`、`requires_manual_review=true`、`not_used_by_main_pipeline=true`。

## 5. 当前主目录职责

- `pipeline/`：日报主 pipeline、输入读取、输出组织。
- `plc/`：PLC 工况、响应、气体和 cell response。
- `geology_v2/`：正式地质证据标准化、过滤、投影、融合、forward profile。
- `coupling/`：ConstructionStateCell 与 GRS/RAI/GRCI。
- `llm/`：Evidence Pack、prompt、LLM generation、planner、quality、trace、revision。
- `geology_text/`：P3 旁路候选地质文本结构化。
- `scripts/`：smoke、导出、批量审计、批量运行、P3 旁路抽取。
- `tests/`：契约测试和回归测试。

## 6. 关键边界

`daily_plc_range` 是实际 PLC 推进范围；`daily_excavated_scope` 是 10m cell 对齐后的复核范围。前者可写作实际施工推进，后者只能写作建模与复核范围。

`forward_attention` 是当前掌子面前方关注提示，不表示已发生事实。前方 cell 不进入 high GRCI。

`GRCI` 是地质-施工响应耦合关注度，不是灾害概率，也不是前方风险。
