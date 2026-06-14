# LLM 论文写作精简上下文

- 项目一句话：本项目面向 TBM 施工日报自动生成，构建“时空证据门控 + ConstructionStateCell 施工状态孪生 + Prompt Evidence Pack 证据约束 LLM 生成”的研究框架。

- 核心链路：
  ```text
  PLC + TSP/HSP/sketch
  -> time_valid 与 spatial_relevant 证据门控
  -> 10m ConstructionStateCell
  -> RAI / GRS / GRCI
  -> Prompt Evidence Pack
  -> Report Planner / Generator / Revision
  -> Quality / Trace
  -> TBM 施工日报
  ```

- 数据规模：当前有 91 天 PLC 日运行数据，91 天均可用于 pipeline；正式地质 evidence 共 484 条，其中 TSP 139 条、HSP/sonic 176 条、sketch 169 条；日期分类结果为 A 类 83 天、B 类 8 天；batch pipeline 91/91 passed，batch mock LLM 91/91 passed，平均日推进约 13.8571 m。

- 核心对象：`ConstructionStateCell` 是 10m 里程单元下的施工状态表达，汇集 PLC response、地质证据、source_trace、RAI、GRS、GRCI、cell_role 和 trace 字段。

- 证据角色：`daily_review` 是已掘复核 cell，可使用 GRCI；`forward_attention` 是当前掌子面前方关注提示，只用 GRS/source_trace，不使用 GRCI；`local_background` 只作背景上下文。

- 指标边界：RAI 是 PLC 施工响应异常关注度；GRS 是地质证据关注度；GRCI 是已掘 cell 的地质-施工响应耦合关注度，不是灾害概率，不是前方风险。没有 RAI 或没有 PLC response 的 cell 不计算正式 GRCI。

- 范围边界：`daily_plc_range` 是 PLC 实测推进范围；`daily_excavated_scope` 是 10m cell 对齐后的已掘复核范围，不是实际推进范围。系统设置 E14 检查，防止 LLM 把对齐范围误写为实际推进。

- LLM 角色：LLM 不是数值计算器，也不直接读取全部原始数据。LLM 只能消费 Prompt Evidence Pack；planner 先规划章节和证据角色，generator 写正文，Quality/Trace 检查 claim 支撑，revision 根据错误反馈修订。

- P3 模块：P3 是 sidecar geology text extraction，仅从 raw_text/source_text/original_text_span 抽取 candidate evidence，输出 `candidate_evidence_db.csv`，并强制 `candidate_only=true`、`requires_manual_review=true`、`not_used_by_main_pipeline=true`。P3 不写入正式 evidence_db，不进入 GRS/GRCI/Evidence Pack。

- 当前完成状态：P0 Evidence Pack 约束生成、P1 Quality/Trace 修订与 E14、P2 Report Planner、任务 3 的 91 天审计和批量运行、P3 sidecar 地质文本结构化均已完成；当前测试为 `62 passed`。

- 论文写作禁忌：不要写成“直接调用 LLM 写日报”；不要写成“LLM 判断地质风险”；不要把 GRCI 写成概率；不要把 forward_attention 写成已发生事实；不要把 91 天单工程验证夸大为多工程泛化；不要把 P3 写成正式主链路。
