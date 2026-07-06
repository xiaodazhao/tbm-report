# 论文方法理论增强补充稿

> 用途：本文件用于补强现有论文初稿中“方法论不够细、公式不够多、PLC 处理不够理论化、LLM 链路不够分层”的问题。  
> 建议用法：将本文中的第 1-7 节分别合并到论文第 3 章“方法”和第 4 章“实验设置与评价指标”中。  
> 约束：本文只基于当前项目真实实现撰写，不引入未实现的新算法，不把 RAI/GRS/GRCI 写成灾害概率，不把 LLM 写成地质风险判断器。

---

## 1 方法总体理论定位：从“日报生成”改写为“证据治理型施工状态孪生 + 可追溯知识生成”

现有论文表述如果只写“TBM 施工日报自动生成”，容易让读者误解为一个普通文本生成任务。更准确的理论定位应是：

> 本文研究对象不是自由文本生成，而是多源工程证据约束下的 TBM 施工可信知识生成。施工日报只是该可信知识生成框架的一个验证场景和主要输出形式。

因此，本文方法可以抽象为六层结构：

```text
--------------------------------------------------------------------------------+
| 第 6 层：可追溯生成与审计层                                                     |
| LLM 生成、结构化追踪、质量检查、边界检查、反馈修订                              |
+-----------------------------------------▲--------------------------------------+
                                          |
+-----------------------------------------|--------------------------------------+
| 第 5 层：Evidence Pack 证据包层                                                 |
| 角色化证据选择、key cells、source trace、generation constraints                |
+-----------------------------------------▲--------------------------------------+
                                          |
+-----------------------------------------|--------------------------------------+
| 第 4 层：DailyConstructionTwin 日施工状态孪生层                                  |
| scope、cells、daily_review、forward_attention、local_background、governance     |
+-----------------------------------------▲--------------------------------------+
                                          |
+-----------------------------------------|--------------------------------------+
| 第 3 层：ConstructionStateCell 施工状态单元层                                    |
| 位置状态、施工响应、地质状态、气体状态、耦合状态、质量状态、追踪状态             |
+----------------------▲--------------------------------▲------------------------+
                       |                                |
+----------------------|-------------------+  +---------|--------------------------+
| 第 2A 层：PLC 施工响应证据层          |  | 第 2B 层：地质证据治理层             |
| 停机识别、异常点过滤、有效掘进、稳态段 |  | 时间可用、空间相关、角色分层         |
+----------------------▲-------------------+  +---------▲--------------------------+
                       |                                |
+----------------------|--------------------------------|-------------------------+
| 第 1 层：原始数据层                                                           |
| PLC 日运行 CSV、正式 evidence_db、TSP/HSP/掌子面素描/气体监测等                |
+--------------------------------------------------------------------------------+
```

该六层结构的理论意义在于：  

1. **将原始数据转化为可生成证据**：原始 PLC 和地质资料并不直接进入 LLM，而是先被整理成可解释、可追踪、可约束的证据对象。  
2. **将施工状态从文本问题前移为结构化问题**：日报生成前先构建 `ConstructionStateCell` 和 `DailyConstructionTwin`，使 LLM 面对的是状态对象，而不是杂乱数据。  
3. **将 LLM 从判断器降级为受控表达器**：LLM 不负责计算 RAI/GRS/GRCI，不判断地质风险，只负责在 Evidence Pack 约束下组织和修订文本。  
4. **将报告质量评价从主观阅读转化为 claim-level 审计**：系统将报告拆分为主张，逐条检查证据支撑、数值一致性和边界合规性。

---

## 2 PLC 施工响应证据构建：从原始样本到稳态 cell 指标

### 2.1 PLC 数据处理的理论目标

PLC 日运行数据具有高频、噪声、停机、换步、辅助作业和短时扰动混杂的特点。若直接对全样本计算日均值，会把停机样本和过渡样本混入施工响应指标，导致推进速度、推力、扭矩、贯入度等变量失真。因此，本文将 PLC 处理目标定义为：

> 在不构建预测模型的前提下，从原始 PLC 样本中提取已掘区段内可解释、可追踪、可写入日报的施工响应证据。

这里的“施工响应证据”不是地质风险结论，而是设备在已掘区段中的运行表现。例如，推力波动、扭矩波动、有效掘进样本比例、稳态段负载 proxy 等只能说明施工响应状态，不能单独证明前方地质异常。

### 2.2 PLC 样本向量定义

对施工日期 \(d\)，设原始 PLC 样本序列为：

\[
P_d=\{p_i\}_{i=1}^{N_d}
\]

其中第 \(i\) 条样本可表示为：

\[
p_i=(t_i,m_i,v_i,F_i,T_i,\omega_i,q_i,s_i,\mathbf{g}_i)
\]

