# TBM 施工状态证据治理与受控报告生成方法说明书

本文档用于从方法逻辑层面解释当前 TBM 项目，而不是解释某个函数如何调用。读者可以把它当作“项目 idea 审查说明书”：从原始数据进入系统开始，逐层说明数据如何被清洗、如何形成证据、如何计算指标、如何约束报告生成、如何检查文本是否越界。

本文档遵循两个写法原则：

1. 所有关键英文变量都给出中文解释，例如“施工响应关注度（RAI）”。
2. 所有重要步骤尽量写成算法流程、公式、表格和边界说明，而不是只列代码文件名。

---

## 1. 项目总体定位

### 1.1 项目不是做什么

当前项目不是以下几类系统：

| 容易误解的说法 | 为什么不准确 |
|---|---|
| “用大模型直接写 TBM 日报” | 大模型不是直接读取原始数据自由生成，而是受证据包约束 |
| “预测 TBM 参数” | 项目不训练推进速度、推力、扭矩等预测模型 |
| “预测地质灾害概率” | 项目没有灾害标签，不输出灾害发生概率 |
| “物理仿真数字孪生” | 项目没有三维仿真或力学仿真，而是证据状态数字孪生 |
| “PLC 自动判断前方地质风险” | PLC 只用于已掘区段施工响应复核，不能用于前方事实判断 |

### 1.2 项目实际做什么

项目实际做的是：

> 将 TBM 日施工 PLC 数据、多源地质证据和报告生成约束统一组织为按里程单元表达的施工状态证据，再用模板或大模型在证据边界内生成日报，并通过质量、追踪和边界检查核验报告。

### 1.3 一张总流程图

```text
┌──────────────────────────────────────────────────────────┐
│  原始数据输入                                              │
│  ├─ PLC 日运行数据                                         │
│  └─ TSP / HSP / 掌子面素描 / 其他地质证据                  │
└──────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│  数据治理                                                  │
│  ├─ PLC：质量检查、工况识别、有效掘进样本、稳态段、cell 汇总 │
│  └─ 地质：标准化、时间过滤、空间筛选、cell 投影、融合       │
└──────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│  10m 施工状态单元 ConstructionStateCell                   │
│  ├─ 已掘复核单元 daily_review                              │
│  ├─ 前方关注单元 forward_attention                         │
│  └─ 局部背景单元 local_background                          │
└──────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│  启发式关注指标                                            │
│  ├─ 施工响应关注度 RAI                                      │
│  ├─ 地质证据关注度 GRS                                      │
│  └─ 地质-施工响应耦合关注度 GRCI                            │
└──────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│  DailyConstructionTwin + Evidence Pack                    │
│  ├─ 明确哪些证据能写                                       │
│  ├─ 明确哪些证据只能提示                                   │
│  └─ 明确哪些表达禁止                                       │
└──────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│  报告生成与校核                                            │
│  ├─ 模板报告 / LLM 报告                                    │
│  ├─ 章节完整性检查                                         │
│  ├─ 证据支撑检查                                           │
│  ├─ 数值语义检查                                           │
│  └─ 边界违规检查                                           │
└──────────────────────────────────────────────────────────┘
```

---

## 2. 核心概念与中文-英文字段对照

下面这些概念贯穿整个项目。

| 中文概念 | 英文字段或简称 | 含义 |
|---|---|---|
| 施工状态单元 | 施工状态单元（ConstructionStateCell） | 按 10m 里程划分的基本证据单元 |
| 当日实测推进范围 | 当日 PLC 范围（daily_plc_range） | PLC 原始数据中当天实际推进起止里程 |
| 当日推进量 | 日推进量（daily_advance_m） | 当日最大里程减最小里程 |
| 对齐后已掘复核范围 | 已掘复核范围（daily_excavated_scope） | 按 10m cell 对齐后的复核范围，不等于实际推进范围 |
| 当前掌子面 | 当前掌子面里程（current_chainage） | 当日末端或当前施工面位置 |
| 已掘复核单元 | 已掘复核（daily_review） | 可使用 PLC、RAI、GRS、GRCI 的 cell |
| 前方关注单元 | 前方关注（forward_attention） | 当前掌子面前方 cell，只能使用地质证据 |
| 局部背景单元 | 局部背景（local_background） | 只提供地质上下文，不作为当日结论 |
| 施工响应关注度 | 施工响应关注度（RAI） | PLC 显示出的施工响应关注程度 |
| 地质证据关注度 | 地质证据关注度（GRS / GRS_geo_base） | 地质证据本身的关注程度 |
| 耦合关注度 | 地质-施工响应耦合关注度（GRCI） | 已掘区段内 GRS 和 RAI 的耦合关注程度 |
| 证据包 | 证据包（Evidence Pack） | 交给模板或大模型的结构化证据输入 |
| 证据追踪 | 证据追踪（Trace） | 报告句子与证据来源的匹配关系 |
| 质量检查 | 质量检查（Quality） | 章节、禁用表述、支撑率、数值等检查 |
| 边界检查 | 边界检查（Boundary） | 防止前方事实化、GRCI 概率化、PLC proxy 误用 |

---

## 3. 数据输入层

### 3.1 PLC 日运行数据

PLC 数据是按日期读取的一张表。典型字段如下：

| 中文字段 | 项目内部中文含义 | 标准化概念 |
|---|---|---|
| 运行时间-time | 采样时间 | 时间（time） |
| 掘进状态 | 设备原始掘进状态 | 原始状态（raw_state） |
| 导向盾首里程 | 当前里程 | 里程（chainage） |
| 开累进尺 | 累计进尺 | 备用里程/进尺字段 |
| 推进速度 | TBM 推进速度 | 推进速度（advance_speed） |
| 推进给定速度 | 设定推进速度 | 设定速度（set_advance_speed） |
| 推力 | 推进总推力 | 推力（thrust） |
| 刀盘扭矩 | 刀盘负载扭矩 | 扭矩（torque） |
| 刀盘实际转速 | 刀盘实际转速 | 转速（rpm） |
| 刀盘给定转速 | 设定转速 | 设定转速（set_rpm） |
| 贯入度 | 设备记录贯入度 | 贯入度（penetration） |
| CO2/H2S/SO2/NO2/NO/CH4 检测 | 气体检测值 | 气体监测（gas_monitoring） |

PLC 的用途分为三类：

