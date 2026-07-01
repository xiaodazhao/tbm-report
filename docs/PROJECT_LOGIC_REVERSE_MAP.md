# TBM 项目全链路方法逻辑反向说明书

> 目的：这份文档不再写“项目做了什么”，而是回答“项目内部各部分到底按照什么逻辑运行”。  
> 口径：基于当前代码真实逻辑反向梳理。  
> 注意：RAI / GRS / GRCI 均为启发式关注指标，不是灾害概率、故障概率或监督学习预测结果。

---

## 1. 总体逻辑一句话

项目的核心逻辑是：

```text
把每日 PLC 施工响应和时间可用、空间相关的多源地质证据统一投到 10m 里程单元，
再按“已掘复核 / 前方关注 / 局部背景”分配证据角色，
在已掘复核单元内计算地质-施工响应耦合关注度，
最后把这些结构化证据交给模板或 LLM 生成报告，并用 Quality / Trace / Boundary 检查其是否越界。
```

这里最重要的不是“生成日报”，而是：

```text
数据 → cell → 状态 → 证据角色 → 关注指标 → Evidence Pack → 受约束文本 → 可追溯检查
```

---

## 2. 配置与数据定位逻辑

### 2.1 系统先找哪些路径

入口文件：

```text
backend/config.py
```

核心路径：

```text
DATA_ROOT
DATA_DIR
EVIDENCE_DB_PATH
```

逻辑：

```text
如果 .env 或环境变量里设置了 DATA_ROOT：
    使用用户指定 DATA_ROOT
否则：
    走 legacy fallback 自动探测路径
    同时写入 CONFIG_WARNINGS

DATA_DIR 默认 = DATA_ROOT / TBM9_2023
EVIDENCE_DB_PATH 默认 = DATA_ROOT / DB / evidence_db.csv
```

风险：

```text
如果 DATA_ROOT 没有显式配置，系统仍可能跑起来，
但这时复现性较差，因为它依赖本机 fallback 路径。
```

论文/实验口径：

```text
正式实验必须明确 DATA_ROOT、DATA_DIR、EVIDENCE_DB_PATH。
```

---

## 3. API 层逻辑

入口：

```text
backend/app.py
→ backend/routes/report.py
```

当前 API 只有四个主接口：

| 接口 | 逻辑 |
|---|---|
| `GET /api/tbm/health` | 只检查服务是否活着，不跑 pipeline |
| `GET /api/tbm/dates` | 扫描可用 PLC 日期 |
| `POST /api/tbm/report` | 跑主 pipeline，但只返回面向前端展示的核心结果 |
| `POST /api/tbm/report/debug` | 跑同一条主 pipeline，但返回完整中间结果 |

重要逻辑：

```text
/report 和 /report/debug 调的是同一个 run_daily_report_pipeline()
差别只在返回字段多少，不是两套业务流程。
```

---

## 4. 主 pipeline 的控制逻辑

主入口：

```text
backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline()
```

整体顺序：

```text
1. 读取输入
2. 分析 PLC
3. 运行 geology_v2 online 时间过滤
4. 构建日报空间范围
5. 对地质证据做日报空间筛选
6. 构建 report-scope cells
7. 投影地质证据到 cells
8. 融合 geo_states
9. 构建 ConstructionStateCell
10. 构建 DailyConstructionTwin
11. 从 Twin 构建 Evidence Pack
12. 生成模板或 LLM 报告
13. Quality / Trace / Boundary 检查
14. 汇总 DailyReportResult
```

### 4.1 生成模式逻辑

参数：

```python
use_llm: bool = False
generation_mode: str | None = None
```

逻辑：

```text
如果 generation_mode 显式传入：
    使用 generation_mode
否则：
    use_llm=False → template
    use_llm=True  → evidence_pack_llm
```

实际默认：

```text
template / no-LLM 是默认稳定模式。
```

---

## 5. 输入读取逻辑

文件：

```text
backend/pipeline/inputs.py
```

函数：

```python
load_daily_inputs(date)
```

逻辑：

```text
1. 根据 date 找 PLC CSV
2. 读取 evidence_db.csv
3. 如果 evidence_db 不存在：
       evidence_df = 空 DataFrame
       warnings 加入 evidence table not found
4. 返回 DailyInputs
```

关键点：

```text
PLC 是日报必需输入；
地质证据可以为空，但为空时 GRS/GRCI 会受限。
```

---

## 6. PLC 施工响应逻辑

入口：

