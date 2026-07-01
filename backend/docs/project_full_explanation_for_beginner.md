# TBM 施工状态数字孪生与日报生成项目完整说明

> 本文档面向第一次接触本项目的人，目标是用“人话”把项目从数据输入到报告输出的全流程讲清楚。  
> 它不是代码审计清单，也不是论文正文，而是一份帮助理解系统逻辑、模块边界和方法含义的总说明。

---

## 0. 给新读者的最短说明

### 一句话版本

本项目把 TBM 当日 PLC 运行数据和 TSP/HSP/掌子面素描等地质证据整理成 10m 里程单元，构建施工状态数字孪生，再用证据包约束模板或大模型生成施工日报，并用质量、追踪和边界检查核验报告是否有证据支撑。

### 五句话版本

1. 后端先读取某一天的 TBM PLC 日运行 CSV 和正式地质证据库。
2. PLC 数据被清洗、识别工况、统计气体，并投影到 10m 里程单元，形成施工响应证据。
3. 地质证据经过标准化、时间可用过滤和日报范围筛选后，也投影到相同的 10m 单元。
4. 每个单元形成一个 `ConstructionStateCell`，里面同时放 PLC 响应、地质证据、证据追踪、RAI/GRS/GRCI 和角色边界。
5. 系统再构建 `DailyConstructionTwin` 和 Evidence Pack，用模板或 LLM 生成报告，并检查报告是否乱写、越界或缺少证据。

### 一页版

这个项目不是一个“让大模型自由写日报”的系统，而是一个“先治理施工证据，再约束生成，再核验报告”的后端研究原型。它的核心对象不是日报文本，而是按里程单元组织好的施工状态证据。

系统每天读取一份 PLC 日运行数据。PLC 里包含时间、里程、掘进状态、推进速度、推力、刀盘扭矩、刀盘转速、贯入度、气体监测等字段。代码先做数据质量检查，再识别工作、停机、过渡和异常工况，统计运行时长、气体超限情况和聚类状态。之后，PLC 会按 10m 里程单元聚合，形成每个 cell 的施工响应指标。现在还加入了论文式 PLC 预处理：识别停机样本、异常点、有效掘进区间和稳态段，并输出稳态推进速度、推力、扭矩、转速、贯入度、波动系数和若干 proxy 指标。这些增强指标只是解释施工响应，不替代 RAI，不直接判断地质风险。

地质证据来自正式 evidence_db，包括 TSP、HSP、掌子面素描和其他扩展资料。系统先把这些证据标准化，再按报告日期过滤掉未来证据，避免信息泄漏。之后，系统根据当日 PLC 实测推进范围、当前掌子面、前方 30m 和局部背景范围，只保留日报相关证据。旧的全局地质 cell 不再作为日报主流程。地质证据被投影到 10m cell 后，融合出围岩等级、主要关注现象、置信度、不确定性、证据来源和 GRS。

PLC 与地质最后汇合到 `ConstructionStateCell`。这个对象有三种角色：`daily_review` 表示当日已掘复核单元，可以计算 GRCI；`forward_attention` 表示当前掌子面前方关注单元，只能用地质 GRS 和 source_trace 做提示，不能使用 PLC、RAI 或 GRCI；`local_background` 表示局部背景，只能作为上下文，不能当作当日结论。

系统中的三个关注指标含义很重要。RAI 是施工响应异常/关注度，不是设备故障概率；GRS 是地质证据关注度，不是灾害概率；GRCI 是已掘区段内地质证据和施工响应同时存在时的耦合关注度，不是前方风险，也不是灾害发生概率。只有 `daily_review` cell 同时有 GRS 和 RAI 时，才计算 GRCI。

日报生成时，系统先把 `ConstructionStateCell` 组织成 `DailyConstructionTwin`，再从 Twin 构建 Evidence Pack。Evidence Pack 不是简单拼接文本，而是把证据按“已掘复核、前方关注、局部背景”分层，并附带生成约束。模板报告直接根据 Evidence Pack 填充标准章节；LLM 模式则把 Evidence Pack 和约束交给大模型。M4 实验模式还会先检查初稿，再把 unsupported、numeric、boundary 等问题反馈给大模型修订。

最后，Quality Checker 检查章节、禁用表述、数值语义、GRCI 概率误用、前方事实误用等；Grounding Checker 检查报告 claim 是否能在 Evidence Pack 中找到支撑；Boundary Checker 检查 GRCI、forward、PLC proxy、stop_ratio、local_background 等方法边界是否被误用。报告输出不仅有 `report_text`，还带 Evidence Pack、Trace、Quality、Twin、high GRCI cells、forward profile 和 warnings。

---

## 1. 项目整体分层

可以把当前后端理解成八层：

```text
原始数据层
│
├─ PLC 日运行 CSV
├─ 正式 evidence_db 地质证据库
│
▼
数据读取与质量检查层
│
├─ 根据日期读取 PLC CSV
├─ 读取 evidence_db
├─ 检查字段、时间、里程、缺失情况
│
▼
PLC 施工响应层
│
├─ 工况识别：停机 / 过渡 / 稳定掘进 / 异常扭矩
├─ 聚类状态与效率统计
├─ 气体统计
├─ paper-based PLC preprocessing
└─ 10m cell_response_df
│
▼
地质证据治理层
│
├─ 地质证据标准化
├─ 时间可用过滤
├─ HSP 异常点去重
├─ 日报空间范围筛选
└─ cell 级地质融合
│
▼
施工状态单元层
│
└─ ConstructionStateCell
   ├─ daily_review
   ├─ forward_attention
   └─ local_background
│
▼
数字孪生与证据包层
│
├─ DailyConstructionTwin
└─ Prompt Evidence Pack
│
▼
报告生成层
│
├─ template/no-LLM
├─ Evidence Pack constrained LLM
├─ Planner LLM
└─ Revision LLM
│
▼
质量核验与导出层
  ├─ Quality Checker
  ├─ Grounding Checker
  ├─ Boundary Checker
  ├─ Trace Builder
  ├─ API 输出
  └─ 实验导出
```

代码依据：

| 层 | 主要文件 |
|---|---|
| API | `backend/app.py`, `backend/routes/report.py` |
| 主 pipeline | `backend/pipeline/daily_report_pipeline.py` |
| 输入 | `backend/pipeline/inputs.py`, `backend/utils/io_utils.py` |
| PLC | `backend/plc/response.py`, `backend/plc/cell_response.py`, `backend/plc/paper_based_preprocessing.py`, `backend/analysis/*` |
| 地质 | `backend/geology_v2/*`, `backend/pipeline/evidence_scope.py` |
| cell / coupling | `backend/schemas/pipeline.py`, `backend/coupling/grs_rai_grci.py` |
| Twin | `backend/twin/construction_twin.py`, `backend/schemas/twin.py` |
| Evidence Pack / report | `backend/llm/evidence_pack.py`, `backend/llm/llm_report_generator.py` |
| 检查 | `backend/llm/report_quality_checker.py`, `backend/llm/report_grounding_checker.py`, `backend/llm/twin_boundary_checker.py`, `backend/llm/report_trace_builder.py` |
| 实验 | `experiments/exp01_twin_full_run`, `experiments/exp02_llm_generation_modes`, `experiments/exp_plc_preprocessing_validation` |

