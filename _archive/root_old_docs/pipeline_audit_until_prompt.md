# TBM 数据处理到 Prompt 构建全链路审查

## 1. 审查目标

本文档审查当前项目从原始输入到 LLM prompt 构建之前的完整链路，覆盖：

1. PLC CSV 的读取、字段要求、工况处理、状态识别、气体分析和输出结构。
2. PDF 的解析方式、各 parser 的提取规则、结构化结果和证据输出格式。
3. 地质证据库的构建、存储、清洗、增量导入和读取方式。
4. PLC 与地质库的融合、区段分析、前方风险、耦合分析和 `CST` 更新。
5. 最后进入 `llm_summary` 和 `prompt_builder` 的数据契约。

本文档既说明“当前代码真实做了什么”，也标出“当前最容易出问题的薄弱层”。

---

## 2. 结论先行：当前链路最主要的问题

先给结论，便于后面读细节时有主线。

### 2.1 主要薄弱点

1. **不同层对同一概念的统计口径并不统一。**
   - `active_source_count` 有时表示当前里程命中的独立报告数。
   - `evidence_count` 有时表示当前里程证据条数。
   - `multi_source_count` 在前方风险里又是前方窗口内去重后的 `(source_type, report_id)` 数。
   - `multi_source_segment_count` 在区段摘要里是 `active_source_count_max >= 3` 的区段数。
   - 这些值在不同层都叫“多源”“证据数”“高风险段”，但语义不同。

2. **PLC 主链内部就存在多套状态判定口径。**
   - `dataprocess.py` 用 `掘进状态 + 推力 + 推进速度 + 刀盘扭矩` 划分 `stop/transition/work/abnormal`。
   - `excavation_state.py` 聚类时只把 `掘进状态 != 0` 当工作样本。
   - `gas_analysis.py` 又用 `掘进状态 != 0` 或 `贯入度 > 0` 划分掘进/停机。
   - `geology_response_coupling.py` 的 `RAI` 还会使用 `speed_zero_ratio`、`stop_state_ratio` 和 `routine_ring_building_score`。
   - 这些状态口径没有收敛成一个统一的“主状态定义”。

3. **三类 PDF parser 输出字段名一致，但字段语义并不等价。**
   - `support_grade`、`risk_level`、`risk_tags` 在 `TSP/HSP/sketch` 中都存在。
   - 但它们分别来自结论段、表格、反射异常解释、掌子面素描观察，证据等级不同。
   - 下游融合和前方风险会把这些字段混在一个统一空间中使用。

4. **前方风险、区段耦合、CST、prompt 之间存在信息重组和重命名，但没有强校验。**
   - `digital_twin_state`、`cst_state`、`llm_summary` 都是重包装层。
   - 包装时有字段丢失、口径变化和命名不一致的问题。

5. **prompt 构建层存在明确契约错误。**
   - `llm_summary` 里写入的 `"区段风险-施工响应耦合分析"`，`prompt_builder` 读取的是 `"区段地质-施工耦合分析"`。
   - 时窗 prompt 要求区分当前掌子面与前方提示，但并未接收 `face_geo_text`。
   - prompt 某些段落直接把 Python `dict` 串给模型，而不是文本摘要。

---

## 3. 总体流程图

当前主链可以拆成下面这条路径：

```text
PLC CSV
  -> load_csv / load_df_by_time
  -> attach_geology_labels（把地质证据挂回 PLC）
  -> dataprocess（基础工况分段）
  -> excavation_state（无监督施工状态聚类）
  -> gas_analysis（全天 / 掘进 / 停机 / 状态级气体统计）
  -> segment_analysis（固定里程区段统计）
  -> geology_response_coupling（GRS / RAI / GRCI）
  -> geology_summary / forward_risk_advisor
  -> digital_twin_state
  -> cst_update_service
  -> llm_summary
  -> prompt_builder / prompt_builder_timewindow
  -> call_llm
```

地质侧独立主线为：

```text
TSP / HSP / sketch PDF
  -> parser
  -> EvidenceRecord
  -> DataFrame
  -> clean_evidence_dataframe
  -> evidence_db.csv
  -> SQLite evidence_records
  -> load_evidence_db
  -> fusion
```

---

## 4. PLC 输入层

### 4.1 入口文件

- `backend/utils/io_utils.py`
- `backend/utils/time_window_utils.py`

### 4.2 文件定位规则

PLC 数据默认来自 `config.py` 中的 `DATA_DIR`。

