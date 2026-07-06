# TBM 项目全貌说明书：面向导师/审稿人的方法逻辑版

> 这份文档用于让没有参与开发的人快速、完整地理解当前项目。它不是 API 文档，也不是代码审计清单，而是从研究思路、数据治理、指标计算、LLM 生成、质量评价和实验验证几个层面，说明这个项目到底在做什么、为什么这样做、当前能证明什么、不能证明什么。

---

## 阅读导引

如果只想快速理解项目，可以先看第 1、2、3、12、24、27 节；如果要指导论文方法章节，重点看第 5 到第 15 节；如果要评估实验可靠性，重点看第 17 到第 25 节。

| 关心的问题 | 建议阅读 |
|---|---|
| 项目到底是什么 | 第 1-3 节 |
| PLC 到底怎么处理 | 第 5 节 |
| 地质证据怎么治理 | 第 6-7 节 |
| ConstructionStateCell 和 Twin 是什么 | 第 8-9 节 |
| RAI、GRS、GRCI 怎么算 | 第 10 节 |
| LLM、Planner、Reviser 是什么 | 第 12-16 节 |
| 评价体系是什么 | 第 17-23 节 |
| 实验结果说明什么 | 第 24-25 节 |
| 论文能怎么讲、不能怎么讲 | 第 27-31 节 |

---

## 1. 一句话概括

本项目不是让大语言模型直接“自由写”TBM 施工日报，而是先将 PLC 施工数据、地质证据、气体监测和里程范围治理成可追溯的施工状态证据，再通过 Evidence Pack 约束模板或大模型生成日报，并用 Quality、Grounding、Boundary 和 Structured Trace 对报告逐句审计。

更准确地说，它是一个“多源工程证据治理 → 施工状态单元建模 → 施工状态孪生底座 → Evidence Pack 约束生成 → 大模型受控组织文本 → 报告主张可追溯审计”的系统。日报只是主要输出形式，真正的研究对象是 TBM 施工场景下的可信工程知识生成。

---

## 2. 为什么不能直接让 LLM 写日报

TBM 施工日报不是普通文本续写任务。它涉及实际推进范围、掘进状态、地质揭示、超前预报、前方关注、气体监测和施工建议等多种信息。每一类信息都有严格的时间、空间和语义边界。

| 约束类型 | 具体含义 | 直接 LLM 容易出现的问题 |
|---|---|---|
| 数值约束 | 推进范围、日进尺、里程、气体、GRCI 等不能乱写 | 编造数值，或把对齐范围写成实际推进 |
| 时间约束 | 只能使用报告日期之前或当日已可用证据 | 使用未来证据，形成信息泄漏 |
| 空间约束 | 地质证据必须和里程区段对应 | 把远距离证据写成当日结论 |
| 角色约束 | 已掘复核、前方关注、局部背景不能混用 | 把前方预报写成已发生事实 |
| 指标边界 | RAI、GRS、GRCI 都不是概率模型 | 把 GRCI 写成灾害概率或风险概率 |
| 工程语义 | 停机、proxy、气体字段都需要谨慎解释 | 把 stop_ratio 直接解释为异常原因 |

因此，本项目的核心不是“换一个更好的 prompt”，而是建立一条工程证据治理链：原始数据先变成受控证据，受控证据再进入报告生成，报告生成后再逐句核验。

---

## 3. 系统总框架

当前系统可以理解为七层结构。第一层是原始数据，包含 PLC 日运行 CSV、正式地质 evidence_db 和气体监测字段；第二层是数据治理，负责 PLC 预处理、稳态段识别、地质证据标准化、时间过滤和空间筛选；第三层是状态单元，将 10 m 里程范围组织成 ConstructionStateCell；第四层是 DailyConstructionTwin，把当天所有 cell 组织成施工状态孪生底座；第五层是 Evidence Pack，只把允许写入报告的证据交给模板或 LLM；第六层是报告生成，包括模板、Generator、Planner 和 Reviser；第七层是审计评价，包括 Quality、Grounding、Boundary 和 Structured Trace。

| 层级 | 名称 | 作用 |
|---|---|---|
| 第 1 层 | 原始数据层 | 接收 PLC、地质报告 PDF、正式 evidence_db、气体字段 |
| 第 2 层 | 数据治理层 | 建立地质库，清洗 PLC，筛选地质证据，确定证据时空边界 |
| 第 3 层 | 状态单元层 | 用 10 m cell 统一 PLC、地质和报告空间粒度 |
| 第 4 层 | 施工状态孪生层 | 汇总每日所有 cell、scope、roles、trace 和 governance |
| 第 5 层 | 证据包层 | 构建 Evidence Pack，作为报告生成唯一受控材料包 |
| 第 6 层 | 报告生成层 | 模板或 LLM 在 Evidence Pack 约束下生成与修订 |
| 第 7 层 | 审计评价层 | 对报告主张做证据支撑、数值、边界和 trace 检查 |

总体数据流如下：

| 阶段 | 输入 | 输出 | 关键边界 |
|---|---|---|---|
| PLC 处理 | 原始 PLC 日运行数据 | cell_response_df、operation_summary、gas_summary | 不直接用全样本均值代表施工响应 |
| 地质库建立与治理 | TSP/HSP/掌子面素描 PDF、正式 evidence_db | EvidenceRecord、evidence_db.csv、normalized evidence、geo_states_df、forward_profile | 原始 PDF 先结构化入库；日报生成不直接读取完整地质库，不使用未来证据，不把前方提示写成已发生 |
| Cell 建模 | PLC cell response + geo states | ConstructionStateCell | 统一到 10 m 里程单元 |
| Twin 构建 | 全部 ConstructionStateCell | DailyConstructionTwin | 区分 daily_review、forward_attention、local_background |
| Evidence Pack | DailyConstructionTwin | 角色化证据材料包 | LLM 只能消费 Evidence Pack |
| 报告生成 | Evidence Pack | template/LLM report | 不自行计算指标，不新增证据 |
| 报告审计 | report + Evidence Pack + Twin | Quality、Trace、Boundary | 逐句检查证据、数值和边界 |