各变量含义如下：

| 符号 | 中文含义 | 项目字段/英文名 | 说明 |
|---|---|---|---|
| \(t_i\) | 运行时间 | 运行时间-time (`time`) | 用于排序、时间间隔和运行时长统计 |
| \(m_i\) | 里程 | 导向盾首里程 / chainage (`chainage`) | 用于投影到 10 m cell |
| \(v_i\) | 推进速度 | 推进速度 (`advance_speed`) | 稳态段优先检测信号 |
| \(F_i\) | 推力 | 推力 (`thrust`) | 停机识别、负载统计 |
| \(T_i\) | 刀盘扭矩 | 刀盘扭矩 (`torque`) | 停机识别、负载统计 |
| \(\omega_i\) | 刀盘实际转速 | 刀盘实际转速 (`rpm`) | 有效掘进判定、功率 proxy |
| \(q_i\) | 贯入度 | 贯入度 (`penetration`) | 贯入效率 proxy，不作为严格 penetration rate |
| \(s_i\) | 掘进状态 | 掘进状态 (`is_working` 派生) | 若存在则参与有效样本判定 |
| \(\mathbf{g}_i\) | 气体监测变量 | CO2/H2S/SO2/NO2/NO/CH4 等 | 用于气体监测分析 |

### 2.3 时间和里程质量检查

时间和里程质量检查用于保证样本顺序和空间投影可信。

#### 2.3.1 时间间隔检查

对相邻样本计算时间间隔：

\[
\Delta t_i=t_i-t_{i-1}
\]

取正时间间隔的中位数：

\[
\widetilde{\Delta t}=\operatorname{median}(\Delta t_i|\Delta t_i>0)
\]

时间跳变阈值定义为：

\[
\tau_t=\max(3\widetilde{\Delta t},10)
\]

若：

\[
\Delta t_i>\tau_t
\]

则标记为时间间隔异常 (`time_gap`)。该标记不直接删除样本，但会触发连续有效掘进区间切分。

#### 2.3.2 里程反向与跳变检查

对相邻样本计算里程增量：

\[
\Delta m_i=m_i-m_{i-1}
\]

当前项目采用：

\[
\epsilon_m=0.01,\quad J_m=5.0
\]

若：

\[
\Delta m_i<-\epsilon_m
\]

则标记为里程反向 (`chainage_reverse`)；若：

\[
|\Delta m_i|>J_m
\]

则标记为里程跳变 (`chainage_jump`)。

里程有效性可表示为：

\[
chainage\_valid_i = \neg chainage\_reverse_i \land (m_i \neq null)
\]

该步骤的理论作用是防止同一日样本被错误投影到不连续或反向的里程单元中。

### 2.4 停机与辅助停机识别

参考 TBM 运行参数研究中“先剔除停机段再分析工作段”的思想，本文用推力和刀盘扭矩识别主停机样本。

设：

\[
\epsilon_F=0,\quad \epsilon_T=0
\]

则停机标记为：

\[
shutdown_i=(F_i\le \epsilon_F)\lor(T_i\le \epsilon_T)
\]

同时，使用推进速度和刀盘转速识别辅助停机或非有效掘进状态：

\[
auxiliary\_shutdown_i=(v_i\le \epsilon_v)\lor(\omega_i\le \epsilon_\omega)
\]

当前实现中：

\[
\epsilon_v=0,\quad \epsilon_\omega=0
\]

需要强调的是，PLC 字段当前不能可靠区分“计划停机”和“非计划停机”。因此：

```text
stop_ratio 只能解释为施工响应关注信号；
不能直接解释为异常停机原因；
不能作为地质异常或设备故障的因果证据。
```

### 2.5 非停机样本 3σ 异常点过滤

异常点过滤仅在非停机样本集合上进行。对核心参数：

\[
x\in\{v,F,T,\omega,q\}
\]

在非停机样本中计算均值和标准差：

\[
\mu_x=\frac{1}{n}\sum x_i,\quad
\sigma_x=\sqrt{\frac{1}{n-1}\sum(x_i-\mu_x)^2}
\]

若有效样本数小于：

\[
n<30
\]

则跳过该字段的 3σ 过滤，避免小样本下误判。

否则，异常点判定为：

\[
outlier_{i,x} =
\begin{cases}
1, & x_i<\mu_x-3\sigma_x\ \text{or}\ x_i>\mu_x+3\sigma_x\\
0, & otherwise
\end{cases}
\]

样本级异常标记为：

\[
outlier_i=\bigvee_x outlier_{i,x}
\]

该步骤只用于识别统计异常点，不解释为工程异常原因或地质异常。