命名约定：

```text
tbm_data_YYYYMMDD.csv
```

按日期读取通过：

- `get_csv_path_by_date(date_str)`
- `load_csv_by_date(date_str)`

最新文件读取通过：

- `get_latest_csv_path()`
- `load_latest_csv()`

### 4.3 PLC 最低要求字段

`load_csv()` 至少要求存在时间列：

- `运行时间-time`

如果没有这个列，但有 `time`，会自动重命名。

若时间列不存在，直接报错，不进入后续流程。

### 4.4 PLC 基础标准化

`load_csv()` 做了 3 件事：

1. 读 CSV。
2. 时间列转 `datetime`。
3. 删除无效时间行并按时间排序。

### 4.5 时窗分析入口

`load_df_by_time()` 支持：

- 直接传 DataFrame
- 传 CSV 路径

它会：

1. 兼容 `time -> 运行时间-time`
2. 解析开始结束时间
3. 过滤时间窗内样本

这里的行为和 `load_csv()` 大体一致，但它是另一套实现，不是同一个底层函数。

### 4.6 这一层的输出

输出是一个按时间排序的 DataFrame，仍保留原始 PLC 列，不做业务字段派生。

---

## 5. PLC 基础工况分段层

### 5.1 入口文件

- `backend/analysis/dataprocess.py`

### 5.2 这一层关注的字段

工况判定主要看：

- `掘进状态`
- `推力`
- `推进速度`
- `刀盘扭矩`

### 5.3 工况分类逻辑

`_judge_condition(row)` 输出四类工况编码：

1. `0 -> stop`
2. `1 -> transition`
3. `2 -> work`
4. `3 -> abnormal`

判定规则大致是：

1. 如果有 `掘进状态` 且其值为 `0`，直接判停机。
2. 否则根据 `推力/推进速度/刀盘扭矩` 是否非零组合判别。

当前逻辑的工程含义是：

- `推力 + 推进速度` 同时明显非零，视为稳定掘进。
- 有推力但没有推进速度，视为启动/过渡或受阻阶段。
- 没推力但有明显扭矩，视为异常扭矩段。

### 5.4 基础分段

`load_and_process()` 会：

1. 标准化时间。
2. 逐行生成 `condition_code`。
3. 生成 `condition_name`。
4. 当 `condition_code` 变化时切段。
5. 形成基础工况段列表 `segments`。

每个 segment 结构大致为：

```python
{
  "start": Timestamp,
  "end": Timestamp,
  "state": "stop/transition/work/abnormal",
  "state_code": 0/1/2/3,
  "duration_sec": float
}
```

### 5.5 统计输出

`compute_stats(segments)` 输出：

- 各类工况段数量
- 各类工况总时长
- 最长段
- 短时段列表（小于 60 秒）

输出结构是一个 `stats` 字典。

### 5.6 文本输出

供后续 LLM 使用的文本包括：

- `segments_to_text(segments)`
- `stats_to_text(stats)`

这两段是自然语言文本，而不是结构化表。

### 5.7 这一层的主要问题

1. 这里定义的 `work/stop/transition/abnormal` 是一套明确的业务状态，但后面的聚类状态、气体状态、耦合异常又用别的标准。
2. `abnormal` 只基于“无推力但有扭矩”这类规则，不等于后面 `RAI` 的异常。
3. 这层输出的“主导工况”会进入数字孪生和 `CST`，但它和后面 `state_id` 的语义状态不是同一种东西。

---

## 6. 常规环级停顿识别层

### 6.1 入口函数

- `annotate_routine_ring_building_stops()`

### 6.2 用途

不是为了单独出报告，而是为了给后续 `RAI` 做停顿惩罚折减。

### 6.3 输入字段

通过字段别名自动找：

- 时间列
- 里程列
- 状态列
- 速度列

### 6.4 算法逻辑

先识别“停顿样本”，规则是：

1. `掘进状态 == 0`
2. 或推进速度接近 0

然后按时间连续性切成停顿段。每个停顿段计算：

- 持续时间
- 中心里程
- 停顿期间里程漂移
- 前后是否是工作样本

再根据下列因素算置信度：

1. **环周期性**：相邻停顿中心间距是否接近 `1.5m / 1.8m`
2. **持续时间**：是否位于 `25~90 min`
3. **里程漂移小**
4. **前后邻接工作样本**

如果周期性 > 0 且总置信度 >= 0.70，则打上：

- `routine_ring_building_candidate = 1.0`
- `routine_ring_building_score = confidence`

