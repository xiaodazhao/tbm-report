# TBM 施工日报后端方法与计算逻辑白皮书

本文是 `backend/docs/current_backend_system_manual.md` 的方法与计算逻辑补充。系统总览文档回答“当前后端怎么跑”，本文回答“每一步到底怎么算、哪些字段参与、哪些结论允许写、哪些结论不能写”。

本文只描述当前代码真实执行逻辑，不描述理想设计，不补写论文实验，不把尚未实现的算法写成已经实现的能力。

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
construction_state_cells_row_count = 157
geo_states_df cell 数 = 157
```

说明地质链路形成了 157 个 10m cell，而当日 PLC 施工响应只覆盖其中 2 个。

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