---

## 2. 当前后端目录怎么理解

### 主流程目录

| 目录/文件 | 作用 |
|---|---|
| `backend/app.py` | FastAPI 应用入口，只注册日报相关路由 |
| `backend/routes/report.py` | 当前 API 路由，负责调用主 pipeline |
| `backend/pipeline/` | 每日主流程、输入读取、日报空间范围筛选 |
| `backend/plc/` | PLC 响应聚合与 paper-based preprocessing |
| `backend/analysis/` | PLC 工况、聚类、气体、质量检查等基础分析函数 |
| `backend/geology_v2/` | 当前主地质链路 |
| `backend/coupling/` | ConstructionStateCell 构建和 GRCI 计算 |
| `backend/twin/` | DailyConstructionTwin 构建 |
| `backend/llm/` | Evidence Pack、prompt、LLM 调用、报告质量和追踪检查 |
| `backend/schemas/` | Pydantic 数据结构 |
| `backend/scripts/` | smoke、导出、批量脚本 |
| `backend/tests/` | 后端契约测试 |

### 归档目录

`backend/_archive/` 里是旧路线、旧服务、旧 agent、旧 geology、旧测试等历史代码。当前主流程不应该从 `_archive/` import 任何内容。它的作用是保留历史参考，不参与现在的日报生成和实验结果。

---

## 3. 一天的日报到底怎么跑

主调用链：

```text
backend/app.py
  └─ register_report_routes(app)
     └─ POST /api/tbm/report 或 /api/tbm/report/debug
        └─ run_daily_report_pipeline(date, ...)
           ├─ load_daily_inputs(date)
           ├─ analyze_plc_response(df_plc)
           ├─ run_geology_v2_context(...)
           ├─ build_scope_summary(...)
           ├─ apply_spatial_relevance_filter(...)
           ├─ build_scope_cells(...)
           ├─ project_evidence_to_cells(...)
           ├─ fuse_geo_states(...)
           ├─ build_forward_profile(...)
           ├─ build_construction_state_cells(...)
           ├─ build_daily_construction_twin(...)
           ├─ build_evidence_pack_from_twin(...)
           ├─ build_prompt(...)
           ├─ build_template_report(...) 或 generate_llm_report(...)
           ├─ check_report_quality(...)
           ├─ build_report_trace(...)
           ├─ check_twin_boundary_violations(...)
           └─ DailyReportResult
```

普通接口 `/api/tbm/report` 返回给前端看的简版结果：

```text
date
report_text
quality_summary
trace_summary
forward_profile
high_grci_cells
generation_mode
llm_summary
warnings
```

调试接口 `/api/tbm/report/debug` 返回研究和排查用的完整中间结果，包括：

```text
operation_summary
cluster_summary
gas_summary
normalized_evidence_summary
construction_state_cells
prompt_evidence_pack
prompt_text
quality
trace
daily_construction_twin
twin_summary
twin_boundary_summary
time_valid_evidence
spatial_relevant_evidence
excluded_evidence
cell_response_records
geo_state_records
method_metrics
```

---

## 4. 输入数据是什么

### 4.1 PLC 日运行 CSV

PLC 数据按日期读取。日期接口会扫描 `tbm_data_YYYYMMDD.csv` 这类文件名，并转成 `YYYY-MM-DD`。

核心字段包括：

| 类别 | 典型字段 | 当前用途 |
|---|---|---|
| 时间 | `运行时间-time` | 排序、推断采样间隔、统计时长 |
| 里程 | `导向盾首里程`、`开累进尺` 等别名 | 当日推进范围、cell 分组 |
| 状态 | `掘进状态` | 初步工况识别 |
| 推进 | `推进速度`、`推进给定速度` | 工况、RAI、稳态识别 |
| 负载 | `推力`、`刀盘扭矩` | 工况、RAI、稳态负载 |
| 刀盘 | `刀盘实际转速`、`刀盘给定转速` | working-only 和稳态 proxy |
| 贯入 | `贯入度` | 贯入效率 proxy |
| 气体 | `CO2检测`、`H2S检测`、`SO2检测`、`NO2检测`、`NO检测`、`CH4检测` | 气体统计和阈值检查 |

字段映射由 `analysis/plc_contract.py` 管理。它把不同中文字段名或英文别名统一解析成标准键，例如 `advance_speed`、`thrust`、`torque`、`rpm`、`penetration`。

重要边界：

- PLC 字段单位并不完全由代码确认，部分单位需要依赖项目数据字典或现场说明。
- `cutterhead_power_proxy` 只是扭矩和转速相乘的 proxy，不是严格物理功率。
- `thrust_per_penetration`、`torque_per_penetration` 是负载-贯入关系 proxy，不是严格比能。

### 4.2 地质证据库

地质证据来自 `EVIDENCE_DB_PATH` 指向的 CSV，通常是正式 evidence_db。

系统支持的证据类型包括：

| 类型 | 当前系统中的角色 |
|---|---|
| TSP 超前地质预报 | 前方或局部背景证据，必须经过时间和空间筛选 |
| HSP 超前地质预报 | 前方或局部背景证据，异常点会做去重 |
| 掌子面素描 | 若日期和里程可用，可作为更接近现场揭示的证据 |
| 其他地质资料 | 通过标准化字段进入统一 evidence_df |

重要边界：

- 报告日期之后形成的证据不能进入当前日报。
- 当前掌子面之后才形成的素描不能用于当前日报。
- 超前预报只能写成“提示、关注、需复核”，不能写成现场已经揭露的事实。

---

## 5. PLC 处理逻辑详细说明

PLC 处理的主入口是：

```text
backend/plc/response.py::analyze_plc_response
```

它做五件事：

```text
PLC DataFrame
│
├─ check_plc_quality
├─ annotate_operation_mode
├─ annotate_routine_ring_building_stops
├─ detect_excavation_state + KMeans 聚类
├─ compute_gas_stats
└─ project_plc_response_to_cells
```

这里要特别说明：当前 PLC 处理已经不是简单依赖“推进速度 > 0、推力 > 0、刀盘扭矩 > 0、刀盘转速 > 0”的旧式判断。这个简单规则现在只保留在 `cell_response.py::_working_mask` 的 fallback 分支里。主线在进入 cell 聚合时会调用 `paper_based_preprocessing.py::apply_paper_based_preprocessing`，先识别停机样本、异常点、有效掘进样本、连续有效掘进区间和稳态段，再把稳态统计和 proxy 指标合并回 `cell_response_df`。