```text
backend/plc/response.py::analyze_plc_response()
```

PLC 处理不是直接算 RAI，而是分几层：

```text
原始 PLC
→ 数据质量检查
→ 工况识别
→ 聚类/效率统计
→ 气体统计
→ cell_response_df
→ RAI
```

### 6.1 PLC 质量检查

文件：

```text
backend/analysis/plc_quality_checker.py
```

逻辑：

```text
检查 PLC 是否存在关键字段、空值、异常值、日期范围等。
结果进入 quality_report，不直接决定 GRCI。
```

### 6.2 工况识别逻辑

文件：

```text
backend/analysis/dataprocess.py
```

逻辑大致是：

```text
根据掘进状态、推进速度、推力、扭矩等字段，
把每条 PLC 记录标成工作、停机、异常、过渡等施工状态。
```

注意：

```text
这些状态是工程规则识别，不是监督学习分类。
```

### 6.3 cell_response_df 逻辑

文件：

```text
backend/plc/cell_response.py::project_plc_response_to_cells()
```

逻辑：

```text
1. 找里程字段
2. 找速度、推力、扭矩、转速、贯入度字段
3. 按 cell_length 默认 10m 对 PLC 记录分组
4. 对每个 cell 聚合施工响应指标
5. 计算 RAI
```

字段优先级：

```text
优先使用 motion_cols.advance_speed
优先使用 motion_cols.thrust
优先使用 motion_cols.torque
优先使用 motion_cols.rpm
优先使用 motion_cols.penetration
同时保留旧 key fallback
```

### 6.4 working-only 逻辑

有效掘进样本条件：

```text
推进速度 > 0
推力 > 0
刀盘扭矩 > 0
刀盘实际转速 > 0
如果存在 is_working，则还要求 is_working=True
```

停机样本逻辑：

```text
停机样本不进入 working-only 均值/CV；
但会进入 stop_ratio。
```

样本不足：

```text
working_sample_count < 20
→ insufficient_working_samples=True
→ CV 等统计可能为空
```

### 6.5 RAI 计算逻辑

公式：

```text
RAI = 0.40 * stop_ratio
    + 0.25 * abnormal_ratio
    + 0.20 * speed_drop_score
    + 0.10 * torque_volatility_score
    + 0.05 * speed_volatility_score
```

解释：

| 分量 | 含义 |
|---|---|
| `stop_ratio` | cell 内停机占比 |
| `abnormal_ratio` | cell 内异常/非正常施工占比 |
| `speed_drop_score` | 推进速度低于同日参考水平的程度 |
| `torque_volatility_score` | 扭矩波动程度 |
| `speed_volatility_score` | 速度波动程度 |

边界：

```text
RAI 越高，表示施工响应越需要关注；
不表示设备故障概率；
不表示地质灾害概率；
不直接说明异常原因。
```

### 6.6 PLC enhanced fields 逻辑

新增字段：

```text
working_sample_count
working_ratio
working_speed_cv
working_thrust_cv
working_torque_cv
penetration_mean
cutterhead_power_proxy
thrust_per_penetration
torque_per_penetration
```

逻辑：

```text
这些字段只用于提高 PLC 证据解释性；
不改变 RAI；
不改变 GRCI；
不进入 forward_attention；
不作为地质风险判断。
```

---

## 7. 地质证据逻辑

入口：

```text
backend/geology_v2/pipeline.py::run_geology_v2_context()
```

### 7.1 地质证据先做时间过滤

逻辑：

```text
所有 evidence 先标准化
再按 online 模式过滤时间可用性
```

online 规则核心：

```text
报告日期之后形成的 evidence 不能进入；
当前掌子面之后才形成的掌子面素描不能进入；
超前预报可以作为 prediction evidence，但不能写成现场揭露事实。
```

### 7.2 HSP 异常点去重

文件：

```text
backend/geology_v2/evidence_dedup.py
```

逻辑：

```text
HSP anomaly_point 在边界或重复报告中可能重复，
根据里程、掌子面、hazard family 等规则合并。
```

### 7.3 空间投影逻辑

文件：

```text
backend/geology_v2/evidence_projector.py
```

核心公式：

```text
effective_weight = spatial_weight * source_reliability * evidence_strength
```

其中：

```text
spatial_weight：证据与 cell 空间距离/重叠关系
source_reliability：不同证据来源的相对可靠性
evidence_strength：证据自身强度
```

输出：

```text
cell_evidence_df
```

重要字段：