### 6.5 输出用途

这些字段不会单独进入报告主文本，但会在 `geology_response_coupling.py` 中降低停机异常惩罚。

### 6.6 这一层的主要问题

它是一个很有工程味的启发式模块，但它的输出没有在更高层被明确解释给用户；最终只以 `row_routine_stop_relief` 的形式隐式影响 `RAI`，因此可解释性不足。

---

## 7. 施工状态聚类层

### 7.1 入口文件

- `backend/analysis/excavation_state.py`

### 7.2 用到的字段

默认特征：

- `推力`
- `刀盘扭矩`
- `刀盘实际转速`
- `推进速度`

### 7.3 有效样本判定

在 `tbm_analysis_service.py` 中会先估计有效样本数，再选择状态数：

- 小于 5：不聚类
- 5~9：2 类
- 10~29：3 类
- 30 以上：4 类

### 7.4 聚类算法

`detect_excavation_state()` 的核心算法是：

1. 只选存在的特征列。
2. 只保留“工作中”样本：
   - 优先用 `掘进状态 != 0`
   - 否则用 `推力/推进速度` 是否明显非零
3. 特征标准化：`StandardScaler`
4. 聚类：`KMeans`

输出：

- `df["state_id"]`

### 7.5 状态段输出

`excavation_state_segments()` 会把同一 `state_id` 按时间连续性切段，过滤短于 `min_duration_sec` 的段。

输出结构：

```python
{
  state_id: [(start_time, end_time), ...]
}
```

### 7.6 语义标签生成

`explain_excavation_states()` 根据各聚类中心均值相对中位数的位置，自动给状态命名，例如：

- 高负载稳定推进状态
- 高推力低速受阻状态
- 低负载快速推进状态
- 低负载调整状态

### 7.7 效率统计

`excavation_state_efficiency()` 对每个 `state_id` 聚合：

- 平均推进速度
- 平均推力
- 平均刀盘扭矩
- 平均刀盘实际转速
- 平均推进给定速度

并派生：

- 推力/推进速度
- 扭矩/推进速度
- 速度跟随率

### 7.8 这层输出

返回给主流程的关键字段包括：

- `df_state`
- `state_labels`
- `state_segments`
- `state_text`
- `eff_df`
- `eff_text`
- `state_stats`
- `state_stats_text`

### 7.9 这一层的主要问题

1. 它的“工作样本定义”和 `dataprocess.py` 的状态切分不是同一套标准。
2. `KMeans` 是无监督聚类，标签是相对性的，不保证跨天语义稳定。
3. 这层生成的 `state_id` 与基础工况 `stop/work/...` 是两套状态体系，但后面都被称作“状态”。

---

## 8. 气体分析层

### 8.1 入口文件

- `backend/analysis/gas_analysis.py`

### 8.2 使用的气体字段

默认硬编码：

- `CO2检测`
- `H2S检测`
- `SO2检测`
- `NO2检测`
- `NO检测`
- `CH4检测`

### 8.3 算法逻辑

对每个气体字段做：

1. 数值化。
2. 计算均值、最大、最小。
3. 如果设置阈值，则判断超阈值事件。
4. 超阈值事件按连续区间切段。

### 8.4 掘进 / 停机切分

`_split_work_stop()` 的优先级是：

1. `掘进状态 != 0` 视为掘进
2. 否则 `贯入度 > 0` 视为掘进

这和 `dataprocess.py` 的工况划分标准不是同一个定义。

### 8.5 输出结构

`compute_gas_stats()` 返回：

- `all`
- `work`
- `stop`
- `by_state`（可选）

其中每个气体项结构大致为：

```python
{
  "mean": float,
  "max": float,
  "min": float,
  "threshold": float,
  "exceed_event_count": int,
  "exceed_segments": [
    {"start": ts, "end": ts, "duration_sec": float}
  ]
}
```

### 8.6 这一层的主要问题

1. 阈值是硬编码的，注释里自己也承认单位未必确认。
2. 掘进/停机划分和其他模块不统一。
3. `by_state` 使用的是聚类状态，不是基础工况状态，容易和上层混淆。

---

## 9. PDF 解析层

### 9.1 统一结构

三类 parser 都输出 `EvidenceRecord`：

```python
EvidenceRecord(
  evidence_id,
  source_type,
  source_level,
  report_id,
  report_date,
  issue_date,
  tunnel_name,
  start_num,
  end_num,
  face_num,
  next_forecast_num,
  confidence,
  attrs_json,
  raw_text,
)
```

