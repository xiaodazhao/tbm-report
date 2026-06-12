# 地质-施工融合技术路线

## 1. 文档目标

本文档用于系统说明本项目中“地质证据与 TBM 施工数据融合”的技术路线、实现逻辑、运行操作和输出去向。

这里的“融合”不是直接预测灾害是否发生，也不是单纯把 PDF 文本拼到报告里，而是把 `TSP / HSP / 掌子面素描` 等多源地质证据映射到统一里程轴，再与 TBM 日运行 `CSV` 逐里程对齐，形成结构化的地质关注字段，供后续区段分析、耦合分析、`CST` 更新和报告生成使用。

## 2. 融合在系统中的位置

项目主线可以概括为：

```text
地质 PDF / 现场素描
    -> parser 结构化解析
    -> evidence_db.csv / SQLite
    -> 逐里程地质融合
    -> 区段级 GRS / RAI / GRCI
    -> Construction State Twin
    -> 报告 / 前端 / Agent
```

对应代码位置如下：

- 地质证据导入与建库：
  - `backend/scripts/build_evidence_db.py`
  - `backend/scripts/import_evidence_reports.py`
  - `backend/services/evidence_import_service.py`
- 融合主入口：
  - `backend/services/tbm_analysis_service.py`
- 证据加载与逐里程挂接：
  - `backend/geology/geology_fusion_backend.py`
- 逐里程事实融合规则：
  - `backend/geology/fusion.py`
- 融合后的下游使用：
  - `backend/geology/geology_summary.py`
  - `backend/analysis/forward_risk_advisor.py`
  - `backend/analysis/geology_response_coupling.py`
  - `backend/services/cst_update_service.py`

## 3. 输入数据与前置准备

### 3.1 TBM 日运行数据

融合主线的施工侧输入是每日 TBM `CSV`，至少需要可识别的里程字段。当前系统按以下优先级统一里程轴：

1. `chainage`
2. `导向盾首里程`
3. `开累进尺`

这一步在 `backend/geology/geology_fusion_backend.py` 的 `_ensure_chainage_column()` 中完成。

### 3.2 地质证据数据

地质侧输入来自三类 PDF：

1. `TSP`
2. `HSP` / `sonic`
3. `sketch`（掌子面 / 洞身素描）

这些 PDF 先由 parser 转成统一的 `EvidenceRecord`，再写入证据库。常见结构化字段包括：

- `evidence_id`
- `report_id`
- `source_type`
- `source_level`
- `start_num`
- `end_num`
- `confidence`
- `attrs_json`

其中 `attrs_json` 里保存围岩等级、出水、掉块、变形、岩性、节理、风化等细粒度属性。

## 4. 证据库构建与更新路线

### 4.1 首次建库或全量覆盖重建

首次接入数据、parser 规则整体调整后，推荐全量建库：

```bash
cd backend
python scripts/build_evidence_db.py
```

该脚本会：

1. 扫描配置目录下的 `TSP / HSP / SKETCH` PDF。
2. 调用对应 parser。
3. 合并为统一表结构。
4. 清洗异常记录。
5. 写入 `evidence_db.csv`。
6. 同步到 SQLite 中的 `evidence_records` 表。

### 4.2 日常新增超报的增量导入

如果只是新增了少量超前预报，使用增量导入更合适：

```bash
cd backend
python scripts/import_evidence_reports.py "/path/to/new_report.pdf" --source-type sketch --dry-run
python scripts/import_evidence_reports.py "/path/to/new_report.pdf" --source-type sketch
```

增量导入逻辑在 `backend/services/evidence_import_service.py` 中实现，具备以下特性：

1. 自动或显式选择 parser。
2. 支持文件和目录输入。
3. 支持 `dry_run`。
4. 默认跳过已有 `evidence_id`。
5. 使用 `--replace-existing` 时替换旧记录。
6. 正式写入前自动生成 CSV 备份。

### 4.3 证据清洗规则

建库与增量导入都会执行统一清洗，核心规则如下：

1. 必须存在 `evidence_id`、`start_num`、`end_num`。
2. 里程字段必须能转成数值。
3. 删除 `start_num > end_num` 的异常记录。
4. 以 `evidence_id` 去重，保留最后一条。
5. 对 `source_level == segment` 的记录，限制区段长度不超过 `300 m`。
6. 最终按 `source_type / report_id / start_num / end_num` 排序。