---

## 4. 原始输入：系统到底吃什么数据

### 4.1 PLC 日运行数据

PLC 数据回答的是“当天 TBM 事实上怎么运行”。它提供推进里程、推进速度、推力、刀盘扭矩、刀盘转速、贯入度、掘进状态和气体字段等信息。

| 中文含义 | 常见字段 |
|---|---|
| 时间 | 运行时间-time |
| 掘进状态 | 掘进状态 |
| 实际里程 | 导向盾首里程、导向盾中里程等 |
| 累计进尺 | 开累进尺 |
| 推进速度 | 推进速度 |
| 推进给定速度 | 推进给定速度 |
| 推力 | 推力 |
| 刀盘扭矩 | 刀盘扭矩 |
| 刀盘实际转速 | 刀盘实际转速 |
| 刀盘给定转速 | 刀盘给定转速 |
| 贯入度 | 贯入度 |
| 气体字段 | CO2、H2S、SO2、NO2、NO、CH4 等 |

PLC 原始样本不能直接求均值，因为其中混有停机、换步、辅助作业、低速过渡、异常采样、短时扰动和稳定掘进。项目的 PLC 模块要做的，是从这些混杂样本中提取可用于日报复核的施工响应证据。

### 4.2 正式地质 evidence_db

地质 evidence_db 回答的是“截至报告日期，已有地质资料提示了什么”。它包括 TSP、HSP、掌子面素描或其他地质记录。系统不会让 LLM 直接读取完整 evidence_db，而是先做标准化、时间可用过滤、空间相关筛选和证据角色划分。

需要特别补充的是，`evidence_db` 不是天然存在的原始输入，而是由项目中的地质库建立脚本从原始地质报告中解析、清洗和写入得到。也就是说，地质证据进入日报主流程之前，先经过一层“地质证据库构建”。

### 4.3 地质证据库建立链路

地质库建立的目标，是把分散在 TSP、HSP 和掌子面素描 PDF 中的非结构化或半结构化地质信息，整理成统一的 `EvidenceRecord`，再保存为正式的 `evidence_db.csv`。后续主流程读取的是这个正式库，而不是直接读取原始 PDF。

| 建库环节 | 对应脚本或模块 | 输入 | 输出 | 作用 |
|---|---|---|---|---|
| 全量重建地质库 | `backend/scripts/build_evidence_db.py` | `TSP_DIR`、`HSP_DIR`、`SKETCH_DIR` 下的 PDF | `DB/evidence_db.csv`，并同步 SQLite | 扫描全部地质报告，解析、去重、清洗后重建正式证据库 |
| 增量导入地质报告 | `backend/scripts/import_evidence_reports.py` | 新增 PDF 文件或文件夹 | 更新后的 `evidence_db.csv` | 不重跑全部历史报告，只把新增报告解析后并入正式库 |
| 导入服务 | `backend/services/evidence_import_service.py` | PDF 路径、source_type、写库参数 | 导入结果 JSON、备份文件、更新后的证据表 | 负责 PDF 收集、来源判断、解析、清洗、去重、备份和写库 |
| 证据库审计 | `backend/scripts/audit_evidence_db.py` | `EVIDENCE_DB_PATH` | `evidence_db_audit.csv/json` | 统计证据条数、来源类型、日期、里程几何有效性和 warning |
| 旁路候选抽取 | `backend/scripts/run_geology_text_extraction.py` | 地质文本 | candidate evidence | 只生成候选证据，不自动进入正式主流程 |

全量建库流程可以抽象为：

```text
TSP / HSP / 掌子面素描 PDF
        │
        ▼
PDF 文件收集与文件级去重
        │
        ├─ 剔除无效 PDF
        ├─ 规范化文件名
        └─ 跳过重复报告
        │
        ▼
规则解析器
        │
        ├─ parse_tsp_pdf
        ├─ parse_hsp_pdf
        └─ parse_sketch_pdf
        │
        ▼
EvidenceRecord
        │
        ├─ evidence_id
        ├─ source_type
        ├─ source_level
        ├─ report_id / report_date / issue_date
        ├─ start_num / end_num / face_num / next_forecast_num
        ├─ confidence
        ├─ attrs_json
        └─ raw_text
        │
        ▼
证据表清洗
        │
        ├─ 删除重复 evidence_id
        ├─ start_num / end_num 数值化
        ├─ 删除缺失里程或起终点反向记录
        ├─ segment 证据长度限制在 0-300 m
        └─ 按 source_type / report_id / mileage 排序
        │
        ▼
正式 evidence_db.csv + SQLite evidence_records
```

增量导入流程和全量重建使用同一套清洗规则。区别是：增量导入会先读取已有 `evidence_db.csv`，默认跳过已经存在的 `evidence_id`；如果显式指定 `replace_existing`，才会用新解析记录替换已有记录。正式写库前会创建备份文件，因此它是更适合日常维护地质库的入口。

地质库记录的核心字段含义如下：