```text
evidence_overlap_length
evidence_overlap_ratio
source_reliability
evidence_confidence
effective_weight
```

### 7.4 地质融合逻辑

文件：

```text
backend/geology_v2/fusion_engine.py
```

输出：

```text
geo_states_df
```

核心字段：

```text
fused_grade
main_hazards
hazard_scores
confidence_score
uncertainty_level
conflict_level
GRS_geo_base
source_trace
```

### 7.5 GRS 计算逻辑

公式：

```text
GRS_geo_base = 0.45 * grade_score_component
             + 0.45 * hazard_component
             + 0.10 * confidence_component
```

其中：

```text
hazard_component = 0.75 * max_hazard_score
                 + 0.25 * avg_hazard_score
```

边界：

```text
GRS 是地质证据关注度；
不是灾害概率；
不是风险发生概率；
无证据和低关注必须区分。
```

---

## 8. 日报空间范围与证据角色逻辑

文件：

```text
backend/pipeline/evidence_scope.py
```

这是项目最核心的治理逻辑之一。

### 8.1 为什么不是全局 cell

早期项目曾出现全局 geo cells，例如 157 个 cell。  
现在主流程不再保留全局 geo cells 作为日报主链路。

当前逻辑：

```text
日报只关心当前日期附近的 report scope：
1. 当日已掘复核范围
2. 当前掌子面前方关注范围
3. 局部背景范围
```

### 8.2 三类 cell role

| role | 判定逻辑 | 用途 | 可用指标 |
|---|---|---|---|
| `daily_review` | 与当日已掘 cell 对齐范围重叠 | 已掘区段复核 | RAI / GRS / GRCI |
| `forward_attention` | 当前掌子面前方严格 forward cell | 前方关注提示 | GRS / source_trace |
| `local_background` | 局部范围内但非 daily/forward | 背景语境 | GRS / source_trace |

### 8.3 daily_plc_range vs daily_excavated_scope

这两个字段的逻辑完全不同：

| 字段 | 含义 |
|---|---|
| `daily_plc_range` | PLC 实测当日推进范围 |
| `daily_advance_m` | PLC 实测推进量 |
| `daily_excavated_scope` | 10m cell 对齐后的已掘复核范围 |

硬边界：

```text
不能用 daily_excavated_scope 计算实际推进量；
不能把 10m 对齐范围写成“当日推进范围”；
这类错误对应 E14。
```

---

## 9. ConstructionStateCell 合并逻辑

文件：

```text
backend/coupling/grs_rai_grci.py::build_construction_state_cells()
```

逻辑：

```text
cells_df 提供空间单元
cell_response_df 提供 PLC 响应
geo_states_df 提供地质状态
cell_evidence_df 提供证据投影关系
normalized_evidence_df 提供 source_trace
scope_summary 提供 role 和范围
```

然后每个 cell 形成一个：

```text
ConstructionStateCell
```

### 9.1 has_plc_response 逻辑

```text
如果 cell_response_df 中有该 cell 的施工响应记录：
    has_plc_response=True
    RAI 可用
否则：
    has_plc_response=False
    RAI=None
```

### 9.2 has_geology_evidence 逻辑

```text
如果 cell_evidence_df 中有该 cell 的空间相关证据：
    has_geology_evidence=True
    GRS_available 取决于融合结果
否则：
    has_geology_evidence=False
    GRS_available=False
```

### 9.3 GRCI 计算前提

只有同时满足：

```text
cell_role == daily_review
has_plc_response == True
RAI is not None
GRS_geo_base is not None
GRCI_available == True
```

才计算 GRCI。

forward_attention 和 local_background 不计算正式 GRCI。

---

## 10. GRCI 逻辑

文件：

```text
backend/coupling/grs_rai_grci.py::compute_cell_grci()
```

公式：

```text
GRCI = 0.55 * GRS_geo_base
     + 0.35 * RAI
     + 0.10 * GRS_geo_base * RAI
```

解释：

```text
GRCI 是已掘区段中，
地质证据关注度和施工响应关注度同时存在时的耦合复核关注度。
```

不表示：

```text
不表示灾害概率；
不表示风险发生概率；
不表示前方风险；
不表示因果诊断。
```

缺失逻辑：

| 情况 | GRCI |
|---|---|
| 缺 PLC response / RAI | `None` |
| 缺 GRS | `None` |
| forward_attention | `None` |
| local_background | `None` |

分级：

```text
GRCI >= 0.75 → high
0.50 <= GRCI < 0.75 → medium
0.25 <= GRCI < 0.50 → low
GRCI < 0.25 → none/low attention
```