这一步的目标不是做风险判断，而是确保进入融合主线的证据在空间范围上可信、可计算。

## 5. 后端触发方式

### 5.1 启动后端

融合必须在后端执行。启动入口是：

```bash
cd backend
uvicorn app:app --reload --port 8000
```

FastAPI 入口位于 `backend/app.py`。

### 5.2 触发融合分析

后端日分析流程在 `backend/routes/tbm.py` 的 `_get_daily_analysis()` 中调用主分析函数。该函数会：

1. 根据日期定位 TBM `CSV`。
2. 读取日运行数据。
3. 调用 `analyze_tbm_data(...)`。
4. 在分析内部进入地质融合主线。
5. 将结果缓存并提供给报告、状态页、地质页、风险页等接口。

这意味着融合不是一个独立页面上的一次性脚本，而是每日分析主流程中的标准步骤。

## 6. 融合主流程

### 6.1 分析主入口

在 `backend/services/tbm_analysis_service.py` 的 `_run_geology_analysis()` 中，融合主线的核心调用是：

```text
load_evidence_db(EVIDENCE_DB_PATH)
    -> attach_geology_labels(df, evidence_df)
    -> annotate_routine_ring_building_stops(df_geo)
    -> run_segment_analysis(df_geo)
    -> run_coupling_analysis(df_geo)
    -> summarize_geology_record_level(df_geo)
    -> summarize_geology_segment_level(segment_df)
    -> generate_forward_risk_summary(df_geo, evidence_df)
```

其中真正完成“逐里程地质挂接”的步骤是 `attach_geology_labels(...)`。

### 6.2 证据库加载策略

`backend/geology/geology_fusion_backend.py` 中的 `load_evidence_db()` 采用“双通道”加载策略：

1. 优先从 SQLite 读取 `evidence_records`。
2. 如果 SQLite 读取失败，则回退到 `evidence_db.csv`。
3. 回退成功后，再尝试把 CSV 同步回 SQLite。

这样做的目的有两个：

1. 对线上接口尽量提供稳定、较快的读取方式。
2. 即使数据库状态异常，也不至于阻塞整个融合主线。

### 6.3 证据属性展开

证据记录中的很多细粒度属性都存在 `attrs_json` 中。加载后会先展开常用字段，例如：

- `risk_level`
- `water_flag`
- `collapse_flag`
- `deformation_flag`
- `support_grade`
- `water_type`
- `risk_tags`

这一步是为了让后续融合和调试可以直接按列访问，不必在每个下游模块重复解析 JSON。

## 7. 里程对齐逻辑

### 7.1 统一施工侧里程轴

系统先把 TBM `CSV` 转成带 `chainage` 的统一表。若找不到可用里程列，则地质融合直接降级返回原始数据，不继续挂接。

### 7.2 证据层级过滤

真正参与逐里程融合的证据层级只有三种：

1. `segment`
2. `report_conclusion`
3. `point`

其中：

- `segment` 表示明确里程区段证据；
- `report_conclusion` 表示结论性区段证据；
- `point` 主要是掌子面素描这类点位证据。

`overview` 这类整份报告概览信息不会进入逐里程融合，因为它缺少明确的空间约束。

### 7.3 唯一里程表

为了避免对同一里程重复计算，系统会先从 TBM 数据中提取唯一 `chainage`，排序后形成唯一里程表，然后逐个里程点执行证据命中与融合。

这一步由 `annotate_unique_chainage()` 完成，最后再把融合结果按 `chainage` 合并回原始 PLC 表。

## 8. 逐里程命中规则

逐里程命中逻辑在 `backend/geology/fusion.py` 的 `get_active()` 中实现。

### 8.1 区段类证据命中

对 `segment` 和 `report_conclusion`：

```text
start_num - TOLERANCE_M <= chainage <= end_num + TOLERANCE_M
```

其中 `TOLERANCE_M` 来自 `backend/config.py`，默认值为 `3.0 m`。

设计意图是给报告区段边界一个小范围容差，避免由于里程离散采样和取整误差导致本应命中的证据被漏掉。

### 8.2 点位类证据命中

对 `point`：