1. 计算当日推进范围；
2. 分析施工响应；
3. 生成已掘区段复核证据。

### 3.2 地质证据数据

地质证据来自正式证据库。主要包括：

| 类型 | 英文标识 | 证据性质 | 使用边界 |
|---|---|---|---|
| 掌子面素描 | 掌子面素描（face_sketch） | 现场揭示证据 | 只能在形成时间之后使用 |
| TSP 超前预报 | TSP（TSP） | 超前预报证据 | 是预测/预报，不是现场已揭露事实 |
| HSP 超前预报 | HSP（HSP） | 超前预报证据 | 可拆出异常点，但仍是预报证据 |
| 钻孔/揭示 | 钻孔（borehole） | 现场或近现场揭示 | 可作为较高可靠性证据 |
| 报告结论 | 报告结论（report_conclusion） | 人工解释证据 | 有概括性，需保留来源 |
| 区域背景 | 背景（overview/background） | 背景信息 | 不作为强逐里程结论 |

地质证据的核心不是“原文有多长”，而是能否被转成可计算、可追踪的结构化证据。

---

## 4. PLC 预处理与施工响应证据构建

PLC 处理是当前项目最重要的工程基础之一。它回答的问题是：

> 当日已掘区段内，TBM 施工响应是否出现值得复核的变化？

它不回答：

> 前方是否已经发生地质异常？

### 4.1 PLC 处理总流程图

```text
原始 PLC 样本
│
├─ A. 字段标准化
│   ├─ 时间（time）
│   ├─ 里程（chainage）
│   ├─ 推进速度（advance_speed）
│   ├─ 推力（thrust）
│   ├─ 扭矩（torque）
│   ├─ 转速（rpm）
│   └─ 贯入度（penetration）
│
├─ B. 基础工况识别
│   ├─ 停机（stop）
│   ├─ 启动/过渡（transition）
│   ├─ 工作/稳定掘进（work）
│   └─ 异常扭矩类状态（abnormal）
│
├─ C. paper-based PLC preprocessing
│   ├─ 时间和里程质量检查
│   ├─ 停机/辅助停机识别
│   ├─ 3σ 异常点过滤
│   ├─ 有效掘进样本识别
│   ├─ 连续有效掘进区间切分
│   ├─ 稳态段识别
│   └─ cell 级稳态指标汇总
│
├─ D. 10m cell 聚合
│   ├─ 原始全样本统计
│   ├─ working-only 统计
│   ├─ steady-state 统计
│   └─ RAI 分量计算
│
└─ E. 输出施工响应证据
    ├─ operation_summary
    ├─ gas_summary
    ├─ cell_response_df
    └─ ConstructionStateCell.plc_metrics
```

### 4.2 A. 字段标准化

字段标准化的作用是把不同表头统一成内部标准概念。

| 内部中文概念 | 英文字段 | 来源字段示例 | 处理方式 |
|---|---|---|---|
| 时间 | 时间（time） | 运行时间-time | 转为时间类型，用于排序和时间间隔 |
| 里程 | 里程（chainage） | 导向盾首里程、开累进尺 | 转为数值，用于 cell 分组 |
| 推进速度 | 推进速度（advance_speed） | 推进速度 | 转为数值 |
| 推力 | 推力（thrust） | 推力 | 转为数值 |
| 扭矩 | 刀盘扭矩（torque） | 刀盘扭矩 | 转为数值 |
| 转速 | 刀盘转速（rpm） | 刀盘实际转速 | 转为数值 |
| 贯入度 | 贯入度（penetration） | 贯入度 | 转为数值 |

如果某个字段缺失，相关统计会降级为空值或 fallback，不应让系统崩溃。

### 4.3 B. 基础工况识别

基础工况识别用于形成运行统计和原 RAI 所需的状态，不代表完整 PLC 清洗。

判定规则如下：

| 条件 | 工况编码 | 中文工况 | 英文状态 |
|---|---:|---|---|
| 掘进状态为 0，或推力/速度/扭矩均接近 0 | 0 | 停机 | stop |
| 有推力但推进速度不足 | 1 | 启动/过渡 | transition |
| 推力有效且推进速度有效 | 2 | 工作/稳定掘进 | work |
| 无明显推力推进但扭矩存在 | 3 | 异常扭矩类状态 | abnormal |

基础工况的作用：

- 统计工作、停机、过渡、异常持续时间；
- 支撑运行概况；
- 支撑聚类样本选择；
- 支撑 RAI 中的停机和异常分量；
- 保持旧实验和主流程指标口径稳定。

基础工况的边界：

- 它是工程规则，不是监督学习分类；
- 它不能区分计划停机和非计划停机；
- 它不能单独解释地质原因。

### 4.4 C1. 时间和里程质量检查

paper-based PLC preprocessing 的第一步是检查采样顺序和里程连续性。

#### 4.4.1 里程差分

对相邻样本计算：

```text
里程差（chainage_diff_i） =
  当前样本里程（chainage_i） - 上一样本里程（chainage_{i-1}）
```

判定规则：

| 规则 | 当前阈值 | 中文解释 |
|---|---:|---|
| 里程倒退（chainage_reverse） | chainage_diff < -0.01 m | 认为存在明显倒退 |
| 里程跳变（chainage_jump） | abs(chainage_diff) > 5.0 m | 认为相邻样本里程跳变过大 |
| 里程有效（chainage_valid） | 非倒退且里程非空 | 可用于后续有效掘进判断 |

#### 4.4.2 时间间隔

如果存在时间字段，则计算相邻样本时间差：

```text
时间差（time_diff_i） =
  当前样本时间（time_i） - 上一样本时间（time_{i-1}）
```

先取所有正时间差的中位数：

```text
中位采样间隔（median_dt） = median(time_diff_i > 0)
```

时间间断阈值：

```text
时间间断阈值 = max(3 × median_dt, 10 秒)
```

如果：

```text
time_diff_i > 时间间断阈值
```

则该样本位置标记为时间间断（time_gap）。

理论意义：

- 时间间断会切断连续工作区间；
- 避免把中间缺失很长时间的数据误认为连续施工。

### 4.5 C2. 停机/辅助停机识别

停机识别不是简单看推进速度，而是先看核心负载是否为零或接近零。

当前阈值：