这是整个地质证据链最重要的统一结构。

### 9.2 TSP parser

入口：

- `backend/parsers/tsp_parser.py`

#### 9.2.1 PDF 文本提取

使用 `PyMuPDF(fitz)` 直接提整页文本。

#### 9.2.2 TSP 会输出多种层级记录

1. `overview`
2. `report_conclusion`
3. `segment`

#### 9.2.3 TSP 结构化逻辑

它会从报告中提取：

- 报告元信息
- 预报范围
- 掌子面里程
- 下次预报里程
- 7 结论中的围岩等级结论
- 7 结论中的掉块风险结论
- 7 结论中的出水结论
- 表 2 区段物性参数和结论

#### 9.2.4 TSP 的记录类型

1. `overview`
   - 一份报告一个
   - `source_level="overview"`
   - 更像报告级概览

2. `support_grade_conclusion`
   - `source_level="report_conclusion"`
   - 从“建议按X级围岩施工”提取

3. `collapse_risk_conclusion`
   - `source_level="report_conclusion"`
   - 从结论段提掉块、裂隙、泥质填充等

4. `water_risk_conclusion`
   - `source_level="report_conclusion"`
   - 从结论段提线状/股状出水等

5. `table2_segment`
   - `source_level="segment"`
   - 从表 2 逐段结构化抽取

#### 9.2.5 TSP 的额外处理

`attach_grade_conflicts()` 会把结论段与表 2 的围岩等级冲突标记出来：

- `grade_conflict = 1`
- 同时写入 `support_grade_conclusion / support_grade_table2 / support_grade_final`

### 9.3 HSP parser

入口：

- `backend/parsers/hsp_parser.py`

#### 9.3.1 文本与表格提取

同时使用：

- `fitz` 提全文
- `pdfplumber` 提表格

#### 9.3.2 粒度

HSP 只输出 `segment` 级记录：

- `source_level="segment"`

#### 9.3.3 提取逻辑

HSP 重点从表 1 行级提取：

- 里程范围
- 反射异常等级
- 建议围岩等级
- 节理裂隙
- 岩体破碎程度
- 风化
- 稳定性
- 岩性
- 掉块提示

#### 9.3.4 风险字段构造

HSP 会显式构造：

- `risk_level`
- `risk_tags`

而且风险推断 heavily 依赖“反射异常 + 掉块 + 围岩等级 + 岩体破碎”等启发式规则。

### 9.4 sketch parser

入口：

- `backend/parsers/sketch_parser.py`

#### 9.4.1 粒度

sketch 只输出一个 `point` 级记录：

- `source_level="point"`

每份素描文件通常只对应掌子面附近一个点位。

#### 9.4.2 提取逻辑

它直接从全文提取：

- 里程点
- 围岩级别
- 风化
- 节理裂隙
- 岩体状态
- 岩质均匀性
- 稳定性
- 出水类型
- 掉块现象
- 岩性

#### 9.4.3 风险字段构造

也会构造：

- `risk_level`
- `risk_tags`

但这里的语义更接近“现场观察结果”，与 TSP/HSP 的“预测或解释结果”不同。

### 9.5 PDF 层的主要问题

1. 三个 parser 都输出了 `risk_level/risk_tags/support_grade`，但来源语义不同。
2. TSP 同时输出 `overview/report_conclusion/segment` 三个层级，而 HSP 只有 `segment`，sketch 只有 `point`，下游虽然能过滤层级，但对证据强度只做了轻量权重调整。
3. parser 的很多抽取规则是正则和关键词启发式，模板变动时很脆弱。

---

## 10. 地质证据库构建层

### 10.1 入口文件

- `backend/scripts/build_evidence_db.py`
- `backend/services/evidence_import_service.py`

### 10.2 全量建库

`build_evidence_db.py` 会：

1. 扫描 `TSP_DIR/HSP_DIR/SKETCH_DIR`
2. 做文件名去重
3. 排除左线 PDF
4. 调各 parser
5. 合并为 `DataFrame`
6. 调 `clean_evidence_dataframe()`
7. 写入 CSV
8. 同步 SQLite

### 10.3 增量导入

`import_evidence_files()` 支持：

- 文件或目录
- 显式 `source_type`
- 自动推断 parser
- `dry_run`
- `replace_existing`
- 写入前备份

### 10.4 证据库格式

CSV 主体就是 `EvidenceRecord` 展平后的字段：