因此，PLC 层现在可以理解为三层：

| 层次 | 作用 | 主要输出 | 是否改变 RAI/GRCI |
|---|---|---|---|
| 基础工况层 | 生成 operation summary、停机时长、聚类和旧 RAI 所需基础状态 | `operation_mode`、`is_working`、`is_stopped`、`is_abnormal` | 不直接改变公式 |
| cell 响应层 | 按 10m cell 汇总原有施工响应分量 | `stop_ratio`、`abnormal_ratio`、`speed_drop_score`、`RAI` | 使用既有 RAI 公式 |
| paper-based preprocessing 层 | 论文式清洗与稳态段提取，用于增强 PLC 证据解释性 | `valid_excavation_mask`、`steady_*`、`*_proxy`、`plc_preprocessing_quality_grade` | 不替换 RAI，不改变 GRCI |

### 5.1 PLC 质量检查

质量检查读取字段、时间、里程范围和缺失情况，输出 `quality_report`。主流程从里面取：

```text
current_chainage
day_start_chainage
day_end_chainage
```

这三个值之后用于确定：

- PLC 实测推进范围；
- 当日已掘复核范围；
- 当前掌子面；
- 前方关注范围。

### 5.2 基础工况识别：保留，但不是完整 PLC 预处理

`analysis/dataprocess.py::annotate_operation_mode` 是基础工况生产者。

它把每行 PLC 记录分为：

| code | operation_mode | 含义 |
|---:|---|---|
| 0 | stop | 停机 |
| 1 | transition | 启动/过渡 |
| 2 | work | 稳定掘进 |
| 3 | abnormal | 异常扭矩类状态 |

它的大致逻辑是：

```text
若掘进状态为 0，记为 stop；
否则结合推力、推进速度、刀盘扭矩是否非零：
  推力和速度都有 -> work
  有推力但速度不足 -> transition
  无明显推力但扭矩存在 -> abnormal
  其他 -> stop 或 transition
```

注意：这是基础工程规则识别，不是有标签的监督学习分类，也不是当前 PLC enhanced fields 的完整依据。它主要服务：

- 运行概况统计；
- 工作/停机/过渡时长；
- 聚类前的基础样本筛选；
- 旧 RAI 分量中的停机、异常和速度下降统计；
- 与既有实验结果保持兼容。

真正用于增强 PLC 证据解释性的“有效掘进样本”和“稳态段”判断，发生在后面的 `paper_based_preprocessing.py`。当前 `_working_mask` 的优先级也是：如果 cell 样本里已经有 `valid_excavation_mask`，就优先使用它；只有缺少该字段时，才退回到“速度/推力/扭矩/转速 > 0”的旧 fallback。

### 5.3 常规停机候选

`annotate_routine_ring_building_stops` 会尝试识别可能是常规换步/拼装相关的停机候选。它看停机持续时间、里程漂移、前后是否有工作段、是否符合环长周期等。这部分输出用于解释，但当前 RAI 仍保留原有公式，没有因为这个候选直接重写停机项。

### 5.4 聚类状态

`analysis/excavation_state.py::detect_excavation_state` 在工作样本上用推力、扭矩、转速、推进速度做 KMeans 聚类，得到 `state_id`。后续会对每个状态做持续时间、效率和语义标签。

这部分的作用是描述“施工参数状态分组”，不是预测地质风险。

### 5.5 气体统计

`analysis/gas_analysis.py::compute_gas_stats` 统计 CO2、H2S、SO2、NO2、NO、CH4 的均值、最大值、最小值和阈值超限段。它还按工作/停机状态拆分统计。

重要边界：

- 气体字段单位有假设，代码中写了阈值，但实际字段可能是浓度，也可能是报警/检测量。
- 报告中不能把不确定单位的字段过度解释为真实浓度异常。

### 5.6 按 10m cell 聚合 PLC 响应

`plc/cell_response.py::project_plc_response_to_cells` 把 PLC 行按里程划分到 10m cell。

这个函数现在有一个关键步骤：

```text
project_plc_response_to_cells
│
├─ 解析时间、里程、推进速度、推力、扭矩、转速、贯入度等字段
├─ 生成 cell_start / cell_end / cell_id
├─ 调用 apply_paper_based_preprocessing
├─ 把 sample 级 valid_excavation_mask / paper_plc_stage 合并回 PLC 行
├─ 把 cell 级 steady-state metrics 合并进 cell_response_df
└─ 继续计算原有 RAI 分量和 working-only metrics
```

也就是说，cell 聚合不是先用简单 `>0` 规则筛一遍就结束。当前 cell 里同时保留三类 PLC 结果：

| 类型 | 字段示例 | 用途 |
|---|---|---|
| 全样本/基础统计 | `speed_mean`、`thrust_mean`、`torque_mean`、`stop_duration_min` | 描述 cell 当日整体施工响应 |
| 原 RAI 分量 | `stop_ratio`、`abnormal_ratio`、`speed_drop_score`、`torque_volatility_score` | 保持原有 RAI/GRCI 口径稳定 |
| 更新后的稳态增强指标 | `steady_speed_mean`、`steady_torque_cv`、`steady_penetration_mean`、`steady_cutterhead_power_proxy` | 用于解释有效掘进状态下的负载、波动和贯入效率 |

每个 cell 输出：

```text
sample_count
duration_min
work_duration_min
stop_duration_min
abnormal_duration_min
speed_mean
thrust_mean
torque_mean
rpm_mean
stop_ratio
abnormal_ratio
speed_drop_score
torque_volatility_score
speed_volatility_score
RAI
working-only metrics
steady-state metrics
```

### 5.7 RAI 的计算

当前 RAI 公式为：

```text
RAI =
  0.40 * stop_ratio
+ 0.25 * abnormal_ratio
+ 0.20 * speed_drop_score
+ 0.10 * torque_volatility_score
+ 0.05 * speed_volatility_score
```

含义：

| 分量 | 含义 |
|---|---|
| stop_ratio | cell 内停机时间占比 |
| abnormal_ratio | 异常工况时间占比 |
| speed_drop_score | 推进速度相对全日较高速度水平的下降程度 |
| torque_volatility_score | 扭矩波动程度 |
| speed_volatility_score | 速度波动程度 |

边界：

- RAI 是施工响应关注度，不是设备故障概率。
- stop_ratio 权重高，但当前 PLC 不能严格区分计划停机和非计划停机。
- 因此报告必须说明：stop_ratio 只作为施工响应关注信号，不能直接写成异常原因。

### 5.8 更新后的 paper-based PLC preprocessing：当前 PLC 解释性增强主线

当前新增的 PLC 预处理在：

```text
backend/plc/paper_based_preprocessing.py
```

它借鉴 TBM 参数预测论文中的数据清洗和稳态段提取思想，但不做预测模型。

它的入口是：