| 参数 | 阈值 |
|---|---:|
| 推力阈值（eps_thrust） | 0.0 |
| 扭矩阈值（eps_torque） | 0.0 |
| 推进速度阈值（eps_speed） | 0.0 |
| 转速阈值（eps_rpm） | 0.0 |

停机样本判定：

```text
推力为零或近零（thrust_zero） = 推力 <= eps_thrust
扭矩为零或近零（torque_zero） = 扭矩 <= eps_torque

停机样本（is_shutdown_segment） =
  thrust_zero OR torque_zero
```

停机原因（shutdown_reason）：

| 情况 | 原因 |
|---|---|
| 推力和扭矩缺失 | missing_thrust_or_torque |
| 推力和扭矩均为零 | both_thrust_and_torque_zero_or_near_zero |
| 仅推力为零 | thrust_zero_or_near_zero |
| 仅扭矩为零 | torque_zero_or_near_zero |

辅助停机判定：

```text
辅助停机（auxiliary_shutdown） =
  推进速度 <= eps_speed OR 转速 <= eps_rpm
```

边界说明：

- 停机样本用于排除非有效掘进状态；
- 停机不等于异常停机；
- 当前 PLC 字段未可靠区分计划停机与非计划停机。

### 4.6 C3. 3σ 异常点过滤

异常点过滤只在非停机样本中进行。

参与检查的连续参数：

| 中文名 | 英文字段 |
|---|---|
| 推进速度 | advance_speed |
| 推力 | thrust |
| 扭矩 | torque |
| 转速 | rpm |
| 贯入度 | penetration |

对每个参数，若有效样本数不少于 30，且标准差大于极小值，则计算：

```text
均值（mean） = 参数均值
标准差（std） = 参数标准差
下界（lower） = mean - 3 × std
上界（upper） = mean + 3 × std
```

异常点规则：

```text
若 参数值 < lower 或 参数值 > upper
则标记为异常点（is_outlier=True）
```

异常原因（outlier_reason）会记录类似：

```text
speed_outside_3sigma
thrust_outside_3sigma
torque_outside_3sigma
rpm_outside_3sigma
penetration_outside_3sigma
```

如果某个参数样本数不足或标准差太小，则跳过该参数的 3σ 检查。

理论意义：

- 避免传感器尖峰值污染稳态均值；
- 只做数据清洗，不做异常原因判断。

### 4.7 C4. 有效掘进样本识别

有效掘进样本（valid_excavation_mask）是当前 PLC enhanced fields 的核心。

一个样本要成为有效掘进样本，必须同时满足：

```text
不是停机样本
AND 不是 3σ 异常点
AND 里程有效
AND 推力 > eps_thrust
AND 扭矩 > eps_torque
AND 如果推进速度字段存在，则推进速度 > eps_speed
AND 如果转速字段存在，则转速 > eps_rpm
AND 如果已有基础工况 is_working，则必须 is_working=True
```

写成公式：

```text
valid_excavation_mask =
  NOT is_shutdown_segment
  AND NOT is_outlier
  AND chainage_valid
  AND thrust > eps_thrust
  AND torque > eps_torque
  AND optional(advance_speed > eps_speed)
  AND optional(rpm > eps_rpm)
  AND optional(is_working = True)
```

这里的 optional 表示：如果字段存在，才使用该条件。

重要解释：

- 这一步才是当前有效掘进样本判断的主逻辑；
- 简单“四个参数大于 0”只是缺少 valid_excavation_mask 时的 fallback；
- 有效掘进样本用于 working-only 统计和后续稳态段识别。

### 4.8 C5. 连续有效掘进区间切分

有效掘进样本不是全部混在一起，而是切成连续区间。

区间开始条件：

```text
当前样本有效
AND (
  上一个样本无效
  OR 出现时间间断
  OR 出现里程倒退
)
```

每个连续区间统计：

| 中文指标 | 英文字段 |
|---|---|
| 区间开始时间 | interval_start_time |
| 区间结束时间 | interval_end_time |
| 区间持续时间 | interval_duration_seconds |
| 区间样本数 | interval_sample_count |
| 区间起点里程 | interval_chainage_start |
| 区间终点里程 | interval_chainage_end |
| 区间推进长度 | interval_chainage_length |

有效区间判定：

```text
有效连续掘进区间 =
  interval_sample_count >= 20
  AND interval_duration_seconds >= 30
```

否则标记为短过渡区间（short_transition_interval）。

理论意义：

- 一个孤立的有效样本不能代表稳定施工；
- 过短片段更可能是启动、试推或噪声。

### 4.9 C6. 稳态段识别

稳态段识别只在有效连续掘进区间内进行。

#### 4.9.1 检测信号选择

优先使用推进速度：

```text
如果推进速度存在且有正值：
  检测信号 = 推进速度（advance_speed）
```

如果推进速度不可用，则使用贯入度作为最后 fallback：

```text
如果贯入度存在且有正值：
  检测信号 = 贯入度（penetration）
```

注意：这里的贯入度只是设备记录值，用作稳态切分信号，不被解释为严格贯入率。

#### 4.9.2 滚动均值

对检测信号计算滚动均值：

```text
滚动均值（rolling_mean_i） =
  最近 20 个样本检测信号的平均值
```

最少有效样本数：

```text
steady_min_periods = 5
```

即滚动窗口内至少 5 个有效值才计算。

#### 4.9.3 稳态候选阈值

先计算滚动均值的中位数：

```text
median_value = median(rolling_mean)
```

稳态候选阈值：

```text
threshold = 0.8 × median_value
```

候选稳态样本：

```text
candidate_i = rolling_mean_i >= threshold
```

#### 4.9.4 候选片段选择

将连续的候选样本形成候选片段。若有多个候选片段，按以下优先级选一个：

```text
1. 样本数最多
2. 持续时间最长
3. 里程长度最长
```

候选片段成为正式稳态段还必须满足：

```text
样本数 >= 20
AND 持续时间 >= 30 秒
```

否则不认为稳态段可用，而是记录 fallback。

#### 4.9.5 样本阶段标签

每个样本会被标记为：

| 中文阶段 | 英文字段值 |
|---|---|
| 停机 | shutdown |
| 异常点 | abnormal_outlier |
| 非掘进 | non_excavation |
| 启动或加速段 | ascending_or_startup |
| 稳态段 | steady_state |
| 末端或减速段 | end_or_deceleration |
| 无法识别稳态时的工作 fallback | working_only_fallback |