### 2.6 有效掘进样本识别

有效掘进样本是后续 working-only 和 steady-state 指标的基础。当前项目的有效掘进判定可写为：

\[
\begin{aligned}
valid_i = &\neg shutdown_i \land \neg outlier_i \land chainage\_valid_i \\
&\land (F_i>\epsilon_F) \land (T_i>\epsilon_T) \\
&\land (v_i>\epsilon_v \ \text{if}\ v_i\ \text{available}) \\
&\land (\omega_i>\epsilon_\omega \ \text{if}\ \omega_i\ \text{available}) \\
&\land (is\_working_i=True \ \text{if existing})
\end{aligned}
\]

该公式比简单的“推进速度 > 0、推力 > 0、扭矩 > 0、转速 > 0”更严格，因为它同时排除了停机段、异常点、里程无效样本和非工作状态样本。

### 2.7 连续有效掘进区间切分

有效样本集合仍可能由多个短时区间组成，因此需要切分连续有效掘进区间。对样本 \(i\)，当满足以下任一条件时开启新区间：

\[
new\_interval_i =
\neg valid_{i-1}
\lor time\_gap_i
\lor chainage\_reverse_i
\]

每个连续区间 \(I_k\) 的样本数和持续时间为：

\[
n_k=|I_k|,\quad D_k=\sum_{i\in I_k}\Delta t_i
\]

当前项目采用：

\[
n_k\ge 20,\quad D_k\ge 30s
\]

作为有效工作区间的最低要求。否则，该区间被标记为短过渡区间 (`short_transition_interval`)。

### 2.8 稳态段识别

稳态段识别用于从有效工作区间中提取相对稳定的施工响应片段。当前项目优先使用推进速度作为稳态检测信号：

\[
y_i=v_i
\]

若推进速度不可用，则使用贯入度字段作为 fallback：

\[
y_i=q_i
\]

但该 fallback 被明确标记为：

```text
penetration_value_fallback_not_rate
```

即它不是严格 penetration rate，只是稳态切分的备用单调信号。

对每个有效工作区间，计算滚动均值：

\[
\bar{y}^{(w)}_i=\frac{1}{w}\sum_{j=i-w+1}^{i}y_j
\]

其中：

\[
w=20,\quad min\_periods=5
\]

稳态候选阈值为：

\[
\theta_y=0.8\cdot median(\bar{y}^{(w)}_i)
\]

稳态候选样本为：

\[
steady\_candidate_i=
\begin{cases}
1, & \bar{y}^{(w)}_i\ge \theta_y\\
0, & otherwise
\end{cases}
\]

若存在多个候选连续段，则按以下优先级选择稳态段：

```text
1. 样本数最多；
2. 持续时间最长；
3. 里程长度最大；
4. 出现时间最早。
```

稳态段最低要求为：

\[
n_{steady}\ge 20,\quad D_{steady}\ge 30s
\]

若无法获得满足要求的稳态段，但有效工作样本充足，则使用 working-only fallback，并标记 `steady_state_fallback_used=True`。

### 2.9 10 m cell 稳态施工响应指标

设第 \(c\) 个 10 m 单元为：

\[
C_c=[a_c,b_c),\quad b_c-a_c=10m
\]

属于该 cell 的样本集合为：

\[
P_c=\{p_i|m_i\in C_c\}
\]

有效掘进样本集合：

\[
W_c=\{p_i\in P_c|valid_i=1\}
\]

稳态样本集合：

\[
S_c=\{p_i\in P_c|paper\_plc\_stage_i=steady\_state\}
\]

主要覆盖指标为：

\[
working\_ratio_c=\frac{|W_c|}{|P_c|}
\]

\[
steady\_ratio_c=\frac{|S_c|}{|P_c|}
\]

\[
steady\_to\_working\_ratio_c=\frac{|S_c|}{|W_c|}
\]

对任一参数 \(x\in\{v,F,T,\omega,q\}\)，稳态均值、标准差和变异系数为：

\[
\mu_{c,x}=\frac{1}{|S_c|}\sum_{p_i\in S_c}x_i
\]

\[
\sigma_{c,x}=\sqrt{\frac{1}{|S_c|-1}\sum_{p_i\in S_c}(x_i-\mu_{c,x})^2}
\]

\[
CV_{c,x}=
\begin{cases}
\frac{\sigma_{c,x}}{|\mu_{c,x}|}, & |\mu_{c,x}|>\epsilon\\
null, & otherwise
\end{cases}
\]

其中：

\[
\epsilon=10^{-6}
\]

负载-贯入关系 proxy 为：

\[
power\_proxy_c=\mu_{c,T}\cdot \mu_{c,\omega}
\]