| 字段 | 中文含义 | 说明 |
|---|---|---|
| `evidence_id` | 证据唯一编号 | 后续 trace 和 source reference 的基础 |
| `source_type` | 证据来源类型 | TSP、HSP/sonic、sketch 等 |
| `source_level` | 证据层级 | overview、report_conclusion、segment、point 等 |
| `report_id` | 报告编号 | 通常来自 PDF 文件或报告标题 |
| `report_date` / `issue_date` | 报告日期 / 发布日期 | 后续用于时间可用过滤 |
| `start_num` / `end_num` | 证据覆盖里程 | 后续用于空间相关筛选和 cell 投影 |
| `face_num` | 报告对应掌子面里程 | 用于判断预报与当前掌子面的关系 |
| `next_forecast_num` | 下一次预报里程 | 作为部分报告中的辅助边界信息 |
| `confidence` | 解析或证据置信描述 | 后续可映射到 confidence_component |
| `attrs_json` | 扩展属性 | 保存围岩等级、异常标签、hazard 标签、解析器版本、parse warning 等 |
| `raw_text` | 原始文本片段 | 便于人工复核和 trace 解释 |

这层的论文意义是：系统不是把地质 PDF 直接塞给 LLM，也不是让 LLM 自己读原始报告，而是先将地质资料转成可检查、可排序、可追溯的结构化证据库。后续的时间过滤、空间筛选、GRS 融合、Evidence Pack 和 Trace 都建立在这个正式 evidence_db 之上。

### 4.4 旁路候选证据

项目中存在 LLM 地质文本结构化模块，但它只是 sidecar candidate evidence。当前主流程中，这些候选证据不写入正式 evidence_db，不进入 time_valid，不进入 spatial_relevant，不参与 GRS / GRCI，也不进入 Evidence Pack。

---

## 5. PLC 施工响应证据构建

PLC 预处理是本项目最近增强的重要部分。它的目标不是做参数预测，也不是判断地质风险，而是把原始 PLC 样本转成“已掘区段施工响应证据”。

一个 PLC 样本可以抽象为：

| 符号 | 中文含义 | 说明 |
|---|---|---|
| t_i | 时间 | 样本时间戳 |
| m_i | 里程 | TBM 导向里程或等效里程 |
| v_i | 推进速度 | advance speed |
| F_i | 推力 | thrust |
| T_i | 刀盘扭矩 | torque |
| ω_i | 刀盘转速 | rpm |
| q_i | 贯入度 | penetration |
| s_i | 掘进状态 | operating state |
| g_i | 气体字段 | gas readings |

PLC 处理不是一个单一规则，而是一条连续处理链：

| 步骤 | 处理内容 | 目的 |
|---|---|---|
| 1 | 时间质量检查 | 识别时间倒序、时间间隔异常、长时间断点和重复采样 |
| 2 | 里程质量检查 | 识别里程反向跳变、异常突跳、缺失或无法映射到 cell 的样本 |
| 3 | 停机识别 | 用推力和扭矩识别不应进入有效掘进统计的样本 |
| 4 | 3σ 异常过滤 | 仅对非停机样本标记异常点，避免极端值污染稳态统计 |
| 5 | 有效掘进样本识别 | 保留非停机、非异常且核心字段有效的样本 |
| 6 | 连续有效掘进区间切分 | 避免孤立样本和短时过渡被当作稳定施工 |
| 7 | 稳态段识别 | 在连续有效区间内识别相对稳定运行片段 |
| 8 | 10 m cell 汇总 | 输出 cell 级施工响应证据 |

### 5.1 停机识别

当前停机识别采用工程规则：

```text
shutdown_i = (F_i <= 0) OR (T_i <= 0)
```

其中 F_i 表示推力，T_i 表示刀盘扭矩。这个规则只用于识别不应进入有效掘进统计的停机样本，不用于判断停机原因。系统明确保留边界：当前 PLC 字段未区分计划停机与非计划停机，因此 stop_ratio 只能作为施工响应关注信号，不能直接写成异常停机原因。

### 5.2 3σ 异常点过滤

3σ 过滤只对非停机样本进行。对某个核心参数 x，计算：

```text
lower_x = mean(x) - 3 × std(x)
upper_x = mean(x) + 3 × std(x)
```

若样本满足 `x_i < lower_x` 或 `x_i > upper_x`，则标记为异常点。样本不足时不强行计算，当前口径是有效样本数不足 30 时跳过该字段的 3σ 过滤。

### 5.3 有效掘进样本

有效掘进样本需要满足：非停机、非异常点、推力有效、扭矩有效、推进速度有效、刀盘转速有效、里程有效。如果已有 is_working 标记，则也要求 is_working=True。这个逻辑比早期简单的“推进速度 > 0、推力 > 0、扭矩 > 0、转速 > 0”更稳健，因为它先排除了停机和异常，再识别有效掘进。

### 5.4 连续有效掘进区间

有效样本不会孤立使用，而是按时间和里程连续性切成 working interval。新区间通常在当前样本有效且前一个有效样本不存在、前一个样本无效、出现明显时间断点或里程异常跳变时开始。过短区间被标记为过渡区间，默认阈值为最小样本数 20、最小持续时间 30 秒。

### 5.5 稳态段识别

系统在连续有效掘进区间内进一步识别稳态段。当前优先使用推进速度作为稳态检测信号，只有当推进速度不可用时才使用贯入度作为 fallback 信号。稳态识别逻辑可以概括为：

```text
y20_i = rolling_mean(y_i, window=20)
threshold = 0.8 × median(y20_i)
steady_candidate_i = y20_i >= threshold
```

如果出现多个候选稳态段，选择优先级是：样本数最多、持续时间最长、覆盖里程最长、出现最早。默认参数为 rolling window = 20，steady threshold factor = 0.8，最小稳态样本数 = 20，最小稳态持续时间 = 30 秒。

### 5.6 10 m cell 稳态指标

稳态段识别后，系统把样本投影到 10 m 里程 cell，并输出下列施工响应证据。