### 4.10 C7. 10m cell 稳态指标汇总

对每个 10m cell，系统分别统计原始样本、有效掘进样本和稳态样本。

#### 4.10.1 样本数指标

| 中文指标 | 英文字段 | 含义 |
|---|---|---|
| 原始样本数 | raw_sample_count | cell 内全部 PLC 样本数 |
| 停机样本数 | shutdown_sample_count | 停机样本数量 |
| 异常点样本数 | outlier_sample_count | 3σ 异常点数量 |
| 有效掘进样本数 | working_sample_count_paper | 有效掘进样本数量 |
| 稳态样本数 | steady_sample_count | 稳态段样本数量 |
| 稳态比例 | steady_ratio | 稳态样本数 / 原始样本数 |
| 稳态占有效掘进比例 | steady_to_working_ratio | 稳态样本数 / 有效掘进样本数 |

#### 4.10.2 稳态统计指标

对稳态样本计算：

```text
均值（mean） = average(x)
标准差（std） = standard_deviation(x)
变异系数（cv） = std / abs(mean)
```

若均值接近 0，则变异系数为空，避免除零。

统计对象包括：

| 中文指标 | 英文字段 |
|---|---|
| 稳态推进速度均值/标准差/变异系数 | steady_speed_mean / steady_speed_std / steady_speed_cv |
| 稳态推力均值/标准差/变异系数 | steady_thrust_mean / steady_thrust_std / steady_thrust_cv |
| 稳态扭矩均值/标准差/变异系数 | steady_torque_mean / steady_torque_std / steady_torque_cv |
| 稳态转速均值/标准差/变异系数 | steady_rpm_mean / steady_rpm_std / steady_rpm_cv |
| 稳态贯入度均值/标准差/变异系数 | steady_penetration_mean / steady_penetration_std / steady_penetration_cv |

#### 4.10.3 proxy 指标

当前计算三个 proxy：

```text
刀盘功率近似量（steady_cutterhead_power_proxy）
  = 稳态扭矩均值 × 稳态转速均值
```

```text
单位贯入推力近似量（steady_thrust_per_penetration）
  = 稳态推力均值 / 稳态贯入度均值
```

```text
单位贯入扭矩近似量（steady_torque_per_penetration）
  = 稳态扭矩均值 / 稳态贯入度均值
```

这些都必须叫“近似量（proxy）”。

原因：

- 扭矩和转速单位未完全确认；
- 没有刀盘面积、开挖体积等完整物理量；
- 不能计算严格比能；
- 不能把 proxy 解释为真实物理功率。

#### 4.10.4 PLC 预处理质量等级

每个 cell 会给一个 PLC 预处理质量等级：

| 等级 | 条件 | 含义 |
|---|---|---|
| A | 有稳态段，稳态样本数 >= 50，稳态/有效掘进比例 >= 0.5，核心指标不少于 3 个 | 高质量稳态证据 |
| B | 有稳态段，稳态样本数 >= 20，核心指标不少于 2 个 | 可用稳态证据 |
| C | 无稳态段，但 working-only fallback 可用，且有效样本 >= 20 | 有效掘进 fallback |
| D | 以上都不满足 | PLC 预处理证据不足 |

### 4.11 D. cell 级 RAI 计算

RAI 不是由 paper-based preprocessing 新公式替换的。当前 RAI 保持原口径。

RAI 分量：

| 中文分量 | 英文字段 | 计算方式 |
|---|---|---|
| 停机比例 | stop_ratio | 停机时长 / cell 总时长 |
| 异常比例 | abnormal_ratio | 异常工况时长 / cell 总时长 |
| 速度下降分 | speed_drop_score | 1 - cell 平均速度 / 当日 75% 分位速度 |
| 扭矩波动分 | torque_volatility_score | 扭矩标准差 / max(abs(扭矩均值), 1) |
| 速度波动分 | speed_volatility_score | 速度标准差 / max(abs(速度均值), 1) |

公式：

```text
RAI =
  0.40 × stop_ratio
+ 0.25 × abnormal_ratio
+ 0.20 × speed_drop_score
+ 0.10 × torque_volatility_score
+ 0.05 × speed_volatility_score
```

每个分量贡献：

```text
停机贡献（stop_component） = 0.40 × stop_ratio
异常贡献（abnormal_component） = 0.25 × abnormal_ratio
速度下降贡献（speed_drop_component） = 0.20 × speed_drop_score
扭矩波动贡献（torque_component） = 0.10 × torque_volatility_score
速度波动贡献（speed_volatility_component） = 0.05 × speed_volatility_score
```

主导分量（dominant_component）取贡献最大的分量。

### 4.12 PLC 处理的理论边界

PLC 证据只能支持：

- 已掘区段施工响应是否值得复核；
- 有效掘进状态下负载、波动、贯入效率是否有变化；
- 停机、异常工况、速度下降是否增加关注。

PLC 证据不能支持：

- 前方地质异常已经发生；
- 地质灾害概率；
- 异常停机原因；
- 真实功率或严格比能；
- GRCI 作为前方风险。

---

## 5. 地质证据治理与融合

地质证据治理回答的问题是：

> 哪些地质证据在当前日报日期可用，且与当日已掘、当前掌子面前方或局部背景范围相关？

### 5.1 地质证据处理总流程图

```text
原始地质证据库
│
├─ A. 证据标准化
│   ├─ 来源类型标准化
│   ├─ 证据角色识别
│   ├─ 空间类型识别
│   ├─ 里程解析
│   ├─ hazard 标签清洗
│   └─ HSP 异常点拆分
│
├─ B. 时间可用性过滤
│   ├─ 报告日期过滤
│   ├─ 现场揭示未来过滤
│   └─ TSP/HSP face_chainage 可用性过滤
│
├─ C. 日报空间范围筛选
│   ├─ 已掘复核范围
│   ├─ 前方 0-30m 范围
│   ├─ 局部背景范围
│   └─ 距离过远排除
│
├─ D. 证据投影到 10m cell
│   ├─ 距离计算
│   ├─ 空间权重
│   ├─ 来源可靠性
│   └─ 有效权重
│
└─ E. cell 地质融合
    ├─ 围岩等级分布
    ├─ hazard_scores
    ├─ confidence_score
    ├─ conflict_level
    └─ GRS
```

### 5.2 A. 证据标准化