```text
backend/plc/paper_based_preprocessing.py::apply_paper_based_preprocessing
```

它不是旁路脚本，而是在主 cell 聚合函数中被调用：

```text
backend/plc/cell_response.py::project_plc_response_to_cells
  → apply_paper_based_preprocessing
  → sample-level flags
  → cell-level steady metrics
  → cell_response_df
  → ConstructionStateCell.plc_metrics
  → DailyConstructionTwin.response_state
  → debug/export/Evidence Pack 摘要
```

流程如下：

```text
PLC cell 原始样本
│
├─ 时间和里程质量检查
├─ 停机样本识别
├─ 3σ 异常点过滤
├─ 有效掘进样本识别
├─ 连续 working interval 切分
├─ 稳态段识别
└─ cell 级稳态指标汇总
```

更具体地说，它做了几类判断：

| 步骤 | 代码含义 | 结果 |
|---|---|---|
| 时间和里程质量检查 | 检查时间间隔、里程倒退、异常跳变 | 标记基础质量问题 |
| 停机样本识别 | 根据推力、扭矩、速度、转速接近 0 的情况区分停机/辅助停机 | `is_shutdown_segment`、`shutdown_reason` |
| 3σ 异常点过滤 | 对非停机状态下的核心连续参数做异常点识别 | `is_outlier`、`outlier_reason` |
| 有效掘进样本识别 | 排除停机、异常点、无效里程和无有效推进响应的样本 | `valid_excavation_mask` |
| 连续区间切分 | 将连续有效掘进样本切成 working interval，并剔除过短片段 | `working_interval_id`、`working_interval_is_valid` |
| 稳态段识别 | 用推进速度或贯入度等信号的滚动均值寻找稳定片段 | `paper_plc_stage=steady_state` |
| cell 级汇总 | 只在稳态样本上统计均值、标准差和变异系数 | `steady_*_mean/std/cv` |

主要输出：

| 字段 | 含义 |
|---|---|
| `is_shutdown_segment` | 是否停机样本 |
| `is_outlier` | 是否 3σ 异常点 |
| `valid_excavation_mask` | 是否有效掘进样本 |
| `working_interval_id` | 有效掘进连续区间编号 |
| `paper_plc_stage` | shutdown / abnormal_outlier / steady_state / startup 等 |
| `steady_state_available` | 是否识别到稳态段 |
| `steady_sample_count` | 稳态样本数量 |
| `steady_speed_mean/std/cv` | 稳态推进速度统计 |
| `steady_thrust_mean/std/cv` | 稳态推力统计 |
| `steady_torque_mean/std/cv` | 稳态扭矩统计 |
| `steady_rpm_mean/std/cv` | 稳态转速统计 |
| `steady_penetration_mean/std/cv` | 稳态贯入度统计 |
| `steady_cutterhead_power_proxy` | 扭矩×转速 proxy |
| `steady_thrust_per_penetration` | 推力/贯入度 proxy |
| `steady_torque_per_penetration` | 扭矩/贯入度 proxy |
| `plc_preprocessing_quality_grade` | A/B/C/D 质量等级 |

关键边界：

- 这些字段用于解释“已掘区段施工响应”，不是前方地质判断。
- 它们不会进入 forward_attention。
- 它们没有替换 RAI，也没有改变 GRCI 公式。
- proxy 字段必须带 proxy 语义，不能写成真实功率或严格比能。

所以，如果看到代码里仍有“推进速度、推力、扭矩、转速 > 0”的判断，不应理解为当前 PLC 处理仍停留在旧逻辑。当前真实优先级是：

```text
优先：paper-based preprocessing 生成的 valid_excavation_mask
其次：已有 is_working / is_stopped / operation_mode
最后：速度、推力、扭矩、转速 > 0 的 fallback
```

这个设计的意义是：在不改动 RAI/GRCI 历史口径的前提下，增加更可解释的 PLC 施工响应证据。论文里可以说“系统在 10m 里程单元内区分停机/异常/有效掘进样本，并提取稳态段下的负载、波动、贯入效率和 proxy 指标”；但不能说“系统用 PLC 指标直接判断前方地质风险”。

---

## 6. 地质证据处理逻辑

地质主链路入口：

```text
backend/geology_v2/pipeline.py::run_geology_v2_context
```

主流程为：

```text
evidence_db
│
├─ normalize_evidence_df
├─ filter_available_evidence
├─ deduplicate_hsp_anomaly_points
├─ build_chainage_cells
├─ project_evidence_to_cells
├─ fuse_geo_states
└─ build_forward_profile
```

### 6.1 证据标准化

标准化把不同来源的证据转换成统一字段，例如：

```text
evidence_id
source_type_norm
report_date / issue_date
start_chainage
end_chainage
center_chainage
face_chainage
grade
hazard_tags
water/collapse/deformation 状态
confidence_text
raw_text
```

### 6.2 时间可用过滤

`filter_available_evidence` 会根据报告日期过滤证据。原则是：

```text
报告日期之后形成的证据不能进入当前日报。
```

这一步解决未来信息泄漏。

### 6.3 HSP 异常点去重

HSP 可能把同一异常拆成多个近似点。`deduplicate_hsp_anomaly_points` 通过里程容差等规则减少重复异常点对 cell 的重复贡献。

### 6.4 日报空间范围筛选

这是当前地质主线和旧版全局 cell 最大的差别。

`pipeline/evidence_scope.py::build_scope_summary` 会根据 PLC 当日推进范围和当前掌子面构建日报范围：

```text
daily_plc_range:
  PLC 实测当日推进范围

daily_excavated_scope:
  10m cell 对齐后的已掘复核范围

forward_scope:
  当前掌子面前方 0-30m

local_background_scope:
  当前掌子面后方一定距离的局部背景

report_scope:
  上述范围的合并
```

重要区别：

```text
daily_plc_range 是实际 PLC 推进范围。
daily_excavated_scope 是 10m 对齐后的复核范围。
二者不能混用。
```

`apply_spatial_relevance_filter` 会把时间可用证据进一步分成：

| role | 含义 |
|---|---|
| `daily_review_evidence` | 和当日已掘复核范围重叠 |
| `forward_attention_evidence` | 和当前掌子面前方范围重叠 |
| `local_background_evidence` | 和局部背景范围重叠 |
| `excluded_by_distance` | 时间可用但离日报范围太远 |
| `excluded_by_missing_geometry` | 缺少里程几何信息 |

这一步让远距离旧 TSP 不再进入当前日报主链路。

### 6.5 地质投影和融合

`project_evidence_to_cells` 把证据投影到 10m cell，计算重叠关系和有效权重。

`fuse_geo_states` 对每个 cell 融合：

```text
围岩等级分布
主要 hazard
hazard_scores
source_support
confidence_score
uncertainty_level
conflict_level
supporting_evidence_ids
source_trace
GRS_geo_base
```

### 6.6 GRS 的计算