| 中文含义 | 字段 |
|---|---|
| 稳态是否可用 | steady_state_available |
| 稳态样本数 | steady_sample_count |
| 稳态样本占比 | steady_ratio |
| 稳态/有效掘进占比 | steady_to_working_ratio |
| 稳态速度均值/标准差/变异系数 | steady_speed_mean / steady_speed_std / steady_speed_cv |
| 稳态推力均值/标准差/变异系数 | steady_thrust_mean / steady_thrust_std / steady_thrust_cv |
| 稳态扭矩均值/标准差/变异系数 | steady_torque_mean / steady_torque_std / steady_torque_cv |
| 稳态转速均值/标准差/变异系数 | steady_rpm_mean / steady_rpm_std / steady_rpm_cv |
| 稳态贯入度均值/标准差/变异系数 | steady_penetration_mean / steady_penetration_std / steady_penetration_cv |
| 刀盘负载 proxy | steady_cutterhead_power_proxy |
| 推力-贯入关系 proxy | steady_thrust_per_penetration |
| 扭矩-贯入关系 proxy | steady_torque_per_penetration |

这些 proxy 只能解释为施工响应 proxy，不能写成严格物理功率、严格比能或地质风险判断。

---

## 6. 施工范围：实际推进范围和 cell 对齐范围

项目中有两个容易混淆但必须严格区分的范围：PLC 实测推进范围和 cell 对齐复核范围。

| 范围 | 字段 | 含义 | 是否可用于实际进尺 |
|---|---|---|---|
| PLC 实测推进范围 | daily_plc_range / daily_chainage_raw | 当天 PLC 真实记录到的推进起止里程和推进量 | 是 |
| cell 对齐复核范围 | daily_excavated_scope | 为按 10 m cell 复核而对齐后的范围 | 否 |

以 2023-12-30 为例：

| 项目 | 数值 | 含义 |
|---|---:|---|
| daily_chainage_min | 1014601.0 | PLC 实测起点 |
| daily_chainage_max | 1014616.0 | PLC 实测终点 |
| daily_advance_m | 15.0 | 实际日推进量 |
| daily_excavated_scope | 1014600.0 - 1014620.0 | 10 m cell 对齐复核范围 |

正确表述是：“PLC 实测推进范围为 1014601.0 至 1014616.0，日推进约 15.0 m；系统按 10m cell 将已掘复核范围对齐为 1014600.0 至 1014620.0。”错误表述是：“本日由 1014600.0 推进至 1014620.0，共推进 20m。”系统用 E14 专门检查这类错误。

---

## 7. 地质证据治理与三类证据角色

地质证据治理的核心不是把证据直接交给 LLM，而是先回答三个问题：证据在报告日期是否可用，证据在空间上是否相关，证据在报告中应该扮演什么角色。

| 证据角色 | 中文含义 | 可以写什么 | 禁止写什么 |
|---|---|---|---|
| daily_review | 已掘复核 | 当日已掘区段复核、地质-施工响应耦合关注 | 不得写成前方预测 |
| forward_attention | 前方关注 | 当前掌子面前方关注提示、谨慎建议 | 不得写成已揭露事实，不得使用 PLC / RAI / GRCI |
| local_background | 局部背景 | 邻近地质上下文 | 不得作为当日结论或高 GRCI 依据 |
| excluded | 排除证据 | 不进入日报主证据链 | 不得用于生成结论 |

这层设计是系统避免“前方提示事实化”和“背景证据结论化”的关键。

---

## 8. ConstructionStateCell：核心状态单元

ConstructionStateCell 是项目的基本状态单元。可以把它理解成一个 10 m 里程小格子，里面同时装入 PLC 响应、地质证据、气体信息、关注指标和 trace 信息。

| 状态层 | 内容 |
|---|---|
| 位置状态 | cell_start、cell_end、cell_center、distance_to_face |
| 角色状态 | daily_review / forward_attention / local_background |
| PLC 响应 | speed、thrust、torque、RAI、steady-state metrics |
| 地质状态 | GRS、hazards、fused_grade、source_trace |
| 耦合状态 | GRCI、coupling_level、available reason |
| 证据追踪 | supporting_evidence_ids、trace_refs |
| 可用性 | has_plc_response、has_geology_evidence、GRS_available、GRCI_available |

ConstructionStateCell 解决了三个数据粒度不一致的问题：PLC 是时间序列，地质证据是空间区段，日报是自然语言文本。通过 cell，三者有了共同的里程坐标。

---

## 9. DailyConstructionTwin：施工状态孪生底座

DailyConstructionTwin 是当天所有 ConstructionStateCell 的结构化汇总。它不是物理仿真型数字孪生，不模拟 TBM-围岩力学过程，而是面向施工日报生成和审计的证据治理型施工状态孪生。

| 组成 | 含义 |
|---|---|
| scope | 当日 PLC 实测范围、cell 对齐复核范围、当前掌子面、forward 范围、background 范围 |
| cells | 全部 TwinCellView |
| daily_review_cells | 已掘复核 cell |
| forward_attention_cells | 前方关注 cell |
| local_background_cells | 背景 cell |
| high_grci_cells | 已掘复核范围内 GRCI 可用的高关注 cell |
| summaries | operation、response、geology、forward、gas、coupling、quality 摘要 |
| trace_index | cell、证据、source_trace 的索引 |
| governance | 角色边界、指标边界、allowed / forbidden claims |

它的作用是让 Evidence Pack、LLM、Quality 和 Trace 都面对同一个结构化状态对象。

---

## 10. RAI、GRS 与 GRCI

### 10.1 RAI：施工响应关注度

RAI 表示 PLC 施工响应关注程度，公式为：

```text
RAI = 0.40 × stop_ratio
    + 0.25 × abnormal_ratio
    + 0.20 × speed_drop_score
    + 0.10 × torque_volatility_score
    + 0.05 × speed_volatility_score
```