证据标准化把不同来源、不同字段名、不同表达方式的地质资料转成统一结构。

#### 5.2.1 来源类型标准化

| 原始可能写法 | 标准中文 | 英文字段值 |
|---|---|---|
| sketch / face_sketch / face_observation | 掌子面素描 | face_sketch |
| tsp / TSP | TSP 超前预报 | TSP |
| sonic / hsp / HSP | HSP 超前预报 | HSP |
| drill / borehole | 钻孔 | borehole |
| report_conclusion / conclusion | 报告结论 | report_conclusion |
| overview / background | 背景 | overview |

#### 5.2.2 证据角色

| 中文角色 | 英文字段值 | 含义 |
|---|---|---|
| 现场揭示 | observed | 掌子面素描、钻孔等现场或近现场证据 |
| 超前预报 | prediction | TSP/HSP 等预测性证据 |
| 背景 | background | 区域或报告概述背景 |
| 解释结论 | interpreted | 报告结论类证据 |

#### 5.2.3 空间类型

| 中文空间类型 | 英文字段值 | 含义 |
|---|---|---|
| 点状 | point | 单点里程证据 |
| 异常点 | anomaly_point | HSP 掉块点等局部异常点 |
| 区段 | segment | 起止里程覆盖的区段证据 |
| 报告结论区段 | report_conclusion | 报告型区段结论 |
| 概述/背景 | overview/background | 不参与强逐里程融合 |

#### 5.2.4 里程解析

地质证据中可能有：

| 中文字段 | 英文字段 |
|---|---|
| 起点里程 | start_chainage |
| 终点里程 | end_chainage |
| 中心里程 | center_chainage |
| 证据形成时掌子面里程 | face_chainage |

对 TSP/HSP，证据形成时的掌子面里程（face_chainage）非常重要。它决定该预报在某个日报日期是否已经可用。

#### 5.2.5 hazard 标签清洗

地质文本中的标签会被分成三类：

| 中文类别 | 英文字段 | 说明 |
|---|---|---|
| 地质关注标签 | hazard_tags | 出水、掉块、破碎、裂隙密集等 |
| 属性标签 | attribute_tags | 围岩等级建议、支护建议等 |
| 方法标签 | method_tags | TSP、HSP、水平声波、掌子面素描等 |
| 未识别标签 | unknown_hazard_tags | 暂未纳入词表的疑似关注标签 |

负向表述会被识别为 negative，例如“未见出水”不能因为包含“出水”两个字就被误判为 positive。

#### 5.2.6 HSP 异常点拆分

HSP 证据中可能包含多个掉块点或异常点。系统会把这些点拆成独立的异常点证据：

```text
一条 HSP 区段证据
│
├─ 保留原区段证据
└─ 拆出多个 HSP anomaly_point
```

每个异常点继承原 HSP 的形成掌子面里程（face_chainage），但空间位置使用异常点自身里程。

### 5.3 B. 时间可用性过滤

时间过滤的目的：避免未来信息泄漏。

#### 5.3.1 现场揭示证据

现场揭示证据包括掌子面素描、钻孔等。如果其空间位置在当前掌子面前方，则不能用于当前日报。

以里程增大方向为例：

```text
如果 observed_chainage > current_chainage + 1m
则排除为未来现场揭示证据
```

其中 1m 是里程容差。

#### 5.3.2 TSP/HSP 预报证据

TSP/HSP 是预报证据，判断其是否可用不能只看证据覆盖区间，而要看它形成时的掌子面里程（face_chainage）。

规则：

```text
如果 TSP/HSP 的 face_chainage 缺失：
  在线模式下保守排除

如果 face_chainage > current_chainage + 1m：
  说明该预报形成于未来掌子面，排除
```

#### 5.3.3 报告日期过滤

如果证据报告日期晚于日报日期，则排除。

```text
issue_date/report_date > analysis_date
=> 排除
```

### 5.4 C. 日报空间范围筛选

时间可用不代表一定与当日有关。还要按空间范围筛选。

#### 5.4.1 范围定义

| 中文范围 | 英文字段 | 含义 |
|---|---|---|
| 当日实测 PLC 范围 | daily_plc_range | 原始 PLC 最小里程到最大里程 |
| 日推进量 | daily_advance_m | daily_chainage_max - daily_chainage_min |
| 已掘复核范围 | daily_excavated_scope | 对齐到 10m cell 后的已掘复核范围 |
| 前方范围 | forward_scope | 当前掌子面前方 30m |
| 局部背景范围 | local_background_scope | 当前掌子面后方局部背景，默认 100m |
| 日报总范围 | report_scope | 背景 + 已掘 + 前方的合并范围 |

重要区别：

```text
daily_plc_range 是实际 PLC 推进范围。
daily_excavated_scope 是 10m cell 对齐后的复核范围。
二者不能混用。
```

#### 5.4.2 范围对齐规则

假设 cell 尺度为 10m：

```text
daily_excavated_scope.start = floor(daily_chainage_min / 10) × 10
daily_excavated_scope.end   = ceil(daily_chainage_max / 10) × 10
```

例如：

```text
PLC 实测范围：1014601 ~ 1014616
日推进量：15m
对齐后复核范围：1014600 ~ 1014620
```

不能把 1014600~1014620 写成实际推进 20m。

#### 5.4.3 证据空间角色

| 判断 | 证据角色 |
|---|---|
| 与已掘复核范围重叠 | 已掘复核证据（daily_review_evidence） |
| 与前方范围重叠 | 前方关注证据（forward_attention_evidence） |
| 与局部背景范围重叠 | 局部背景证据（local_background_evidence） |
| 与日报范围无关 | 距离排除（excluded_by_distance） |
| 缺少里程几何 | 几何缺失排除（excluded_by_missing_geometry） |

### 5.5 D. 证据投影到 10m cell

地质证据需要投影到 10m cell。

#### 5.5.1 距离计算

对区段证据：

```text
如果 cell_center 在证据起止范围内：
  distance_m = 0
否则：
  distance_m = cell_center 到最近区段边界的距离
```

对点状证据：

```text
distance_m = abs(cell_center - evidence_center_chainage)
```

#### 5.5.2 空间权重

空间权重使用高斯衰减：

```text
spatial_weight = exp(-0.5 × (distance_m / sigma_m)^2)
```

其中 sigma_m 根据证据来源和空间类型决定：