- `evidence_id`
- `source_type`
- `source_level`
- `report_id`
- `report_date`
- `issue_date`
- `tunnel_name`
- `start_num`
- `end_num`
- `face_num`
- `next_forecast_num`
- `confidence`
- `attrs_json`
- `raw_text`

### 10.5 清洗规则

统一清洗规则：

1. 必须有 `evidence_id/start_num/end_num`
2. 转数值失败则删除
3. `start_num > end_num` 删除
4. `evidence_id` 去重保留最后一条
5. `segment` 长度必须在 `0~300m`
6. 最终排序

### 10.6 SQLite 存储方式

SQLite 表 `evidence_records` 只显式存：

- `evidence_id`
- `source_type`
- `report_id`
- `start_num`
- `end_num`
- `payload_json`

也就是说，真正完整记录是塞在 `payload_json` 里的。

### 10.7 这一层的主要问题

1. SQLite 里是“删全表再重写”，不是增量更新语义。
2. CSV 和 SQLite 是“双写”，但没有强一致校验。
3. 证据长度过滤只对 `segment` 生效，`report_conclusion` 和 `point` 不受这个逻辑约束。

---

## 11. 地质库读取与融合前展开层

### 11.1 入口文件

- `backend/geology/geology_fusion_backend.py`

### 11.2 读取策略

`load_evidence_db()`：

1. 优先从 SQLite 读 `evidence_records`
2. 失败时回退到 CSV
3. 若从 CSV 成功读到，再同步 SQLite

### 11.3 attrs_json 展开

会展开常用字段：

- `risk_level`
- `water_flag`
- `collapse_flag`
- `deformation_flag`
- `support_grade`
- `water_type`
- `risk_tags`

注意：这里只展开了少数字段，其他细粒度属性仍留在 `attrs_json` 里。

---

## 12. PLC 与地质库融合层

### 12.1 入口文件

- `backend/geology/geology_fusion_backend.py`
- `backend/geology/fusion.py`

### 12.2 PLC 里程轴统一

优先级：

1. `chainage`
2. `导向盾首里程`
3. `开累进尺`

### 12.3 参与融合的证据层级

只保留：

1. `segment`
2. `report_conclusion`
3. `point`

排除：

- `overview`

### 12.4 命中规则

`get_active(chainage, evidence)`：

1. `segment/report_conclusion`
   - 用 `start_num - TOLERANCE_M <= chainage <= end_num + TOLERANCE_M`
   - `TOLERANCE_M` 默认 `3m`

2. `point`
   - 用 `point_buffer`，默认 `±5m`

### 12.5 逐里程融合输出

`fuse()` 对每个里程生成：

- `hazard`
- `hazard_list`
- `fused_grade`
- `water_flag_fused`
- `water_type_fused`
- `collapse_flag_fused`
- `deformation_flag_fused`
- `joint_degree_fused`
- `rock_mass_state_fused`
- `rock_uniformity_fused`
- `weathering_fused`
- `stability_fused`
- `lithology_fused`
- `active_source_count`
- `active_sources`
- `active_evidence_ids`
- `active_report_ids`
- `active_source_levels`
- `uncertainty`
- `evidence_count`
- `weighted_evidence_strength`

### 12.6 融合规则

1. 围岩等级：取最不利等级。
2. 出水/掉块/变形：一票通过。
3. 描述字段：取众数。
4. `hazard`：由 `water_type/water_flag/collapse_flag/deformation_flag/risk_tags` 去重拼接。
5. `active_source_count`：按 `(source_type, normalized_report_id)` 去重。
6. `uncertainty`：
   - 来源数 >= 3 -> `low`
   - 来源数 = 2 -> `medium`
   - 否则 -> `high`
7. `weighted_evidence_strength`：
   - `report_conclusion > point > segment`
   - `high confidence` 增强
   - `grade_conflict` 和 `consistency_flag=0` 惩罚

### 12.7 融合层输出形态

最终把逐里程融合结果按 `chainage` merge 回 PLC DataFrame，得到：

- `df_geo`

这是后面几乎所有地质、耦合、数字孪生和 prompt 的共同输入基底。

### 12.8 这一层的主要问题

1. `risk_level` 在融合层并没有直接变成统一的 `risk_score` 字段。
2. `hazard` 是拼接文本，适合展示，但不一定适合精细分析。
3. `active_source_count` 是“独立来源数”，而 `evidence_count` 是“证据条数”，两者在很多摘要层被混用。