GRS 公式为：

```text
GRS_geo_base =
  0.45 * grade_score_component
+ 0.45 * hazard_component
+ 0.10 * confidence_component
```

含义：

| 分量 | 含义 |
|---|---|
| grade_score_component | 围岩等级关注分 |
| hazard_component | 地质关注现象分 |
| confidence_component | 多源证据置信度分 |

边界：

- GRS 是地质证据关注度。
- GRS 不是灾害概率。
- `GRS_available=False` 时不能解释成低风险，只能解释成缺少可用地质证据。

---

## 7. Evidence Role：三个角色怎么区分

当前系统最重要的语义边界之一，是把同一个 10m cell 分成不同角色。

```text
ConstructionStateCell
│
├─ daily_review
│   ├─ 当日已掘复核单元
│   ├─ 可以使用 PLC 响应
│   ├─ 可以使用 RAI
│   ├─ 有地质证据时可以计算 GRCI
│   └─ high_grci_cells 只能来自这里
│
├─ forward_attention
│   ├─ 当前掌子面前方关注单元
│   ├─ 只使用地质证据 GRS / hazards / source_trace
│   ├─ 不使用 PLC 响应
│   ├─ 不使用 RAI
│   ├─ 不使用 GRCI
│   └─ 只能写成提示、关注、需复核
│
└─ local_background
    ├─ 局部背景证据
    ├─ 用于解释上下文
    ├─ 不作为当日结论
    └─ 不进入 high_grci_cells
```

这三个角色解决了一个核心问题：同样是地质证据，不能都按“当日已发生事实”来写。前方证据和背景证据必须降级表达。

---

## 8. ConstructionStateCell 是什么

`ConstructionStateCell` 是当前系统最核心的数据对象。

定义位置：

```text
backend/schemas/pipeline.py::ConstructionStateCell
```

构建位置：

```text
backend/coupling/grs_rai_grci.py::build_construction_state_cells
```

它把三张表合并：

```text
cells_df
  + cell_response_df
  + geo_states_df
  + cell_evidence_df
  + normalized_evidence_df
  + scope_summary
  = ConstructionStateCell[]
```

### 8.1 位置字段

| 字段 | 含义 |
|---|---|
| `cell_id` | cell 唯一编号 |
| `cell_start` | 起点里程 |
| `cell_end` | 终点里程 |
| `cell_center` | 中心里程 |
| `distance_to_face_m` | 到当前掌子面的距离 |
| `cell_role` | daily_review / forward_attention / local_background |

### 8.2 PLC 响应字段

| 字段 | 含义 |
|---|---|
| `operation_state` | cell 主导工况 |
| `speed_mean` | 平均推进速度 |
| `thrust_mean` | 平均推力 |
| `torque_mean` | 平均扭矩 |
| `stop_duration_min` | 停机时长 |
| `RAI` | 施工响应关注度 |
| `plc_metrics` | working-only 和 steady-state 增强指标 |

### 8.3 地质字段

| 字段 | 含义 |
|---|---|
| `fused_grade` | 融合围岩等级 |
| `main_hazards` | 主要关注现象 |
| `hazard_scores` | 各类 hazard 分 |
| `confidence_score` | 置信度 |
| `uncertainty_level` | 不确定性等级 |
| `conflict_level` | 多源证据冲突程度 |
| `supporting_evidence_ids` | 支撑证据 id |
| `source_trace` | 证据追踪信息 |
| `GRS_geo_base` | 地质证据关注度 |

### 8.4 耦合字段

| 字段 | 含义 |
|---|---|
| `GRCI` | 地质-施工响应耦合关注度 |
| `GRCI_available` | 是否可计算 GRCI |
| `GRCI_source` | GRCI 来源 |
| `GRCI_unavailable_reason` | 不可用原因 |
| `grs_term` | GRCI 中 GRS 项 |
| `rai_term` | GRCI 中 RAI 项 |
| `interaction_term` | GRS×RAI 交互项 |
| `coupling_level` | none/low/medium/high/unavailable |
| `coupling_explanation` | 文本解释 |

### 8.5 边界字段

| 字段 | 含义 |
|---|---|
| `has_plc_response` | 是否有当日 PLC 响应证据 |
| `has_geology_evidence` | 是否有空间相关地质证据 |
| `is_excavated_today` | 是否属于当日已掘复核 |
| `is_current_face_cell` | 是否掌子面所在 cell |
| `is_forward_cell` | 是否严格前方 cell |
| `used_in_evidence_pack` | 是否进入 Evidence Pack |

---

## 9. RAI / GRS / GRCI 怎么用

### 9.1 RAI

RAI 表示施工响应关注度。

```text
RAI =
  0.40 * stop_ratio
+ 0.25 * abnormal_ratio
+ 0.20 * speed_drop_score
+ 0.10 * torque_volatility_score
+ 0.05 * speed_volatility_score
```

不能这样讲：

```text
RAI 是设备异常概率。
RAI 高说明一定发生异常停机。
RAI 高说明前方地质有问题。
```

可以这样讲：

```text
RAI 用于描述已掘 cell 中 PLC 施工响应的关注程度。
```

### 9.2 GRS

GRS 表示地质证据关注度。

```text
GRS_geo_base =
  0.45 * grade_score_component
+ 0.45 * hazard_component
+ 0.10 * confidence_component
```

不能这样讲：

```text
GRS 是灾害概率。
GRS 为 0 说明没有风险。
```

可以这样讲：

```text
GRS 表示当前可用地质证据在该 cell 上形成的关注程度。
```

### 9.3 GRCI

GRCI 表示已掘区段地质证据和施工响应的耦合关注度。

```text
GRCI =
  0.55 * GRS_geo_base
+ 0.35 * RAI
+ 0.10 * GRS_geo_base * RAI
```

计算条件：

```text
cell_role == daily_review
has_plc_response == True
RAI is not None
GRS_available == True
```

如果缺少 PLC 响应：

```text
GRCI = None
GRCI_available = False
GRCI_unavailable_reason = missing_plc_response
```

如果是 forward_attention：

```text
GRCI 不可用
forward 只使用 GRS / main_hazards / source_trace
```

不能这样讲：

```text
GRCI 是灾害概率。
GRCI 是前方风险。
GRCI 高证明地质灾害。
```

可以这样讲：

```text
GRCI 是已掘复核中“地质证据关注”和“施工响应关注”共同较高时的复核优先级指标。
```

---

## 10. DailyConstructionTwin 是什么

`DailyConstructionTwin` 是把所有 cell 重新整理成可查询、可导出、可约束报告生成的数字孪生视图。

构建位置：

```text
backend/twin/construction_twin.py::build_daily_construction_twin
```

它包含：