| 证据 | sigma 大致含义 |
|---|---|
| 掌子面素描点 | 局部影响，sigma 较小 |
| HSP/TSP 区段 | 区段预报，sigma 较大 |
| HSP 异常点 | 局部异常，sigma 较小 |
| overview | 默认不强逐里程融合 |

#### 5.5.3 有效权重

投影后每条 evidence-cell 关系的有效权重：

```text
effective_weight =
  spatial_weight
  × source_reliability
  × evidence_strength
```

其中：

| 中文项 | 英文字段 | 含义 |
|---|---|---|
| 空间权重 | spatial_weight | 离 cell 越近越高 |
| 来源可靠性 | source_reliability | 掌子面素描、钻孔、TSP/HSP 等来源权重 |
| 证据强度 | evidence_strength | 点、异常点、区段、置信度等综合强度 |

有效权重只是融合权重，不是风险概率。

### 5.6 E. 地质融合

地质融合把同一个 cell 上的多条证据合成一个地质状态。

输出包括：

| 中文指标 | 英文字段 | 含义 |
|---|---|---|
| 是否有地质证据 | has_geology_evidence | cell 是否有空间相关证据 |
| 融合围岩等级 | fused_grade | 综合支持度最高的围岩等级 |
| 围岩等级分布 | grade_distribution | 各等级证据支持情况 |
| 地质关注分数 | hazard_scores | 出水、掉块、破碎等标签得分 |
| 主要关注现象 | main_hazards | 排名前几的 hazard |
| 置信度 | confidence_score | 证据量、来源数、冲突等综合 |
| 不确定性等级 | uncertainty_level | 证据不足或冲突导致的不确定性 |
| 冲突等级 | conflict_level | 多源证据是否矛盾 |
| 来源追踪 | source_trace | 支撑证据列表 |

### 5.7 GRS 计算

GRS 表示地质证据关注度。

公式：

```text
GRS =
  0.45 × 围岩等级分量（grade_score_component）
+ 0.45 × 地质现象分量（hazard_component）
+ 0.10 × 置信度分量（confidence_component）
```

#### 5.7.1 围岩等级分量

| 围岩等级 | 关注分 |
|---|---:|
| Ⅰ | 0.05 |
| Ⅱ | 0.20 |
| Ⅲ | 0.40 |
| Ⅳ | 0.70 |
| Ⅴ | 1.00 |

#### 5.7.2 hazard 分量

单个 hazard 的贡献：

```text
hazard_contribution =
  hazard_weight × min(effective_weight, 1.5)
```

同一 hazard 多条证据使用 Noisy-OR 合成：

```text
combined_score =
  1 - ∏(1 - contribution_i)
```

hazard_component 综合主控和平均：

```text
hazard_component =
  0.75 × max(hazard_scores)
+ 0.25 × average(hazard_scores)
```

常见 hazard 权重示例：

| 中文 hazard | 英文字段 | 权重 |
|---|---|---:|
| 出水 | water | 0.35 |
| 突涌水 | water_inrush | 0.45 |
| 塌方 | collapse | 0.40 |
| 掉块 | block_fall | 0.35 |
| 变形 | deformation | 0.30 |
| 围岩破碎 | fractured_rock | 0.30 |
| 围岩极破碎 | extremely_fractured_rock | 0.40 |
| 裂隙密集 | dense_joints | 0.35 |
| 强反射异常 | strong_reflection_anomaly | 0.35 |

#### 5.7.3 置信度分量

置信度大致考虑：

```text
证据总权重越高，置信度越高；
证据条数越多，置信度越高；
来源类型越多，置信度越高；
冲突越大，置信度越低。
```

简化表达：

```text
confidence_score =
  weight_factor
  × evidence_factor
  × source_factor
  × conflict_penalty
```

其中：

```text
weight_factor = 1 - exp(-total_weight / 3)
evidence_factor = min(1, 0.50 + 0.10 × evidence_count)
source_factor = min(1, 0.70 + 0.15 × max(source_type_count - 1, 0))
conflict_penalty = 1 - 0.35 × conflict_score
```

---

## 6. 三类 cell 角色与证据边界

这是项目最重要的 idea 之一。

### 6.1 为什么要分角色

同样是地质证据，处在不同位置时语义不同：

- 当日已掘范围内，可以和 PLC 响应复核；
- 当前掌子面前方，只能作为前方关注提示；
- 当前范围附近背景，只能作为上下文。

如果不分角色，报告会出现典型错误：

```text
把前方预报写成已发生事实；
把背景地质写成当日结论；
把 GRCI 写成前方风险；
把 PLC 已掘响应写成前方地质证明。
```

### 6.2 三类角色定义

| 中文角色 | 英文字段 | 可用证据 | 可写内容 | 禁止内容 |
|---|---|---|---|---|
| 已掘复核 | daily_review | PLC、RAI、地质、GRS、GRCI | 已掘区段复核 | 前方预测 |
| 前方关注 | forward_attention | 地质 GRS、hazard、source_trace、距离 | 前方关注提示 | PLC、RAI、GRCI |
| 局部背景 | local_background | 背景地质证据 | 背景说明 | 当日强结论 |

### 6.3 前方距离分层

前方关注范围默认 30m，按 10m 分段：

| 距离 | 中文分层 | 英文字段 | 权重 |
|---|---|---|---:|
| 0-10m | 近前方 | near_forward | 1.0 |
| 10-20m | 短前方 | short_forward | 0.7 |
| 20-30m | 扩展前方 | extended_forward | 0.4 |

这个权重用于 Evidence Pack 选择，不是风险概率。

---

## 7. GRCI：地质-施工响应耦合关注度

GRCI 只在已掘复核单元中计算。

### 7.1 可用条件

```text
cell_role = daily_review
AND has_plc_response = True
AND RAI 存在
AND GRS 可用
AND has_geology_evidence = True
```

如果缺少 PLC 响应：

```text
GRCI = None
GRCI_available = False
GRCI_unavailable_reason = missing_plc_response
```

如果缺少地质证据：

```text
GRCI = None
GRCI_available = False
GRCI_unavailable_reason = missing_geology_evidence
```

### 7.2 公式

```text
GRCI =
  0.55 × GRS
+ 0.35 × RAI
+ 0.10 × GRS × RAI
```

分项：