\[
thrust\_per\_penetration_c=
\frac{\mu_{c,F}}{\mu_{c,q}},\quad \mu_{c,q}>\epsilon
\]

\[
torque\_per\_penetration_c=
\frac{\mu_{c,T}}{\mu_{c,q}},\quad \mu_{c,q}>\epsilon
\]

这些指标必须写成 proxy，不能写成严格物理功率或严格比能。其论文表述建议为：

> 在 10 m 里程单元内区分有效掘进样本与停机/过渡样本，并在稳态段提取负载、波动、贯入效率及负载-贯入关系 proxy，用于构造可追溯的施工响应证据。

### 2.10 PLC 预处理质量等级

为避免所有 cell 被同等解释，本文对 PLC 预处理质量进行等级标记：

| 等级 | 判定条件 | 解释 |
|---|---|---|
| A | 有稳态段，稳态样本数 ≥ 50，稳态/工作样本比例 ≥ 0.5，速度/推力/扭矩均可用 | 施工响应证据质量较高 |
| B | 有稳态段，稳态样本数 ≥ 20，核心指标至少两项可用 | 施工响应证据基本可用 |
| C | 无稳态段，但 working-only fallback 可用且工作样本数 ≥ 20 | 仅作为降级施工响应证据 |
| D | 其他情况 | 施工响应证据不足 |

该等级只表示 PLC response evidence 的可用性，不表示地质风险等级。

---

## 3 地质证据治理：时间可用、空间相关与角色边界

### 3.1 地质证据对象定义

对施工日期 \(d\)，地质证据集合为：

\[
G_{\le d}=\{g_j|t_j\le d\}
\]

每条证据可表示为：

\[
g_j=(id_j,type_j,t_j,[s_j,e_j],text_j,conf_j)
\]

其中：

| 符号 | 中文含义 | 字段示例 |
|---|---|---|
| \(id_j\) | 证据编号 | `evidence_id` |
| \(type_j\) | 证据类型 | TSP/HSP/掌子面素描 |
| \(t_j\) | 证据可用时间 | 发布日期/记录日期 |
| \([s_j,e_j]\) | 证据空间范围 | 起止里程 |
| \(text_j\) | 原始文本 | 地质描述 |
| \(conf_j\) | 可信度 | evidence_confidence/source_reliability |

时间可用约束为：

\[
time\_valid(g_j,d)=
\begin{cases}
1, & t_j\le d\\
0, & t_j>d
\end{cases}
\]

该约束用于避免未来信息泄漏。

### 3.2 日报局部空间范围

给定当日 PLC 实测推进范围：

\[
[m_{min},m_{max}]
\]

当日实际推进量为：

\[
advance_d=m_{max}-m_{min}
\]

为适配 10 m cell 建模，已掘复核范围对齐为：

\[
daily\_scope_d=
\left[
\left\lfloor \frac{m_{min}}{L}\right\rfloor L,
\left\lceil \frac{m_{max}}{L}\right\rceil L
\right]
\]

其中：

\[
L=10m
\]

需要特别强调：

```text
daily_plc_range 是 PLC 实测实际推进范围；
daily_advance_m 是 PLC 实测实际推进量；
daily_excavated_scope 是 10 m cell 对齐后的复核范围；
daily_excavated_scope 不能写成实际推进范围，也不能用于自行计算日进尺。
```

当前掌子面里程为：

\[
m_f
\]

前方关注范围为：

\[
forward\_scope=[m_f,m_f+30m]
\]

局部背景范围为掌子面后方一定距离内的背景区间，当前默认后退距离为：

\[
100m
\]

### 3.3 空间相关性与证据角色判定

证据区间 \([s_j,e_j]\) 与目标区间 \([a,b]\) 是否重叠可定义为：

\[
overlap(g_j,[a,b])=
\max(s_j,a)<\min(e_j,b)
\]

若证据为点证据，则按照点是否落入目标区间判断。

角色判定规则为：

\[
role(g_j)=
\begin{cases}
daily\_review, & overlap(g_j,daily\_scope_d)\\
forward\_attention, & overlap(g_j,forward\_scope_d)\\
local\_background, & overlap(g_j,local\_background\_scope_d)\\
excluded, & otherwise
\end{cases}
\]

在报告语义上：

| 角色 | 可写内容 | 不可写内容 |
|---|---|---|
| 已掘复核 (`daily_review`) | 当日已掘区段复核、地质-施工响应耦合关注 | 前方预测 |
| 前方关注 (`forward_attention`) | 当前掌子面前方关注提示 | 已发生事实、GRCI、PLC 响应 |
| 局部背景 (`local_background`) | 邻近地质上下文 | 当日结论、高 GRCI |
| 排除证据 (`excluded`) | 不进入日报主证据链 | 不得用于生成结论 |

