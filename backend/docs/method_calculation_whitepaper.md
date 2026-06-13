# TBM 施工日报后端方法与计算逻辑白皮书

本文是 `backend/docs/current_backend_system_manual.md` 的方法与计算逻辑补充。系统总览文档回答“当前后端怎么跑”，本文回答“每一步到底怎么算、哪些字段参与、哪些结论允许写、哪些结论不能写”。

本文只描述当前代码真实执行逻辑，不描述理想设计，不补写论文实验，不把尚未实现的算法写成已经实现的能力。

## 文档导航

- [当前后端系统说明书](current_backend_system_manual.md)：总流程、API、真实数据流案例。
- [后端字段契约](backend_field_contract.md)：API、核心 schema 与 debug 输出字段。
- [方法定义文档](method_definition.md)：任务定义、方法边界与核心对象解释。
- [指标定义文档](metrics_definition.md)：GRS、RAI、GRCI、Quality、Trace 指标解释。
- [系统边界声明](scope_and_limitations.md)：当前系统不做什么。
- [2023-12-30 案例说明](case_2023-12-30.md)：典型日期说明案例。
- [附录 A：字段反向索引](#附录-a字段反向索引)：按字段查来源、计算、下游用途。
- [附录 B：配置常量总表](#附录-b配置常量总表)：按常量查位置、取值和影响。
- [附录 C：导出字段完整性检查](#附录-c导出字段完整性检查)：检查当前 export 是否足够复盘。

## 0. 当前方法定位

当前后端不是一个地质灾害概率预测系统，也不是一个 TSP/HSP 原始信号反演系统，更不是一个 TBM 物理仿真数字孪生系统。它当前做的是：

```text
读取每日 PLC 施工数据和多源地质证据
-> 在 10m 里程单元上构建 ConstructionStateCell
-> 分别形成 PLC 施工响应、地质证据关注、地质-施工响应耦合复核
-> 构建 Evidence Pack
-> 生成证据约束日报
-> 用 Quality / Trace 检查报告是否有证据支撑
```

当前方法的核心目标是“证据约束的日报生成与复核优先级排序”，而不是“判断灾害一定发生”。

### 0.1 三条证据通道

当前后端把日报信息分成三类证据通道。

第一类是事实统计通道：

```text
PLC 日运行数据
-> 工况识别
-> 工况持续时间、停机、异常、气体统计
-> operation_evidence / gas_evidence
```

这类信息回答“当天 PLC 数据统计上发生了什么”。

第二类是已掘区段复核通道：

```text
PLC response cell + geology_state cell
-> ConstructionStateCell
-> GRS / RAI / GRCI
-> high_grci_cells
```

这类信息回答“已经掘进经过的 cell 中，哪些同时有地质证据关注和施工响应异常，值得复核”。这里的 `GRCI` 只表示复核关注度，不表示灾害概率。

第三类是前方关注通道：

```text
当前掌子面前方可用地质证据
-> geo_states_df
-> forward_profile
-> forward_attention_cells
```

这类信息回答“当前掌子面前方有哪些可用地质证据提示需要关注”。前方通道使用 `GRS_geo_base`、`main_hazards`、`source_trace`，不使用 `GRCI`。

## 1. 主流程与代码入口

当前主入口是：

```python
pipeline.daily_report_pipeline.run_daily_report_pipeline(
    date: str,
    use_llm: bool = True,
)
```

FastAPI 入口只通过：

```text
app.py
-> routes/report.py
-> run_daily_report_pipeline
```

当前主流程调用链如下：

| 顺序 | 文件与函数 | 输入 | 输出 | 作用 |
|---:|---|---|---|---|
| 1 | `routes/report.py` | API 请求日期、`use_llm` | API 响应 | 对外暴露 `/api/tbm/report` 和 `/api/tbm/report/debug` |
| 2 | `pipeline/daily_report_pipeline.py::run_daily_report_pipeline` | `date`, `use_llm` | `DailyReportResult` | 唯一日报 pipeline 编排 |
| 3 | `pipeline/inputs.py::load_daily_inputs` | 日期 | PLC DataFrame、evidence DataFrame | 读取原始数据 |
| 4 | `plc/response.py::analyze_plc_response` | PLC DataFrame | operation、cluster、gas、cell response | 完成 PLC 侧分析 |
| 5 | `geology_v2/pipeline.py::run_geology_v2_context` | PLC、evidence、当前里程、日期 | geology_v2 结果 | 完成地质证据结构化、过滤、投影、融合 |
| 6 | `coupling/grs_rai_grci.py::build_construction_state_cells` | cells、cell_response、geo_states、evidence | `ConstructionStateCell[]` | 构建统一 cell 对象 |
| 7 | `coupling/grs_rai_grci.py::high_grci_cells` | `ConstructionStateCell[]` | high GRCI cells | 只筛选已掘且 GRCI 可用 cell |
| 8 | `twin/twin_state.py::build_twin_state` | summaries + cells | twin_state | 构建报告状态摘要 |
| 9 | `llm/evidence_pack.py::build_prompt_evidence_pack` | cells + summaries + forward_profile | Evidence Pack | 构建报告唯一证据包 |
| 10 | `llm/report_prompt.py::build_prompt` | Evidence Pack | prompt_text | 构建 LLM prompt |
| 11 | `llm/evidence_pack.py::build_template_report` | Evidence Pack | report_text | no-LLM 或 LLM fallback 报告 |
| 12 | `llm/report_quality_checker.py::check_report_quality` | report + evidence pack + twin_state | quality | 检查禁用表达、章节、grounding |
| 13 | `llm/report_trace_builder.py::build_report_trace` | report + grounding + evidence pack | trace | 建立 claim 到 evidence 的追溯关系 |

## 2. 原始数据读取

### 2.1 PLC 日运行数据

读取位置：

```text
pipeline/inputs.py::load_daily_inputs
utils/io_utils.py::load_csv_by_date
```

日期查找逻辑：

```text
date = 2023-12-30
-> tbm_data_20231230.csv
-> DATA_DIR / tbm_data_20231230.csv
```

`DATA_DIR` 由 `config.py` 解析，通常来自 `.env`：

```env
DATA_ROOT=G:/我的云端硬盘/TBM9
DATA_DIR=G:/我的云端硬盘/TBM9/TBM9_2023
```

字段识别由 `analysis/plc_contract.py::resolve_plc_columns` 完成。候选字段包括：

| 语义 | 候选字段 |
|---|---|
| 时间 | `运行时间-time`, `timestamp`, `time`, `datetime`, `date_time` |
| 里程 | `chainage`, `当前里程`, `导向盾首里程`, `开累进尺`, `里程` |
| 掘进状态 | `掘进状态`, `施工状态`, `state`, `excavation_state` |
| 推进速度 | `推进速度`, `advance_speed`, `speed`, `actual_speed` |
| 推进给定速度 | `推进给定速度`, `给定速度`, `target_speed`, `set_speed` |
| 推力 | `推力`, `总推力`, `thrust`, `total_thrust` |
| 刀盘扭矩 | `刀盘扭矩`, `扭矩`, `cutter_torque`, `torque` |
| 刀盘转速 | `刀盘实际转速`, `刀盘转速`, `转速`, `cutter_rpm`, `rpm` |
| 贯入度 | `贯入度`, `penetration` |
| 气体 | `CH4检测`, `CO2检测`, `H2S检测`, `SO2检测`, `NO2检测`, `NO检测` 及部分英文/简称别名 |

字段匹配顺序是：

```text
先做大小写归一后的精确匹配
再做大小写归一后的子串匹配
```

如果关键字段缺失，当前代码不会伪造完整分析，而是：

```text
1. 在 quality_report / warnings 中记录缺失；
2. 能计算的部分继续计算；
3. 无法计算的部分返回空结构或默认值；
4. 后续 Evidence Pack 与报告只能使用已形成的结构化证据。
```

### 2.2 多源地质证据

地质证据读取位置：

```text
pipeline/inputs.py::load_daily_inputs
config.py::EVIDENCE_DB_PATH
```

默认配置示例：

```env
EVIDENCE_DB_PATH=G:/我的云端硬盘/TBM9/DB/evidence_db.csv
```

当前代码主要把地质证据统一成如下来源类型：

| 原始来源 | 标准化后 |
|---|---|
| `tsp`, `TSP` | `TSP` |
| `hsp`, `HSP`, `sonic` | `HSP` |
| `sketch`, `face_sketch`, `face_observation` | `face_sketch` |
| `drill`, `borehole` | `borehole` |
| `overview`, `background` | `overview` / `background` |

证据角色由 `geology_v2/config.py::SOURCE_ROLE_MAP` 给出：

| 来源 | evidence_role |
|---|---|
| `face_sketch` | `observed` |
| `borehole` | `observed` |
| `TSP` | `prediction` |
| `HSP` | `prediction` |
| `report_conclusion` | `interpreted` |
| `overview` | `background` |

这一区分直接影响后续写作约束：`prediction` 证据只能写成超前预报提示，不能写成现场已揭露事实。

## 3. PLC 数据质量检查

PLC 数据质量检查由：

```text
plc/quality.py::check_plc_quality
```

以及字段解析工具：

```text
analysis/plc_contract.py
```

共同支持。质量检查输出进入：

```text
plc_result["quality_report"]
operation_summary["data_quality"]
gas_summary["gas_field_diagnostics"]
```

质量检查的作用不是修正原始数据，而是给后续报告提供边界提示，例如：

```text
缺少时间字段
缺少里程字段
缺少关键运动字段
气体字段疑似报警量而不是连续浓度
里程为空或不可解析
```

## 4. 工况识别与 operation_summary

工况识别由：

```text
analysis/dataprocess.py::annotate_operation_mode
analysis/dataprocess.py::load_and_process
analysis/dataprocess.py::compute_stats
analysis/dataprocess.py::build_operation_context
```

完成。

### 4.1 单行工况判别规则

核心函数是 `analysis/dataprocess.py::_judge_condition`。

如果存在 `掘进状态` 字段：

```text
掘进状态 == 0
-> stop / 停机

掘进状态 != 0 且 推力非零 且 推进速度非零
-> work / 稳定掘进

掘进状态 != 0 且 推力非零 且 推进速度为零
-> transition / 启动或过渡

掘进状态 != 0 且 推力为零 且 刀盘扭矩非零
-> abnormal / 异常扭矩

其他
-> transition
```

如果不存在 `掘进状态` 字段，则使用推力、推进速度、刀盘扭矩的非零状态兜底：

```text
推力、推进速度、扭矩均近似为零 -> stop
推力非零、推进速度为零 -> transition
推力非零、推进速度非零 -> work
推力为零、扭矩非零 -> abnormal
其他 -> stop
```

非零阈值当前为：

```text
abs(value) > 1e-8
```

工况编码：

| code | operation_mode | 中文 |
|---:|---|---|
| 0 | `stop` | 停机 |
| 1 | `transition` | 启动/过渡 |
| 2 | `work` | 稳定掘进 |
| 3 | `abnormal` | 异常扭矩 |

### 4.2 工况分段与持续时间

`load_and_process` 会先按时间排序，然后用：

```text
group = operation_mode_code != previous(operation_mode_code)
```

识别连续工况段。

采样间隔由：

```text
infer_sample_interval_sec
```

计算，即时间差的中位数，且只接受：

```text
0 < diff_seconds < 3600
```

每段持续时间：

```text
raw_duration_sec = end_time - start_time
duration_sec = raw_duration_sec + sample_interval_sec
```

如果采样间隔无法推断，则不额外补末端采样间隔。

### 4.3 operation_summary 的语义

`operation_summary` 主要包含：

```text
dominant_mode
dominant_mode_cn
work_total_min
stop_total_min
transition_total_min
abnormal_total_min
work_count
stop_count
transition_count
abnormal_count
work_ratio
stop_ratio
key_operation_segments
routine_stop_summary
```

这些是统计描述，不是地质解释。

## 5. 施工状态聚类与 cluster_summary

施工状态聚类由：

```text
analysis/excavation_state.py::detect_excavation_state
analysis/excavation_state.py::excavation_state_segments
analysis/excavation_state.py::explain_excavation_states
analysis/excavation_state.py::excavation_state_efficiency
analysis/excavation_state.py::excavation_state_stats
analysis/excavation_state.py::build_cluster_context
```

完成。

### 5.1 聚类输入特征

默认特征为：

```text
推力
刀盘扭矩
刀盘实际转速
推进速度
```

实际只使用 PLC 中真实存在的特征。若有效特征少于 2 个，则不形成聚类。

### 5.2 聚类样本筛选

聚类只在“工作中”样本上进行，优先级如下：

```text
1. 如果存在 is_working，则使用 is_working == True；
2. 否则如果存在 operation_mode，则使用 operation_mode == "work"；
3. 否则如果存在 掘进状态，则使用 掘进状态 != 0；
4. 否则使用推力或推进速度明显非零作为工作样本。
```

### 5.3 聚类算法

当前代码使用：

```text
StandardScaler
KMeans(n_clusters=3, random_state=0, n_init="auto")
```

如果有效样本数量小于 `n_states`，则不聚类。

### 5.4 cluster_summary 的作用

聚类结果用于报告中的施工状态与效率说明。它不参与 `RAI`、`GRS`、`GRCI` 的核心公式。

聚类质量判断：

```text
valid_sample_count >= 30
cluster_count >= 2
min_cluster_ratio >= 0.03
```

同时满足时，`is_stable_enough=True`。

## 6. 气体监测统计

气体统计由：

```text
analysis/gas_analysis.py::compute_gas_stats
analysis/gas_analysis.py::build_gas_context
```

完成。

### 6.1 当前气体字段与阈值

当前配置阈值为：

| 字段 | 阈值 | 单位假设 |
|---|---:|---|
| `CO2检测` | 0.5 | % |
| `H2S检测` | 10 | ppm |
| `SO2检测` | 2 | ppm |
| `NO2检测` | 5 | ppm |
| `NO检测` | 20 | ppm |
| `CH4检测` | 0.5 | % |

### 6.2 超限事件计算

对每个气体字段：

```text
series = numeric(gas_column).dropna()
mean = series.mean()
max = series.max()
min = series.min()
exceed = series > threshold
```

连续超限事件用：

```text
group = exceed != previous(exceed)
```

识别。只有 `exceed == True` 的连续段计为超限段。

### 6.3 浓度字段与报警字段的区别

`build_gas_context` 会结合 `quality_report["gas_field_diagnostics"]` 判断字段类型：

```text
field_type_guess == "concentration"
-> 按浓度统计解释

field_type_guess == "alarm_flag"
-> 作为报警量解释，不直接套浓度阈值

field_type_guess == "unknown"
-> 保守提示字段含义未确认
```

这可以避免把 0/1 报警字段误写成真实浓度值。

## 7. PLC response 投影到 10m cell

PLC cell 聚合由：

```text
plc/cell_response.py::project_plc_response_to_cells
```

完成。

### 7.1 cell 划分

当前默认 cell 长度：

```text
cell_length = 10.0 m
```

对每一行 PLC：

```text
cell_start = floor(chainage / cell_length) * cell_length
cell_end = cell_start + cell_length
cell_center = (cell_start + cell_end) / 2
cell_id = f"cell_{cell_start}_{cell_end}"
```

例如里程 `1014601.0` 属于：

```text
cell_1014600_1014610
```

### 7.2 行持续时间

如果存在时间字段：

```text
row_duration_sec = 下一条记录时间 - 当前记录时间
```

只接受：

```text
0 < diff_seconds < 3600
```

异常或缺失时间差用有效时间差中位数填补。

如果没有可用时间字段，每行持续时间兜底为：

```text
1 sec
```

### 7.3 cell 级 PLC 指标

每个 cell 计算：

```text
duration_sec
work_duration_sec
stop_duration_sec
abnormal_duration_sec
speed_mean
speed_std
thrust_mean
thrust_std
torque_mean
torque_std
rpm_mean
rpm_std
sample_count
```

停机占比：

```text
stop_ratio = stop_duration_sec / duration_sec
```

异常占比：

```text
abnormal_ratio = abnormal_duration_sec / duration_sec
```

## 8. RAI 计算逻辑

`RAI` 当前由：

```text
plc/cell_response.py::project_plc_response_to_cells
```

计算，并写入 `cell_response_df`。

### 8.1 RAI 的语义

`RAI` 表示 cell 级施工响应异常度，是工程近似异常指标。它不是地质灾害概率，不直接说明灾害发生。

### 8.2 RAI 公式

当前公式：

```text
RAI = abnormal_score

abnormal_score =
    0.40 * stop_ratio
  + 0.25 * abnormal_ratio
  + 0.20 * speed_drop_score
  + 0.10 * torque_volatility_score
  + 0.05 * speed_volatility_score
```

结果会被限制在 `[0, 1]`。

### 8.3 分量计算

推进速度下降分：

```text
speed_drop_score =
    clip01(1 - speed_mean / max(global_speed_q75, 1e-6))
```

其中 `global_speed_q75` 是当日 PLC 全部有效推进速度的 75% 分位数。

扭矩波动分：

```text
torque_volatility_score =
    clip01(torque_std / max(abs(torque_mean), 1.0))
```

速度波动分：

```text
speed_volatility_score =
    clip01(speed_std / max(abs(speed_mean), 1.0))
```

如果某些字段缺失，相关均值/标准差可能为空，对应分量按代码兜底参与或为 0。系统不会在前端或报告端重新计算 RAI。

## 9. 地质证据标准化

地质证据标准化由：

```text
geology_v2/evidence_normalizer.py::normalize_evidence_df
```

完成。

标准化输出的核心字段包括：

```text
evidence_id
report_id
source_type_norm
evidence_role
spatial_type
start_chainage
end_chainage
center_chainage
face_chainage
grade
lithology
weathering
joint_development
rock_mass_state
stability
water_flag / water_state
collapse_flag / collapse_state
deformation_flag / deformation_state
hazard_tags
attribute_tags
method_tags
unknown_hazard_tags
source_reliability
evidence_strength
raw_text
attrs_json
parse_warnings
```

### 9.1 source_reliability

当前默认来源可靠性来自 `geology_v2/config.py::SOURCE_RELIABILITY`：

| source_type_norm | source_reliability |
|---|---:|
| `face_sketch` | 1.20 |
| `borehole` | 1.15 |
| `TSP` | 0.95 |
| `HSP` | 0.90 |
| `report_conclusion` | 1.00 |
| `overview` | 0.35 |
| `unknown` | 0.60 |

注意：在 evidence 投影阶段，`source_reliability` 会被裁剪到不超过 1.0。因此 `face_sketch=1.20` 只代表配置层偏高，但实际 `effective_weight` 不会超过 1。

### 9.2 evidence_strength

`evidence_strength` 综合来源层级、空间类型、置信度等信息。其基础配置来自：

```text
SOURCE_LEVEL_STRENGTH
SPATIAL_TYPE_STRENGTH
CONFIDENCE_WEIGHT
```

例如：

| spatial_type | spatial strength |
|---|---:|
| `point` | 1.10 |
| `anomaly_point` | 1.20 |
| `segment` | 1.00 |
| `overview` | 0.35 |
| `background` | 0.30 |
| `unknown` | 0.70 |

实际进入投影时同样被限制在 `[0, 1]`。

## 10. online 可用性过滤与未来信息防泄漏

过滤函数：

```text
geology_v2/evidence_normalizer.py::filter_available_evidence
```

主流程调用时使用：

```text
mode = "online"
analysis_date = 当前日报日期
current_chainage = 当日最后里程
advance_direction = 1
chainage_tolerance_m = 1.0
```

### 10.1 observed 证据规则

`face_sketch` 和 `borehole` 等 `observed` 证据按实际揭示里程判断是否未来泄漏。

对正向掘进：

```text
observed_chainage > current_chainage + chainage_tolerance_m
-> 排除
```

`observed_chainage` 的取值优先级：

```text
center_chainage
face_chainage
start_chainage
```

### 10.2 forecast_like 证据规则

对 `TSP` / `HSP` 且角色为：

```text
prediction
interpreted
background
```

的证据，统一视为 `forecast_like`。

可用性由报告形成时的掌子面里程 `face_chainage` 判断：

```text
face_chainage 缺失
-> online 模式保守排除

face_chainage > current_chainage + tolerance
-> 对正向掘进而言，视为当前尚不可用，排除
```

### 10.3 report_date / issue_date 规则

如果传入 `analysis_date`，且 evidence 有 `issue_date` 或 `report_date`：

```text
issue_date/report_date > analysis_date
-> 排除
```

这条规则避免报告日期之后形成的证据进入当前日报。

过滤摘要会写入：

```text
normalized_df.attrs["availability_filter"]
```

其中包括：

```text
input_count
output_count
excluded_future_observed_count
excluded_unavailable_prediction_count
excluded_missing_face_chainage_count
excluded_future_forecast_like_count
excluded_future_report_count
```

## 11. HSP anomaly_point 去重

去重函数：

```text
geology_v2/evidence_dedup.py::deduplicate_hsp_anomaly_points
```

只处理：

```text
source_type_norm == "HSP"
spatial_type == "anomaly_point"
```

默认容差：

```text
chainage_tol_m = 0.5
face_tol_m = 1.0
```

dedup key 包含：

```text
report_id
source_type_norm
spatial_type
face_chainage rounded by face_tol_m
center_chainage rounded by chainage_tol_m
hazard_family
```

重复组处理方式：

```text
1. 选一个 base row 保留；
2. 合并 duplicate_evidence_ids；
3. 合并 hazard_tags / attribute_tags / method_tags / unknown_hazard_tags；
4. 三态字段按 positive 优先合并；
5. 数值字段取 max；
6. 写入 duplicate_count、dedup_key、dedup_note。
```

目的：防止 HSP 报告边界或异常点拆分造成同一异常被重复加权。

## 12. 地质 10m cell 构建

cell 构建函数：

```text
geology_v2/cell_builder.py::build_chainage_cells
```

当前默认：

```text
cell_length = 10.0 m
```

输出字段：

```text
cell_id
cell_start
cell_end
cell_center
```

地质 cell 的空间范围由 PLC 当日范围和 evidence 范围共同决定。因地质证据覆盖范围通常大于当日掘进范围，所以 `geo_states_df` 的 cell 数量往往远大于 `cell_response_df`。

## 13. 地质证据投影到 cell

投影函数：

```text
geology_v2/evidence_projector.py::project_evidence_to_cells
```

输入：

```text
cells_df
normalized_evidence_df
```

输出：

```text
cell_evidence_df
```

核心字段：

```text
cell_id
evidence_id
source_type_norm
spatial_type
distance_m
spatial_weight
source_reliability
evidence_strength
effective_weight
```

### 13.1 距离计算

对 segment / report_conclusion：

```text
如果 cell_center 落在 [start_chainage, end_chainage] 内：
    distance_m = 0
否则：
    distance_m = cell_center 到最近边界的距离
```

对 point / anomaly_point：

```text
distance_m = abs(cell_center - center_chainage)
```

overview / background 当前不进入强投影关系。

### 13.2 空间衰减权重

空间 sigma 来自：

```text
geology_v2/config.py::get_spatial_sigma
```

部分默认值：

| source / spatial | sigma_m |
|---|---:|
| `face_sketch + point` | 5 |
| `borehole + point` | 4 |
| `HSP + segment` | 12 |
| `HSP + anomaly_point` | 4 |
| `TSP + segment` | 15 |
| `TSP + report_conclusion` | 12 |
| `overview` / `background` | 30 |

投影保留半径：

```text
projection_radius = max(3 * sigma_m, 1.0)
```

空间权重：

```text
spatial_weight = exp(-0.5 * (distance_m / sigma_m)^2)
```

### 13.3 effective_weight

有效权重：

```text
effective_weight =
    spatial_weight
  * clip01(source_reliability)
  * clip01(evidence_strength)
```

如果 `effective_weight <= 1e-12`，该投影关系被丢弃。

## 14. 地质状态融合 geo_states_df

地质融合函数：

```text
geology_v2/fusion_engine.py::fuse_geo_states
```

输入：

```text
cells_df
cell_evidence_df
normalized_evidence_df
```

输出：

```text
geo_states_df
```

核心字段：

```text
cell_id
cell_start
cell_end
cell_center
has_geology_evidence
fused_grade
grade_distribution
hazard_scores
main_hazards
water_score
collapse_score
deformation_score
source_support
source_type_count
evidence_count
confidence_score
uncertainty_level
conflict_level
conflict_reasons
supporting_evidence_ids
source_trace
grade_score_component
hazard_component
confidence_component
GRS_formula_text
GRS_component_method
GRS_geo_base
```

### 14.1 重复有效权重截断

`fusion_engine` 内部会对重复证据组进行权重截断，避免同一报告重复记录导致权重过大。

重复 key 大致包括：

```text
report_id
source_type_norm
spatial_type
rounded center_chainage
grade
sorted hazard_tags
```

若同一重复组有 `n` 条记录：

```text
raw_sum = sum(effective_weight)
max_weight = max(effective_weight)
capped_sum = min(raw_sum, max_weight * (1 + log(n)))
```

然后按比例压缩为 `effective_weight_capped`。

### 14.2 围岩等级融合

围岩等级按 `effective_weight_capped` 汇总支持度：

```text
support(grade) = sum(effective_weight_capped for evidence with this grade)
share(grade) = support(grade) / total_support
```

融合等级采用保守规则：

```text
best_support = 最大支持度
candidate_grades = support >= 0.75 * best_support 的等级
fused_grade = candidate_grades 中围岩等级更差者
```

等级关注分来自 `geology_v2/config.py::GRADE_ATTENTION_SCORE`：

| 等级 | 分值 |
|---|---:|
| I / Ⅰ / 1 | 0.05 |
| II / Ⅱ / 2 | 0.20 |
| III / Ⅲ / 3 | 0.40 |
| IV / Ⅳ / 4 | 0.70 |
| V / Ⅴ / 5 | 1.00 |

### 14.3 hazard_scores

每条 evidence 先抽取 hazard key，例如：

```text
water
water_inrush
collapse
block_fall
deformation
fractured_rock
extremely_fractured_rock
joint_development
dense_joints
soft_hard_uneven
strong_reflection_anomaly
```

hazard 权重来自 `geology_v2/config.py::HAZARD_WEIGHT`，部分值如下：

| hazard | weight |
|---|---:|
| `water` | 0.35 |
| `water_inrush` | 0.45 |
| `collapse` | 0.40 |
| `block_fall` | 0.35 |
| `deformation` | 0.30 |
| `fractured_rock` | 0.30 |
| `extremely_fractured_rock` | 0.40 |
| `joint_development` | 0.25 |
| `dense_joints` | 0.35 |
| `soft_hard_uneven` | 0.25 |
| `reflection_anomaly` | 0.25 |
| `strong_reflection_anomaly` | 0.35 |
| `poor_stability` | 0.35 |

单条证据对某 hazard 的贡献：

```text
contribution = hazard_weight * min(effective_weight_capped, 1.5)
```

同一 hazard 多条证据使用 Noisy-OR 合并：

```text
hazard_score = 1 - product(1 - contribution_i)
```

`main_hazards` 取 `hazard_scores` 中分数大于 `0.05` 的前 5 个。

### 14.4 confidence_score

融合置信度不是准确率，只表示当前 cell 内证据融合的支持强弱与冲突惩罚。

公式在 `fusion_engine.py::_confidence_score`：

```text
total_weight = sum(effective_weight_capped)
evidence_count = unique evidence_id count
source_type_count = unique source_type_norm count

weight_factor = 1 - exp(-total_weight / 3.0)
evidence_factor = min(1.0, 0.50 + 0.10 * evidence_count)
source_factor = min(1.0, 0.70 + 0.15 * max(source_type_count - 1, 0))
conflict_penalty = 1 - 0.35 * clip01(conflict_score)

confidence_score =
    clip01(weight_factor * evidence_factor * source_factor * conflict_penalty)
```

### 14.5 conflict_level 与 uncertainty_level

等级冲突、三态冲突等会形成 `conflict_score`。

典型规则：

```text
如果围岩等级跨度 >= 2 且第二等级支持度占比 >= 0.20：
    grade_conflict_score >= 0.70

如果围岩等级跨度 >= 1 且第二等级支持度占比 >= 0.30：
    grade_conflict_score >= 0.45

如果不同来源主导等级跨度 >= 2：
    grade_conflict_score >= 0.75
```

水、掉块、变形等三态字段中，如果 positive 与 negative 同时有较强支持，也会增加冲突分。

`uncertainty_level` 由：

```text
max(1 - confidence_score, conflict_score)
```

映射得到。

## 15. GRS_geo_base 计算逻辑

`GRS_geo_base` 在：

```text
geology_v2/fusion_engine.py::_grs_geo_base_components
```

计算。它是纯地质证据关注度，不引入 PLC 响应，也不引入 `RAI`。

公式：

```text
GRS_geo_base =
    0.45 * grade_score_component
  + 0.45 * hazard_component
  + 0.10 * confidence_component
```

其中：

```text
grade_score_component = GRADE_ATTENTION_SCORE[fused_grade]

hazard_component =
    0.75 * max(hazard_scores)
  + 0.25 * average(hazard_scores)

confidence_component = confidence_score
```

最终结果限制在 `[0, 1]`。

如果该 cell 没有地质证据：

```text
GRS_geo_base = 0.0
GRS_component_method = "empty"
```

## 16. ConstructionStateCell

`ConstructionStateCell` 是当前系统的核心对象，定义在：

```text
schemas/pipeline.py
```

构建函数：

```text
coupling/grs_rai_grci.py::build_construction_state_cells
```

它合并三类输入：

```text
cells_df
cell_response_df
geo_states_df
```

并用：

```text
cell_evidence_df
normalized_evidence_df
```

补充 `source_trace`。

### 16.1 字段来源

| 字段 | 来源 | 说明 |
|---|---|---|
| `cell_id`, `cell_start`, `cell_end`, `cell_center` | cells_df / geo_states_df / cell_response_df | 10m cell 空间标识 |
| `operation_state` | cell_response_df | cell 内主导工况 |
| `plc_metrics` | cell_response_df | PLC 聚合指标 |
| `stop_duration_min` | cell_response_df | cell 内停机时长 |
| `abnormal_score` | cell_response_df | 与 RAI 同源的异常分 |
| `RAI` | cell_response_df | 施工响应异常度 |
| `has_plc_response` | cell_response_df 是否命中 | 是否有当日 PLC 施工响应证据 |
| `fused_grade` | geo_states_df | 融合围岩等级 |
| `main_hazards` | geo_states_df | 主要地质关注标签 |
| `hazard_scores` | geo_states_df | hazard 分数 |
| `confidence_score` | geo_states_df | 地质融合置信度 |
| `uncertainty_level` | geo_states_df | 地质融合不确定性 |
| `conflict_level` | geo_states_df | 多源证据冲突等级 |
| `GRS_geo_base` | geo_states_df | 地质证据关注度 |
| `has_geology_evidence` | geo_states_df | 是否有地质证据支撑 |
| `supporting_evidence_ids` | geo_states_df | 支撑该 cell 的证据 ID |
| `source_trace` | normalized evidence | 证据来源可追溯信息 |
| `GRCI`, `GRCI_available` | coupling 模块 | 地质-施工响应耦合关注度及可用性 |
| `is_excavated_today` | day_start/day_end 与 cell 区间重叠 | 是否属于当日已掘范围 |
| `is_current_face_cell` | current_chainage 与 cell 区间关系 | 当前掌子面所在 cell |
| `is_forward_cell` | current_chainage 和 lookahead | 是否严格前方 cell |

### 16.2 空间状态判断

当日已掘 cell：

```text
is_excavated_today =
    max(cell_start, day_start_chainage)
    < min(cell_end, day_end_chainage)
```

当前掌子面 cell：

```text
is_current_face_cell =
    cell_start <= current_chainage < cell_end
```

严格前方 cell：

```text
is_forward_cell =
    cell_start >= current_chainage
    and cell_start within [current_chainage, current_chainage + lookahead_m)
```

因此当前掌子面所在 cell 不会因为 cell 与前方窗口重叠而直接混入严格 forward cell。

## 17. GRCI 计算逻辑

`GRCI` 计算函数：

```text
coupling/grs_rai_grci.py::compute_cell_grci
```

### 17.1 GRCI 的语义

`GRCI` 表示 cell 级地质-施工响应耦合关注度，用于已掘区段复核排序。

它不表示：

```text
灾害概率
灾害预测
地质灾害已经发生
前方风险
TSP/HSP 结论一定真实
```

### 17.2 GRCI 可用性条件

只有同时满足以下条件才计算正式 `GRCI`：

```text
GRS_geo_base is not None
RAI is not None
has_plc_response == True
```

如果缺少 PLC response 或 `RAI`：

```text
GRCI = None
GRCI_available = False
GRCI_source = "unavailable"
GRCI_unavailable_reason = "missing_plc_response"
coupling_level = "unavailable"
coupling_explanation = "该里程单元缺少当日 PLC 施工响应证据，暂不计算地质-施工响应耦合关注度。"
```

如果缺少地质证据：

```text
GRCI = None
GRCI_available = False
GRCI_source = "unavailable"
GRCI_unavailable_reason = "missing_geology_evidence"
```

### 17.3 GRCI 公式

当前公式：

```text
GRCI =
    0.55 * GRS_geo_base
  + 0.35 * RAI
  + 0.10 * GRS_geo_base * RAI
```

输入会先限制在 `[0, 1]`，输出保留 4 位小数。

`coupling_level` 分类：

| GRCI | coupling_level |
|---:|---|
| `None` | `unknown` / `unavailable` |
| `>= 0.75` | `high` |
| `>= 0.50` | `medium` |
| `>= 0.25` | `low` |
| `< 0.25` | `none` |

### 17.4 high_grci_cells 筛选

筛选函数：

```text
coupling/grs_rai_grci.py::high_grci_cells
```

候选条件：

```text
GRCI_available == True
GRCI is not None
is_excavated_today == True
is_forward_cell == False
```

按 `GRCI` 从高到低排序，默认取前 10。

这保证：

```text
前方 cell 不进入 high_grci_cells
没有 RAI 的 cell 不进入 high_grci_cells
没有 PLC response 的 cell 不进入 high_grci_cells
```

## 18. Forward Profile

前方 profile 构建函数：

```text
geology_v2/forward_profile.py::build_forward_profile
```

输入：

```text
geo_states_df
current_chainage
lookahead_m = 30.0
step_m = 10.0
advance_direction = 1
```

输出：

```text
forward_profile
```

### 18.1 前方窗口划分

以 `current_chainage` 为起点，按 `step_m` 划分：

```text
0-10m
10-20m
20-30m
```

正向掘进时：

```text
range_start = current_chainage + distance_start
range_end = current_chainage + distance_end
```

每个窗口选择：

```text
cell_center >= range_start
and cell_center < range_end
```

的 geo cell。

### 18.2 attention_level

每个前方窗口的分数：

```text
score = max(GRS_geo_base of cells in this window)
```

关注等级：

| score | attention_level |
|---:|---|
| `>= 0.75` | `high` |
| `>= 0.50` | `medium` |
| `>= 0.25` | `low` |
| `< 0.25` 或无证据 | `none` |

### 18.3 前方提示不使用 GRCI

`forward_profile` 只使用：

```text
GRS_geo_base
fused_grade
main_hazards
confidence_score
uncertainty_level
supporting_evidence_ids
source_trace
```

不使用：

```text
RAI
GRCI
high_grci_cells
```

原因是前方 cell 没有当日 PLC response，不能形成地质-施工响应耦合复核指标。

## 19. Evidence Pack 构建

Evidence Pack 构建函数：

```text
llm/evidence_pack.py::build_prompt_evidence_pack
```

它是报告生成的唯一证据入口。

### 19.1 当前 Evidence Pack 分层

当前 Evidence Pack 主要包含：

```text
report_scope
operation_evidence
cluster_evidence
gas_evidence
geology_evidence
excavated_review_evidence
forward_evidence
forward_attention_evidence
background_context_evidence
coupling_evidence
quality_evidence
source_trace
generation_constraints
warnings
```

### 19.2 geology_evidence.key_cells 与 selected_cells

正式字段：

```text
geology_evidence.key_cells
```

兼容字段：

```text
geology_evidence.selected_cells
```

当前两者内容一致。Grounding checker 优先读取 `key_cells`，如果没有再 fallback 到 `selected_cells`。

### 19.3 三类地质 cell

Evidence Pack 将关键地质 cell 分成三类：

已掘复核 cell：

```text
excavated_review_evidence.review_cells
coupling_evidence.high_grci_cells
```

这些 cell 必须已经掘进，且有正式 GRCI。

前方关注 cell：

```text
forward_attention_evidence.forward_attention_cells
forward_evidence.forward_attention_cells
```

这些 cell 是当前掌子面前方 cell，不使用 GRCI。

背景上下文 cell：

```text
background_context_evidence.background_context_cells
```

这些 cell 有地质证据，但不属于当日已掘复核，也不属于当前前方 30m 窗口。它们用于提供地质证据上下文，不能写成当日施工响应异常。

## 20. 报告生成约束

报告 prompt 构建：

```text
llm/report_prompt.py::build_prompt
```

no-LLM 模板报告：

```text
llm/evidence_pack.py::build_template_report
```

当前报告必须遵守：

```text
不得把 GRCI 写成灾害概率；
不得把 GRCI 写成前方风险；
不得把前方提示写成已发生事实；
不得把 TSP/HSP 预报写成现场揭露事实；
不得声称 TSP/HSP 结论一定真实；
不得无证据推断地质灾害；
不得让 LLM 重新计算 GRCI / RAI / forward cell。
```

`use_llm=False` 时：

```text
直接生成模板报告
warnings 包含 "LLM disabled"
```

`use_llm=True` 时：

```text
先调用 llm_api
如果失败或返回不可用
-> fallback 到模板报告
-> 写入 warning
```

## 21. Quality / Grounding / Trace

### 21.1 claim 抽取

claim 抽取函数：

```text
llm/report_claim_extractor.py
```

它按规则识别报告中的技术主张，类型包括：

```text
operation
gas
coupling
forward_segment
current_face
geology
recommendation
unknown
```

非技术性标题、表格分隔符、短标签等会在 Trace 阶段被过滤。

### 21.2 grounding checker

grounding 检查函数：

```text
llm/report_grounding_checker.py::check_report_grounding
```

它从 Evidence Pack 中读取：

```text
operation_evidence
cluster_evidence
gas_evidence
geology_evidence.key_cells
forward_evidence.forward_profile
coupling_evidence.high_grci_cells
generation_constraints
```

并尝试为每条 claim 找到结构化支撑。

### 21.3 trace_support_type

当前 trace 会标注支撑类型：

| trace_support_type | 含义 |
|---|---|
| `statistical_support` | PLC、工况、气体等统计支撑 |
| `coupling_review_support` | high GRCI / 耦合复核支撑 |
| `forward_attention_support` | forward_profile 前方关注支撑 |
| `observed_support` | 掌子面素描、钻孔等 observed 证据 |
| `forecast_support` | TSP/HSP 等 prediction 证据 |
| `interpreted_support` | report_conclusion 等解释性证据 |
| `cell_evidence_support` | key cell 结构化地质证据支撑 |
| `policy_support` | 生成约束、方法边界或建议策略支撑 |
| `none` | 未找到可用支撑 |

### 21.4 quality_score

质量检查函数：

```text
llm/report_quality_checker.py::check_report_quality
```

基础分：

```text
score = 100
```

扣分来自：

```text
禁用表达
强结论越界
章节缺失
grounding_rate 过低
unsupported claim 相关 warning
```

当前策略文件：

```text
llm/report_policy.py
```

默认扣分权重包括：

```text
forbidden_error = 15
warning = 5
missing_section = 3
unsupported_claim = 8
low_grounding_rate = 10
```

注意：`quality_score` 是报告合规和可追溯质量分，不是工程安全分，也不是模型预测精度。

## 22. 2023-12-30 真实数据流复盘

本节基于当前导出目录：

```text
backend/outputs/pipeline_exports/2023-12-30/
```

以及当前系统说明文档中记录的真实读取信息。由于当前导出文件没有单独落盘完整 `geo_states_df` 和原始 `evidence_db.csv` 行数，本文不虚构这些未导出的中间数；凡是当前导出可直接复核的，均列出具体值。

### 22.1 输入

日期：

```text
2023-12-30
```

PLC 文件：

```text
G:/我的云端硬盘/TBM9/TBM9_2023/tbm_data_20231230.csv
```

地质证据库：

```text
G:/我的云端硬盘/TBM9/DB/evidence_db.csv
```

PLC 读取结果：

```text
PLC 行数：4098
daily_chainage_min：1014601.0
daily_chainage_max：1014616.0
daily_advance_m：15.0
current_chainage：1014616.0
```

地质证据库总行数当前没有在 export 中单独落盘，因此本文不写具体总行数。当前可复核的 Evidence Pack 地质证据引用为：

```text
key_cells 去重 supporting_evidence_ids：58 条
excavated_review_evidence 去重 supporting_evidence_ids：6 条
forward_attention_evidence 去重 supporting_evidence_ids：5 条
background_context_evidence 去重 supporting_evidence_ids：51 条
```

### 22.2 PLC response cells

`cell_response_df` 行数：

```text
2
```

对应两个当日施工响应 cell：

| cell_id | cell_start | cell_end | sample_count | stop_duration_min | RAI |
|---|---:|---:|---:|---:|---:|
| `cell_1014600_1014610` | 1014600.0 | 1014610.0 | 3005 | 837.3333 | 0.517548 |
| `cell_1014610_1014620` | 1014610.0 | 1014620.0 | 1093 | 236.5000 | 0.447116 |

这两个 cell 与当日推进范围 `1014601.0 - 1014616.0` 对齐。当日推进 15m，10m cell 粒度下覆盖两个 cell 是合理结果。

RAI 分量示例：

| cell_id | stop_ratio | abnormal_ratio | speed_drop_score | torque_volatility_score | speed_volatility_score |
|---|---:|---:|---:|---:|---:|
| `cell_1014600_1014610` | 0.793180 | 0.001105 | 1.0 | 0.0 | 0.0 |
| `cell_1014610_1014620` | 0.615351 | 0.003903 | 1.0 | 0.0 | 0.0 |

代入公式：

```text
cell_1014600_1014610:
RAI = 0.40*0.793180 + 0.25*0.001105 + 0.20*1.0 + 0.10*0 + 0.05*0
    = 0.517548

cell_1014610_1014620:
RAI = 0.40*0.615351 + 0.25*0.003903 + 0.20*1.0 + 0.10*0 + 0.05*0
    = 0.447116
```

### 22.3 geo_states 与 ConstructionStateCell

当前导出 summary：

```text
construction_state_cells_row_count = 14
geo_states_df cell 数 = 14
```

说明当前日报主链路只保留 `report_scope` 内 14 个 10m cell，其中当日 PLC 施工响应覆盖 2 个 `daily_review` cell。

这正是当前方法的关键区别：

```text
geo_states_df：描述地质证据覆盖的 cell
cell_response_df：描述当日 PLC 实际经过的 cell
construction_state_cells：二者的统一合并对象
```

### 22.4 high GRCI cells

2023-12-30 有两个 high GRCI 复核 cell：

| cell_id | GRS_geo_base | RAI | GRCI | coupling_level | excavated | forward |
|---|---:|---:|---:|---|---|---|
| `cell_1014600_1014610` | 0.575306 | 0.517548 | 0.5273 | medium | true | false |
| `cell_1014610_1014620` | 0.611930 | 0.447116 | 0.5204 | medium | true | false |

GRCI 计算复核：

```text
cell_1014600_1014610:
GRCI =
    0.55*0.5753056256736392
  + 0.35*0.5175481528260184
  + 0.10*0.5753056256736392*0.5175481528260184
  = 0.5273

cell_1014610_1014620:
GRCI =
    0.55*0.611930359971126
  + 0.35*0.44711621856027756
  + 0.10*0.611930359971126*0.44711621856027756
  = 0.5204
```

这两个 cell 都满足：

```text
GRCI_available == True
has_plc_response == True
has_geology_evidence == True
is_excavated_today == True
is_forward_cell == False
```

### 22.5 前方 profile

当前掌子面：

```text
current_chainage = 1014616.0
lookahead_m = 30.0
```

forward_profile 三个窗口：

| range_label | start | end | supporting_cell_ids | attention_level | GRS 使用来源 |
|---|---:|---:|---|---|---|
| `0-10m` | 1014616.0 | 1014626.0 | `cell_1014620_1014630` | medium | `GRS_geo_base=0.535269` |
| `10-20m` | 1014626.0 | 1014636.0 | `cell_1014630_1014640` | medium | `GRS_geo_base=0.557462` |
| `20-30m` | 1014636.0 | 1014646.0 | `cell_1014640_1014650` | low | `GRS_geo_base=0.483092` |

这些前方 cell 的状态：

```text
RAI = None
GRCI = None
GRCI_available = False
GRCI_unavailable_reason = "missing_plc_response"
is_forward_cell = True
```

因此它们只能进入 `forward_profile` 与 `forward_attention_cells`，不能进入 `high_grci_cells`。

### 22.6 Evidence Pack key_cells

2023-12-30：

```text
key_cells_count = 13
selected_cells_count = 13
grounding_key_cells_seen = 13
```

`key_cells` 列表如下：

| 顺序 | cell_id | cell_start | cell_end | GRS | RAI | GRCI | 类型 |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `cell_1014600_1014610` | 1014600.0 | 1014610.0 | 0.575306 | 0.517548 | 0.5273 | 已掘复核 |
| 2 | `cell_1014610_1014620` | 1014610.0 | 1014620.0 | 0.611930 | 0.447116 | 0.5204 | 已掘复核 |
| 3 | `cell_1014630_1014640` | 1014630.0 | 1014640.0 | 0.557462 | None | None | 前方关注 |
| 4 | `cell_1014620_1014630` | 1014620.0 | 1014630.0 | 0.535269 | None | None | 前方关注 |
| 5 | `cell_1014640_1014650` | 1014640.0 | 1014650.0 | 0.483092 | None | None | 前方关注 |
| 6 | `cell_1013180_1013190` | 1013180.0 | 1013190.0 | 0.898125 | None | None | 背景上下文 |
| 7 | `cell_1013540_1013550` | 1013540.0 | 1013550.0 | 0.894525 | None | None | 背景上下文 |
| 8 | `cell_1013670_1013680` | 1013670.0 | 1013680.0 | 0.891841 | None | None | 背景上下文 |
| 9 | `cell_1013220_1013230` | 1013220.0 | 1013230.0 | 0.870221 | None | None | 背景上下文 |
| 10 | `cell_1013120_1013130` | 1013120.0 | 1013130.0 | 0.869908 | None | None | 背景上下文 |
| 11 | `cell_1013130_1013140` | 1013130.0 | 1013140.0 | 0.868046 | None | None | 背景上下文 |
| 12 | `cell_1013570_1013580` | 1013570.0 | 1013580.0 | 0.862671 | None | None | 背景上下文 |
| 13 | `cell_1013110_1013120` | 1013110.0 | 1013120.0 | 0.861413 | None | None | 背景上下文 |

注意：背景上下文 cell 的 GRS 可以很高，但它们没有当日 PLC response，不是 high GRCI cell，也不是当日前方 30m cell。

### 22.7 报告 claim 与证据映射

典型 claim 支撑关系：

| 报告 claim | 支撑位置 |
|---|---|
| 本日已形成 2 个可用的已开挖区段 GRCI 复核优先 cell。 | `coupling_evidence.high_grci_cells` |
| GRCI 仅用于已开挖区段复核排序。 | `generation_constraints` 与 `high_grci_cells` 筛选规则 |
| 前方关注提示来自 forward_profile，共 3 个前方窗口。 | `forward_evidence.forward_profile.profile` |
| PLC 工况统计显示主导工况为停机。 | `operation_evidence.operation_mode_summary` |
| `cell_1014600_1014610` 的 GRCI 复核优先级为 medium，GRCI 约 0.53。 | `coupling_evidence.high_grci_cells[0]` |
| `cell_1014610_1014620` 的 GRCI 复核优先级为 medium，GRCI 约 0.52。 | `coupling_evidence.high_grci_cells[1]` |
| 前方 cell 仅表示关注提示，不表示已发生事实。 | `generation_constraints` 与 `forward_profile` |

2023-12-30 当前质量摘要：

```text
quality_score = 92
grounding_rate = 0.913
unsupported_claim_count = 2
```

当前两个 unsupported claim 已审计：

| claim | 类型 | 审计结论 |
|---|---|---|
| `如无当日可用掌子面素描，不把前方证据写成已揭露事实。` | 方法边界说明 | 应归入 policy_support 或 generation_constraints 支撑，不影响方法逻辑 |
| `前方关注提示（当前掌子面前方地质关注提示）` | 报告章节标题 | 应作为结构性句子过滤，不影响方法逻辑 |

因此当前 `unsupported_claim_count=2` 暴露的是 checker 对边界声明和标题的识别问题，不是 GRCI / forward / Evidence Pack 主方法逻辑错误。

## 23. 当前计算链总表

| 阶段 | 输入 | 输出 | 关键公式或规则 | 报告用途 |
|---|---|---|---|---|
| PLC 读取 | date | `df_plc` | `tbm_data_YYYYMMDD.csv` | 当日施工事实 |
| PLC 质量检查 | `df_plc` | `quality_report` | 字段别名识别、缺失诊断 | warning、边界说明 |
| 工况识别 | PLC 行 | `operation_mode` | 状态字段 + 推力/速度/扭矩规则 | 工况统计 |
| 工况分段 | operation_mode + time | segments | 连续状态分组，补采样间隔 | 工况时长 |
| 聚类状态 | working rows | cluster_summary | StandardScaler + KMeans(3) | 施工状态辅助描述 |
| 气体统计 | gas cols | gas_summary | mean/max/min/exceed | 气体监测分析 |
| PLC cell 聚合 | PLC rows | `cell_response_df` | 10m cell + duration aggregation | RAI |
| RAI | cell response | `RAI` | 0.40 stop + 0.25 abnormal + 0.20 speed drop + 0.10 torque volatility + 0.05 speed volatility | 施工响应异常 |
| 地质标准化 | evidence_df | normalized_evidence_df | 来源、角色、里程、hazard、grade 统一 | 地质证据结构化 |
| online 过滤 | normalized evidence | available evidence | current_chainage + analysis_date + face_chainage | 防未来信息泄漏 |
| HSP 去重 | available evidence | dedup evidence | report/source/face/center/hazard family | 防重复加权 |
| 地质 cell | evidence range | cells_df | 10m cell | 地质空间单元 |
| 证据投影 | evidence + cells | cell_evidence_df | Gaussian spatial weight | evidence-cell 关系 |
| 地质融合 | cell_evidence | geo_states_df | grade/hazard/confidence/conflict | GRS |
| GRS | geo state | GRS_geo_base | 0.45 grade + 0.45 hazard + 0.10 confidence | 地质关注度 |
| ConstructionStateCell | response + geology | cells | cell_id 合并 | 唯一核心对象 |
| GRCI | GRS + RAI | GRCI | 0.55 GRS + 0.35 RAI + 0.10 GRS*RAI | 已掘复核 |
| high_grci | cells | high_grci_cells | 可用 GRCI + 已掘 + 非前方 | 复核重点 |
| forward_profile | geo_states + current | forward profile | 前方 0-30m，按 GRS 分级 | 前方关注提示 |
| Evidence Pack | summaries + cells | prompt_evidence_pack | 分层证据包 | 报告唯一证据源 |
| 报告生成 | Evidence Pack | report_text | 模板或 LLM fallback | 日报正文 |
| Quality | report + pack | quality_summary | 禁用表达、章节、grounding | 质量分 |
| Trace | report + pack | report_trace | claim -> evidence | 可追溯核验 |

## 24. 当前未实现或不应误解的内容

当前系统没有做以下事情：

```text
没有重新解释 TSP/HSP 原始探测信号；
没有做地质灾害概率预测；
没有做 TBM 物理仿真数字孪生；
没有从 PLC 数据反推出真实地质成因；
没有判断 TSP/HSP 结论一定真实；
没有让 LLM 参与数值计算；
没有把 Agent 接入当前主流程；
没有把前方 cell 计算为 GRCI；
没有把 background_context_cell 当作当日施工异常；
没有用当前 smoke test 替代论文实验。
```

## 25. 白话总结

当前后端的方法可以用一句话概括：

```text
把 PLC 当日施工响应和多源地质证据统一放到 10m 里程 cell 上，已掘区段用 GRS + RAI 形成 GRCI 复核关注度，前方区段只用可用地质证据形成 forward_profile，再用 Evidence Pack 约束报告生成，并用 Quality / Trace 检查报告里的每一句技术主张能否回到结构化证据。
```

其中：

```text
GRS 是地质证据关注度；
RAI 是施工响应异常度；
GRCI 是已掘区段地质-施工响应耦合复核关注度；
forward_profile 是前方地质关注提示；
Evidence Pack 是报告可写内容的证据边界；
Trace 是报告 claim 到证据的追溯链。
```

最重要的边界是：

```text
GRCI 不是灾害概率；
GRCI 不是前方风险；
没有 RAI 不计算正式 GRCI；
前方提示不能写成已发生事实；
TSP/HSP 只能作为超前预报证据，不能被写成现场揭露事实。
```

## 附录 A：字段反向索引

本附录用于从字段反查来源、计算方法、可空条件、下游用途和报告/Trace 关系。表中的“进入报告/Trace”表示该字段可能直接进入 Evidence Pack、报告模板或 trace 支撑；不是说它一定逐字出现在报告正文中。

### A.1 PLC / cell_response_df 字段

主要产生函数：

```text
plc/cell_response.py::project_plc_response_to_cells
plc/response.py::analyze_plc_response
analysis/dataprocess.py::annotate_operation_mode
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `cell_id` | `cell_response_df` / `ConstructionStateCell` | `project_plc_response_to_cells` | PLC 里程列 | `cell_{cell_start}_{cell_end}` | 缺少里程时整表为空 | cell 合并、Evidence Pack、debug | 是 | 10m cell 主键 |
| `cell_start` | 同上 | 同上 | PLC 里程列 | `floor(chainage/cell_length)*cell_length` | 缺少里程时为空表 | 空间判断、GRCI、forward | 是 | cell 起点 |
| `cell_end` | 同上 | 同上 | `cell_start` | `cell_start + cell_length` | 缺少里程时为空表 | 空间判断、GRCI、forward | 是 | cell 终点 |
| `cell_center` | 同上 | 同上 | `cell_start`, `cell_end` | `(cell_start + cell_end)/2` | 缺少里程时为空表 | 地质投影、forward、debug | 是 | cell 中心里程 |
| `sample_count` | `cell_response_df` / `plc_metrics` | `project_plc_response_to_cells` | PLC 行 | cell 内记录数 | 无 PLC 命中时无该 cell response | `plc_metrics` | debug 为主 | 反映 cell 内 PLC 样本量 |
| `duration_sec` | `cell_response_df` | `project_plc_response_to_cells` | 时间列 | cell 内 row duration 求和 | 无时间时每行按 1s 兜底；无 PLC 命中为空 | `duration_min`, `plc_metrics` | debug 为主 | cell 施工记录持续秒数 |
| `duration_min` | `plc_metrics` | `build_construction_state_cells` | `duration_sec` | `duration_sec/60` 或直接从 response 记录换算 | 无 PLC response 时为空 | Evidence Pack/debug | 可进入 debug | cell 施工记录持续分钟 |
| `operation_state` | `cell_response_df` / `ConstructionStateCell` | `project_plc_response_to_cells` | operation flags | work/stop/abnormal/transition 按持续时间主导状态 | 无 PLC response 时为空 | Evidence Pack、报告工况说明 | 可进入报告 | cell 内主导工况 |
| `work_duration_sec` | `cell_response_df` | `project_plc_response_to_cells` | `is_working` + duration | working 行 duration 求和 | 无 PLC response 时为空 | `plc_metrics` | debug 为主 | 稳定掘进时长 |
| `work_duration_min` | `plc_metrics` | `build_construction_state_cells` | `work_duration_sec` | 秒转分钟 | 无 PLC response 时为空 | Evidence Pack/debug | debug 为主 | 稳定掘进分钟 |
| `stop_duration_sec` | `cell_response_df` | `project_plc_response_to_cells` | `is_stopped` + duration | stopped 行 duration 求和 | 无 PLC response 时为空 | `stop_ratio` | debug 为主 | 停机时长 |
| `stop_duration_min` | `ConstructionStateCell` | `build_construction_state_cells` | `cell_response_df` | 秒转分钟或 response 字段读取 | 无 PLC response 时为空 | Evidence Pack/debug | 可进入报告 | 停机高不一定代表地质异常，可能包含组织停机或计划停机 |
| `abnormal_duration_sec` | `cell_response_df` | `project_plc_response_to_cells` | `is_abnormal` + duration | abnormal 行 duration 求和 | 无 PLC response 时为空 | `abnormal_ratio` | debug 为主 | 异常扭矩等响应时长 |
| `abnormal_duration_min` | `plc_metrics` | `build_construction_state_cells` | `abnormal_duration_sec` | 秒转分钟 | 无 PLC response 时为空 | Evidence Pack/debug | debug 为主 | 异常响应分钟 |
| `speed_mean` | `cell_response_df` / `ConstructionStateCell` | `project_plc_response_to_cells` | 推进速度列 | cell 内均值 | 缺字段或全空时为空 | RAI 分量、debug | 可进入 debug | 推进速度均值 |
| `speed_std` | `cell_response_df` | 同上 | 推进速度列 | cell 内标准差 | 缺字段或样本不足为空/0 | `speed_volatility_score` | debug 为主 | 速度波动来源 |
| `thrust_mean` | `ConstructionStateCell` | 同上 | 推力列 | cell 内均值 | 缺字段或全空时为空 | debug/Evidence Pack | 可进入 debug | 推力均值 |
| `thrust_std` | `cell_response_df` | 同上 | 推力列 | cell 内标准差 | 缺字段或样本不足为空/0 | debug | debug 为主 | 当前不直接进入 RAI 公式 |
| `torque_mean` | `ConstructionStateCell` | 同上 | 刀盘扭矩列 | cell 内均值 | 缺字段或全空时为空 | debug/Evidence Pack | 可进入 debug | 扭矩均值 |
| `torque_std` | `cell_response_df` | 同上 | 刀盘扭矩列 | cell 内标准差 | 缺字段或样本不足为空/0 | `torque_volatility_score` | debug 为主 | 扭矩波动来源 |
| `rpm_mean` | `cell_response_df` | 同上 | 刀盘转速列 | cell 内均值 | 缺字段或全空时为空 | debug | debug 为主 | 转速均值，当前不直接进入 RAI |
| `rpm_std` | `cell_response_df` | 同上 | 刀盘转速列 | cell 内标准差 | 缺字段或样本不足为空/0 | debug | debug 为主 | 转速波动，当前不直接进入 RAI |
| `stop_ratio` | `cell_response_df` / `plc_metrics` | `project_plc_response_to_cells` | `stop_duration_sec`, `duration_sec` | `stop_duration_sec/duration_sec` | duration 为 0 或无 PLC response 时为空/0 | RAI | 间接进入报告 | 停机占比；不是异常原因判定 |
| `abnormal_ratio` | 同上 | 同上 | `abnormal_duration_sec`, `duration_sec` | `abnormal_duration_sec/duration_sec` | duration 为 0 或无 PLC response 时为空/0 | RAI | 间接进入报告 | 异常响应占比 |
| `speed_drop_score` | `cell_response_df` / `plc_metrics` | `project_plc_response_to_cells` | `speed_mean`, 当日速度分布 | `clip01(1-speed_mean/max(global_speed_q75,1e-6))` | 速度缺失时兜底 | RAI | 间接进入报告 | 使用当日推进速度 75% 分位数作参照 |
| `torque_volatility_score` | 同上 | 同上 | `torque_std`, `torque_mean` | `clip01(torque_std/max(abs(torque_mean),1.0))` | 扭矩缺失时为 0 或空 | RAI | 间接进入报告 | 扭矩波动启发式分量 |
| `speed_volatility_score` | 同上 | 同上 | `speed_std`, `speed_mean` | `clip01(speed_std/max(abs(speed_mean),1.0))` | 速度缺失时为 0 或空 | RAI | 间接进入报告 | 速度波动启发式分量 |
| `abnormal_score` | `cell_response_df` / `ConstructionStateCell` | `project_plc_response_to_cells` | RAI 分量 | `0.40*stop_ratio+0.25*abnormal_ratio+0.20*speed_drop_score+0.10*torque_volatility_score+0.05*speed_volatility_score` | 无 PLC response 时为空 | `RAI`, Evidence Pack | 可进入报告 | 工程启发式异常分 |
| `RAI` | `cell_response_df` / `ConstructionStateCell` | `project_plc_response_to_cells` | `abnormal_score` | `RAI=abnormal_score` | 无 PLC response 时为空 | GRCI、Evidence Pack、已掘复核章节 | 是 | 施工响应异常度，不是灾害概率 |
| `response_support_count` | `cell_response_df` | `project_plc_response_to_cells` | PLC 行 | cell 内样本数 | 无 PLC response 时为空 | debug、可信度辅助 | debug 为主 | PLC response 支撑样本数 |
| `response_metrics` | `cell_response_df` / `plc_metrics` | `project_plc_response_to_cells`, `build_construction_state_cells` | 聚合分量 | dict/JSON 形式保存 RAI 分量 | 无 PLC response 时为空 | debug、导出复盘 | debug 为主 | 当前 CSV 中以 `plc_metrics` 字段承载 |

### A.2 地质 normalized_evidence_df 字段

主要产生函数：

```text
geology_v2/evidence_normalizer.py::normalize_evidence_df
geology_v2/evidence_normalizer.py::filter_available_evidence
geology_v2/evidence_dedup.py::deduplicate_hsp_anomaly_points
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `evidence_id` | `normalized_evidence_df` | `normalize_evidence_df` | evidence_db | 原始 ID 或标准化生成 | 理论上不应为空 | source_trace、supporting ids | 是 | 证据唯一标识 |
| `report_id` | 同上 | 同上 | evidence_db | 原始报告 ID | 旧数据可能为空 | dedup、source_trace | 是 | 报告来源标识 |
| `source_type` | 同上 | 同上 | 原始 source | 原始来源类型 | 可为空 | 标准化前参考 | debug 为主 | 原始来源，不作为主逻辑字段 |
| `source_type_norm` | 同上 | 同上 | `source_type` | alias 映射为 TSP/HSP/face_sketch 等 | unknown 兜底 | 投影、融合、Trace | 是 | 区分证据来源类型 |
| `evidence_role` | 同上 | 同上 | `source_type_norm` | SOURCE_ROLE_MAP 映射 | unknown/background 兜底 | online 过滤、Trace 支撑类型 | 是 | prediction/observed/interpreted/background |
| `spatial_type` | 同上 | 同上 | 原始字段/attrs | point/anomaly_point/segment/overview 等 | unknown 兜底 | 投影距离、sigma | 是 | 证据空间形态 |
| `report_date` | 同上 | 同上 | evidence_db/attrs | 日期解析 | 旧数据可空 | online 过滤 | debug/Trace | 报告日期 |
| `issue_date` | 同上 | 同上 | evidence_db/attrs | 日期解析 | 可空 | online 过滤 | debug/Trace | 形成/签发日期 |
| `available_date` | 同上 | 同上 | evidence_db/attrs | 当前代码若存在则保留 | 可空 | 可用性参考 | debug 为主 | 不是当前主要过滤字段 |
| `start_num` | 原始 evidence 字段 | 输入保留 | evidence_db | 原始起点里程 | 可空 | 标准化里程 | debug 为主 | 原始数值 |
| `end_num` | 原始 evidence 字段 | 输入保留 | evidence_db | 原始终点里程 | 可空 | 标准化里程 | debug 为主 | 原始数值 |
| `face_num` | 原始 evidence 字段 | 输入保留 | evidence_db | 原始掌子面里程 | 可空 | `face_chainage` | debug 为主 | 可用性判断候选 |
| `start_chainage` | `normalized_evidence_df` | `normalize_evidence_df` | `start_num/end_num/attrs` | 数值化并保证 start <= end | 点证据或缺里程时可空 | 投影、source_trace | 是 | 标准化起点 |
| `end_chainage` | 同上 | 同上 | 同上 | 数值化并保证 start <= end | 可空 | 投影、source_trace | 是 | 标准化终点 |
| `center_chainage` | 同上 | 同上 | start/end/face | 区间中点或点里程 | 缺里程时可空 | 投影、过滤 | 是 | 证据中心 |
| `face_chainage` | 同上 | 同上 | face_num/attrs/report_id/raw_text | 优先原始 face 字段，缺失时从文本桩号兜底 | 可空；forecast_like 缺失会被 online 排除 | online 过滤 | debug/Trace | 防未来信息泄漏关键字段 |
| `grade` | 同上 | 同上 | attrs_json | support_grade/grade 等归一 | 可空 | GRS grade component | 是 | 围岩等级关注来源 |
| `lithology` | 同上 | 同上 | attrs_json/raw | 文本或属性解析 | 可空 | source_trace | 可进入 Trace | 岩性描述 |
| `weathering` | 同上 | 同上 | attrs_json/raw | 文本或属性解析 | 可空 | hazard/trace | 可进入 Trace | 风化描述 |
| `joint_development` | 同上 | 同上 | attrs_json/raw | 文本或属性解析 | 可空 | hazard_tags | 可进入 Trace | 裂隙发育信息 |
| `rock_mass_state` | 同上 | 同上 | attrs_json/raw | 文本或属性解析 | 可空 | hazard_tags | 可进入 Trace | 围岩完整性 |
| `stability` | 同上 | 同上 | attrs_json/raw | 文本或属性解析 | 可空 | hazard_tags | 可进入 Trace | 稳定性描述 |
| `water_flag` | 同上 | 同上 | attrs_json | 兼容 0/1 flag | 缺失填 0 | hazard_scores | 间接进入报告 | 0 只表示非 positive，不等于明确无水 |
| `water_state` | 同上 | 同上 | attrs_json | positive/negative/unknown | 可 unknown | 冲突检测 | debug/Trace | 三态水信息 |
| `collapse_flag` | 同上 | 同上 | attrs_json/HSP anomaly | 兼容 0/1 flag | 缺失填 0 | hazard_scores | 间接进入报告 | 0 不等于明确无掉块 |
| `collapse_state` | 同上 | 同上 | attrs_json/HSP anomaly | positive/negative/unknown | 可 unknown | 冲突检测 | debug/Trace | 三态掉块信息 |
| `deformation_flag` | 同上 | 同上 | attrs_json | 兼容 0/1 flag | 缺失填 0 | hazard_scores | 间接进入报告 | 0 不等于明确无变形 |
| `deformation_state` | 同上 | 同上 | attrs_json | positive/negative/unknown | 可 unknown | 冲突检测 | debug/Trace | 三态变形信息 |
| `hazard_tags` | 同上 | 同上 | attrs/raw/parser | 标准 hazard tag 列表 | 可为空 | hazard_scores、报告 | 是 | prediction 中表示预报提示，不等于已发生事实 |
| `attribute_tags` | 同上 | 同上 | attrs/raw/parser | 属性标签列表 | 可为空 | debug/Trace | 可进入 Trace | 辅助描述 |
| `method_tags` | 同上 | 同上 | attrs/raw/parser | 方法标签列表 | 可为空 | debug/Trace | 可进入 Trace | 证据方法来源 |
| `unknown_hazard_tags` | 同上 | 同上 | attrs/raw/parser | 未识别 hazard 标签 | 可为空 | debug | debug 为主 | 解析不确定项 |
| `confidence` | 同上 | 同上 | attrs_json | 原始/解析置信度 | 可空 | evidence_strength | debug 为主 | 来源置信，不是准确率 |
| `source_reliability` | 同上 | 同上 | config | SOURCE_RELIABILITY 映射 | unknown 兜底 | effective_weight | 间接进入报告 | 来源权重，不是真实概率 |
| `evidence_strength` | 同上 | 同上 | config + attrs | source/spatial/confidence 综合 | unknown 兜底 | effective_weight | 间接进入报告 | 证据强度权重 |
| `raw_text` | 同上 | 输入保留 | evidence_db | 原始文本 | 可空 | source_trace excerpt | 是 | 报告追溯文本片段 |
| `attrs_json` | 同上 | 输入保留/解析 | evidence_db | JSON 属性 | 解析失败为空 dict | 标准化字段来源 | debug 为主 | 原始结构化属性 |
| `parse_warnings` | 同上 | 标准化/去重 | parser/normalizer | 解析不确定性列表 | 可为空 | debug/质量解释 | 可进入 debug | 记录解析不确定性 |

### A.3 cell_evidence_df 字段

产生函数：

```text
geology_v2/evidence_projector.py::project_evidence_to_cells
geology_v2/fusion_engine.py::fuse_geo_states
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `cell_id` | `cell_evidence_df` | `project_evidence_to_cells` | `cells_df` | 投影命中的 cell | 无投影则无记录 | geo fusion | 间接进入 Trace | cell-evidence 关系键 |
| `evidence_id` | 同上 | 同上 | normalized evidence | 投影命中的证据 | 无投影则无记录 | geo fusion/source_trace | 是 | 支撑证据 ID |
| `source_type_norm` | 同上 | 同上 | normalized evidence | 直接带入 | 可 unknown | sigma、fusion | 是 | 来源类型 |
| `evidence_role` | 当前投影表未必直接导出 | merge 后来自 normalized evidence | normalized evidence | 当前 `cell_evidence_df` 主输出未必包含，fusion merge 后可用 | 可空 | Trace 支撑类型 | 是 | prediction/observed 等角色 |
| `spatial_type` | `cell_evidence_df` | `project_evidence_to_cells` | normalized evidence | 直接带入 | unknown 兜底 | sigma、distance | 是 | 空间形态 |
| `distance_m` | `cell_evidence_df` | `project_evidence_to_cells` | cell center 与 evidence 里程 | 点证据取中心距离；区间证据取到区间距离 | 里程缺失时无投影 | spatial_weight | debug/间接 | 空间距离 |
| `sigma_m` | 当前主输出未保留该字段 | `get_spatial_sigma` 内部计算 | config | 用于 spatial_weight，当前导出未包含独立列 | 当前 export 未包含 | 权重计算内部 | 否 | 建议后续 export 可补充 |
| `spatial_weight` | `cell_evidence_df` | `project_evidence_to_cells` | `distance_m`, `sigma_m` | `exp(-0.5*(distance_m/sigma_m)^2)` | 无投影则无记录 | effective_weight | 间接 | 空间衰减权重 |
| `source_reliability` | `cell_evidence_df` | 同上 | normalized evidence | `clip01(source_reliability)` | unknown 兜底 | effective_weight | 间接 | 来源权重 |
| `evidence_strength` | `cell_evidence_df` | 同上 | normalized evidence | `clip01(evidence_strength)` | unknown 兜底 | effective_weight | 间接 | 证据强度 |
| `effective_weight` | `cell_evidence_df` | 同上 | 三个分量 | `spatial_weight*clip01(source_reliability)*clip01(evidence_strength)` | 无投影则无记录 | geo fusion | 间接 | 原始 evidence-cell 有效权重 |
| `effective_weight_capped` | fusion 内部字段 | `fusion_engine::_cap_duplicate_effective_weights` | `effective_weight` | 重复组截断后权重 | 当前原始投影输出不包含；fusion 内部存在 | geo fusion | 间接 | 不是原始投影字段，当前 export 未直接落盘 |

### A.4 geo_states_df 字段

产生函数：

```text
geology_v2/fusion_engine.py::fuse_geo_states
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `cell_id` | `geo_states_df` | `fuse_geo_states` | cells_df | 直接带入 | cells 缺失时为空表 | ConstructionStateCell | 是 | 地质 cell 主键 |
| `cell_start` | 同上 | 同上 | cells_df | 直接带入 | 同上 | 空间判断 | 是 | cell 起点 |
| `cell_end` | 同上 | 同上 | cells_df | 直接带入 | 同上 | 空间判断 | 是 | cell 终点 |
| `cell_center` | 同上 | 同上 | cells_df | 直接带入 | 同上 | forward_profile | 是 | cell 中心 |
| `has_geology_evidence` | 同上 | 同上 | cell_evidence_df | 有有效投影证据为 true | 无投影为 false | GRCI 可用性 | 是 | 是否有地质证据 |
| `fused_grade` | 同上 | 同上 | evidence grade | 支持度最高且保守取较差等级 | 无证据时空 | Evidence Pack | 是 | 融合围岩等级 |
| `grade_distribution` | 同上 | 同上 | evidence grade + weight | 按等级汇总支持度/share | 无证据时空 dict | debug/GRS | debug 为主 | 等级支持分布 |
| `hazard_scores` | 同上 | 同上 | hazard_tags + flags | hazard weight + Noisy-OR 合并 | 无证据时空 dict | GRS、Evidence Pack | 是 | hazard 关注分，不是灾害概率 |
| `main_hazards` | 同上 | 同上 | `hazard_scores` | 分数 >0.05 的前 5 个 | 无证据时空 | 报告/Trace | 是 | 关注标签，不等于已发生灾害 |
| `water_score` | 同上 | 同上 | hazard_scores | max(water, water_inrush) | 无证据为 0 | debug | 间接 | 水相关关注 |
| `collapse_score` | 同上 | 同上 | hazard_scores | max(collapse, block_fall) | 无证据为 0 | debug | 间接 | 掉块/坍塌相关关注 |
| `deformation_score` | 同上 | 同上 | hazard_scores | deformation 分数 | 无证据为 0 | debug | 间接 | 变形关注 |
| `source_support` | 同上 | 同上 | evidence source + weight | 按来源汇总支持 | 无证据为空 | debug | debug 为主 | 来源支持结构 |
| `source_type_count` | 同上 | 同上 | source_type_norm | 去重来源数量 | 无证据为 0 | confidence | debug | 多源数量 |
| `evidence_count` | 同上 | 同上 | evidence_id | 去重证据数量 | 无证据为 0 | confidence | debug | 支撑证据数 |
| `confidence_score` | 同上 | 同上 | weight/evidence/source/conflict | `weight_factor*evidence_factor*source_factor*conflict_penalty` | 无证据为 0 | GRS、Evidence Pack | 是 | 融合置信度，不是准确率 |
| `uncertainty_level` | 同上 | 同上 | confidence/conflict | max(1-confidence, conflict) 分级 | 无证据可 unknown | Evidence Pack | 是 | 不确定性等级 |
| `conflict_level` | 同上 | 同上 | grade/state conflict | conflict_score 分级 | 无冲突为 none | Evidence Pack | 是 | 多源冲突等级 |
| `conflict_reasons` | 同上 | 同上 | conflict 检测 | 文本原因列表 | 可空 | debug | debug 为主 | 冲突原因 |
| `supporting_evidence_ids` | 同上 | 同上 | cell_evidence_df | 去重 evidence_id | 无证据为空 | Evidence Pack/Trace | 是 | 支撑证据 ID |
| `source_trace` | 同上 | 同上 | normalized evidence | evidence_id/source/role/excerpt | 无证据为空 | Trace | 是 | 报告追溯基础 |
| `grade_score_component` | 同上 | `_grs_geo_base_components` | `fused_grade` | grade attention score | 无证据为 0 | GRS 复盘 | 当前 export 未直接保留在 ConstructionStateCell | GRS 组件 |
| `hazard_component` | 同上 | 同上 | hazard_scores | `0.75*max + 0.25*avg` | 无证据为 0 | GRS 复盘 | 当前 export 未直接保留在 ConstructionStateCell | GRS 组件 |
| `confidence_component` | 同上 | 同上 | confidence_score | `clip01(confidence_score)` | 无证据为 0 | GRS 复盘 | 当前 export 未直接保留在 ConstructionStateCell | GRS 组件 |
| `GRS_formula_text` | 同上 | 同上 | 固定公式 | 文本常量 | 无证据为空 | debug | 当前 export 未直接保留 | GRS 公式说明 |
| `GRS_component_method` | 同上 | 同上 | 固定字符串 | `direct_from_fusion_engine` 或 `empty` | 无证据为 empty | debug | 当前 export 未直接保留 | 组件来源 |
| `GRS_geo_base` | 同上 / `ConstructionStateCell` | 同上 | 三个组件 | `0.45*grade+0.45*hazard+0.10*confidence` | 无证据为 0 或空 | GRCI、forward、Evidence Pack | 是 | 地质证据关注度，不是灾害概率 |

### A.5 ConstructionStateCell 字段

定义与构建：

```text
schemas/pipeline.py
coupling/grs_rai_grci.py::build_construction_state_cells
coupling/grs_rai_grci.py::compute_cell_grci
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `cell_id` | `ConstructionStateCell` | `build_construction_state_cells` | cells/response/geo | 合并键 | 不应为空 | 全链路 | 是 | 核心对象 ID |
| `cell_start` | 同上 | 同上 | cells/response/geo | 合并带入 | 不应为空 | 空间状态 | 是 | cell 起点 |
| `cell_end` | 同上 | 同上 | cells/response/geo | 合并带入 | 不应为空 | 空间状态 | 是 | cell 终点 |
| `cell_center` | 同上 | 同上 | cells/response/geo | 合并带入 | 不应为空 | forward/profile | 是 | cell 中心 |
| `has_plc_response` | 同上 | 同上 | cell_response_df | 是否有 response row | false 合法 | GRCI 可用性 | 是 | 控制 GRCI 是否可用 |
| `has_geology_evidence` | 同上 | 同上 | geo_states_df | 是否有地质证据 | false 合法 | GRCI 可用性 | 是 | 控制地质支撑 |
| `is_excavated_today` | 同上 | 同上 | day_start/day_end | cell 与当日推进范围是否重叠 | false 合法 | high_grci 筛选 | 是 | 控制已掘复核 |
| `is_current_face_cell` | 同上 | 同上 | current_chainage | `cell_start <= current < cell_end` | false 合法 | debug/forward 边界 | 是 | 当前掌子面所在 cell |
| `is_forward_cell` | 同上 | 同上 | current/lookahead | `cell_start >= current_chainage` 且在前方窗口 | false 合法 | forward_attention | 是 | 控制前方关注通道 |
| `operation_state` | 同上 | 同上 | cell_response_df | 主导工况 | 无 PLC response 为空 | Evidence Pack | 可进入报告 | PLC cell 工况 |
| `plc_metrics` | 同上 | 同上 | cell_response_df | 聚合指标 dict | 无 PLC response 为空 | debug/RAI 复盘 | debug 为主 | RAI 分量主要在此 |
| `speed_mean` | 同上 | 同上 | cell_response_df | 均值带入 | 缺字段/无 response 为空 | debug | debug 为主 | 速度均值 |
| `thrust_mean` | 同上 | 同上 | cell_response_df | 均值带入 | 缺字段/无 response 为空 | debug | debug 为主 | 推力均值 |
| `torque_mean` | 同上 | 同上 | cell_response_df | 均值带入 | 缺字段/无 response 为空 | debug | debug 为主 | 扭矩均值 |
| `stop_duration_min` | 同上 | 同上 | cell_response_df | 秒转分钟 | 无 response 为空 | Evidence Pack | 可进入报告 | 停机时长 |
| `abnormal_score` | 同上 | 同上 | cell_response_df | response abnormal_score | 无 response 为空 | RAI/GRCI | 是 | 施工响应异常分 |
| `RAI` | 同上 | 同上 | cell_response_df | `RAI=abnormal_score` | 无 response 为空 | GRCI/Evidence Pack | 是 | 施工响应异常度 |
| `fused_grade` | 同上 | 同上 | geo_states_df | 融合等级 | 无地质证据为空 | Evidence Pack | 是 | 地质等级 |
| `main_hazards` | 同上 | 同上 | geo_states_df | hazard_scores 排序 | 无地质证据为空 | Report/Trace | 是 | 关注标签 |
| `hazard_scores` | 同上 | 同上 | geo_states_df | hazard 分数 dict | 无地质证据为空 | GRS 解释 | 是 | 地质关注分量 |
| `confidence_score` | 同上 | 同上 | geo_states_df | 置信分 | 无证据为 0/空 | Evidence Pack | 是 | 融合置信度 |
| `uncertainty_level` | 同上 | 同上 | geo_states_df | 不确定性等级 | 可 unknown | Evidence Pack | 是 | 证据不确定性 |
| `conflict_level` | 同上 | 同上 | geo_states_df | 冲突等级 | 可 none | Evidence Pack | 是 | 多源冲突 |
| `GRS_geo_base` | 同上 | 同上 | geo_states_df | GRS 带入 | 无证据为 0/空 | GRCI/forward | 是 | 地质证据关注度 |
| `supporting_evidence_ids` | 同上 | 同上 | geo_states_df | evidence ids | 无证据为空 | Trace | 是 | 支撑证据 |
| `source_trace` | 同上 | 同上 | normalized evidence | 来源追溯列表 | 无证据为空 | Trace | 是 | 报告可追溯基础 |
| `GRCI` | 同上 | `compute_cell_grci` | GRS + RAI | 公式计算 | 缺 GRS/RAI/PLC 时 None | high_grci/report | 是 | 已掘复核关注度 |
| `GRCI_available` | 同上 | 同上 | GRCI 可用条件 | bool | false 合法 | high_grci 筛选 | 是 | false 通常不是错误 |
| `GRCI_source` | 同上 | 同上 | 计算状态 | `cell_grs_rai_formula_v1` 或 `unavailable` | 不应空 | debug/Trace | 是 | GRCI 来源 |
| `GRCI_unavailable_reason` | 同上 | 同上 | 可用性判断 | `missing_plc_response` / `missing_geology_evidence` | 可为 null | debug | 是 | 解释不可用原因 |
| `coupling_level` | 同上 | `classify_grci` | GRCI | high/medium/low/none/unavailable | 不应空 | 报告复核章节 | 是 | 复核优先级，不是风险等级 |
| `coupling_explanation` | 同上 | `build_construction_state_cells` | GRS/RAI/GRCI/hazards | 文本解释 | 可为空但不建议 | 报告/debug | 是 | 耦合解释或不可用解释 |
| `trace_refs` | 同上 | 同上 | supporting_evidence_ids | 证据 ID 列表 | 无证据为空 | Trace/debug | 是 | 快速追溯引用 |

### A.6 Evidence Pack 字段

产生函数：

```text
llm/evidence_pack.py::build_prompt_evidence_pack
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `report_scope` | Evidence Pack | `build_prompt_evidence_pack` | date/current_chainage | 运行范围摘要 | 不应空 | prompt/report | 是 | 报告范围 |
| `operation_evidence` | Evidence Pack | 同上 | operation_summary | 直接写入 | PLC 空时可空结构 | 报告工况章节 | 是 | 事实统计 |
| `cluster_evidence` | Evidence Pack | 同上 | cluster_summary | 直接写入 | 聚类失败时空结构 | 报告聚类章节 | 是 | 辅助施工状态 |
| `gas_evidence` | Evidence Pack | 同上 | gas_summary | 直接写入 | 无气体字段时空结构 | 报告气体章节 | 是 | 气体监测证据 |
| `geology_evidence` | Evidence Pack | 同上 | selected cells | 聚合 key/selected/background/forward/review | 可空 | grounding checker | 是 | 地质证据聚合 |
| `geology_evidence.key_cells` | Evidence Pack | 同上 | review + forward + background | 正式字段 | 无地质证据时空 | Trace | 是 | Grounding 正式入口 |
| `geology_evidence.selected_cells` | Evidence Pack | 同上 | 同 key_cells | 兼容字段 | 无地质证据时空 | fallback | 是 | 与 key_cells 当前一致 |
| `excavated_review_evidence` | Evidence Pack | 同上 | high_grci_cells | 已掘复核分层 | 无可用 GRCI 时空 | 报告复核章节 | 是 | 正式方法解释应优先看这里 |
| `excavated_review_evidence.review_cells` | Evidence Pack | 同上 | high_grci cells -> full cell | 复核 cell 列表 | 可空 | Trace/report | 是 | 已掘复核对象 |
| `forward_attention_evidence` | Evidence Pack | 同上 | forward_profile + forward cells | 前方关注分层 | 无前方证据时空 | 报告前方章节 | 是 | 不使用 GRCI |
| `forward_attention_evidence.forward_profile` | Evidence Pack | 同上 | build_forward_profile | 直接写入 | 可空结构 | 报告前方章节 | 是 | 前方窗口 |
| `forward_attention_evidence.forward_attention_cells` | Evidence Pack | 同上 | `is_forward_cell` cells | GRS 排序选择 | 可空 | Trace/report | 是 | 前方关注 cell |
| `background_context_evidence` | Evidence Pack | 同上 | 非已掘非前方地质 cells | GRS 排序 top context | 可空 | 背景解释 | 可进入 Trace | 不能写成当日施工异常 |
| `background_context_evidence.background_context_cells` | Evidence Pack | 同上 | background cells | 上下文 cell 列表 | 可空 | Trace/debug | 是 | 背景上下文 |
| `coupling_evidence` | Evidence Pack | 同上 | high_grci_cells | 耦合复核证据 | 可空 | 报告复核章节 | 是 | 已掘区段 GRCI 入口 |
| `coupling_evidence.high_grci_cells` | Evidence Pack | 同上 | high_grci_cells | 筛选后写入 | 可空 | 报告/Trace | 是 | 只含 GRCI_available 且已掘非前方 cell |
| `quality_evidence` | Evidence Pack | 同上 | quality context | 数据质量/警告 | 可空 | 报告边界 | 是 | 质量边界 |
| `source_trace` | Evidence Pack | 同上 | selected cells | 跨 cell 汇总 source trace | 可空 | Trace | 是 | 追溯汇总 |
| `generation_constraints` | Evidence Pack | 同上 | 常量 | 生成约束列表 | 不应空 | prompt/quality | 是 | policy_support 来源 |
| `warnings` | Evidence Pack | 同上 | pipeline warnings | 直接写入 | 可空 | report/API | 是 | 运行警告 |

### A.7 Quality / Trace 字段

产生函数：

```text
llm/report_claim_extractor.py
llm/report_grounding_checker.py
llm/report_quality_checker.py
llm/report_trace_builder.py
```

| 字段名 | 所属对象/文件 | 产生函数 | 输入来源 | 计算/赋值方法 | 可为空情况 | 下游使用位置 | 是否进入报告/Trace | 方法含义与注意事项 |
|---|---|---|---|---|---|---|---|---|
| `raw_claim_count` | quality/trace | claim extractor / trace builder | report_text | 原始抽取 claim 数 | 报告空时 0 | quality/trace summary | 是 | 原始候选主张数 |
| `excluded_non_trace_claim_count` | trace/quality | trace builder | raw claims | 过滤标题、表格等非技术 claim | 可 0 | trace summary | 是 | 非追溯 claim 数 |
| `claim_trace_count` | trace | trace builder | traced claims | trace 中 claim 总数 | 报告空时 0 | trace summary | 是 | trace claim 数 |
| `grounded_claim_count` | quality/trace | grounding checker | claim results | grounded=true 计数 | 可 0 | quality/trace | 是 | Evidence Pack 内部支撑数 |
| `unsupported_claim_count` | quality/trace | grounding checker | claim results | grounded=false 计数 | 可 0 | quality warning | 是 | 不一定代表业务错误，可能是标题/边界句未识别 |
| `grounding_rate` | quality | grounding checker | grounded/claim | `grounded_claim_count/claim_count` | claim_count=0 时兜底 | quality | 是 | Evidence Pack 内部支撑率，不是事实真实率 |
| `trace_coverage` | trace | trace builder | grounded/trace count | `grounded_claim_count/claim_trace_count` | claim_trace_count=0 时兜底 | trace summary | 是 | 追溯覆盖率 |
| `quality_score` | quality | quality checker | violations + grounding | 规则扣分 | 报告空时低分/占位 | API/report debug | 是 | 合规与可追溯评分，不是真实正确率 |
| `violations` | quality | quality checker | report + policy | 禁用表达/缺章节/误用规则 | 可空 | debug/API | 是 | 规则违规列表 |
| `warnings` | quality/trace/pipeline | 多处 | 运行和检查结果 | warning 列表 | 可空 | API/report | 是 | 警告不一定失败 |
| `trace_support_type` | trace claim | grounding checker | support source | statistical/coupling/forward 等 | unsupported 时 none | Trace | 是 | 证据角色 |
| `support_type` | trace claim | grounding checker | support source | operation_context/key_cell 等 | unsupported 时 none | Trace | 是 | 支撑对象类型 |
| `source_refs` | 当前 trace 未以该字段统一导出 | trace/source_trace | source_trace | 当前多使用 `source_trace` 和 `supporting_evidence_ids` | 当前字段名不统一 | 后续可优化 | 否/部分 | 当前 export 未见统一 `source_refs` |
| `matched_evidence_ids` | 当前 trace 未以该字段统一导出 | grounding checker | matched evidence | 当前使用 `supporting_evidence_ids` | 当前字段名不同 | 后续可优化 | 否/部分 | 当前 export 未见统一 `matched_evidence_ids` |
| `matched_cell_ids` | 当前 trace 未以该字段统一导出 | grounding checker | matched cell | 当前多通过 claim/source_trace 间接表达 | 当前字段名不同 | 后续可优化 | 否/部分 | 当前 export 未见统一 `matched_cell_ids` |

## 附录 B：配置常量总表

本附录列出当前方法中主要人为设定的常量、阈值和权重。它们是工程方法参数，不是物理定律；后续论文实验可围绕其中部分参数做敏感性分析，但当前文档只描述真实代码取值。

### B.1 空间与 cell 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `cell_length` | `10.0 m` | `run_daily_report_pipeline`, `build_chainage_cells`, `project_plc_response_to_cells` | 构建 10m cell | PLC response、geo_states、ConstructionStateCell | 改变 cell 数量、GRCI 对齐粒度 | 当前 ConstructionStateCell 空间粒度 |
| `lookahead_m` | `30.0 m` | `run_daily_report_pipeline`, `build_forward_profile` | 前方关注范围 | forward_profile | 改变前方窗口数量和范围 | 当前前方关注窗口 |
| `step_m` | `10.0 m` | `build_forward_profile` | 前方 profile 分段 | forward_profile | 改变 0-10/10-20/20-30 分段 | 与 cell_length 对齐 |
| `advance_direction` | `1` | pipeline/geology filter/forward | 掘进方向 | online filter、forward | 影响未来证据判断和前方窗口方向 | 当前按里程增大方向 |
| `chainage_tolerance_m` | `1.0 m` | `filter_available_evidence` | online 过滤容差 | 地质可用性 | 影响未来证据排除严格程度 | 避免小里程误差被当作泄漏 |
| `projection_radius` | `max(3*sigma_m,1.0)` | `project_evidence_to_cells` | evidence 投影半径 | cell_evidence_df | 改变证据影响范围 | 方法参数，不是物理边界 |

### B.2 PLC / RAI 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| 非零阈值 | `1e-8` | `analysis/dataprocess.py::_judge_condition` | 判断推力/速度/扭矩是否非零 | 工况识别 | 影响 stop/work/transition/abnormal | 工程数值容差 |
| 时间差有效范围 | `0 < diff_seconds < 3600` | `infer_sample_interval_sec`, `_infer_row_duration_seconds` | 排除异常时间差 | 工况分段、cell duration | 影响持续时间和 ratio | 采样间隔清洗 |
| KMeans `n_clusters` | `3` | `detect_excavation_state` | 施工状态聚类数 | cluster_summary | 改变聚类标签数量 | 辅助描述，不参与 GRCI |
| KMeans `random_state` | `0` | `detect_excavation_state` | 聚类可复现 | cluster_summary | 改变可复现性 | 固定随机种子 |
| KMeans `n_init` | `"auto"` | `detect_excavation_state` | KMeans 初始化 | cluster_summary | 可能影响聚类稳定性 | sklearn 参数 |
| cluster valid sample threshold | `30` | `build_cluster_context` | 聚类质量判断 | cluster_summary | 改变 `is_stable_enough` | 工程阈值 |
| cluster min ratio threshold | `0.03` | `build_cluster_context` | 最小簇占比 | cluster_summary | 改变聚类质量 warning | 工程阈值 |
| RAI stop weight | `0.40` | `project_plc_response_to_cells` | RAI 分量 | RAI/GRCI | 停机占比影响变大/小 | 启发式权重 |
| RAI abnormal weight | `0.25` | 同上 | RAI 分量 | RAI/GRCI | 异常段影响变大/小 | 启发式权重 |
| RAI speed drop weight | `0.20` | 同上 | RAI 分量 | RAI/GRCI | 速度下降影响变大/小 | 启发式权重 |
| RAI torque volatility weight | `0.10` | 同上 | RAI 分量 | RAI/GRCI | 扭矩波动影响变大/小 | 启发式权重 |
| RAI speed volatility weight | `0.05` | 同上 | RAI 分量 | RAI/GRCI | 速度波动影响变大/小 | 启发式权重 |
| `global_speed_q75` | 当日速度 75% 分位数 | `project_plc_response_to_cells` | `speed_drop_score` 参照 | RAI | 改变速度下降分 | 当日内部参照 |
| `clip01` | `[0,1]` 裁剪 | 多处 | 分数边界 | RAI/GRS/GRCI | 防止异常值越界 | 数值稳定 |

RAI 当前完整公式：

```text
RAI =
  0.40 * stop_ratio
+ 0.25 * abnormal_ratio
+ 0.20 * speed_drop_score
+ 0.10 * torque_volatility_score
+ 0.05 * speed_volatility_score
```

这些是工程启发式权重，不是标定后的物理模型。

### B.3 气体阈值配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `CO2检测` | `0.5 %` | `analysis/gas_analysis.py::THRESHOLDS` | CO2 超阈统计 | gas_summary | 改变 CO2 exceed | 仅对浓度字段解释 |
| `H2S检测` | `10 ppm` | 同上 | H2S 超阈统计 | gas_summary | 改变 H2S exceed | 同上 |
| `SO2检测` | `2 ppm` | 同上 | SO2 超阈统计 | gas_summary | 改变 SO2 exceed | 同上 |
| `NO2检测` | `5 ppm` | 同上 | NO2 超阈统计 | gas_summary | 改变 NO2 exceed | 同上 |
| `NO检测` | `20 ppm` | 同上 | NO 超阈统计 | gas_summary | 改变 NO exceed | 同上 |
| `CH4检测` | `0.5 %` | 同上 | CH4 超阈统计 | gas_summary | 改变 CH4 exceed | 同上 |

如果字段被质量诊断判定为 `alarm_flag`，则不应直接套浓度阈值解释。

### B.4 地质 source reliability 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `face_sketch` | `1.20` | `geology_v2/config.py::SOURCE_RELIABILITY` | 来源权重 | effective_weight | 提高/降低素描影响 | 配置可超过 1，但投影时 clip |
| `borehole` | `1.15` | 同上 | 来源权重 | effective_weight | 改变钻孔影响 | 同上 |
| `TSP` | `0.95` | 同上 | 来源权重 | effective_weight | 改变 TSP 影响 | 不是真实概率 |
| `HSP` | `0.90` | 同上 | 来源权重 | effective_weight | 改变 HSP 影响 | 不是真实概率 |
| `report_conclusion` | `1.00` | 同上 | 来源权重 | effective_weight | 改变结论段影响 | 不是真实概率 |
| `overview` | `0.35` | 同上 | 背景权重 | background/context | 改变背景证据影响 | 背景低权重 |
| `unknown` | `0.60` | 同上 | 兜底权重 | evidence projection | 改变未知来源影响 | 保守兜底 |

### B.5 evidence_strength 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `point` | `1.10` | `SPATIAL_TYPE_STRENGTH` | 点状证据强度 | effective_weight | 改变点证据影响 | 投影时 clip |
| `anomaly_point` | `1.20` | 同上 | 异常点强度 | effective_weight | 改变异常点影响 | 投影时 clip |
| `segment` | `1.00` | 同上 | 区间证据强度 | effective_weight | 改变区间证据影响 | 标准强度 |
| `overview` | `0.35` | 同上 | 概览证据强度 | context | 改变概览影响 | 背景低权重 |
| `background` | `0.30` | 同上 | 背景证据强度 | context | 改变背景影响 | 背景低权重 |
| `unknown` | `0.70` | 同上 | 兜底空间强度 | effective_weight | 改变未知空间证据影响 | 保守兜底 |
| confidence high | `1.15` | `CONFIDENCE_WEIGHT` | 高置信证据 | evidence_strength | 改变高置信权重 | 投影时 clip |
| confidence medium | `1.00` | 同上 | 中置信证据 | evidence_strength | 标准权重 | 标准 |
| confidence low | `0.80` | 同上 | 低置信证据 | evidence_strength | 降低影响 | 保守 |
| confidence unknown | `0.75` | 同上 | 未知置信 | evidence_strength | 降低影响 | 保守 |

### B.6 spatial sigma 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `face_sketch + point` | `5` | `get_spatial_sigma` | 空间衰减 | evidence projection | 改变素描点影响范围 | sigma 越大影响越宽 |
| `borehole + point` | `4` | 同上 | 空间衰减 | evidence projection | 改变钻孔点影响范围 | 点证据较局部 |
| `HSP + segment` | `12` | 同上 | 空间衰减 | evidence projection | 改变 HSP 区间影响 | 超前预报区间 |
| `HSP + anomaly_point` | `4` | 同上 | 空间衰减 | evidence projection | 改变异常点影响范围 | 异常点局部 |
| `TSP + segment` | `15` | 同上 | 空间衰减 | evidence projection | 改变 TSP 区间影响 | TSP 影响范围较宽 |
| `TSP + report_conclusion` | `12` | 同上 | 空间衰减 | evidence projection | 改变结论段影响 | 结论段 |
| `overview/background` | `30` | 同上 | 背景衰减 | context | 改变背景覆盖 | 当前强投影不保留 overview/background |

### B.7 grade attention score 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `I` / `Ⅰ` / `1` | `0.05` | `GRADE_ATTENTION_SCORE` | GRS grade component | GRS | 改变好围岩关注分 | 不是灾害概率 |
| `II` / `Ⅱ` / `2` | `0.20` | 同上 | 同上 | GRS | 同上 | 同上 |
| `III` / `Ⅲ` / `3` | `0.40` | 同上 | 同上 | GRS | 同上 | 同上 |
| `IV` / `Ⅳ` / `4` | `0.70` | 同上 | 同上 | GRS | 同上 | 关注程度较高 |
| `V` / `Ⅴ` / `5` | `1.00` | 同上 | 同上 | GRS | 同上 | 关注程度最高 |

### B.8 hazard weight 配置

| hazard | weight | 语义 |
|---|---:|---|
| `water` | 0.35 | 出水关注 |
| `water_inrush` | 0.45 | 出水增强/突水相关关注 |
| `collapse` | 0.40 | 坍塌相关关注 |
| `block_fall` | 0.35 | 掉块相关关注 |
| `deformation` | 0.30 | 变形关注 |
| `fractured_rock` | 0.30 | 围岩破碎关注 |
| `extremely_fractured_rock` | 0.40 | 围岩极破碎关注 |
| `joint_development` | 0.25 | 裂隙发育关注 |
| `dense_joints` | 0.35 | 裂隙密集关注 |
| `weak_interlayer` | 0.30 | 软弱夹层关注 |
| `mud_filling` | 0.30 | 泥质填充关注 |
| `soft_hard_uneven` | 0.25 | 软硬不均关注 |
| `reflection_anomaly` | 0.25 | 反射异常关注 |
| `strong_reflection_anomaly` | 0.35 | 明显反射异常关注 |
| `poor_stability` | 0.35 | 稳定性较差关注 |

hazard weight 用于 `hazard_scores`。如果 hazard 来自 prediction evidence，它表示预报提示，不等于已发生灾害。

### B.9 GRS 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| grade weight | `0.45` | `_grs_geo_base_components` | GRS | GRS/GRCI/forward | 改变围岩等级影响 | 地质关注度权重 |
| hazard weight | `0.45` | 同上 | GRS | GRS/GRCI/forward | 改变 hazard 影响 | 地质关注度权重 |
| confidence weight | `0.10` | 同上 | GRS | GRS/GRCI/forward | 改变置信度影响 | 地质关注度权重 |
| hazard max weight | `0.75` | 同上 | hazard_component | GRS | 改变主控 hazard 影响 | 主控关注 |
| hazard average weight | `0.25` | 同上 | hazard_component | GRS | 改变多 hazard 叠加影响 | 多灾种叠加 |

公式：

```text
hazard_component = 0.75 * max(hazard_scores) + 0.25 * average(hazard_scores)
GRS_geo_base = 0.45 * grade_score_component + 0.45 * hazard_component + 0.10 * confidence_component
```

`GRS_geo_base` 是地质证据关注度，不是地质风险概率。

### B.10 GRCI 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| GRS weight | `0.55` | `compute_cell_grci` | GRCI | high_grci | 改变地质关注影响 | 复核关注权重 |
| RAI weight | `0.35` | 同上 | GRCI | high_grci | 改变施工响应影响 | 复核关注权重 |
| interaction weight | `0.10` | 同上 | GRCI | high_grci | 改变共现增强 | GRS 与 RAI 交互 |
| high threshold | `>=0.75` | `classify_grci` | coupling_level | report | 改变 high 数量 | 复核优先级 |
| medium threshold | `>=0.50` | 同上 | coupling_level | report | 改变 medium 数量 | 复核优先级 |
| low threshold | `>=0.25` | 同上 | coupling_level | report | 改变 low 数量 | 复核优先级 |
| none threshold | `<0.25` | 同上 | coupling_level | report | 改变 none 数量 | 复核优先级 |

公式：

```text
GRCI = 0.55 * GRS + 0.35 * RAI + 0.10 * GRS * RAI
```

`coupling_level` 在文档和报告中应解释为复核优先级，不是风险等级。

### B.11 forward attention 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| forward score | `max(GRS_geo_base in window)` | `build_forward_profile` | 前方关注分数 | forward_profile | 改变窗口代表值 | 只看地质证据 |
| high threshold | `>=0.75` | `_attention_level` | attention_level | report | 改变 high 数量 | 前方关注等级 |
| medium threshold | `>=0.50` | 同上 | attention_level | report | 改变 medium 数量 | 前方关注等级 |
| low threshold | `>=0.25` | 同上 | attention_level | report | 改变 low 数量 | 前方关注等级 |
| none threshold | `<0.25` | 同上 | attention_level | report | 改变 none 数量 | 前方关注等级 |

forward attention 只使用 `GRS_geo_base` 和 `source_trace`，不使用 `RAI` / `GRCI`。

### B.12 Quality / Trace 配置

| 配置项 | 当前值 | 所在文件/函数 | 用途 | 影响模块 | 改动后可能影响 | 方法解释 |
|---|---|---|---|---|---|---|
| `forbidden_error` | `15` | `report_policy.py`, `report_quality_checker.py` | 禁用表达扣分 | quality_score | 改变违规扣分 | 规则评分 |
| `warning` | `5` | 同上 | warning 扣分 | quality_score | 改变 warning 扣分 | 规则评分 |
| `missing_section` | `3` | 同上 | 缺章节扣分 | quality_score | 改变章节完整性扣分 | 规则评分 |
| `unsupported_claim` | `8` | policy 配置 | unsupported 权重 | quality/grounding | 当前代码不一定逐条按 8 扣分，应以 checker 实际逻辑为准 | 配置项，不等同实际逐条扣分 |
| `low_grounding_rate` | `10` | quality checker | 低 grounding 扣分 | quality_score | 改变低支撑率惩罚 | 规则评分 |
| required sections | policy 中定义 | `report_policy.py` | 章节完整性检查 | quality | 改变缺章节判断 | 报告结构约束 |
| forbidden expressions | policy 中定义 | `report_policy.py` | 禁用表达检查 | quality | 改变误用检测 | 禁止概率化/事实化误写 |
| GRCI probability misuse | regex/rules | quality + grounding | 防止 GRCI 写成概率 | quality/trace | 改变误用敏感度 | 方法边界 |
| forward-as-fact rules | regex/rules | quality + grounding | 防止前方提示写成已发生 | quality/trace | 改变误用敏感度 | 方法边界 |
| gas misuse rules | regex/rules | quality + grounding | 防止报警量/浓度误写 | quality/trace | 改变气体误用检测 | 数据语义边界 |

`quality_score` 是规则评分，不是事实真实性评分。

## 附录 C：导出字段完整性检查

本附录基于当前导出目录检查：

```text
backend/outputs/pipeline_exports/2023-12-30/
backend/outputs/pipeline_exports/2023-12-28/
```

检查结论只描述当前导出，不等同于代码内部是否存在该字段。部分字段在中间 DataFrame 中存在，但当前 export 未单独落盘。

### C.1 文件存在性检查表

| 文件名 | 2023-12-30 是否存在 | 2023-12-28 是否存在 | 内容用途 | 是否足够复盘 |
|---|---|---|---|---|
| `report.txt` | 是 | 是 | 模板日报正文 | 足够复盘报告文本 |
| `prompt.txt` | 是 | 是 | LLM prompt / no-LLM prompt | 足够复盘输入提示 |
| `evidence_pack.json` | 是 | 是 | 报告证据包 | 足够复盘报告证据分层 |
| `quality.json` | 是 | 是 | 报告质量检查 | 足够复盘 quality |
| `trace.json` | 是 | 是 | claim trace | 足够复盘主要 trace |
| `construction_state_cells.json` | 是 | 是 | 核心 cell 对象 | 足够复盘 GRCI，部分 RAI/GRS 组件需看嵌套或缺失 |
| `construction_state_cells.csv` | 是 | 是 | 核心 cell 表格 | 足够浏览核心字段，不足以完全展开嵌套 dict |
| `forward_profile.json` | 是 | 是 | 前方关注 profile | 足够复盘前方关注 |
| `high_grci_cells.json` | 是 | 是 | high GRCI cell | 足够复盘已掘复核 cell |
| `warnings.json` | 是 | 是 | pipeline warnings | 足够复盘警告 |
| `summary.json` | 是 | 是 | 核心摘要指标 | 足够快速概览，不足以论文级完整指标 |
| `method_metrics.json` | 否 | 否 | 统一方法指标 | 当前未导出 |
| `cell_response_df.csv` | 否 | 否 | PLC response 原始 cell 表 | 当前未导出 |
| `geo_states_df.csv` | 否 | 否 | 地质融合 cell 表 | 当前未导出 |
| `cell_evidence_df.csv` | 否 | 否 | evidence-cell 投影关系 | 当前未导出 |

### C.2 RAI 组件导出检查

| 字段 | construction_state_cells.csv | construction_state_cells.json | evidence_pack.json | 其他文件 | 是否可用于公式复盘 | 结论 |
|---|---|---|---|---|---|---|
| `stop_ratio` | 间接在 `plc_metrics` JSON 字符串中 | 是，`plc_metrics.stop_ratio` | 部分 cell 可能保留在 cell payload | 无 `cell_response_df.csv` | 是，但需解析嵌套 | 可复盘 |
| `abnormal_ratio` | 间接在 `plc_metrics` | 是 | 部分 | 无 | 是，但需解析嵌套 | 可复盘 |
| `speed_drop_score` | 间接在 `plc_metrics` | 是 | 部分 | 无 | 是，但需解析嵌套 | 可复盘 |
| `torque_volatility_score` | 间接在 `plc_metrics` | 是 | 部分 | 无 | 是，但需解析嵌套 | 可复盘 |
| `speed_volatility_score` | 间接在 `plc_metrics` | 是 | 部分 | 无 | 是，但需解析嵌套 | 可复盘 |
| `abnormal_score` | 是 | 是 | 是 | high_grci_cells 间接 | 是 | 可复盘 |
| `RAI` | 是 | 是 | 是 | high_grci_cells.json | 是 | 可复盘 |

判断：

```text
当前 export 足以复盘 RAI，但不够舒服。
RAI 分量在 construction_state_cells.json 的 plc_metrics 中可查；
CSV 中是嵌套 JSON 字符串，不如单独 cell_response_df.csv 清晰。
建议后续小改 export：增加 cell_response_df.csv，或把 RAI components 平铺到 construction_state_cells.csv。
```

### C.3 GRS 组件导出检查

| 字段 | construction_state_cells.csv | construction_state_cells.json | evidence_pack.json | 其他文件 | 是否可用于公式复盘 | 结论 |
|---|---|---|---|---|---|---|
| `grade_score_component` | 否 | 否 | 否 | 当前未导出 `geo_states_df.csv` | 否 | 中间 geo_states_df 内部存在，但当前 export 不足以直接复盘 |
| `hazard_component` | 否 | 否 | 否 | 当前未导出 `geo_states_df.csv` | 否 | 同上 |
| `confidence_component` | 否 | 否 | 否 | 当前未导出 `geo_states_df.csv` | 否 | 同上 |
| `GRS_formula_text` | 否 | 否 | 否 | 当前未导出 `geo_states_df.csv` | 公式可由文档复盘，字段不可查 | 建议导出 |
| `GRS_component_method` | 否 | 否 | 否 | 当前未导出 `geo_states_df.csv` | 否 | 建议导出 |
| `GRS_geo_base` | 是 | 是 | 是 | forward/high_grci | 是，结果可查 | 可复盘结果，不能复盘完整组件 |
| `hazard_scores` | 是 | 是 | 是 | forward_profile 部分 | 部分可复盘 | 可复盘 hazard 结构 |
| `main_hazards` | 是 | 是 | 是 | forward/high_grci | 是 | 可复盘主要标签 |
| `confidence_score` | 是 | 是 | 是 | forward_profile | 部分可复盘 | 可查置信分，但缺 GRS 组件字段 |

判断：

```text
当前 export 可以复盘 GRS_geo_base 的结果和 hazard_scores/main_hazards，
但不能完整复盘 GRS 三组件公式，因为 grade_score_component、
hazard_component、confidence_component 没有落到当前导出文件。
建议后续小改 export：导出 geo_states_df.csv，或将 GRS components 加入 construction_state_cells。
```

### C.4 GRCI 组件导出检查

| 字段 | construction_state_cells.csv | construction_state_cells.json | evidence_pack.json | high_grci_cells.json | 是否可用于公式复盘 |
|---|---|---|---|---|---|
| `GRS_geo_base` | 是 | 是 | 是 | 是 | 是 |
| `RAI` | 是 | 是 | 是 | 是 | 是 |
| `GRCI` | 是 | 是 | 是 | 是 | 是 |
| `GRCI_available` | 是 | 是 | 是 | 是 | 是 |
| `GRCI_source` | 是 | 是 | 是 | 是 | 是 |
| `GRCI_unavailable_reason` | 是 | 是 | 是 | 是/可空 | 是 |
| `coupling_level` | 是 | 是 | 是 | 是 | 是 |
| `coupling_explanation` | 是 | 是 | 是 | 是 | 是 |

判断：

```text
当前 export 足以复盘 GRCI。
```

### C.5 forward_profile 导出检查

| 字段 | forward_profile.json | evidence_pack.json | construction_state_cells.json | 结论 |
|---|---|---|---|---|
| `range_label` | 是 | 是 | 不适用 | 可复盘 |
| `window_start` | 当前字段名为 `start_chainage` | 是 | 不适用 | 字段名与文档示例不同 |
| `window_end` | 当前字段名为 `end_chainage` | 是 | 不适用 | 字段名与文档示例不同 |
| `supporting_cell_ids` | 是 | 是 | 可按 cell_id 查 | 可复盘 |
| `attention_level` | 是 | 是 | 不适用 | 可复盘 |
| `fused_grade` | 是 | 是 | 是 | 可复盘 |
| `main_hazards` | 是 | 是 | 是 | 可复盘 |
| `source_trace` | profile item 中不总是完整；forward_attention_cells 中有 | 是 | 是 | 可复盘，但建议统一 |
| `forward_attention_cells` | 是 | 是 | 可按 `is_forward_cell` 查 | 可复盘 |

判断：

```text
当前 export 足以解释前方关注提示。
需要注意字段名是 start_chainage/end_chainage，不是 window_start/window_end。
```

### C.6 Evidence Pack 分层导出检查

| 字段 | 是否存在 | 结论 |
|---|---|---|
| `excavated_review_evidence` | 是 | 可区分已掘复核 |
| `excavated_review_evidence.review_cells` | 是 | 可查看复核 cell |
| `forward_attention_evidence` | 是 | 可区分前方关注 |
| `forward_attention_evidence.forward_profile` | 是 | 可查看前方窗口 |
| `forward_attention_evidence.forward_attention_cells` | 是 | 可查看前方 cell |
| `background_context_evidence` | 是 | 可区分背景上下文 |
| `background_context_evidence.background_context_cells` | 是 | 可查看背景 cell |
| `geology_evidence.key_cells` | 是 | Grounding 正式入口 |
| `geology_evidence.selected_cells` | 是 | 兼容字段 |
| `coupling_evidence.high_grci_cells` | 是 | 已掘复核 GRCI 入口 |

判断：

```text
当前 export 足以区分已掘复核、前方关注、背景上下文。
```

### C.7 Trace support type 导出检查

`trace.json` 当前存在：

```text
trace_support_type
support_type
supporting_evidence_ids
source_trace
```

当前未统一导出字段名：

```text
source_refs
matched_evidence_ids
matched_cell_ids
```

但相同信息可通过 `supporting_evidence_ids`、`source_trace` 和 claim 文本/支撑对象间接获得。

2023-12-30 出现过的 `trace_support_type`：

```text
statistical_support
coupling_review_support
forward_attention_support
observed_support
none
```

2023-12-28 出现过的 `trace_support_type`：

```text
statistical_support
coupling_review_support
forward_attention_support
forecast_support
none
```

未在这两个日期出现，但代码支持或语义保留的类型：

```text
interpreted_support
cell_evidence_support
policy_support
```

判断：

```text
当前 Trace 足以说明 claim 的主要证据角色；
如果后续要做论文实验级批量统计，建议统一增加 matched_evidence_ids、
matched_cell_ids、source_refs。
```

### C.8 method_metrics / summary 完整性检查

当前没有统一导出：

```text
method_metrics.json
```

当前已有：

```text
summary.json
outputs/smoke_summary.json
```

`summary.json` 当前包含：

```text
date
construction_state_cells_row_count
grci_available_count
high_grci_cell_count
forward_cell_count
key_cells_count
quality_score
grounding_rate
unsupported_claim_count
warnings
```

当前 `summary.json` 未统一包含：

```text
plc_row_count
daily_chainage_min
daily_chainage_max
daily_advance_m
cell_response_count
forward_attention_cell_count
grounded_claim_count
trace_coverage
```

其中部分指标在 `smoke_summary.json` 中可见，部分需从导出文件计算。

### C.9 导出改进建议

| 缺失字段/文件 | 影响 | 是否影响当前方法理解 | 是否建议后续小改 export | 优先级 |
|---|---|---|---|---|
| `cell_response_df.csv` | RAI 复盘需要解析 `plc_metrics` 嵌套 | 不影响主方法，但影响人工复盘便利性 | 建议 | P1 |
| `geo_states_df.csv` | GRS 三组件无法直接复盘 | 不影响 GRS 结果理解，但影响公式复盘完整性 | 强烈建议 | P1 |
| `cell_evidence_df.csv` | 无法完整复盘 evidence-cell 投影权重 | 不影响报告解释，但影响方法审计 | 建议 | P1 |
| `method_metrics.json` | 缺少统一方法指标文件 | 不影响单次运行，但影响批量实验统计 | 建议 | P1 |
| RAI components 平铺到 CSV | 当前嵌套在 `plc_metrics` | 不影响 JSON 复盘，影响 Excel 查看 | 建议 | P2 |
| GRS components 加入 ConstructionStateCell | 当前只在 geo_states_df 内部，export 未保留 | 影响 GRS 公式完整复盘 | 建议 | P1 |
| `matched_evidence_ids` / `matched_cell_ids` | Trace 批量统计不够直观 | 不影响当前 trace 阅读 | 建议 | P2 |

当前结论：

```text
RAI：当前 export 可复盘，但建议增加 cell_response_df.csv 或平铺分量。
GRS：当前 export 可复盘结果，不能完整复盘三组件，建议导出 geo_states_df.csv 或补充 GRS components。
GRCI：当前 export 足以复盘。
Forward：当前 export 足以解释前方关注提示。
Evidence Pack 分层：当前 export 足以区分已掘复核、前方关注、背景上下文。
Trace：当前 export 足以说明主要支撑类型，但可增加 matched_* 字段提升批量统计能力。
```