```text
DailyConstructionTwin
│
├─ scope
│   ├─ daily_plc_range
│   ├─ daily_excavated_scope
│   ├─ current_chainage
│   ├─ forward_scope
│   └─ local_background_scope
│
├─ cells
│   └─ TwinCellView[]
│
├─ daily_review_cells
├─ forward_attention_cells
├─ local_background_cells
├─ high_grci_cells
├─ summaries
├─ trace_index
├─ governance
└─ warnings
```

每个 `TwinCellView` 又分成多个状态面：

| state | 内容 |
|---|---|
| `position_state` | 位置、角色、是否已掘、是否前方 |
| `operation_state` | 工况、停机比例、停机解释边界 |
| `response_state` | RAI、PLC 均值、working-only 和 steady-state 指标 |
| `geology_state` | GRS、hazards、证据 id、source_trace |
| `forward_state` | 前方角色和 GRCI 禁用边界 |
| `coupling_state` | GRCI、coupling level、解释边界 |
| `quality_state` | 可用性、缺证据原因、警告 |
| `trace_state` | claim 到证据的追踪索引 |

Twin 的作用：

1. 给 Evidence Pack 一个结构化来源；
2. 给 debug/API/export 一个统一状态对象；
3. 给 boundary checker 提供治理规则；
4. 给论文方法提供“施工状态数字孪生底座”的实现依据。

---

## 11. Evidence Pack 是怎么约束报告的

Evidence Pack 由：

```text
backend/llm/evidence_pack.py::build_evidence_pack_from_twin
```

从 DailyConstructionTwin 构建。

它不是简单把所有数据塞给 LLM，而是分层：

```text
Prompt Evidence Pack
│
├─ report_scope
│   ├─ daily_plc_range
│   ├─ daily_excavated_scope
│   └─ current_chainage
│
├─ operation_evidence
├─ cluster_evidence
├─ gas_evidence
│
├─ geology_evidence
│   ├─ key_cells
│   ├─ selected_cells
│   ├─ excavated_review_cells
│   ├─ forward_attention_cells
│   └─ background_context_cells
│
├─ daily_review_evidence
├─ excavated_review_evidence
├─ forward_attention_evidence
├─ local_background_evidence
├─ coupling_evidence
├─ source_trace
├─ evidence_governance
└─ generation_constraints
```

### key_cells 和 selected_cells

当前正式字段是 `geology_evidence.key_cells`。为了兼容旧 checker，也同时输出 `selected_cells`，两者内容一致。

### Evidence Pack 的选择逻辑

Evidence Pack 不是把全部 cell 都送进去，而是选重点 cell：

| 角色 | 选择原则 |
|---|---|
| daily_review | GRCI、RAI、GRS、trace completeness 综合 |
| forward_attention | GRS、距离掌子面、证据置信度、trace completeness |
| local_background | GRS、证据置信度、trace completeness |

前方选择不使用 GRCI。

### Evidence Pack 的约束作用

它告诉报告生成器：

- 哪些是已掘复核；
- 哪些是前方关注；
- 哪些只是背景；
- 哪些句子可以用 GRCI；
- 哪些句子不能写成概率或事实；
- 哪些指标只是 proxy；
- 每个结论能追踪到哪些 evidence_id。

---

## 12. 报告生成模式

后端主 pipeline 支持这些 generation mode：

| mode | 含义 |
|---|---|
| `template` | 不调用 LLM，直接模板生成 |
| `evidence_pack_llm` | Evidence Pack 约束 LLM 生成 |
| `evidence_pack_llm_with_revision` | LLM 生成后再修订 |
| `evidence_pack_planner_llm` | 先生成报告计划，再生成报告 |
| `evidence_pack_planner_llm_with_revision` | planner + generation + revision |

Exp02 里进一步包装成五种对比模式：

| 实验模式 | 含义 |
|---|---|
| M0_template_only | 模板基线 |
| M1_direct_llm | 只给少量基础信息，让 LLM 直接写 |
| M2_raw_evidence_llm | 给粗粒度原始证据摘要 |
| M3_twin_evidence_pack_llm | 给 Twin/Evidence Pack，但不修订 |
| M4_full_twin_governance_trace_boundary_reviser | Evidence Pack + governance + Quality/Trace/Boundary + revision |

### 模板报告

模板报告由：

```text
backend/llm/evidence_pack.py::build_template_report
```

生成，当前已经对齐 checker 标准章节：

```text
## 综合摘要
## 总体概况
## 工况统计
## 聚类状态与效率分析
## 掌子面与地质揭示
## 已掘区段地质-施工响应复核
## 气体监测
## 前方地质关注提示
## 结论与建议
```

模板的作用是提供稳定基线，不代表自然语言生成能力强。

### LLM 生成和修订

LLM 生成主入口：

```text
backend/llm/llm_report_generator.py::generate_llm_report
```

流程：

```text
Evidence Pack
│
├─ 可选 Planner：生成报告计划
├─ build_generation_prompt
├─ LLMProvider.generate
├─ clean_llm_report_text
├─ check_report_quality + build_report_trace
├─ 可选 revise_llm_report
├─ 再次 check_report_quality + build_report_trace
└─ 返回 report_final
```

LLM 失败时会回落到模板报告，并写入 warning。

---

## 13. Quality / Trace / Boundary 怎么核验报告

### 13.1 Quality Checker

文件：

```text
backend/llm/report_quality_checker.py
```

检查内容：

| 检查项 | 作用 |
|---|---|
| 必选章节 | 检查报告是否缺章 |
| forbidden terms | 禁止“灾害概率”“必然发生”等表述 |
| GRCI 概率误用 | 防止把 GRCI 写成概率 |
| 前方事实误用 | 防止把 forward 写成已发生 |
| gas 字段误用 | 防止气体单位/浓度过度解释 |
| stop_ratio 因果误用 | 防止把停机比例直接解释为异常原因 |
| E14 数值语义 | 防止把 10m 对齐复核范围写成实际推进范围 |
| grounding | 引入 Grounding Checker 的结果 |

评分大致从 100 开始扣分：

```text
error 级 violation 扣至少 15
warning 扣至少 5
缺章节每个扣 3
grounding_rate < 0.6 扣 20
grounding_rate < 0.8 扣至少 10
```

配置位置：

```text
backend/configs/quality_checker_policy.json
```

### 13.2 Grounding Checker

文件：

```text
backend/llm/report_grounding_checker.py
```

它把报告抽成 claim，然后判断 claim 能否被 Evidence Pack 支撑。

支撑类型包括：

| support type | 含义 |
|---|---|
| `statistical_support` | PLC/气体/运行统计支撑 |
| `daily_review_support` | 已掘复核 cell 支撑 |
| `forward_attention_support` | 前方关注证据支撑 |
| `local_background_support` | 背景证据支撑 |
| `observed_support` | 现场揭示类证据支撑 |
| `forecast_support` | 超前预报类证据支撑 |
| `policy_support` | 方法边界/生成约束支撑 |
| `none` | 未找到支撑 |

### 13.3 Trace Builder