| 分量 | 中文含义 |
|---|---|
| stop_ratio | 停机比例 |
| abnormal_ratio | 异常样本比例 |
| speed_drop_score | 速度下降分数 |
| torque_volatility_score | 扭矩波动分数 |
| speed_volatility_score | 速度波动分数 |

RAI 不是异常原因、不是地质风险、不是灾害概率，也不是故障概率。它只说明这个已掘 cell 的 PLC 施工响应值得关注。

### 10.2 GRS：地质证据关注度

GRS 表示已有地质证据对 cell 的关注程度，公式为：

```text
GRS = 0.45 × grade_score_component
    + 0.45 × hazard_component
    + 0.10 × confidence_component
```

| 分量 | 中文含义 |
|---|---|
| grade_score_component | 围岩等级关注 |
| hazard_component | 地质 hazard 标签关注 |
| confidence_component | 证据置信度 |

GRS 为 0 不一定代表地质条件好，也可能表示没有可用空间相关地质证据。因此解释 GRS 时必须同时看 GRS_available、GRS_unavailable_reason 和 has_geology_evidence。

### 10.3 GRCI：已掘区段地质-施工响应耦合关注度

GRCI 只用于已掘复核 daily_review cell，公式为：

```text
GRCI = 0.55 × GRS
     + 0.35 × RAI
     + 0.10 × GRS × RAI
```

GRCI 的含义是：在已掘区段内，地质证据关注和施工响应关注是否在同一 cell 中共同出现。它只有在 cell_role = daily_review、has_plc_response = True、RAI 存在且 GRS_available = True 时才可用。

| GRCI 范围 | 等级 |
|---|---|
| >= 0.75 | high |
| 0.50 - 0.75 | medium |
| 0.25 - 0.50 | low |
| < 0.25 | none |

GRCI 不是灾害概率，不是风险概率，不是前方风险，也不是因果证明。

---

## 11. Evidence Pack：LLM 真正看到的材料包

Evidence Pack 是从 DailyConstructionTwin 派生出的报告材料包。它不是原始数据库，而是经过治理后的、带有证据角色和边界约束的报告输入。

| 模块 | 内容 |
|---|---|
| report_scope | 日期、PLC 实测范围、cell 对齐范围、当前掌子面、前方范围 |
| operation_evidence | PLC 运行摘要 |
| gas_evidence | 气体监测摘要 |
| geology_evidence | key_cells、selected_cells、daily review、forward、background |
| daily_review_evidence | 已掘复核 cell |
| forward_attention_evidence | 前方关注 cell 和 forward profile |
| background_context_evidence | 局部背景 cell |
| coupling_evidence | high_grci_cells 和 coupling 说明 |
| evidence_units | 原子证据单元 |
| generation_constraints | 报告生成约束 |
| metric_boundaries | RAI、GRS、GRCI、proxy 的解释边界 |
| forbidden_claims | 禁止表达 |

### 11.1 EvidenceUnit

EvidenceUnit 是 Evidence Pack 中的原子证据单元。它描述某个 cell 或证据片段能支撑什么、不能支撑什么。

| 字段 | 中文含义 |
|---|---|
| evidence_id | 证据编号 |
| source_type | 来源类型 |
| time_scope | 时间范围 |
| spatial_scope | 空间范围 |
| role | 证据角色 |
| entity | 证据实体 |
| state | 状态 |
| certainty | 确定性 |
| support_value | 支撑值 |
| allowed_expression | 允许表达 |
| source_ref | 来源引用 |

### 11.2 Evidence Pack 选择分数

进入 Evidence Pack 的 cell 不是随机选择，而是按角色计算 selection_score。

| 角色 | selection_score |
|---|---|
| daily_review | 0.40 × GRCI + 0.25 × RAI + 0.25 × GRS + 0.10 × trace_completeness |
| forward_attention | 0.45 × GRS + 0.25 × forward_distance_weight + 0.30 × trace_completeness |
| local_background | 0.50 × GRS + 0.50 × trace_completeness |

这里再次强调：forward_attention 的选择分数不使用 GRCI。

---

## 12. LLM 后端通用链路

后端通用 LLM 生成器支持 template、evidence_pack_llm、evidence_pack_llm_with_revision、evidence_pack_planner_llm、evidence_pack_planner_llm_with_revision 五类模式。

| 模式 | 流程 | 是否调用 LLM |
|---|---|---|
| template | Evidence Pack → 固定模板 → 审计 | 否 |
| evidence_pack_llm | Evidence Pack → generation prompt → LLM draft → 审计 | 是 |
| evidence_pack_llm_with_revision | LLM draft → 初评 → revision prompt → 修订稿 → 复评 | 是 |
| evidence_pack_planner_llm | Evidence Pack → Planner → Plan Validation → Generator | 是 |
| evidence_pack_planner_llm_with_revision | Planner → Generator → 初评 → Reviser → 复评 | 是 |

这个通用链路说明项目不仅有“生成”，还有“生成前计划”和“生成后修订”。

---

## 13. Planner、Generator 与 Reviser

### 13.1 Planner

Planner 不写日报正文，它写报告生成计划。计划内容包括章节、每章目的、允许使用的证据角色、允许使用的指标、禁止表达和写作策略。

| Plan 内容 | 示例 |
|---|---|
| section_title | 前方地质关注提示 |
| allowed_cell_roles | forward_attention |
| allowed_metrics | GRS、main_hazards、distance_to_face |
| forbidden_claims | forward_as_fact、GRCI_probability |
| evidence_use_policy | 前方关注只写提示，不写已发生事实 |