---

## 13. 区段聚合层

### 13.1 入口文件

- `backend/geology/segment_analysis.py`

### 13.2 区段划分

按固定长度划分，默认：

- `10m`

生成：

- `segment_start`
- `segment_end`
- `segment_id`

### 13.3 区段聚合字段

会对以下字段做聚合：

- 施工参数：均值、标准差、最小、最大
- 地质融合字段：`risk_score / geo_prior_score / active_source_count / water_flag_fused / ...`
- 模式字段：`risk/hazard/coverage/uncertainty/fused_grade`

### 13.4 区段解释逻辑

`analyze_segment_response()` 根据：

- `risk_score`
- 平均推进速度
- 平均推力
- 平均扭矩
- 多源数量

输出 `interpretation` 文本。

### 13.5 这一层的主要问题

1. 它优先依赖 `risk_score`，但融合层并没有稳定地产生这个字段。
2. 如果缺少 `risk_score` 或 `speed`，就直接退化成“当前区段级施工响应关联条件仍不充分”。
3. 它的 `high_risk_segment_count` 和后面的 `forward_risk_count` 不是同一个统计口径。

---

## 14. 前方风险提示层

### 14.1 入口文件

- `backend/analysis/forward_risk_advisor.py`

### 14.2 逻辑

基于当前掌子面位置前方 `lookahead_m` 范围，对证据库做截取：

```text
end_num >= forward_start
and
start_num <= forward_end
```

### 14.3 统计指标

输出：

- `forward_segment_count`
- `high_risk_count`
- `multi_source_count`
- `risk_level_dist`
- `main_hazards`
- `source_types`

### 14.4 风险等级推断

1. `high_risk_count > 0` 且 `multi_source_count >= 3` -> `high`
2. 有高风险或多源>=2 -> `medium`
3. 只有前方证据 -> `low`
4. 否则 `none`

### 14.5 这一层的主要问题

1. 它直接统计前方窗口中的证据记录，而不是已聚合区段。
2. 因此 `forward_segment_count` 和区段分析里的 `segment_count` 根本不是一个维度。
3. 这就是前方提示和区段耦合摘要经常“看起来互相打架”的根源之一。

---

## 15. GRS / RAI / GRCI 耦合分析层

### 15.1 入口文件

- `backend/analysis/geology_response_coupling.py`
- `backend/analysis/geo_risk_model.py`

### 15.2 GRS

`compute_row_grs_base()` 的分量包括：

1. `grade_score`
2. `hazard_score`
3. `water_score`
4. `collapse_score`
5. `source_confidence`

处理方式：

1. 各分量映射到 `0~1`
2. 各分量 min-max 归一化
3. 等权平均得 `row_grs_base`

然后在 `run_coupling_analysis()` 中：

1. 对 `row_grs_base` 做高斯平滑
2. 聚合到区段
3. 形成 `GRS_base`
4. 用 `RAI + stop_ratio` 做动态修正
5. 得到最终 `GRS`

### 15.3 RAI

行级异常构造：

1. `IsolationForest` 基于：
   - 推力
   - 扭矩
   - 速度
   - 转速
   - 贯入度
2. 额外的稳健异常分数：
   - 速度下降
   - 推力偏高
   - 扭矩偏高
   - 转速异常
   - 贯入度异常
3. 低速停顿与状态停顿
4. 常规环级停顿折减

行级 `RAI`：

```text
0.70 * IsolationForest + 0.15 * stop_anomaly + 0.15 * efficiency_anomaly
```

区段级 `RAI` 再做 mean/max 混合。

### 15.4 GRCI

核心分量：

1. 同步性 `sync`
2. 滞后性 `lag`
3. 响应变化 `response_change`
4. 多参数一致性 `multi_param`
5. 来源置信修正 `confidence`

最终：

```text
GRCI = (0.40*sync + 0.25*lag + 0.25*response_change + 0.10*multi_param) * confidence
```

### 15.5 分类输出

1. `coupling_level` / `coupling_label`
2. `grci_class_code` / `grci_class_label`
3. `coupling_interpretation`

### 15.6 验证输出

`_validate_coupling()` 使用：

- `weak_anomaly_label`
- `GRCI`

生成：

- `top_k_hit_rate`
- `precision`
- `recall`
- `tp/fp/fn`

### 15.7 这一层的主要问题