```text
start_num - point_buffer <= chainage <= end_num + point_buffer
```

默认 `point_buffer = 5.0 m`。

这样做是因为掌子面素描、点位揭示等现场证据通常具有更强的局部代表性，但单一里程点和 PLC 采样点不一定完全重合，因此需要一个小缓冲带。

## 9. 逐里程融合规则

`fuse(chainage, df)` 的原则是：

**只做事实融合，不在这个阶段直接做风险判定。**

也就是说，这一层输出的是“该里程附近有哪些地质事实或关注表现”，而不是“该里程已经发生某灾害”。

### 9.1 空命中时的默认输出

如果某一里程没有命中任何证据，系统仍返回完整结构，但内容为默认值，例如：

- `coverage = none`
- `hazard = 无明显异常`
- `active_source_count = 0`
- `weighted_evidence_strength = 0.0`
- `uncertainty = high`

这样可以保证后续模块始终面对固定 schema，而不需要额外处理大量缺列情况。

### 9.2 围岩等级融合

围岩等级先做标准化，再取“最不利等级”作为 `fused_grade`。

例如同一里程命中多条记录，若分别为 `III`、`IV`、`V`，则融合结果取 `V`。

这样做的理由是：

1. 围岩等级本身具有明显序关系。
2. 对施工安全关注而言，最不利等级更保守，也更符合工程解释习惯。

### 9.3 灾害标签融合

系统会从每条证据的 `attrs_json` 中提取：

- `water_type` / `water_flag`
- `collapse_flag`
- `deformation_flag`
- `risk_tags`

然后去重保序，形成：

- `hazard_list`
- `hazard`

其中 `hazard` 是一个以 `+` 连接的简短摘要，例如：

```text
出水+掉块+变形
```

如果没有提取到风险表现，则记为 `无明显异常`。

### 9.4 布尔型异常项融合

以下字段采用“有一票即判定存在”的方式融合：

- `water_flag_fused`
- `collapse_flag_fused`
- `deformation_flag_fused`

也就是只要命中证据中有任意一条记录标记了该现象，融合结果就置为 `1`。

这种规则适合安全相关特征，因为它强调“不要漏掉已被某来源记录的异常现象”。

### 9.5 描述型字段融合

以下字段采用众数融合：

- `joint_degree_fused`
- `rock_mass_state_fused`
- `rock_uniformity_fused`
- `weathering_fused`
- `stability_fused`
- `lithology_fused`

如果众数不存在或值过少，则退化为取第一条有效值。

这类字段更适合用“多数来源的一致描述”来表示主导特征。

### 9.6 水类型融合

`water_type_fused` 会收集所有非空 `water_type`，去重后用 `;` 拼接。

这比单一类别更适合保留工程语义，因为不同报告可能同时提到“滴水”“线状出水”“局部渗水”等表述。

## 10. 来源统计与不确定性估计

除了事实字段，融合层还会生成来源与证据统计字段。

### 10.1 来源去重方式

系统会对每条命中记录提取：

- `source_type`
- `source_level`
- `report_id`

同时对 `report_id` 做规范化，避免同一报告因为命名尾缀差异被重复统计。

最终使用 `(source_type, normalized_report_id)` 作为来源去重键。

### 10.2 active_source_count

`active_source_count` 表示当前里程命中了多少个独立来源报告，而不是多少条证据行。

这是一个很重要的设计，因为同一份报告可能拆成多条 `EvidenceRecord`，如果直接按记录数统计，会夸大证据支持强度。

### 10.3 uncertainty

当前不确定性采用简单规则：

1. `active_source_count >= 3` 时，`uncertainty = low`
2. `active_source_count == 2` 时，`uncertainty = medium`
3. 否则为 `high`

这里的不确定性含义更接近“多源支持程度”，而不是严格统计意义上的置信区间。

### 10.4 weighted_evidence_strength

系统还会计算 `weighted_evidence_strength`，其权重只表示证据强度和可信度，不直接用于本层风险判定。

权重规则包括：

1. `report_conclusion` 稍高于普通 `segment`
2. `point` 略有提升
3. `confidence=high` 提升，`low` 降低
4. `consistency_flag=0` 时惩罚
5. `grade_conflict=1` 时惩罚