Planner 输出后要经过验证。验证内容包括：是否缺标准章节、前方章节是否允许 RAI/GRCI、GRCI 是否出现在非 daily_review 章节、local_background 是否被写成当日异常、是否引用 excluded evidence、是否包含 GRCI 非概率边界、是否包含 forward 非事实边界、是否包含 daily_excavated_scope 非实际推进边界。

如果 LLM 生成的 plan 不合格，系统退回规则 plan。

### 13.2 Generator

Generator 根据 Evidence Pack 和可选 report plan 生成报告初稿。它不能新增 Evidence Pack 外的证据，不能自行计算 RAI/GRS/GRCI，不能把前方证据写成已发生事实，不能把 GRCI 写成概率，不能把 proxy 写成严格物理量。

### 13.3 Reviser

Reviser 不是润色器，而是错误反馈修订器。它接收 draft_report、quality_before_revision、trace_before_revision、boundary violations 和 Evidence Pack constraints，然后删除无证据句、降级过强判断、纠正数值不支撑、纠正前方事实误用、纠正 GRCI 概率化，并保留标准章节。

---

## 14. Exp02 中的 M0-M4

Exp02 是论文实验脚本中的生成模式对比。它和后端通用 LLM 链路有关，但不是完全同一个入口。

| 模式 | 中文含义 | 输入与机制 |
|---|---|---|
| M0_template_only | 模板基线 | 使用主 pipeline 的模板报告，不调用 LLM |
| M1_direct_llm | 直接 LLM | 只给日期、scope、operation、gas 简要信息 |
| M2_raw_evidence_llm | 原始证据 LLM | 给 operation、gas、normalized evidence、forward profile 和若干 preview |
| M3_twin_evidence_pack_llm | Evidence Pack LLM | 给压缩后的 Evidence Pack，但不做修订 |
| M4_full_twin_governance_trace_boundary_reviser | 完整闭环 | Evidence Pack + governance + Quality/Trace/Boundary feedback + revision |

M4 的流程是：先跑 no-LLM baseline 取得 Evidence Pack 和 Twin，再用 M4 full generation prompt 生成初稿，然后做 Quality / Trace / Boundary 初评，构造 revision_feedback，再用 M4 revision prompt 修订，最后经过 Section Guard 和复评。

需要特别说明：后端有独立 JSON Planner 能力，但 Exp02 主实验中的 M4 主要体现为 prompt 内规划约束和 revision 闭环，不应误写成每次都调用独立 JSON planner，除非实验配置确实这样运行。

---

## 15. Section Guard

M4 修订阶段曾出现过“修订后报告过度压缩、缺章”的问题，因此加入 Section Guard。它检查报告是否包含 9 个标准章节。

| 标准章节 |
|---|
| 综合摘要 |
| 总体概况 |
| 工况统计 |
| 聚类状态与效率分析 |
| 掌子面与地质揭示 |
| 已掘区段地质-施工响应复核 |
| 气体监测 |
| 前方地质关注提示 |
| 结论与施工建议 |

如果缺章，系统不会从初稿复制旧正文，而是补安全占位句：“当前 Evidence Pack 未提供足够证据，不作扩展判断。”这样既保留结构，又避免把初稿里的 unsupported 或 numeric 错误重新带回来。

---

## 16. 评价体系总览

评价体系不是一个分数，而是一条多层审计链：报告文本先被 Claim Extractor 切成主张，再由 Grounding Checker 检查证据支撑，由 Quality Checker 汇总结构、数值和禁用表达问题，由 Boundary Checker 检查工程边界违规，最后由 Structured Trace 汇总主张、证据和错误类型。

| 层级 | 作用 |
|---|---|
| Claim Extractor | 从报告中抽取可检查的 claim |
| Grounding Checker | 判断 claim 是否有 Evidence Pack / Twin 支撑 |
| Quality Checker | 计算质量分、检查缺章、禁用词、数值和 grounding |
| Boundary Checker | 检查 GRCI 概率化、前方事实化、proxy 误用等边界错误 |
| Structured Trace | 汇总 claim、support type、mismatch type 和 trace 覆盖 |
| Experiment Aggregation | 汇总每个 date/mode 的实验指标 |

---

## 17. Claim Extractor

Claim Extractor 把自然语言报告切分成结构化主张。每条 claim 包含 claim_id、claim_text、claim_type、entity、value、unit、time_scope、range_dk、relative_range、hazards、metrics、gases、spatial_scope、claim_role、certainty 和 source_sentence_index 等信息。

这一步的意义是：报告不能只作为一整段文本评价，而要拆成一条条可以追溯、可以匹配证据、可以判断边界的主张。

---

## 18. Grounding Checker

Grounding Checker 根据 Evidence Pack 和 Twin 检查每条 claim 是否有证据支撑。它会读取 key_cells、forward_segments、gas_summaries、coupling_evidence、operation_evidence、cluster_evidence 和 allowed_hazards。

| 输出字段 | 含义 |
|---|---|
| grounded | 是否有证据支撑 |
| support_type | 支撑类型 |
| trace_support_type | 更细粒度支撑类型 |
| supporting_evidence_ids | 支撑证据编号 |
| source_trace | 来源追踪 |
| messages | 解释信息 |
| suggestions | 修改建议 |
| mismatch_type | 不匹配类型 |

常见 support_type 包括 daily_review_support、forward_attention_support、local_background_support、statistical_support、observed_support、forecast_support、policy_support、recommendation_policy 和 none。常见 mismatch_type 包括 missing_evidence、scope_mismatch、role_mismatch、numeric_or_metric_mismatch、overclaim 和 policy_boundary。

---

## 19. Quality Checker

Quality Checker 是综合评分器。它检查禁用词、强灾害词越界、GRCI 概率化、前方事实误用、气体字段误用、stop_ratio 因果误用、daily_excavated_scope 误写为实际推进、缺失章节、grounding rate 过低和 required facts 覆盖不足。