文件：

```text
backend/llm/report_trace_builder.py
```

它把 claim 和 evidence 关系整理成 trace：

```text
claim_text
claim_type
grounded
support_type
trace_support_type
supporting_evidence_ids
source_trace
support_note
```

这使报告中每个技术句子都可以回看它依赖的 Evidence Pack 或证据来源。

### 13.4 Boundary Checker

文件：

```text
backend/llm/twin_boundary_checker.py
```

它不检查普通错别字，而是检查方法边界是否被破坏：

| boundary type | 防止什么 |
|---|---|
| `grci_probability_misuse` | 把 GRCI 写成灾害/风险概率 |
| `forward_fact_misuse` | 把前方提示写成已发生事实 |
| `plc_proxy_misuse` | 把 PLC proxy 写成真实物理量或地质证明 |
| `stop_causality_misuse` | 把 stop_ratio 直接写成异常原因 |
| `local_background_scope_misuse` | 把背景证据写成当日结论 |

---

## 14. 输出层有哪些东西

### API 输出

当前核心接口：

```text
GET  /api/tbm/health
GET  /api/tbm/dates
POST /api/tbm/report
POST /api/tbm/report/debug
```

### 导出文件

导出脚本会保存：

```text
report.txt / report.md
prompt.txt / prompt.md
evidence_pack.json
quality.json / quality_summary.json
trace.json / trace_summary.json
construction_state_cells.json / csv
daily_construction_twin.json
twin_cell_views.json / csv
forward_profile.json
high_grci_cells.json
warnings.json
summary.json
method_metrics.json
```

---

## 15. Exp01 做什么

目录：

```text
experiments/exp01_twin_full_run/
```

Exp01 是 no-LLM 主流程稳定性实验。它批量跑 template 模式，检查：

- 每个日期 pipeline 是否成功；
- DailyConstructionTwin 是否能导出；
- ConstructionStateCell 数量和角色是否正常；
- forward cell 是否进入 high GRCI；
- forward_attention 是否泄漏 PLC/RAI/GRCI；
- boundary checker 是否能识别违规句；
- PLC enhanced metrics 在 daily_review 的覆盖率。

它不是 LLM 生成模式对比，而是证明主流程和 Twin 底座能稳定跑。

---

## 16. PLC preprocessing validation 做什么

目录：

```text
experiments/exp_plc_preprocessing_validation/
```

这个实验验证新增 PLC 预处理是否安全：

```text
91 天 PLC preprocessing validation
│
├─ daily summary
├─ cell summary
├─ coverage summary
├─ quality grade summary
├─ side-by-side summary
├─ forward leakage check
└─ main pipeline smoke summary
```

它重点确认：

- 稳态指标是否能覆盖足够 cell；
- 统计口径是否一致；
- forward_attention 没有泄漏 PLC enhanced metrics；
- no-LLM 主流程仍可跑通；
- 没有改变 RAI/GRCI。

---

## 17. Exp02 做什么

目录：

```text
experiments/exp02_llm_generation_modes/
```

Exp02 是生成模式对比实验。

```text
同一日期
│
├─ M0 模板
├─ M1 直接 LLM
├─ M2 原始证据 LLM
├─ M3 Twin Evidence Pack LLM
└─ M4 完整闭环 LLM
```

每个模式都用同一套 checker 评价：

```text
quality_score
grounding_rate
unsupported_claim_count
numeric_error_count
boundary_violation_count
E14_count
missing_sections
section_completeness
report_length
```

当前固定的 15 天 v3.1 结果概要：

| 模式 | 平均质量分 | 证据支撑率 | unsupported | numeric | boundary | E14 | 缺章 |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 模板 | 76.00 | 1.0000 | 0 | 0 | 0 | 0 | 3.00 |
| M1 直接 LLM | 69.67 | 0.7110 | 192 | 76 | 2 | 0 | 2.00 |
| M2 原始证据 LLM | 68.67 | 0.7222 | 189 | 44 | 3 | 1 | 2.00 |
| M3 Twin 证据包 LLM | 74.00 | 0.7729 | 205 | 45 | 0 | 0 | 2.00 |
| M4 完整闭环 | 96.67 | 0.9093 | 64 | 16 | 0 | 0 | 0.00 |

这说明：

- M0 是模板基线，稳定但不能代表自由生成能力；
- M1/M2 说明“直接让 LLM 写”或“只给原始证据”不够可靠；
- M3 说明结构化 Evidence Pack 有帮助，但没有 revision 时 LLM 仍会复述过多、产生 unsupported；
- M4 是当前表现最好的 LLM 模式，关键原因是生成后还有 Quality / Trace / Boundary feedback 和修订闭环。

---

## 18. 项目最重要的边界

这些话论文和报告里必须守住：

| 内容 | 不能怎么说 | 应该怎么说 |
|---|---|---|
| RAI | 设备故障概率、异常原因概率 | 施工响应关注指标 |
| GRS | 灾害概率、风险概率 | 地质证据关注指标 |
| GRCI | 灾害概率、前方风险 | 已掘复核耦合关注度 |
| forward_attention | 前方已发生异常 | 当前掌子面前方关注提示 |
| TSP/HSP | 现场已揭露事实 | 超前预报证据来源 |
| daily_excavated_scope | 实际推进范围 | 10m cell 对齐后的已掘复核范围 |
| daily_plc_range | 复核范围 | PLC 实测推进范围 |
| cutterhead_power_proxy | 真实刀盘功率 | 扭矩×转速 proxy |
| stop_ratio | 异常停机原因 | 施工响应关注信号 |
| local_background | 当日结论 | 局部背景上下文 |

---

## 19. 当前系统还有什么不足

### 工程实现层面

1. 后端历史迭代多，`_archive/` 中旧代码较多，虽然不参与主流程，但容易让新读者混淆。
2. 一些文件存在中文乱码显示问题，说明编码或终端显示环境需要统一。
3. checker 规则较多，部分依赖正则和关键词，仍可能有误伤或漏判。
4. Exp02 和主 pipeline 有部分实验包装逻辑，读代码时需要区分“正式主流程”和“实验复刻”。

### 方法层面

1. RAI/GRS/GRCI 仍是启发式关注指标，权重不是监督学习标定。
2. PLC 字段单位仍需数据字典确认，proxy 指标必须谨慎表述。
3. 当前没有灾害发生标签、异常原因标签或现场复核标签，因此不能做灾害预测准确率。
4. 单工程数据不能直接证明跨工程泛化。
5. 自动评价指标不能完全替代人工复核。

### 论文表述层面

不能把项目写成：

```text
LLM 判断地质风险。
系统预测灾害概率。
GRCI 证明灾害发生。
前方关注提示等于现场揭露事实。
```

更合适的论文定位是：

```text
面向 TBM 施工日报的多源证据治理、施工状态数字孪生表达与证据约束大模型生成方法。
```

---