1. `top_k_hit_rate` 和 `precision/recall` 使用的是不同评价视角，很容易对外解释冲突。
2. `GRCI` 排序最高的区段，不一定在 `grci_class_label` 上看起来“最危险”，因为类标签是阈值分象限，而排序是连续值。
3. `summary_text` 直接引用最高 `GRCI` 区段的类标签，容易出现“最高关注区段却是 D 类正常稳定区段”的尴尬表述。

---

## 16. 地质摘要与掌子面描述层

### 16.1 入口文件

- `backend/geology/geology_summary.py`

### 16.2 记录级摘要

`summarize_geology_record_level(df_geo)` 输出：

- `coverage_counts`
- `risk_counts`
- `hazard_counts`
- `max_attention`
- `mean_attention`
- `high_attention_count`

### 16.3 区段级摘要

`summarize_geology_segment_level(segment_df)` 输出：

- `segment_count`
- `risk_dist`
- `interpretation_dist`
- `high_risk_segment_count`
- `multi_source_segment_count`

### 16.4 当前掌子面地质描述

`build_face_geo_text()` **只用 `sketch + point`**。

如果最近 sketch 点离掌子面太远（默认大于 `20m`），则明确返回“当前掌子面直接揭示资料不足”。

这是当前系统里少数锁得比较紧的一层。

### 16.5 这一层的主要问题

1. 记录级摘要里的 `risk_counts` 依赖 `df_geo["risk"]`，但融合层并没有稳定生成这个列，很多时候会是空的。
2. 区段级摘要里的 `high_risk_segment_count` 使用 `risk_score_max >= 3`，与耦合层的 `GRCI`、前方层的 `risk_level` 不是同一语义。

---

## 17. 数字孪生层

### 17.1 入口文件

- `backend/services/digital_twin_state.py`

### 17.2 结构

数字孪生状态输出为：

- `time_state`
- `position_state`
- `operation_state`
- `geology_state`
- `safety_state`
- `forward_risk_state`
- `coupling_state`

### 17.3 来源

它不是独立重新计算，而是从：

- `df_geo`
- `stats`
- `state_stats`
- `gas_stats`
- `geo_summary_segment`
- `forward_risk_summary`
- `coupling_summary`

中再包装一层。

### 17.4 这一层的主要问题

1. 它把不同层的结果压成一个较短摘要，但不保留足够来源语义。
2. 其中一些字段，比如 `geology_state.current_active_source_count`，来自当前最后一条 PLC 记录，不一定等于区段或前方层的“证据数”。

---

## 18. CST 更新层

### 18.1 入口文件

- `backend/services/cst_update_service.py`

### 18.2 输入

`build_or_update_cst()` 使用：

- `stats`
- `state_stats`
- `gas_stats`
- `geo_summary_record`
- `geo_summary_segment`
- `forward_risk_summary`
- `coupling_summary`
- `digital_twin_state`
- `face_geo_text`
- `high_attention_segments`
- `warnings`

### 18.3 结构

`cst_state` 包括：

- `time_window`
- `temporal_state`
- `spatial_state`
- `operation_state`
- `geological_state`
- `response_state`
- `attention_state`
- `provenance_state`
- `raw_twin_state`
- `llm_summary`
- `gas_state`

### 18.4 这层的主要问题

1. 有些字段是从 `digital_twin_state` 继承，有些从 `geo_summary` 继承，有些从 `high_attention_segments` 拿第一段，语义来源并不统一。
2. `geological_state.evidence_count` 当前是：
   - 优先用 `current_active_source_count`
   - 否则用 `multi_source_segment_count`
   这两个量不是一回事。
3. `uncertainty` 依赖 `geo_summary_segment/geo_summary_record`，但这些摘要层未必保留了融合层的 `uncertainty`。

---

## 19. llm_summary 包装层

### 19.1 入口文件

- `backend/services/tbm_analysis_service.py`

### 19.2 作用

它把各层结果打包成给前端、Agent 和 prompt 层使用的中间字典。

### 19.3 当前写入的主要键

- `基础工况统计`
- `施工状态标签`
- `施工状态统计`
- `施工状态效率表`
- `气体统计`
- `地质摘要_记录级`
- `地质摘要_区段级`
- `典型地质区段`
- `前方风险提示摘要`
- `前方风险提示文本`
- `有效状态样本数`
- `状态识别配置`
- `区段风险-施工响应耦合分析`
- `耦合分析弱标签验证`
- `耦合分析高关注区段`
- `数字孪生状态`
- `Construction State Twin`
- `CST`

### 19.4 这一层的主要问题