质量分采用扣分制：

```text
quality_score = 100
                - forbidden/error 扣分
                - warning 扣分
                - missing section 扣分
                - low grounding rate 扣分
```

当前配置口径为：

| 项目 | 扣分或阈值 |
|---|---:|
| forbidden_error | 15 |
| warning | 5 |
| missing_section | 3 |
| unsupported_claim | 8 |
| low_grounding_rate | 10 |
| minimum_ok_score | 80 |
| grounding_rate < 0.6 | 额外扣 20 |
| grounding_rate < 0.8 | 额外扣 10 |

Quality Checker 要求的标准章节与 Section Guard 一致，共 9 个章节。

---

## 20. Boundary Checker

Boundary Checker 专门检查工程语义越界。

| 类型 | 含义 |
|---|---|
| grci_probability_misuse | GRCI 被写成灾害概率或风险概率 |
| forward_fact_misuse | 前方关注被写成已发生事实 |
| plc_proxy_misuse | proxy 被写成真实物理量 |
| stop_causality_misuse | stop_ratio 被写成异常原因 |
| local_background_scope_misuse | 背景证据被写成当日结论 |

如果句子是明确的边界声明，例如“GRCI 不是灾害概率”“前方关注提示不是已发生事实”“proxy 不是严格物理量”，系统不会把它当成违规。

---

## 21. Structured Trace

Structured Trace 汇总报告主张和证据之间的关系。它输出 raw_claim_count、excluded_non_trace_claim_count、claim_trace_count、grounded_claim_count、unsupported_claim_count、trace_coverage、support_type_distribution、claim_type_distribution、source_role_distribution、source_type_distribution、unsupported_by_claim_type、support_status_distribution 和 mismatch_type_distribution。

它回答的是：报告有多少句被抽成 claim，多少句有证据，unsupported 主要是哪类，支撑来自 daily_review 还是 forward_attention，错误主要是缺证据、角色错还是数值错。

---

## 22. 错误类型 E1-E14

| 编号 | 含义 |
|---|---|
| E1 | 无证据主张 |
| E2 | 前方预报写成已发生事实 |
| E3 | GRCI 写成概率 |
| E4 | forward 写成已掘复核 |
| E5 | background 写成当日响应 |
| E6 | 气体字段误用 |
| E7 | 无证据建议 |
| E8 | 缺失必要章节 |
| E9 | 证据角色混淆 |
| E10 | 数值无证据 |
| E11 | 标题误抽取 |
| E12 | 方法边界说明 |
| E13 | stop_reason 过度解释 |
| E14 | 对齐复核范围误写为实际推进 |

E14 是本项目很重要的错误类型，因为它直接针对 TBM 日报中常见的数值语义错误。

---

## 23. Exp02 说明了什么

Exp02 是生成模式对比实验。它回答的是：为什么不能直接让 LLM 写，为什么只给原始证据还不够，为什么 Evidence Pack 还需要 revision，完整治理闭环是否有效。

91 天 structured_trace_v1 真实 LLM 回归结果如下：

| 模式 | 质量 | 支撑率 | unsupported | numeric | boundary | missing |
|---|---:|---:|---:|---:|---:|---:|
| M0 模板 | 100.00 | 1.0000 | 0 | 0 | 0 | 0 |
| M1 直接 LLM | 70.76 | 0.7295 | 1143 | 445 | 10 | 182 |
| M2 原始证据 LLM | 72.96 | 0.7253 | 1221 | 334 | 23 | 182 |
| M3 Evidence Pack LLM | 68.93 | 0.7592 | 1256 | 226 | 2 | 184 |
| M4 完整闭环 | 94.18 | 0.9153 | 376 | 78 | 0 | 0 |

M4 修订前 unsupported 为 637，修订后为 376，减少 261，降低 40.97%。这说明 Reviser 不是装饰性润色，而是实际减少了无证据主张。

---

## 24. Exp03 说明了什么

Exp03 针对 RAI / GRS / GRCI 的权重主观性问题。当前指标是启发式权重，因此项目做了旁路复算，包括 V0_current、V1_percentile_equal、V2_percentile_interaction、V3_percentile_entropy、V4_percentile_critic 和 V5_strict_min。

比较指标包括 Spearman rank correlation、Top-K Jaccard、high attention date overlap 和 forward GRCI leakage。结论应谨慎表达为：当前 V0 指标在排序层面具有一定稳健性，高关注 cell 精确选择对耦合公式仍有敏感性，GRCI 仍应作为启发式复核关注指标，而不是灾害预测模型。

---

## 25. API 和前端角色

当前 API 主要包括 GET /api/tbm/health、GET /api/tbm/dates、POST /api/tbm/report 和 POST /api/tbm/report/debug。普通 report 接口返回 report_text、quality_summary、trace_summary、high_grci_cells、forward_profile 和 warnings。debug 接口返回 Evidence Pack、ConstructionStateCells、DailyConstructionTwin、Quality、Trace、Boundary 和 Raw JSON。

前端只是展示工作台，不计算 GRCI，不处理 PLC，不拼 Evidence Pack，不判断 forward cell。

---

## 26. 当前系统能支撑什么结论

| 能支撑的结论 |
|---|
| TBM 施工日报生成应被建模为多源证据约束生成问题，而不是自由文本生成问题。 |
| ConstructionStateCell 可以作为 PLC、地质、气体和报告文本之间的统一中间层。 |
| DailyConstructionTwin 能把当日施工状态组织成可查询、可导出、可审计的证据底座。 |
| Evidence Pack 能限制 LLM 输入范围，并明确证据角色和指标边界。 |
| Quality / Grounding / Boundary / Structured Trace 能自动发现一部分无证据、数值、边界和结构问题。 |
| M4 完整治理闭环在本工程 91 天真实 LLM 回归中明显优于 M1/M2/M3。 |
| Reviser 能有效降低 unsupported claim。 |
| Exp03 能缓解 RAI/GRS/GRCI 权重主观性的质疑。 |