这个字段的意义是为后续区段关注度评估提供更细的支持信息，而不是取代显式工程规则。

## 11. 融合层输出字段

逐里程融合后，PLC 数据会新增一批地质字段，典型包括：

- `coverage`
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

这张融合后的表通常在代码中命名为 `df_geo`。

## 12. 融合后的下游分析

融合层本身不输出最终风险，而是为下游模块提供统一输入。

### 12.1 记录级与区段级摘要

`backend/geology/geology_summary.py` 会对 `df_geo` 和 `segment_df` 做总结，输出：

- 覆盖情况
- 高关注记录数
- 主要关注表现
- 区段风险分布
- 典型区段解释

### 12.2 当前掌子面地质描述

当前掌子面地质文字不是简单取最近预报，而是只使用：

```text
source_type == sketch 且 source_level == point
```

也就是说，掌子面描述优先依赖现场素描点位记录，而不是直接把超前预报等同为当前掌子面实况。

这条约束非常关键，避免报告出现“把前方预报写成当前揭示”的工程语义错误。

### 12.3 前方风险提示

`backend/analysis/forward_risk_advisor.py` 会基于当前掌子面前方 `lookahead_m` 范围内的证据，生成前方风险摘要，包括：

- 前方关注段数量
- 高风险段数量
- 多源共同关注数
- 主要风险类型
- 建议重点监测参数
- 建议支护准备措施

### 12.4 区段耦合分析

`backend/analysis/geology_response_coupling.py` 在融合结果基础上继续计算：

- `GRS`：地质关注度
- `RAI`：施工响应异常度
- `GRCI`：地质-施工耦合关注度

注意：

1. `fusion.py` 不负责最终 `GRS / RAI / GRCI`。
2. `fusion.py` 的职责是把多源地质证据组织成可信的逐里程事实层。
3. 指标计算属于下一层的区段建模与耦合分析。

### 12.5 CST 更新

后续 `cst_update_service.py` 会把地质关注、证据数量、耦合高关注区段等写入正式 `cst_state`，用于：

- 状态连续性表达
- 报告 prompt 构造
- 历史状态对比
- Agent 问答读取

## 13. 实际运行操作建议

### 13.1 首次运行建议顺序

1. 配置 `.env` 中的数据路径，确保 `TSP_DIR`、`HSP_DIR`、`SKETCH_DIR`、`EVIDENCE_DB_PATH` 正确。
2. 执行一次全量建库。
3. 启动后端服务。
4. 在前端或 API 上按日期触发分析。
5. 检查地质页、风险页和报告页输出是否合理。

### 13.2 日常更新建议顺序

1. 新增超报 PDF 到对应目录。
2. 先做 `dry_run` 增量导入。
3. 检查解析数量、重复记录和报错。
4. 正式导入证据库。
5. 重新触发当日分析。
6. 检查融合后高关注区段是否有变化。

### 13.3 验证融合是否生效

如果想确认融合生效，可以重点检查：

1. `df_geo` 中是否新增了 `active_source_count`、`hazard`、`fused_grade` 等字段。
2. 地质摘要页是否出现区段风险与典型区段。
3. 当前掌子面地质描述是否能读到素描点位信息。
4. 前方风险提示是否反映最新导入的超报。
5. `cst_state` 中的地质状态和 attention 状态是否更新。

## 14. 设计边界与注意事项

当前融合方案有几个明确边界：

1. 融合层只做事实整合，不直接认定灾害已经发生。
2. 证据空间对齐主要依赖报告中的里程范围质量，如果 parser 提取错误，融合结果会连带偏移。
3. `overview` 类记录不参与逐里程融合，因为空间约束不足。
4. 点位证据依赖缓冲匹配，适合表达邻近揭示，不等于精确逐厘米对齐。
5. `active_source_count` 表示独立来源数，不等于证据绝对真实性。
6. 当前不确定性是工程启发式规则，不是统计置信区间。
7. 当前掌子面描述严格限制使用 `sketch + point`，不能直接用远距离超前预报替代。

## 15. 一句话总结

本项目的融合技术路线本质上是：

**先把多源地质证据标准化入库，再按统一里程轴逐点匹配，做保守的事实型融合，最后把融合结果作为区段分析、CST 更新和自动报告生成的基础状态层。**