```text
地质项（grs_term） = 0.55 × GRS
响应项（rai_term） = 0.35 × RAI
交互项（interaction_term） = 0.10 × GRS × RAI
```

### 7.3 等级

| GRCI 范围 | 中文等级 | 英文等级 |
|---|---|---|
| >= 0.75 | 高关注 | high |
| 0.50-0.75 | 中关注 | medium |
| 0.25-0.50 | 低关注 | low |
| < 0.25 | 无明显关注 | none |

### 7.4 不能误解

GRCI 不是：

- 灾害概率；
- 风险概率；
- 前方风险；
- 施工异常原因；
- 地质真实状态。

GRCI 是：

> 已掘复核范围内，地质证据关注和施工响应关注是否在同一 cell 中共同出现的启发式关注指标。

---

## 8. ConstructionStateCell：统一状态单元

施工状态单元（ConstructionStateCell）是所有证据的汇合点。

### 8.1 一个 cell 包含什么

```text
施工状态单元 ConstructionStateCell
│
├─ 位置状态
│   ├─ cell 起点 / 终点 / 中心
│   ├─ 是否当日已掘
│   ├─ 是否当前掌子面 cell
│   └─ 是否前方 cell
│
├─ PLC 响应状态
│   ├─ 基础速度 / 推力 / 扭矩
│   ├─ RAI 及分量
│   ├─ working-only 指标
│   └─ steady-state 指标
│
├─ 地质状态
│   ├─ GRS 及分量
│   ├─ 围岩等级
│   ├─ hazard_scores
│   └─ source_trace
│
├─ 耦合状态
│   ├─ GRCI
│   ├─ GRCI_available
│   └─ coupling_explanation
│
└─ 证据治理状态
    ├─ cell_role
    ├─ trace_completeness
    ├─ selection_score
    └─ warnings
```

### 8.2 cell 的理论意义

这个对象解决一个问题：

> PLC 是时间序列，地质证据是里程区段，报告是自然语言。三者需要一个共同载体。

10m cell 就是这个共同载体。

---

## 9. DailyConstructionTwin：日报前的结构化底座

DailyConstructionTwin 不是仿真，而是结构化证据底座。

```text
DailyConstructionTwin
│
├─ 范围 scope
│   ├─ daily_plc_range
│   ├─ daily_excavated_scope
│   ├─ current_chainage
│   ├─ forward_scope
│   └─ local_background_scope
│
├─ cell 集合
│   ├─ daily_review_cells
│   ├─ forward_attention_cells
│   └─ local_background_cells
│
├─ 高关注复核
│   └─ high_grci_cells
│
├─ 摘要 summaries
│   ├─ operation_summary
│   ├─ response_summary
│   ├─ geology_summary
│   ├─ gas_summary
│   └─ coupling_summary
│
├─ 追踪 trace_index
└─ 治理 governance
```

它的作用是让报告生成前，系统已经知道：

- 每个证据属于哪个 cell；
- 每个 cell 属于哪个角色；
- 哪些指标可用；
- 哪些话不能写；
- 每个结论可以追踪到哪里。

---

## 10. Evidence Pack：大模型能看到的证据边界

Evidence Pack 是报告生成输入，不是普通 prompt。

### 10.1 Evidence Pack 的分层

| 中文层 | 英文字段 | 作用 |
|---|---|---|
| 运行证据 | operation_evidence | 当日施工运行概况 |
| 气体证据 | gas_evidence | 气体监测统计 |
| 地质证据 | geology_evidence | key cells、已掘/前方/背景地质证据 |
| 已掘复核证据 | daily_review_evidence | 可使用 GRCI 的复核 cell |
| 前方关注证据 | forward_attention_evidence | 只能使用 GRS/source_trace 的前方提示 |
| 背景证据 | background_context_evidence | 只作上下文 |
| 耦合证据 | coupling_evidence | high_grci_cells 和耦合说明 |
| 质量证据 | quality_evidence | 质量检查信息 |
| 来源追踪 | source_trace | 证据来源 |
| 生成约束 | generation_constraints | 禁止和推荐表达 |

### 10.2 cell 选择分

Evidence Pack 不会无限放入所有 cell，而是按选择分排序。

#### 已掘复核 cell 选择分

```text
daily_review_selection_score =
  0.40 × GRCI
+ 0.25 × RAI
+ 0.25 × GRS
+ 0.10 × trace_completeness
```

缺失项会按可用项重新归一化。

#### 前方关注 cell 选择分

```text
forward_attention_selection_score =
  0.45 × GRS
+ 0.25 × forward_distance_weight
+ 0.20 × evidence_confidence
+ 0.10 × trace_completeness
```

注意：前方选择分不使用 GRCI。

#### 局部背景 cell 选择分

```text
local_background_selection_score =
  0.50 × GRS
+ 0.25 × evidence_confidence
+ 0.25 × trace_completeness
```

### 10.3 Evidence Pack 的理论作用

Evidence Pack 的理论作用有三个：

1. **压缩证据**：不把所有原始数据交给 LLM；
2. **分配角色**：已掘、前方、背景分开；
3. **约束表达**：告诉模型哪些不能说。

---

## 11. 报告生成与自动修订

### 11.1 五种生成模式的逻辑

| 模式 | 中文名 | 输入 | 理论目的 |
|---|---|---|---|
| M0 | 模板生成 | 结构化证据 | 稳定基线 |
| M1 | 直接 LLM | 少量基础信息 | 检验自由生成风险 |
| M2 | 原始证据 LLM | 原始摘要证据 | 检验“给材料”是否足够 |
| M3 | Twin 证据包 LLM | 结构化 Evidence Pack | 检验证据组织作用 |
| M4 | 完整闭环 | Evidence Pack + 检查 + 修订 | 检验证据约束闭环 |

M1 → M2 → M3 → M4 是递进式消融：

```text
直接生成
│
├─ 增加原始证据
├─ 增加结构化证据包
├─ 增加边界治理
├─ 增加质量/追踪检查
└─ 增加自动修订
```

### 11.2 M4 闭环流程

```text
Evidence Pack
│
▼
生成初稿
│
▼
质量检查
├─ 章节缺失
├─ unsupported claim
├─ numeric error
├─ E14 对齐范围误用
└─ boundary violation
│
▼
形成反馈
│
▼
大模型修订
│
▼
章节保护
│
▼
最终报告
```