---

## 27. 当前系统不能声称什么

| 不能声称的内容 | 原因 |
|---|---|
| 实现了 TBM 地质灾害预测 | 系统没有灾害标签和预测模型 |
| GRCI 是灾害概率 | GRCI 是启发式耦合关注度 |
| LLM 判断地质风险 | LLM 只组织和修订文本 |
| forward_attention 是前方已发生事实 | forward_attention 只表示关注提示 |
| PLC proxy 是严格物理功率或比能 | 当前仅为 proxy |
| 系统已经跨工程泛化 | 当前主要是单工程 91 天验证 |
| 自动评价完全替代人工评价 | Quality/Trace 是规则化自动评价 |
| RAI/GRS/GRCI 权重已经专家标定 | 当前是工程启发式权重，并通过 Exp03 做稳健性检查 |

---

## 28. 导师可能继续追问的问题

| 问题 | 建议回答 |
|---|---|
| Planner 到底是不是主实验的一部分？ | 后端有独立 JSON Planner 能力；Exp02 主实验 M4 主要使用 prompt 内规划约束和 revision 闭环。论文中应区分“规划约束”和“独立 Planner 调用”。 |
| M3 为什么 Evidence Pack 后 unsupported 仍高？ | Evidence Pack 提供更多结构化细节，提高相关性，但没有 revision、section guard 和 feedback；LLM 复述越多，越容易产生 unsupported 和 numeric。 |
| M0 质量 100 是否说明模板最好？ | 不是。M0 是确定性模板基线，几乎不自由发挥，不能代表自然语言生成能力。 |
| Quality score 是人工质量吗？ | 不是。它是自动规则评价，衡量结构、证据、数值和边界，仍需要人工复核。 |
| GRCI 为什么可信？ | GRCI 不被解释为灾害概率，只是复核关注排序；Exp03 做了多版本稳健性分析，但仍是启发式指标。 |

---

## 29. 当前薄弱但可控的地方

| 薄弱点 | 当前应对 |
|---|---|
| RAI/GRS/GRCI 权重主观 | Exp03 稳健性分析 |
| 自动评价不能替代人工 | 后续补人工复核 |
| 单工程数据 | 论文中限定为本工程 91 天 |
| LLM 输出仍有残余 unsupported | 作为残余问题和案例分析 |
| PLC proxy 非严格物理量 | 明确写 proxy，不写物理功率 |
| Planner 表述容易混淆 | 区分通用 planner 和 Exp02 prompt planning |
| 地质 evidence_db 质量依赖解析规则与人工复核 | 说明系统做的是报告级证据结构化，不重新解释原始 TSP/HSP 信号 |

---

## 30. 最推荐的讲法

推荐表述：

> 本文提出一种面向 TBM 施工日报的多源工程证据治理与可追溯大模型生成方法。方法首先通过 PLC 预处理、地质证据库建立和地质证据时空筛选构建 10 m 施工状态单元；然后以 DailyConstructionTwin 组织已掘复核、前方关注和局部背景三类证据角色；再通过 Evidence Pack 将可写证据、指标边界和禁止表达传递给模板或大模型；最后利用 Quality、Grounding、Boundary 和 Structured Trace 对生成报告进行逐句审计与反馈修订。91 天真实 LLM 实验表明，完整治理闭环显著优于直接 LLM、原始证据输入 LLM 和仅 Evidence Pack LLM。

不推荐表述：

| 不推荐说法 | 原因 |
|---|---|
| 我们用 LLM 自动写 TBM 日报 | 太弱，掩盖了证据治理和审计框架 |
| 我们用 GRCI 预测地质风险 | 错误，GRCI 不是预测概率 |
| 我们用 PLC 判断前方异常 | 错误，PLC 只用于已掘响应 |
| 我们实现了数字孪生仿真 | 不准确，当前是证据治理型状态孪生 |
| 我们证明了跨工程泛化 | 当前没有跨工程验证 |

---

## 31. 给老师看的最短版总结

这个项目的核心不是大模型本身，而是大模型前后的工程证据治理链。前端输入的 PLC 和地质资料先被整理为 10 m 级施工状态单元；每个单元中明确区分已掘复核、前方关注和局部背景三类角色，并计算 RAI、GRS、GRCI 等启发式关注指标。DailyConstructionTwin 将这些 cell 汇总成当天的施工状态孪生底座，再派生 Evidence Pack 作为报告生成的唯一证据输入。

LLM 在系统中只负责受控文本组织和修订，不直接读取原始 PLC 或完整 evidence_db，也不计算指标或判断地质风险。生成后的报告会被拆成 claim，并通过 Grounding、Quality、Boundary 和 Structured Trace 检查证据支撑、数值一致性、角色边界和章节完整性。

91 天真实 LLM 对比实验表明，完整的 Evidence Pack + governance + trace + revision 闭环，比直接 LLM、原始证据 LLM 和仅 Evidence Pack LLM 更稳定，unsupported、numeric、boundary 和缺章问题显著减少。

---

## 32. 下一步建议

当前不建议优先继续堆功能，更重要的是固定口径并补足论文可信度材料。建议顺序为：固定 structured_trace_v1 实验口径；补人工复核样本；统一论文中 Planner / M4 的表述；把 Exp02、Exp03、PLC preprocessing 写成正式方法和实验章节；选择 1 个主案例和 1 个残余问题案例做深入分析；明确所有边界，包括单工程、启发式指标、自动评价和非物理仿真。