### 3.4 证据与 cell 的重叠解释字段

对于证据 \(g_j=[s_j,e_j]\) 和 cell \(C_c=[a_c,b_c]\)，重叠长度可定义为：

\[
L_{j,c}=\max(0,\min(e_j,b_c)-\max(s_j,a_c))
\]

cell 内证据重叠比例可写为：

\[
R_{j,c}^{cell}=\frac{L_{j,c}}{b_c-a_c}
\]

如果需要按证据自身长度归一化，也可定义：

\[
R_{j,c}^{evidence}=\frac{L_{j,c}}{e_j-s_j}
\]

当前系统导出 `evidence_overlap_length`、`max_overlap_ratio`、`mean_overlap_ratio`、`evidence_count` 和 `source_type_distribution` 等字段。这些字段主要用于解释证据如何投影到 cell，不改变 RAI/GRS/GRCI 的默认语义。

---

## 4 ConstructionStateCell：施工状态单元的形式化表达

### 4.1 Cell 的状态向量

每个 10 m cell 可形式化为一个状态向量：

\[
C_c=(P_c,O_c,R_c,G_c,F_c,A_c,Q_c,T_c)
\]

其中：

| 分量 | 中文含义 | 主要内容 |
|---|---|---|
| \(P_c\) | 位置状态 (`position_state`) | 起止里程、中心里程、与掌子面距离、cell 角色 |
| \(O_c\) | 运行状态 (`operation_state`) | 运行模式、停机、异常、聚类状态 |
| \(R_c\) | 施工响应状态 (`response_state`) | PLC 指标、稳态指标、RAI |
| \(G_c\) | 地质状态 (`geology_state`) | 地质证据、GRS、hazards、source trace |
| \(F_c\) | 前方状态 (`forward_state`) | forward distance band、前方权重 |
| \(A_c\) | 气体状态 (`gas_state`) | 气体监测与告警上下文 |
| \(Q_c\) | 耦合状态 (`coupling_state`) | GRCI、耦合等级、可用性 |
| \(T_c\) | 追踪状态 (`trace_state`) | evidence ids、source_trace、trace completeness |

这种状态向量的意义在于：报告生成不再直接面对原始表格，而是面对统一时空单元上的状态对象。

### 4.2 Cell 角色

cell 角色由空间范围决定：

\[
role(C_c)=
\begin{cases}
daily\_review, & C_c \cap daily\_scope_d \neq \emptyset\\
forward\_attention, & C_c \cap forward\_scope_d \neq \emptyset\\
local\_background, & C_c \cap background\_scope_d \neq \emptyset\\
outside, & otherwise
\end{cases}
\]

该角色决定了哪些指标可以进入报告：

| 指标/证据 | daily_review | forward_attention | local_background |
|---|---:|---:|---:|
| PLC 稳态指标 | 可用 | 不可用 | 不作为结论 |
| RAI | 可用 | 不可用 | 不作为结论 |
| GRS | 可用 | 可用于关注提示 | 可作为背景 |
| GRCI | 可用 | 禁止 | 禁止 |
| source_trace | 可用 | 可用 | 可用 |
| 结论语气 | 复核 | 提示 | 背景 |

---

## 5 RAI、GRS、GRCI：启发式关注指标而非概率模型

### 5.1 RAI：施工响应关注度

RAI（Response Attention Index，施工响应关注度）用于描述已掘 cell 中 PLC 响应的异常关注程度。当前公式为：

\[
RAI =
0.40S+
0.25A+
0.20D+
0.10V_T+
0.05V_v
\]

其中：

| 符号 | 中文含义 | 字段 |
|---|---|---|
| \(S\) | 停机比例 | `stop_ratio` |
| \(A\) | 异常样本比例 | `abnormal_ratio` |
| \(D\) | 速度下降分数 | `speed_drop_score` |
| \(V_T\) | 扭矩波动分数 | `torque_volatility_score` |
| \(V_v\) | 速度波动分数 | `speed_volatility_score` |

各分量贡献为：

\[
stop\_component=0.40S
\]

\[
abnormal\_component=0.25A
\]

\[
speed\_drop\_component=0.20D
\]

\[
torque\_component=0.10V_T
\]

\[
speed\_volatility\_component=0.05V_v
\]

主导分量：

\[
dominant=\arg\max_k component_k
\]

RAI 的边界：

```text
RAI 表示施工响应关注度；
RAI 不表示地质风险概率；
RAI 不说明异常原因；
RAI 不用于 forward_attention。
```

### 5.2 GRS：地质证据关注度

GRS（Geological Relevance Score，地质证据关注度）用于描述 cell 内可用地质证据的关注程度。当前公式为：