## 20. 从数据到报告的故事版

可以这样向别人讲整个系统：

```text
第一步，系统打开当天 PLC CSV，知道这一天 TBM 从哪里推进到哪里。

第二步，系统不急着写报告，而是先做基础工况识别和论文式 PLC 预处理：基础工况用于运行统计和 RAI 兼容口径，paper-based preprocessing 用于识别停机样本、异常点、有效掘进样本、连续工作区间和稳态段。

第三步，系统把这些 PLC 样本按 10m 里程切成一个个 cell。每个 cell 一方面保留原有推进速度、推力、扭矩、停机比例、波动程度和 RAI；另一方面增加稳态推进速度、稳态推力、稳态扭矩、稳态转速、稳态贯入度、变异系数和 proxy 指标，用来解释有效掘进状态下的施工响应。

第四步，系统读取 TSP、HSP、掌子面素描等地质证据，先按日期过滤掉未来证据，再按当日推进范围、前方范围和背景范围过滤掉离日报太远的证据。

第五步，系统把地质证据也投影到同样的 10m cell，融合出围岩等级、主要关注现象、置信度、source_trace 和 GRS。

第六步，系统把 PLC 响应和地质证据放进 ConstructionStateCell。如果这个 cell 是当日已掘复核单元，并且同时有 RAI 和 GRS，就计算 GRCI；如果它是前方 cell，就只保留地质关注，不计算 GRCI。

第七步，系统把所有 cell 组织成 DailyConstructionTwin。这个 Twin 就像当天施工状态的结构化底座。

第八步，系统从 Twin 生成 Evidence Pack。Evidence Pack 告诉报告生成器哪些证据能说、哪些不能说、哪些只能提示、哪些可以复核。

第九步，模板或 LLM 生成日报。模板模式稳定；LLM 模式更自然；M4 模式还会把初稿送去质量检查和证据追踪，再反馈给 LLM 修订。

第十步，系统输出日报，同时输出质量分、trace、boundary 检查结果、high GRCI cells、forward profile 和 warnings。
```

---

## 21. 一页文字流程图

```text
PLC 日运行 CSV
│
├─ 字段解析与质量检查
├─ 基础工况识别：停机 / 过渡 / 工作 / 异常
├─ 聚类状态与效率统计
├─ 气体监测统计
├─ paper-based PLC preprocessing
│   ├─ 停机识别
│   ├─ 3σ 异常点过滤
│   ├─ valid_excavation_mask 有效掘进样本
│   ├─ working interval 连续区间
│   └─ steady-state 稳态段指标
└─ cell_response_df
    ├─ RAI
    ├─ working-only metrics（优先使用 valid_excavation_mask）
    └─ steady-state metrics

地质 evidence_db
│
├─ normalize_evidence_df
├─ filter_available_evidence
├─ HSP anomaly dedup
├─ report scope spatial filter
│   ├─ daily_review_evidence
│   ├─ forward_attention_evidence
│   ├─ local_background_evidence
│   └─ excluded evidence
├─ project_evidence_to_cells
└─ fuse_geo_states
    ├─ GRS
    ├─ hazards
    ├─ confidence
    └─ source_trace

cell_response_df + geo_states_df + scope_summary
│
└─ ConstructionStateCell
    ├─ daily_review: 可算 GRCI
    ├─ forward_attention: 只用 GRS/source_trace
    └─ local_background: 只作背景

ConstructionStateCell[]
│
└─ DailyConstructionTwin
    ├─ scope
    ├─ cells
    ├─ daily_review_cells
    ├─ forward_attention_cells
    ├─ local_background_cells
    ├─ high_grci_cells
    ├─ trace_index
    └─ governance

DailyConstructionTwin
│
└─ Evidence Pack
    ├─ operation_evidence
    ├─ gas_evidence
    ├─ daily_review_evidence
    ├─ forward_attention_evidence
    ├─ local_background_evidence
    ├─ coupling_evidence
    ├─ source_trace
    └─ generation_constraints

Evidence Pack
│
├─ template/no-LLM report
└─ LLM report
    ├─ generation
    ├─ quality / trace / boundary feedback
    └─ revision

report_text
│
├─ Quality Summary
├─ Trace Summary
├─ Boundary Summary
├─ Prompt Evidence Pack
├─ DailyConstructionTwin
├─ high_grci_cells
└─ forward_profile
```

---

## 22. 快速定位表

| 想看什么 | 看哪个文件 |
|---|---|
| API 怎么进来 | `backend/routes/report.py` |
| 主流程怎么串起来 | `backend/pipeline/daily_report_pipeline.py` |
| PLC 怎么分析 | `backend/plc/response.py` |
| PLC 怎么投影到 cell | `backend/plc/cell_response.py` |
| paper-based PLC preprocessing | `backend/plc/paper_based_preprocessing.py` |
| 工况识别 | `backend/analysis/dataprocess.py` |
| 聚类状态 | `backend/analysis/excavation_state.py` |
| 气体统计 | `backend/analysis/gas_analysis.py` |
| 地质证据 pipeline | `backend/geology_v2/pipeline.py` |
| 日报范围筛选 | `backend/pipeline/evidence_scope.py` |
| 地质融合和 GRS | `backend/geology_v2/fusion_engine.py` |
| 前方 profile | `backend/geology_v2/forward_profile.py` |
| ConstructionStateCell | `backend/schemas/pipeline.py` |
| GRCI 计算 | `backend/coupling/grs_rai_grci.py` |
| DailyConstructionTwin | `backend/twin/construction_twin.py` |
| Evidence Pack 和模板报告 | `backend/llm/evidence_pack.py` |
| LLM 生成 | `backend/llm/llm_report_generator.py` |
| 报告质量检查 | `backend/llm/report_quality_checker.py` |
| Grounding | `backend/llm/report_grounding_checker.py` |
| Boundary | `backend/llm/twin_boundary_checker.py` |
| Trace | `backend/llm/report_trace_builder.py` |
| Exp01 | `experiments/exp01_twin_full_run/run_exp01_twin_full_run.py` |
| Exp02 | `experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py` |
| PLC validation | `experiments/exp_plc_preprocessing_validation/run_plc_preprocessing_validation.py` |

---

## 23. 手工确认点

为了写论文和答辩更稳，建议后续人工确认：

1. PLC 原始字段单位，尤其推进速度、推力、扭矩、转速、贯入度、气体字段。
2. RAI/GRS/GRCI 权重来源的论文表述，不要写成已标定模型。
3. stop_ratio 是否能区分计划停机和非计划停机，目前代码明确不能。
4. `cutterhead_power_proxy` 等 proxy 的解释边界。
5. 典型日期中 M4 报告的人工可读性和工程表达是否合适。
6. Boundary 和 Grounding checker 的误伤/漏判样本。
7. 单工程 91 天结果是否足够支撑论文结论，跨工程泛化必须作为边界。