---

## 11. Forward Profile 逻辑

文件：

```text
backend/geology_v2/forward_profile.py
backend/pipeline/daily_report_pipeline.py::_with_forward_attention_cells()
```

逻辑：

```text
从当前掌子面向前 lookahead_m 默认 30m；
按 cell_length 默认 10m 分为 0-10m、10-20m、20-30m；
每个 forward cell 只使用 GRS、main_hazards、source_trace 等地质证据；
不使用 RAI；
不使用 GRCI；
不使用 PLC enhanced metrics。
```

距离权重：

```text
0-10m → 1.0
10-20m → 0.7
20-30m → 0.4
```

报告表达：

```text
只能写“前方关注提示”；
不能写“已发生异常”；
不能写“现场已揭露”；
不能写“GRCI 高风险”。
```

---

## 12. DailyConstructionTwin 逻辑

文件：

```text
backend/twin/construction_twin.py
```

逻辑：

```text
ConstructionStateCell 是原始统一 cell；
DailyConstructionTwin 是面向查询、证据治理和 LLM 的状态视图。
```

它不是重新计算指标，而是重组视图：

```text
position_state
operation_state
response_state
geology_state
forward_state
gas_state
coupling_state
quality_state
trace_state
```

### 12.1 forward cell 防护

在 Twin 里再次保证：

```text
forward_attention cell:
    coupling_state.GRCI = None
    coupling_state.GRCI_available = False
```

这是一层冗余保护。

### 12.2 governance 逻辑

Twin 同时带：

```text
governance
trace_index
summaries
```

目的是让 Evidence Pack 和 checker 不只看到数值，还看到：

```text
证据角色
边界规则
source_trace
禁止表达
允许表达
```

---

## 13. Evidence Pack 逻辑

文件：

```text
backend/llm/evidence_pack.py
```

当前主流程使用：

```text
build_evidence_pack_from_twin()
```

核心逻辑：

```text
DailyConstructionTwin
→ 选择关键 daily_review cells
→ 选择 forward_attention cells
→ 选择 local_background cells
→ 加入 operation / cluster / gas / quality / source_trace
→ 加入 generation_constraints
```

### 13.1 Evidence Pack 不是什么

它不是：

```text
原始 PLC 全量 CSV；
完整 evidence_db；
LLM 自由检索数据库；
地质风险预测模型输入。
```

它是：

```text
经过角色划分、范围筛选、字段压缩和边界约束后的结构化证据包。
```

### 13.2 selection_score 逻辑

Evidence Pack 不会把所有 cell 都塞进 prompt，而是选关键 cell。

daily_review selection：

```text
综合 GRCI、GRS、trace completeness、source reliability 等。
```

forward_attention selection：

```text
0.45 * GRS
+ 0.25 * forward_distance_weight
+ 0.20 * evidence_confidence
+ 0.10 * trace_completeness
```

并且：

```text
forward selection 不使用 GRCI。
```

### 13.3 key_cells / selected_cells 逻辑

正式字段：

```text
geology_evidence.key_cells
```

兼容字段：

```text
geology_evidence.selected_cells
```

当前逻辑：

```text
两者内容保持一致；
grounding checker 优先读 key_cells；
如果没有 key_cells，再 fallback 到 selected_cells。
```

---

## 14. 报告生成逻辑

### 14.1 template 模式

文件：

```text
backend/llm/evidence_pack.py::build_template_report()
```

逻辑：

```text
不调用 LLM；
直接根据 Evidence Pack 填充固定结构；
稳定、可复现；
文本较机械。
```

### 14.2 LLM 模式

文件：

```text
backend/llm/llm_report_generator.py
```

逻辑：

```text
Evidence Pack
→ prompt
→ LLM draft
→ clean LLM text
→ Quality / Trace
→ optional revision
→ final report
```

### 14.3 LLM 不允许做的事

prompt 和 checker 都约束：

```text
不能把 GRCI 写成灾害概率；
不能把 forward_attention 写成已发生事实；
不能把 daily_excavated_scope 写成实际推进范围；
不能把 stop_ratio 高写成异常停机原因；
不能把 cutterhead_power_proxy 写成真实功率；
不能声称 TSP/HSP 一定真实；
不能无证据推断灾害。
```

---

## 15. Quality / Trace / Boundary 逻辑

### 15.1 Quality

文件：

```text
backend/llm/report_quality_checker.py
```