\[
GRS =
0.45G+
0.45H+
0.10C
\]

其中：

| 符号 | 中文含义 | 字段 |
|---|---|---|
| \(G\) | 围岩/地质等级分量 | `grade_score_component` |
| \(H\) | hazard 标签分量 | `hazard_component` |
| \(C\) | 证据置信分量 | `confidence_component` |

GRS 的可用性必须由 `GRS_available` 判断。若没有空间相关地质证据：

\[
GRS\_available=False
\]

此时不能把 GRS=0 解释为地质关注低，只能解释为“缺少可用地质证据”。

### 5.3 GRCI：已掘区段地质-施工响应耦合关注度

GRCI（Geology-Response Coupling Index，地质-施工响应耦合关注度）用于 daily_review cell 的复核排序。当前公式为：

\[
GRCI =
0.55GRS+
0.35RAI+
0.10GRS\cdot RAI
\]

三项含义如下：

| 项 | 中文含义 | 公式 |
|---|---|---|
| 地质项 | 地质证据贡献 | \(0.55GRS\) |
| 响应项 | 施工响应贡献 | \(0.35RAI\) |
| 交互项 | 地质-响应同时偏高时的耦合贡献 | \(0.10GRS\cdot RAI\) |

GRCI 可用条件为：

\[
GRCI\_available =
daily\_review
\land has\_plc\_response
\land GRS\_available
\land RAI\_available
\]

若 cell 属于 forward_attention，则：

\[
GRCI\_available=False
\]

GRCI 的等级仅用于关注排序：

| GRCI 范围 | 等级 |
|---|---|
| \(GRCI\ge 0.75\) | high |
| \(0.50\le GRCI<0.75\) | medium |
| \(0.25\le GRCI<0.50\) | low |
| \(GRCI<0.25\) | none |

必须写清：

```text
GRCI 不是灾害概率；
GRCI 不是前方风险；
GRCI 不是因果证明；
GRCI 只用于已掘区段复核排序。
```

---

## 6 Evidence Pack selection：从状态孪生到可生成证据

### 6.1 证据包不是原始数据堆叠

Evidence Pack 的理论角色不是“给 LLM 更多材料”，而是：

> 将 DailyConstructionTwin 中的状态对象压缩为 role-aware、traceable、bounded 的生成证据。

也就是说，Evidence Pack 既选择“写什么”，也限制“不能怎么写”。

### 6.2 daily_review cell 选择分数

对已掘复核 cell，selection score 可写为：

\[
Score_{review}=
\frac{
0.40GRCI+
0.25RAI+
0.25GRS+
0.10TC
}{
\sum w_{available}
}
\]

其中 \(TC\) 表示 trace completeness（证据追踪完整度）。若某一项不可用，则在可用项之间重新归一化，而不是强行记为 0。

该设计体现了：

1. 已掘复核优先考虑 GRCI；
2. 同时保留 RAI 和 GRS 的单项贡献；
3. 证据追踪完整度越高，越适合进入 Evidence Pack。

### 6.3 forward_attention cell 选择分数

前方关注 cell 不使用 RAI 和 GRCI，其选择分数为：

\[
Score_{forward}=
\frac{
0.45GRS+
0.25W_f+
0.20C_e+
0.10TC
}{
\sum w_{available}
}
\]

其中：

| 符号 | 中文含义 |
|---|---|
| \(GRS\) | 地质证据关注度 |
| \(W_f\) | 前方距离权重 |
| \(C_e\) | 证据置信度 |
| \(TC\) | 证据追踪完整度 |

当前前方距离分层为：

| 距掌子面距离 | 分层 | 权重 |
|---|---|---:|
| 0-10 m | 近前方 (`near_forward`) | 1.0 |
| 10-20 m | 短前方 (`short_forward`) | 0.7 |
| 20-30 m | 扩展前方 (`extended_forward`) | 0.4 |

该设计保证：

```text
前方提示来自地质证据和距离权重；
不使用 PLC 响应；
不使用 RAI；
不使用 GRCI。
```

### 6.4 local_background cell 选择分数

局部背景 cell 的选择分数为：

\[
Score_{background}=
\frac{
0.50GRS+
0.25C_e+
0.25TC
}{
\sum w_{available}
}
\]

局部背景只提供上下文，不支撑当日施工响应结论。

---

## 7 LLM 生成链路：Planner、Generator、Checker、Reviser 的闭环机制

### 7.1 LLM 的角色定义

本文中的 LLM 不执行以下任务：

```text
不读取原始 PLC CSV；
不读取完整 evidence_db；
不计算 RAI/GRS/GRCI；
不判断地质灾害概率；
不判断前方风险是否发生；
不替代工程师签发日报。
```

