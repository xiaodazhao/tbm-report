# 最终版方法框架

## 1. 文档定位

这份文档描述的是项目最适合收敛成的正式方法框架。它不是功能清单，而是：

- 当前代码主线应该如何被研究化表述
- `Construction State Twin` 在方法中的中心位置
- 三个核心指标在 Twin 中的角色
- LLM、报告、追溯、Agent 如何围绕同一状态层组织

## 2. 三个主贡献

为了避免主线过大，最终建议只保留三个主贡献。

### Contribution 1

提出 `Construction State Twin`，用于将 TBM 多源施工数据统一表示为可递推更新的状态体。

### Contribution 2

设计 `GRS / RAI / GRCI` 三类状态指标，实现地质关注、施工响应异常和地质-施工耦合关注的状态化表达。

### Contribution 3

提出 `State-aware Prompting` 与 `Traceability Evaluation`，使 LLM 报告生成具备事实约束、风险措辞约束和证据可追溯性。

说明：

- `Agent` 不作为主贡献
- `Agent` 在方法中更适合作为 `an interactive extension of CST`

## 3. 核心主张

最终版方法不再理解为：

`CSV + PDF -> Prompt -> LLM`

而是：

`Raw Data -> Structured Evidence -> Construction State Twin -> State-Aware Prompt -> Traceable Report`

也就是说，LLM 不是直接面向原始工程数据，而是面向由状态组织、时空对齐和证据约束后的中间状态表示。

## 4. 方法总框架

\[
Raw\ Data_t \rightarrow Structured\ Evidence_t \rightarrow CST_t \rightarrow Prompt_t \rightarrow Report_t
\]

其中：

\[
CST_t = \mathcal{U}(CST_{t-1}, PLC_t, Geo_t, Face_t, Gas_t)
\]

这里：

- `CST_{t-1}`：上一状态
- `PLC_t`：当前 TBM 运行数据
- `Geo_t`：当前超前地质证据
- `Face_t`：当前掌子面证据
- `Gas_t`：当前安全监测数据
- `U`：状态更新算子

## 5. 当前已实现版本与理想版本

### 当前已实现

当前代码已经实现：

- 正式 `CST schema`
- 主链产出 `cst_state`
- `SQLite` 持久化
- 基于 `t-1` 的结构化递推更新
- `changed_fields / state_confidence / state_stability`
- `persistent_hazards / persistent_attention_segments`
- `CST` 驱动的 prompt 生成

### 理想增强版

后续仍可继续增强：

- 更重的动态状态空间模型
- 更强的状态衰减和平滑
- 更彻底的 `CST-only` 下游读取链
- 更强的动态更新实验

## 6. Twin 的分层定义

推荐统一使用以下分层状态体。

### 6.1 Temporal State

- 分析日期 / 时间窗
- 持续时长
- 样本数
- `analysis_mode`
- `previous_date`
- `continuity_gap_days`
- `state_stability`

### 6.2 Spatial State

- 起止里程
- 当前掌子面里程
- 推进长度
- 前方关注窗口
- 前方关注等级
- 与上一状态的里程变化

### 6.3 Operation State

- 主导工况
- 工作时长
- 停机时长
- 状态切换次数
- 效率摘要
- 上一工况
- 工况时长变化

### 6.4 Geological State

- 当前掌子面条件
- 区段围岩等级
- 灾害标签
- 证据数量
- 不确定性
- 持续地质关注

### 6.5 Response State

- `RAI`
- 异常类型
- 关键异常参数
- `RAI_delta`

### 6.6 Attention State

- `GRS`
- `GRCI`
- 高关注区段
- 前方关注
- 持续关注区段
- `GRS_delta`
- `GRCI_delta`
- `trend_label`

### 6.7 Provenance State

- 证据列表
- 状态更新来源
- 上一状态变化摘要
- lineage
- changed fields
- state confidence

## 7. 三个指标在 Twin 中的位置

### 7.1 GRS

`GRS` 在论文中建议解释为：

`Geological Attention Score`

它不预测地质灾害真值，而是将已有多源地质证据压缩为 Twin 内部的关注状态。

### 7.2 RAI

`RAI` 用于表达施工响应异常状态，当前以 `Isolation Forest` 为核心，并对常规环级停顿进行折减。

### 7.3 GRCI

`GRCI` 用于表达地质关注和施工响应之间的同步、滞后与变化耦合关系，是 Twin 内部的交叉验证状态。

## 8. State-Aware Prompt 的正式定义

建议将 Prompt 形式化为：

\[
Prompt_t = \{Role\ Instruction,\ CST\ Summary,\ Writing\ Constraints,\ Output\ Schema\}
\]

### Role Instruction

指定模型身份和任务边界。

### CST Summary

从 `CST_t` 中抽取与当前报告最相关的状态摘要。

### Writing Constraints

至少包含：

1. Only describe the specified date or time window.
2. Separate current face observations from forward geological predictions.
3. Use cautious wording for risk-related descriptions.
4. Do not claim unsupported hazards.
5. Every key conclusion should be traceable to the provided CST evidence.

### Output Schema

约束正式报告章节结构。

## 9. 下游任务的统一解码

最终版方法建议将不同任务统一看作对 `CST_t` 的不同读取方式：

- `Report_t = G(CST_t)`
- `Forward_t = F(CST_t)`
- `Compare_t = H(CST_t, CST_{t-1})`
- `Answer_t = Q(CST_t, Query_t, Memory_t)`
- `Trace_t = T(CST_t, Claims_t)`

这意味着报告、前方提示、历史对比、Agent 和追溯都建立在同一状态层之上。

## 10. 当前最接近完全体的位置

当前项目已经从“分析模块集合”升级成：

- 正式状态对象
- 状态递推更新
- 状态持久化
- 状态驱动 prompt
- 状态驱动实验

如果继续增强，最值得优先投入的是：

1. 更彻底的 `CST-only` 下游读取
2. 更强的动态更新实验
3. 更重的状态空间建模

## 11. 一句话总结

最适合这套项目的最终方法表述是：

**通过统一里程轴将 TBM 多源施工数据组织成可递推更新的 Construction State Twin，并在此基础上构造 State-aware Prompt，驱动大语言模型生成可追溯、受约束的施工报告。**