逻辑：

```text
检查章节完整性；
检查禁用表达；
检查 GRCI 概率误用；
检查 forward fact misuse；
检查 aligned scope 误用；
检查 stop_ratio 过度解释；
调用 grounding checker 统计 unsupported。
```

质量分：

```text
从 100 分开始扣分。
```

扣分项包括：

```text
forbidden phrase
warning
missing section
low grounding rate
unsupported claims
```

### 15.2 Trace / Grounding

文件：

```text
backend/llm/report_grounding_checker.py
backend/llm/report_trace_builder.py
```

逻辑：

```text
先抽取 report claims；
再把 claim 和 Evidence Pack 中的 key_cells、forward cells、gas、operation、coupling、policy boundary 匹配；
匹配成功 → grounded；
匹配失败 → unsupported。
```

支持类型：

```text
observed_evidence
prediction_evidence
operation_evidence
gas_evidence
coupling_evidence
policy_support
none
```

### 15.3 Boundary

文件：

```text
backend/llm/twin_boundary_checker.py
```

逻辑：

```text
用规则/正则检查报告是否违反 Twin 证据边界。
```

检查类型：

```text
GRCI 概率误用
前方提示写成事实
PLC proxy 误用
stop_ratio 因果误用
local_background 写成当日结论
```

---

## 16. 自动修订逻辑

### 16.1 主 pipeline 修订

主 pipeline 可以启用：

```text
evidence_pack_llm_with_revision
planned_evidence_pack_llm_with_revision
```

逻辑：

```text
生成初稿
→ 检查初稿
→ 把问题反馈给 LLM
→ 生成修订稿
→ 再检查
```

### 16.2 Exp02 M4 修订

Exp02 的 M4 是实验版闭环：

```text
M4 initial report
→ pre quality/trace/boundary
→ revision prompt
→ revised report
→ section guard
→ post quality/trace/boundary
```

逻辑重点：

```text
修订不是润色；
修订目标是删除、降级或改写无支撑、数值错误、边界违规表达。
```

---

## 17. Exp02 实验逻辑

目录：

```text
experiments/exp02_llm_generation_modes/
```

Exp02 不是主 pipeline 本身，而是对不同生成方式的对比实验。

五种模式：

| 模式 | 逻辑 |
|---|---|
| M0 | 模板生成，不调用 LLM |
| M1 | 直接 LLM，只给少量基础信息 |
| M2 | 给原始/粗略证据摘要 |
| M3 | 给结构化 Twin Evidence Pack |
| M4 | M3 + Quality/Trace/Boundary 检查 + 自动修订 |

递进关系：

```text
M1 → M2 → M3 → M4
```

含义：

```text
逐步增加证据输入、证据结构化、边界约束和修订机制。
因此它既是生成模式对比，也是模块贡献分析。
```

当前结果逻辑：

```text
15 天 → 小样本验证
30 天 → 分层样本扩展验证
91 天 → 本工程全部可用日期验证
```

91 天结果说明：

```text
M4 综合最好；
M4 E14 = 0；
M4 missing_sections = 0；
M4 boundary = 3；
M4 unsupported 和 numeric 明显少于 M1/M2/M3。
```

但不能说明：

```text
不能说明跨工程泛化；
不能说明 LLM 完全可靠；
不能说明自动评价等同人工评价。
```

---

## 18. Exp03 指标稳健性逻辑

目录：

```text
experiments/exp03_indicator_robustness/
```

Exp03 的目的：

```text
不改变主流程；
不改变 Exp02；
只检查 RAI/GRS/GRCI 公式换一种算法后，高关注排序是否稳定。
```

版本：

| 版本 | 逻辑 |
|---|---|
| V0_current | 当前主流程公式 |
| V1_percentile_equal | 分位数标准化 + 均权 |
| V2_percentile_interaction | `sqrt(RAI*GRS)*C` |
| V3_percentile_entropy | 熵权 + 交互 |
| V4_percentile_critic | CRITIC 权重 + 交互 |
| V5_strict_min | `min(RAI,GRS)*C` |

比较方式：

```text
Top-K Jaccard
Spearman rank correlation
high attention date overlap
forward GRCI leakage check
```

逻辑解释：

```text
如果 V0 和其他版本排序高度相关：
    当前启发式指标具有一定稳健性
如果 Top-K 差异大：
    高关注 cell 对公式敏感，需要专家标定或标签校准
```

当前结论：

```text
V0 与 V1-V4 Spearman 较高；
V5 严格耦合差异较大；
forward leakage = 0。
```