LLM 执行的是：

```text
在 Evidence Pack 和生成约束下组织日报文本；
根据 Quality / Grounding / Boundary / Structured Trace 反馈修订文本。
```

### 7.2 五种生成模式的消融逻辑

M0-M4 可以写成递进式消融：

```text
M0：结构化模板，无 LLM
M1：只有任务说明，直接 LLM
M2：加入原始证据摘要
M3：加入 ConstructionStateCell + Evidence Pack
M4：加入 Twin + Evidence Pack + Planning + Boundary + Structured Trace + Reviser
```

理论上对应：

\[
M1 \rightarrow M2 \rightarrow M3 \rightarrow M4
\]

逐步增加：

```text
输入证据量；
证据结构化程度；
证据角色边界；
生成前规划；
生成后核验；
反馈修订。
```

因此该实验不仅是生成模式对比，也可以解释为模块贡献分析。

### 7.3 Report claim 的形式化

报告文本可分解为主张集合：

\[
R_d=\{c_i\}_{i=1}^{M}
\]

每个主张可表示为：

\[
c_i=(type_i,entity_i,value_i,range_i,time_i,role_i)
\]

其中：

| 分量 | 中文含义 |
|---|---|
| \(type_i\) | 主张类型，如 operation、geology、forward、coupling |
| \(entity_i\) | 主张对象，如 cell、气体、掌子面、前方区间 |
| \(value_i\) | 数值或等级 |
| \(range_i\) | 里程范围 |
| \(time_i\) | 时间范围 |
| \(role_i\) | 证据角色 |

Grounding 检查可形式化为：

\[
grounded(c_i)=
\exists e_j\in E_d:
match(c_i,e_j)=1
\land role(c_i)=role(e_j)
\land scope(c_i)\subseteq scope(e_j)
\]

若无法找到匹配证据，则：

\[
grounded(c_i)=0
\]

报告证据支撑率为：

\[
grounding\_rate=
\frac{\sum_i grounded(c_i)}{M}
\]

### 7.4 Quality score 计算逻辑

质量分从 100 分开始，根据错误扣分：

\[
Q=100-P_{error}-P_{warning}-P_{section}-P_{grounding}
\]

其中：

| 扣分项 | 当前默认权重 |
|---|---:|
| 严重错误 (`forbidden_error`) | 15 |
| 警告 (`warning`) | 5 |
| 缺失章节 (`missing_section`) | 3 |
| 低 grounding rate | 10 或 20 |

低 grounding rate 的额外规则为：

\[
P_{grounding}=
\begin{cases}
20, & grounding\_rate<0.6\\
10, & 0.6\le grounding\_rate<0.8\\
0, & grounding\_rate\ge 0.8
\end{cases}
\]

最终：

\[
quality\_score=\max(0,Q)
\]

需要说明：该评分是工程语义审计分，不是自然语言流畅性评分。

### 7.5 Boundary Checker 的理论作用

Boundary Checker 不是一般错别字检查器，而是方法边界检查器。它重点识别：

| 边界问题 | 含义 |
|---|---|
| E14 aligned scope misuse | 将 10 m 对齐复核范围写成实际推进范围 |
| forward fact misuse | 将前方预报写成已发生事实 |
| GRCI probability misuse | 将 GRCI 写成灾害概率或风险概率 |
| PLC proxy misuse | 将 proxy 写成严格物理量或地质证明 |
| stop causality misuse | 将 stop_ratio 直接写成异常停机原因 |
| local background misuse | 将背景证据写成当日结论 |

这些检查对应 TBM 日报中最容易出现的工程语义错误。

### 7.6 Reviser 的约束性修订机制

M4 的修订不是普通润色，而是：

\[
R_d^{final}=Revise(R_d^{draft},F_d,E_d,C_d)
\]

其中：

| 符号 | 含义 |
|---|---|
| \(R_d^{draft}\) | LLM 初稿 |
| \(F_d\) | Quality/Grounding/Boundary 反馈 |
| \(E_d\) | Evidence Pack |
| \(C_d\) | 生成约束 |
| \(R_d^{final}\) | 修订后报告 |

修订目标为：

```text
删除无证据句；
降级过强结论；
纠正数值范围；
保留标准章节；
保留前方提示的谨慎语气；
避免把复核范围写成实际推进范围；
避免把 GRCI 写成概率。
```

91 天实验中，修订机制将 unsupported 从 637 降至 376，说明其不是简单语言润色，而是基于证据反馈的约束性改写。

---

## 8 建议放入论文的方法章节图

### 图 A：PLC 预处理流程图