这里是全链路最典型的“契约层”，但没有 schema 校验。后面的 prompt 读取如果键名写错，不会报错，只会静默退化。

---

## 20. Prompt 构建层

### 20.1 入口文件

- `backend/llm/prompt_builder.py`
- `backend/llm/prompt_builder_timewindow.py`

### 20.2 日报 prompt 输入

日报 prompt 直接接收：

- `seg_text`
- `stats_text`
- `state_text`
- `eff_text`
- `state_stats_text`
- `gas_text`
- `geo_text`
- `face_geo_text`
- `llm_summary`
- `risk_prob_text`

### 20.3 时窗 prompt 输入

时窗 prompt 接收：

- `start_time`
- `end_time`
- `seg_text`
- `stats_text`
- `state_text`
- `eff_text`
- `state_stats_text`
- `gas_text`
- `geo_text`
- `llm_summary`

**注意：时窗 prompt 没有 `face_geo_text`。**

### 20.4 prompt 的结构

当前 prompt 设计是：

1. 先给较强的角色与约束。
2. 再给一个“结构化 CST 摘要”。
3. 再拼接大量补充文本块。

### 20.5 Prompt 构建层的明确问题

1. `llm_summary` 写入的是 `"区段风险-施工响应耦合分析"`，但 prompt 读取的是 `"区段地质-施工耦合分析"`。
2. 时窗 prompt 明确要求区分当前掌子面与前方提示，但没有 `face_geo_text`。
3. 日报 prompt 把 `geo_text` 标成了“前方区段地质融合分析”，但它实际是已开挖区段区段级摘要。
4. `coupling_text` 和 `twin_text` 很可能是 `dict`，直接用 `_safe_text` 转成字符串后塞给模型，格式不干净。

---

## 21. 直到 prompt 之前的结构化输出总表

### 21.1 PLC 主线关键中间对象

1. `df`
   - 原始 PLC DataFrame（时间标准化后）
2. `df_geo`
   - 融合了逐里程地质字段的 PLC DataFrame
3. `segments`
   - 基础工况段列表
4. `stats`
   - 基础工况统计字典
5. `df_state`
   - 带 `state_id` 的 DataFrame
6. `state_segments`
   - 聚类状态段字典
7. `eff_df`
   - 状态效率表
8. `gas_stats`
   - 气体统计字典
9. `segment_df`
   - 区段聚合与耦合分析结果
10. `typical_segments_df`
    - 典型区段表
11. `forward_risk_summary`
    - 前方风险结构化摘要
12. `digital_twin_state`
    - 数字孪生字典
13. `cst_state`
    - 正式 CST 状态
14. `llm_summary`
    - prompt/前端/Agent 共用的中间摘要

### 21.2 PDF 主线关键中间对象

1. `EvidenceRecord`
2. `records_to_dataframe(records)`
3. `evidence_db.csv`
4. `SQLite evidence_records`
5. `evidence_df`
6. `evidence_df + attrs 展开列`

---

## 22. 你现在最该优先修的地方

如果目标是“每一层锁紧”，我建议优先顺序如下：

1. **先统一各层数据契约。**
   - 明确哪些字段是“记录级”、哪些是“区段级”、哪些是“前方窗口级”。
   - 明确哪些叫“来源数”、哪些叫“证据条数”。

2. **统一状态定义。**
   - 至少要规定：基础工况状态、聚类状态、RAI 停机判定三者的关系。

3. **给 `llm_summary` 建 schema。**
   - 不要再靠中文键名随意读写。
   - prompt 只能读取 schema 中定义的字段。

4. **给 prompt 输入做“文本化适配层”。**
   - 不要直接把 dict 串给模型。
   - 所有复杂对象先转成摘要文本。

5. **把前方风险和区段耦合分成两个明确口径。**
   - 一个是“前方窗口里的证据提示”。
   - 一个是“已开挖区段上的回顾性耦合分析”。
   - 这两个不能共用“高风险段数量”这种名字。

---

## 23. 一句话总结

当前系统不是没有逻辑，而是**每一层都各自有逻辑，但跨层的数据契约和统计口径没有完全锁紧**。这导致单层看都“像是对的”，一串起来就容易出现：

- 同名字段不同义
- 同义字段不同名
- 记录级和区段级结果混用
- 前方提示和回顾分析混写
- prompt 拿到的不是最终想表达的状态，而是中间包装残片

这也是你现在会感觉“很多问题一直在冒出来”的根本原因。