论文表述：

```text
可以写“稳健性与敏感性分析”；
不能写“证明当前公式最优”。
```

---

## 19. 项目中最核心的 12 条逻辑边界

1. PLC 只解释已掘施工响应，不解释前方地质事实。
2. 地质证据分为 time-valid 和 spatial-relevant，不是所有 evidence 都能进日报。
3. daily_review 用于复核已掘区段。
4. forward_attention 只用于前方关注提示。
5. local_background 只用于背景语境。
6. RAI 是施工响应关注度，不是异常原因概率。
7. GRS 是地质证据关注度，不是灾害概率。
8. GRCI 是已掘耦合关注度，不是前方风险。
9. GRCI 必须同时有 RAI 和 GRS 才可用。
10. high_grci_cells 只能来自 daily_review。
11. LLM 只能消费 Evidence Pack，不直接判断原始数据。
12. Quality/Trace/Boundary 是自动检查，不等同人工评价。

---

## 20. 用论文语言可以怎么讲

可以讲：

```text
本文构建了一个面向 TBM 施工日报的多源证据治理与可追溯生成框架。
该框架将 PLC 施工响应、多源地质证据和报告生成约束统一到里程单元层面，
通过 ConstructionStateCell 和 DailyConstructionTwin 组织证据，
并将证据角色划分为已掘复核、前方关注和局部背景。
在此基础上，系统构建 Evidence Pack 约束大语言模型生成，
并通过 Quality、Trace 和 Boundary 检查实现报告输出的可追溯核验。
```

不要讲：

```text
本文提出了地质灾害概率预测模型；
本文用 LLM 判断前方地质风险；
GRCI 表示灾害发生概率；
RAI 表示设备异常概率；
系统实现了真实物理数字孪生；
91 天实验证明跨工程泛化。
```

---

## 21. 如果写论文方法章，建议的逻辑结构

```text
1. 任务定义：TBM 日报不是普通文本生成，而是证据约束生成。

2. 多源数据治理：
   PLC 日运行数据；
   TSP/HSP/掌子面素描等地质证据；
   时间可用性与空间相关性过滤。

3. 里程单元状态建模：
   ConstructionStateCell；
   daily_review / forward_attention / local_background。

4. 施工响应与地质证据指标：
   RAI；
   GRS；
   GRCI；
   指标语义边界。

5. DailyConstructionTwin：
   把 cell 状态组织成可查询、可追溯、可约束的状态底座。

6. Evidence Pack：
   把 Twin 转成 LLM 可消费的结构化证据。

7. 证据约束生成：
   template；
   LLM；
   planner；
   revision。

8. Quality / Trace / Boundary：
   自动质量检查；
   claim-grounding；
   边界违规识别。

9. 实验设计：
   Exp02 生成模式对比；
   Exp03 指标稳健性。
```

---

## 22. 当前项目逻辑的薄弱点

| 薄弱点 | 本质 |
|---|---|
| RAI/GRS/GRCI 权重主观 | 没有标签，无法监督标定 |
| Quality/Trace 自动指标有限 | 规则系统无法完全替代人工判断 |
| Exp02 M4 是实验脚本闭环 | 与 API 默认 LLM 链路不是完全同一实现 |
| 地质证据可靠性权重来源需要解释 | source_reliability 可能被审稿人追问 |
| PLC proxy 指标单位边界要写清 | power proxy / penetration ratio 不是严格物理量 |
| 结果只来自单工程 | 不能写跨工程泛化 |
| prompt/checker 曾多轮修补 | 论文需说明最终固定口径 |
| 项目仍有历史目录残留 | 代码工程性还需清理 |

---

## 23. 最该优先讲清楚的 5 个逻辑

1. **为什么要有 cell**  
   因为 PLC 和地质证据天然不是同一粒度，必须统一到里程单元。

2. **为什么要分 daily_review / forward_attention / local_background**  
   因为同一条地质证据在不同空间角色下，报告表达权限不同。

3. **为什么 GRCI 只能用于已掘复核**  
   因为 GRCI 需要 PLC 响应，而前方没有当日 PLC 响应。

4. **为什么 LLM 不能直接写**  
   因为 LLM 容易混用范围、证据角色和数值，所以必须先 Evidence Pack，再检查修订。

5. **为什么 Exp03 必要**  
   因为 RAI/GRS/GRCI 是启发式公式，需要证明排序对不同权重/公式不至于完全失稳。