```text
原始 PLC 样本
    |
    v
时间与里程质量检查
    |-- 时间跳变：Δt_i > max(3 median(Δt), 10)
    |-- 里程反向：Δm_i < -0.01
    |-- 里程跳变：|Δm_i| > 5.0
    v
停机与辅助停机识别
    |-- shutdown_i = (F_i <= 0) OR (T_i <= 0)
    |-- auxiliary_shutdown_i = (v_i <= 0) OR (rpm_i <= 0)
    v
非停机样本 3σ 异常点过滤
    |-- x_i < μ_x - 3σ_x OR x_i > μ_x + 3σ_x
    v
有效掘进样本识别
    |-- 非停机、非异常、里程有效、速度/推力/扭矩/转速有效
    v
连续有效掘进区间切分
    |-- time gap / 里程反向 / invalid 样本触发新区间
    v
稳态段识别
    |-- rolling mean window = 20
    |-- threshold = 0.8 × median(rolling mean)
    v
10 m cell 稳态指标汇总
    |-- mean / std / CV
    |-- power proxy
    |-- thrust/penetration proxy
    |-- torque/penetration proxy
```

### 图 B：证据角色边界图

```text
                       当前掌子面 m_f
                            |
       local_background      | daily_review       forward_attention
<--------------------------->|<--------------->|<------------------->
      背景上下文              当日已掘复核          当前掌子面前方关注

local_background：只作背景，不作当日结论
daily_review：可使用 PLC + GRS + RAI + GRCI
forward_attention：只用 GRS/source_trace，不用 PLC/RAI/GRCI
```

### 图 C：LLM 治理闭环图

```text
DailyConstructionTwin
        |
        v
Role-aware Evidence Pack
        |
        v
Planner 生成章节和边界约束
        |
        v
LLM Draft Report
        |
        v
Quality + Grounding + Boundary + Structured Trace
        |
        v
Feedback with claim-level errors
        |
        v
LLM Reviser
        |
        v
Final Report + Audit Artifacts
```

---

## 9 可以直接替换摘要中的增强表达

原摘要若过于概括，建议替换或补入以下表达：

> 与直接将施工数据输入大语言模型不同，本文将 TBM 施工日报生成建模为多源工程证据约束下的可信知识生成任务。系统首先在 PLC 层面对原始运行样本进行时间-里程质量检查、停机识别、非停机样本 3σ 异常点过滤、有效掘进样本识别、连续工作区间切分和稳态段提取，并在 10 m 里程单元内计算稳态负载、波动、贯入效率与负载-贯入关系 proxy。随后，系统对 TSP、HSP 和掌子面素描等地质证据执行时间可用过滤和空间相关筛选，将证据划分为已掘复核、前方关注和局部背景三类角色。上述信息被统一组织为 ConstructionStateCell，并进一步构建 DailyConstructionTwin，使 LLM 仅消费角色化 Evidence Pack，而不直接读取原始 PLC CSV 或完整 evidence_db。生成后，系统通过 Quality、Grounding、Boundary 和 Structured Trace 对报告主张进行证据支撑、数值一致性、角色边界和章节完整性核验，并将错误反馈给 LLM 进行约束性修订。

---

## 10 可以直接放入论文“方法边界”的段落

本文方法必须保持以下边界。首先，RAI、GRS 和 GRCI 均为启发式关注指标，不是地质灾害发生概率，也不是监督学习预测模型。RAI 反映施工响应关注度，GRS 反映地质证据关注度，GRCI 仅表示已掘区段地质证据与施工响应之间的耦合关注程度。其次，forward_attention 只用于当前掌子面前方关注提示，不使用 PLC 稳态指标、RAI 或 GRCI，也不得写成已发生事实。再次，PLC 中的 cutterhead power、thrust per penetration 和 torque per penetration 均为 proxy 指标，仅用于施工响应解释，不能解释为严格物理功率、严格比能或地质风险证明。最后，LLM 在本文方法中不承担地质风险判断任务，而是在 Evidence Pack 和生成约束下完成报告组织与反馈修订。

---

## 11 论文中应避免的错误表述

| 不建议写法 | 建议写法 |
|---|---|
| 本文预测 TBM 地质灾害风险 | 本文构建 TBM 施工日报证据约束生成与审计方法 |
| GRCI 表示灾害发生概率 | GRCI 表示已掘区段地质-施工响应耦合关注度 |
| PLC 指标证明前方地质异常 | PLC 指标仅作为已掘区段施工响应证据 |
| 前方风险较低 | 当前前方证据关注度较低，但仍需结合现场复核 |
| 10 m 对齐范围为实际推进范围 | PLC 实测范围为实际推进范围，10 m 对齐范围仅用于 cell 复核 |
| LLM 判断地质风险 | LLM 在结构化证据约束下组织和修订日报文本 |