M4 的关键不是“提示词更长”，而是报告生成后有反馈和修订。

---

## 12. 质量、追踪和边界检查

### 12.1 质量分

质量分从 100 分开始扣。

| 检查项 | 扣分 |
|---|---:|
| 严重错误 | 至少 15 |
| warning | 至少 5 |
| 缺少标准章节 | 每章 3 |
| grounding_rate < 0.8 | 至少 10 |
| grounding_rate < 0.6 | 20 |

标准章节包括：

1. 综合摘要；
2. 总体概况；
3. 工况统计；
4. 聚类状态与效率分析；
5. 掌子面与地质揭示；
6. 已掘区段地质-施工响应复核；
7. 气体监测；
8. 前方地质关注提示；
9. 结论与施工建议。

### 12.2 证据支撑率

证据支撑率（grounding_rate）：

```text
grounding_rate =
  有证据支撑的 claim 数 / 可检查 claim 总数
```

无证据主张（unsupported claim）不是说句子一定错，而是表示系统没有在 Evidence Pack / Twin / trace 中找到足够支撑。

### 12.3 数值语义错误

典型数值错误包括：

| 错误 | 说明 |
|---|---|
| 对齐范围误写为实际推进范围 | 把 daily_excavated_scope 写成实际推进 |
| 自行计算日进尺 | 用 10m 对齐范围推导 20m 推进 |
| 数值无来源 | 报告出现 Evidence Pack 中没有的数值 |

E14 专门检查：

```text
把 10m cell 对齐后的已掘复核范围写成实际推进范围或日推进量
```

### 12.4 边界违规

| 边界错误 | 含义 |
|---|---|
| GRCI 概率化 | 把 GRCI 写成灾害概率或风险概率 |
| 前方事实化 | 把前方关注写成已发生事实 |
| PLC 前方泄漏 | 用已掘 PLC 证明前方异常 |
| proxy 物理化 | 把 proxy 写成真实功率/比能 |
| 停机因果化 | 把 stop_ratio 直接写成异常原因 |
| 背景当日化 | 把 local_background 写成当日结论 |

---

## 13. Exp02 实验逻辑

Exp02 验证的是：

> 为什么不能直接让 LLM 写日报，为什么 Evidence Pack + 边界约束 + 自动修订更可靠。

91 天真实 LLM 实验的结论可以概括为：

| 结论 | 含义 |
|---|---|
| M4 综合质量最高 | 完整闭环优于直接生成和只给原始证据 |
| M4 证据支撑率最高 | Evidence Pack 和 Trace 有效 |
| M4 unsupported 更少 | 修订减少无支撑表达 |
| M4 numeric 更少 | 数值语义约束有效 |
| M4 E14 为 0 | 对齐范围没有被误写为实际推进 |
| M4 缺章为 0 | 章节保护有效 |

这个实验能证明的是本工程内的生成模式对比，不证明跨工程泛化。

---

## 14. Exp03 指标稳健性逻辑

Exp03 针对 RAI/GRS/GRCI 的主观权重问题。

它不改变主流程，只旁路复算不同版本：

| 版本 | 思想 |
|---|---|
| V0 当前公式 | 原 RAI/GRS/GRCI |
| V1 分位数等权 | 消除量纲后等权组合 |
| V2 分位数交互 | sqrt(RAI × GRS) |
| V3 熵权 | 用指标信息熵决定权重 |
| V4 CRITIC | 用标准差和相关性决定权重 |
| V5 严格最小值 | min(RAI, GRS) |

比较方法：

- Top-10 / Top-20 / Top-50 high GRCI cell 重合；
- Jaccard 相似度；
- Spearman 排名相关；
- 高关注日期是否稳定；
- forward_attention 是否误用 GRCI。

Exp03 的作用是回应：

> 当前启发式公式的排序是否对权重过度敏感？

---

## 15. 论文里可以讲的创新

### 15.1 证据治理先于生成

不是把原始 PLC 和地质文本直接交给 LLM，而是先做时间、空间、角色、指标和 trace 治理。

### 15.2 统一里程单元表达

PLC 是时间序列，地质是里程证据，报告是文本。项目用 10m cell 把三者统一。

### 15.3 已掘复核和前方提示分离

这是防止报告越界的核心设计。

### 15.4 指标可追溯

RAI、GRS、GRCI 都有分量、公式、可用性条件和边界。

### 15.5 LLM 受控生成

LLM 不是判断器，而是基于 Evidence Pack 的表达和修订工具。

### 15.6 自动校核闭环

报告不是生成即结束，而是要经过 Quality / Trace / Boundary 检查。

---

## 16. 当前方法的薄弱点

| 薄弱点 | 说明 | 应对 |
|---|---|---|
| RAI/GRS/GRCI 是启发式 | 权重未由标签标定 | Exp03 稳健性分析 |
| PLC 稳态识别是规则式 | 不是监督学习分类 | 写成 preprocessing，不写成预测模型 |
| 停机原因不清 | 计划/非计划停机难区分 | stop_ratio 只作关注信号 |
| 地质证据结构化依赖原 evidence_db | 文本抽取错误会影响后续 | P3 仍为候选旁路 |
| 自动 checker 有误伤 | 不能替代人工 | 后续人工复核 |
| 单工程验证 | 不能直接跨工程推广 | 论文限定研究范围 |
| proxy 指标物理含义有限 | 单位和物理量不完整 | 全部保留 proxy 表述 |

---

## 17. 最终安全表述

推荐总表述：

> 本研究提出一种面向 TBM 施工日报的多源证据治理与大模型受控生成方法。方法以 10m 里程单元为载体，先对 PLC 施工响应和多源地质证据进行清洗、筛选、投影和融合，再构建已掘复核、前方关注和局部背景三类证据角色。在此基础上，构建 RAI、GRS 和 GRCI 等启发式关注指标，用于表达施工响应、地质证据和已掘区段地质-施工响应耦合关注程度。报告生成阶段，大模型仅消费 Evidence Pack，并通过质量检查、证据追踪和边界检查进行反馈修订。实验结果表明，在本工程可用日期范围内，完整证据约束与自动修订方法较直接大模型生成具有更好的证据支撑性、章节完整性和边界安全性。

不推荐表述：

```text
系统预测地质灾害概率。
GRCI 表示风险概率。
PLC 指标证明前方地质异常。
LLM 自动判断施工风险。
```

