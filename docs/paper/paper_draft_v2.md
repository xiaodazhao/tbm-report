# 面向 TBM 施工日报的多源证据约束生成与可追溯校核方法

---

## 摘要

隧道掘进机（TBM）施工日报的编写需要综合 PLC 运行参数、超前地质预报和掌子面素描等多种异构数据，当前依赖人工整理，存在效率低、口径不一致和可追溯性差的问题。现有基于大语言模型（LLM）的直接生成方法缺乏对多源证据的结构化组织和工程语义边界约束，易产生无证据支撑的表述和边界越界。本文提出一种多源证据约束生成与可追溯校核方法。该方法将多源异构数据对齐到 10 m 里程单元，构建 ConstructionStateCell 作为统一施工状态表征；将施工空间按证据角色划分为已掘复核、前方关注和局部背景三个层次；以 Prompt Evidence Pack 作为 LLM 的唯一结构化输入，经 Report Planner 进行章节级证据角色控制，生成初稿后由 Quality Checker、Trace Builder 和 Boundary Checker 进行自动校核，并将结果反馈至 LLM 完成约束性修订，形成生成—校核—修订闭环。基于某实际 TBM 工程 91 个施工日，在 deepseek-chat 上完成 91 天 × 5 种模式共 455 次真实 LLM 生成对比实验。完整闭环方法（M4）的平均质量分为 93.02，证据支撑率为 0.9109，较直接 LLM 生成（M1）分别提高 23.03 和 0.1820；未支撑表述从 1 129 条降至 381 条（降幅 66.3%），数值错误从 431 条降至 92 条（降幅 78.7%），E14 类范围误写和缺失章节数均为 0，15/30/91 天三个样本规模下指标保持稳定。消融实验表明，仅提供原始证据或仅组织结构化证据包均不足以有效控制生成错误，结构化证据组织与校核修订闭环需共同作用。当前结果基于单一工程数据，尚不具备跨工程泛化证据，自动评价亦不能替代人工专家评估。

**关键词**：TBM 施工日报；证据约束生成；施工状态单元；可追溯校核；大语言模型；隧道工程

---

## 1 引言

### 1.1 研究背景

隧道掘进机（Tunnel Boring Machine, TBM）施工日报是记录当日掘进状态、地质条件和施工响应的核心工程文件。一份完整的施工日报需整合多类数据：PLC 系统采集的推进速度、推力、刀盘扭矩、转速和停机状态等高频运行参数；TSP 地震波反射法和 HSP 水平声波法等超前地质预报提供的掌子面前方地质信息；以及地质人员现场记录的掌子面素描与围岩等级。这些数据在时间粒度（秒级 PLC 采样 vs 日级地质录入）、空间表达方式（连续里程坐标 vs 区段性预报 vs 点状观测）和工程语义粒度上存在本质差异，使得日报编写成为一项需要丰富跨源综合经验的认知密集型任务。

目前 TBM 施工日报主要依赖现场技术人员手工整理撰写，存在三个突出问题：第一，编写效率低——技术人员需从多个独立系统中逐一提取、核验和综合数据；第二，口径不一致——不同编写者的表达习惯和专业判断差异导致日报的可比性和连续性不佳；第三，可追溯性差——日报中的关键判断（如"某区段耦合关注度较高""前方需重点关注"等）常缺乏明确的证据来源标注，后续复盘和工程验收时难以追溯其依据。

### 1.2 现有方法的不足

大语言模型在工程文本生成领域展现出的潜力引发了将其应用于施工报告自动生成的探索。然而，在 TBM 施工日报这一特定场景中，直接使用 LLM 面临三个核心挑战：

**挑战一：多源异构数据难以统一组织。** PLC 数据是高频时序数值序列，地质预报是空间区段文本描述，掌子面素描是离散里程点观测记录。三者缺乏统一的空间锚点和时间对齐机制。若将原始数据简单转为文本后输入 LLM，模型难以建立不同数据源之间的空间对应关系和时间因果逻辑——例如，一段 TSP 预报描述的"DK1013+200 至 DK1013+250 范围Ⅳ级围岩"与 PLC 数据在 DK1013+219 至 DK1013+224 段的异常扭矩响应之间的关系，很难通过文本拼接让 LLM 自行建立。

**挑战二：工程语义边界敏感。** TBM 施工日报对工程语义有严格边界要求：已掘区段的地质-施工响应复核不能混入前方预报的推测性内容；PLC 代理指标（如刀盘功率 proxy、扭矩代理值等）不能作为真实物理量表述；10 m 对齐后的复核范围不能替代 PLC 实测推进范围；停机比例高不能直接解释为异常停机原因明确。这些边界在通用 LLM 的自由文本生成中易被忽略或混淆，而一旦出现边界越界，日报的工程可信度便受到严重损害。

**挑战三：生成内容缺乏证据追溯。** 通用 LLM 生成的文本无法提供"此句的依据是什么"的可追溯链路。在工程场景中，日报中的每一项数值和判断——从当日的实际推进量到某区段的耦合关注度判断——均需有明确的证据来源支撑。缺乏证据追溯的日报不仅无法通过工程复核，更重要的是会将未经核验的信息纳入施工决策链，产生工程安全隐患。

### 1.3 本文的核心思路

针对上述三个挑战，本文提出一种多源证据约束生成与可追溯校核方法。核心思路不是让 LLM 直接阅读原始数据并自由生成日报，而是在 LLM 与多源数据之间构建两层中间结构：以 10 m 里程单元 ConstructionStateCell 为基本状态单元、以 DailyConstructionTwin 为面向日报的施工状态信息底座，将异构证据统一组织为可追溯的空间化施工状态；然后以此为基础构建 Prompt Evidence Pack 作为 LLM 的唯一结构化输入，通过 Report Planner 进行章节级证据角色控制，生成初稿后由 Quality Checker、Trace Builder 和 Boundary Checker 自动校核，并将校核结果反馈至 LLM 完成约束性修订，形成生成—校核—修订闭环。

### 1.4 主要贡献

本文的主要贡献包括：

1. **施工状态统一表征与证据角色治理方法**：提出 ConstructionStateCell 作为 10 m 里程单元下的施工状态基本表征对象，将 PLC 响应、地质证据、关注指标和来源追溯统一到同一空间网格；在此基础上将施工空间划分为已掘复核、前方关注和局部背景三个证据角色层次，建立不同角色的报告表达权限规则。

2. **证据约束生成与领域错误校核体系**：构建 Prompt Evidence Pack 作为 LLM 唯一输入，引入 Report Planner 实现章节级证据角色控制；设计面向 TBM 日报的领域错误分类体系（涵盖范围误写、指标误用、边界越界等类别），实现生成内容的自动证据匹配与可追溯校核。

3. **基于 91 天全量真实数据的系统验证**：在 91 个施工日上完成 5 种生成模式共 455 次真实 LLM 运行，通过消融实验和稳定性分析验证了各方法模块的贡献，并通过指标鲁棒性实验分析了启发式指标的敏感性。

### 1.5 章节安排

本文后续章节安排如下：第 2 章回顾相关研究工作并指出现有研究的空白；第 3 章详细阐述所提方法的各个环节，包含形式化定义和算法描述；第 4 章以研究问题驱动的方式呈现实验结果与分析；第 5 章讨论方法的工程价值、局限性和未来方向；第 6 章总结全文。

---

## 2 相关研究

### 2.1 TBM 施工数据分析与运行参数建模

TBM 施工数据的分析与建模一直是隧道工程领域的研究热点。在工况识别方面，研究者基于推进速度、刀盘扭矩、推力等运行参数，利用聚类分析、支持向量机等方法建立掘进状态分类模型，区分正常掘进、停机和异常工况[1,2]。在运行参数预测方面，深度神经网络和集成学习方法被用于预测推进速度和刀盘磨损等关键参数[3,4]。在地质-施工耦合分析方面，部分研究将 TBM 运行参数与地质条件进行统计关联，以识别不同围岩等级下的施工响应特征[5,6]。上述工作主要聚焦于单一维度的数据分析或数值预测，未将多源数据组织为可服务于日报生成的结构化施工状态。本文在此基础上，将 PLC 运行分析和地质证据融合的结果统一映射到 10 m 里程单元上，形成可供下游校核和生成调用的一致状态表征。

### 2.2 隧道与地下工程数字孪生

数字孪生在隧道与地下工程中的应用近年来发展迅速。现有工作主要集中在三个方向：一是基于 BIM 和 GIS 的几何孪生，构建隧道三维可视化模型[7,8]；二是基于有限元或离散元方法的物理仿真孪生，模拟围岩变形、支护受力和地层沉降[9,10]；三是面向 TBM 关键部件（刀盘、主轴承等）的设备监测孪生，实现运行状态监控和故障预警[11,12]。本文所构建的 DailyConstructionTwin 与上述物理仿真数字孪生在定位上有本质区别：它不模拟物理过程，不计算围岩应力或支护变形，而是作为面向日报生成的 cell-level 施工状态信息底座，将当日的 PLC 响应、地质证据、耦合指标和追溯信息组织为可查询、可校验、可生成报告的结构化表征。这种以工程文档生成为目标的"状态孪生"定位在隧道工程领域尚属较新的探索方向。

### 2.3 LLM 与 RAG 在工程文本生成中的应用

LLM 在工程文本生成领域的应用正在快速扩展。已有研究将 GPT 等模型应用于施工日志自动生成[13]、安全隐患报告撰写[14]和设备维护记录生成[15]等场景，其共同模式是将结构化或半结构化数据转换为自然语言提示后由 LLM 完成文本生成。检索增强生成（RAG）技术进一步通过从外部知识库检索相关信息来提升生成内容的准确性[16,17]。然而，现有方法在 TBM 日报场景中面临特殊的适配困难：一是缺乏里程空间对齐机制——在 TBM 工程中，里程是连接 PLC 数据、地质预报和掌子面观测的关键空间锚点，缺少空间对齐将导致不同来源的证据之间无法建立逻辑关系；二是缺乏面向工程语义的证据角色治理和边界校核机制，使得 LLM 输出中的越界表述难以被系统性地检测和纠正。

### 2.4 事实一致性与约束生成

在自然语言处理领域，事实一致性（Factual Consistency）和约束生成（Constrained Generation）是与本文工作密切相关的两个研究方向。事实一致性研究关注如何检测和减少 LLM 生成文本中的事实错误，主要技术路线包括基于自然语言推理的事实校验[18]、基于检索的事实核对[19]和基于自一致性的多次采样验证[20]。约束生成研究旨在通过解码约束、提示工程或后处理校核等方式控制 LLM 输出符合预定义规则[21,22]。本文的方法与上述工作存在交叉但有关键区别：本文的约束不是通用语义约束，而是面向 TBM 施工日报的领域特定约束——包括指标使用边界（GRCI 不用于前方）、空间范围语义（10 m 对齐范围 vs 实际推进范围）和证据角色权限（前方提示不能写成已发生事实）等；本文的校核不是通用的"与语料是否一致"，而是基于结构化 Evidence Pack 和 Trace 索引的逐项证据匹配与语义边界检查。

### 2.5 现有研究空白与本文定位

综合以上四方面分析，现有研究存在以下空白：第一，TBM 施工数据分析多关注工况识别或参数预测，较少将分析结果组织为服务于日报生成的结构化施工状态层；第二，现有数字孪生工作多偏几何建模、物理仿真或设备监测，较少关注面向工程文档生成的状态证据底座构建；第三，LLM 工程报告生成方法缺少里程空间对齐、证据角色治理和领域语义边界校核的一体化设计。本文的工作填补了上述空白，提出的方法不是"用 LLM 自动写日报"，也不是"让 LLM 判断地质风险"，而是构建一套多源证据组织、空间角色治理、证据约束生成和可追溯校核的完整链路。

---

## 3 方法

### 3.1 符号定义

本文使用的主要符号如表 1 所示。

**表 1  主要符号定义**

| 符号 | 含义 |
|------|------|
| $t$ | 施工日期索引 |
| $P_t$ | 日期 $t$ 的 PLC 日运行数据（时间序列，含里程、速度、推力、扭矩、转速、状态、气体等字段） |
| $G_t$ | 截至日期 $t$ 可用的正式地质证据集合（经 TSP/HSP/掌子面素描标准化处理） |
| $\mathcal{C}_t = \{c_1, c_2, \ldots, c_n\}$ | 日期 $t$ 的 ConstructionStateCell 集合，$n$ 为 cell 数量 |
| $\mathcal{D}_t$ | 日期 $t$ 的 DailyConstructionTwin |
| $\mathcal{E}_t$ | 日期 $t$ 的 Prompt Evidence Pack |
| $\mathcal{P}_t$ | 日期 $t$ 的 Report Plan |
| $R_t^{(0)}$ | LLM 生成的日报初稿 |
| $\mathcal{Q}(R)$ | 对报告 $R$ 的 Quality / Trace / Boundary 校核结果 |
| $R_t^{(1)}$ | 经 Trace-Guided Revision 后的日报终稿 |
| $\text{cell\_role}(c) \in \{\text{daily\_review}, \text{forward\_attention}, \text{local\_background}\}$ | cell $c$ 的证据角色 |

日报生成任务可形式化定义为：

$$R_t^{(1)} = \text{Revise}\big(R_t^{(0)}, \mathcal{Q}(R_t^{(0)})\big), \quad R_t^{(0)} = \text{Generate}(\mathcal{E}_t, \mathcal{P}_t)$$

其中 $\mathcal{E}_t = \text{PackBuilder}(\mathcal{D}_t)$, $\mathcal{D}_t = \text{TwinBuilder}(\mathcal{C}_t)$, $\mathcal{C}_t = \text{CellBuilder}(P_t, G_t)$。

### 3.2 总体框架

本文方法的总体链路如下：PLC 日运行数据 $P_t$ 与多源地质证据 $G_t$ 首先经过时空证据门控，排除未来证据和空间无关证据；然后按 10 m 里程单元构建 ConstructionStateCell 集合 $\mathcal{C}_t$，计算每个 cell 的关注指标（RAI/GRS/GRCI）并标注证据角色；在此基础上构建 DailyConstructionTwin $\mathcal{D}_t$，按角色分层次组织 cell 视图；从 $\mathcal{D}_t$ 构建 Prompt Evidence Pack $\mathcal{E}_t$，经 Report Planner 规划章节方案 $\mathcal{P}_t$ 后，由 LLM 在证据约束下生成日报初稿 $R_t^{(0)}$；初稿经 Quality Checker、Trace Builder 和 Boundary Checker 校核得到 $\mathcal{Q}(R_t^{(0)})$，LLM 在校核结果约束下完成修订得到终稿 $R_t^{(1)}$。

---

**Algorithm 1: 时空证据门控与 ConstructionStateCell 构建**

```
Input:  P_t (PLC daily data), G_t (geological evidence set),
        L (cell size, default 10 m), d_forward (forward window, default 30 m)
Output: C_t (ConstructionStateCell set)

1.  // Step 1: Temporal gating
2.  G_t_online ← {g ∈ G_t | g.report_date ≤ t}
3.
4.  // Step 2: Extract daily scope
5.  daily_plc_range ← (min chainage(P_t), max chainage(P_t))
6.  daily_advance_m ← max chainage(P_t) - min chainage(P_t)
7.  current_face ← max chainage(P_t)
8.
9.  // Step 3: Compute aligned excavated scope
10. daily_excavated_scope ← align_to_grid(daily_plc_range, L)
11. cells_excavated ← generate_cells(daily_excavated_scope, L)
12. cells_forward ← generate_cells(current_face, current_face + d_forward, L)
13. cells_background ← generate_cells(current_face - d_background, current_face, L)
14.
15. // Step 4: Spatial gating and cell construction
16. for each cell c in (cells_excavated ∪ cells_forward ∪ cells_background) do
17.   c.evidence ← {g ∈ G_t_online | spatial_overlap(g.chainage_range, c.range)}
18.   c.plc_metrics ← compute_plc_response(P_t, c.range)
19.   c.RAI ← compute_RAI(c.plc_metrics)         // Eq.(1)
20.   c.GRS ← compute_GRS(c.evidence)             // Eq.(2)
21.   c.GRCI ← compute_GRCI(c.RAI, c.GRS, c.role) // Eq.(3), daily_review only
22.   c.cell_role ← assign_role(c)                // based on spatial relation to current_face
23.   c.source_trace ← build_trace(c.evidence)
24. end for
25.
26. return C_t
```

### 3.3 时空证据门控

在证据进入施工状态表征之前，系统进行双重过滤。**时间门控**依据报告日期对 $G_t$ 进行 online 过滤，排除报告日期之后才录入的证据，避免后续日期的地质信息泄漏到当前日报中。**空间门控**基于当日 PLC 推进范围、当前掌子面位置和前方/背景窗口筛选空间相关证据——距离过远或与当日施工范围完全无关的地质证据不进入 $\mathcal{C}_t$ 的构建。

时空门控后的证据子集随当日的里程位置动态变化。这一"在效性"过滤机制保证了不同日期日报之间的时序一致性。

### 3.4 ConstructionStateCell 施工状态单元

ConstructionStateCell 是 10 m 里程单元下的施工状态基本表征对象。每个 cell 统一承载：

- **空间定位**：`cell_id`、`cell_start`、`cell_end`、`cell_center`
- **PLC 响应**：`has_plc_response`、停机占比、异常工况占比、速度下降评分、扭矩波动评分、速度波动评分、RAI 及其各分项
- **地质证据**：`has_geology_evidence`、GRS 及其各分项（等级评分、风险分量、置信分量）、主要风险类型
- **耦合复核**：GRCI 及其各分量（地质项、响应项、交互项）、`GRCI_available`、耦合关注等级
- **空间角色**：`cell_role` ∈ {daily_review, forward_attention, local_background}
- **来源追溯**：`source_trace`、支撑证据 ID 列表、trace 引用

三种证据角色的划分逻辑如下：

- **daily_review**：cell 位于当日 10 m 对齐后的已掘复核范围内，可同时使用 PLC 响应和地质证据，可使用 GRCI 进行耦合复核。
- **forward_attention**：cell 位于当前掌子面前方 0-30 m，尚未开挖，仅有超前地质预报和前方地质推测，仅使用 GRS 和 source_trace，不使用 GRCI。
- **local_background**：cell 位于掌子面附近的局部背景区间，已有地质证据但非当日开挖区域，仅作上下文参考，不作为当日主复核结论依据。

需要严格区分的两对空间概念：
- `daily_plc_range` / `daily_advance_m`：PLC 实测推进范围与实际推进量
- `daily_excavated_scope`：10 m cell 对齐后的已掘复核范围

两者不能混用。例如，某日 PLC 实测范围为 DK1013+219 至 DK1013+224（推进量 5.0 m），10 m 对齐复核范围为 DK1013+210 至 DK1013+230（两个 10 m cell）。报告中不得将对齐范围写成实际推进 20 m——这正是 E14 错误类型所防范的问题。

### 3.5 RAI、GRS 与 GRCI 关注指标

RAI、GRS 和 GRCI 均为启发式关注指标，用于日报中的关注排序和复核提示，不是灾害概率、故障概率或监督学习预测结果。权重基于工程经验设定，其敏感性通过鲁棒性实验分析（见第 4.7 节）。

#### 3.5.1 RAI（施工响应关注度）

RAI 综合停机占比、异常工况占比、速度下降和参数波动，识别当日已掘区段中施工响应较显著的单元：

$$\text{RAI} = 0.40 \cdot r_{\text{stop}} + 0.25 \cdot r_{\text{abnormal}} + 0.20 \cdot s_{\text{speed\_drop}} + 0.10 \cdot s_{\text{torque\_vol}} + 0.05 \cdot s_{\text{speed\_vol}}$$

语义边界：当前 PLC 字段未区分计划停机与非计划停机，$r_{\text{stop}}$ 仅作为施工响应关注信号，不能直接解释为异常停机原因；各分量为启发式关注度，不是严格的物理量。

#### 3.5.2 GRS（地质证据关注度）

GRS 综合地质等级、风险类型和置信度，识别地质证据提示较显著的单元：

$$\text{GRS} = 0.45 \cdot g_{\text{grade}} + 0.45 \cdot h_{\text{hazard}} + 0.10 \cdot c_{\text{confidence}}$$

重要区分：`GRS_available = false`（无可用空间相关地质证据或证据几何无效）与 `GRS = 0`（有证据但关注度低）语义不同——前者表示缺乏判断基础，后者表示判断后认为关注度不高。下游模块必须区分这两种情况。

#### 3.5.3 GRCI（地质-施工响应耦合关注度）

GRCI 表示已掘区段中地质关注与施工响应的耦合复核指标。**只有同时满足以下全部条件才计算正式 GRCI**：（1）cell 属于 daily_review；（2）`GRS_available = true`；（3）RAI 存在；（4）`has_plc_response = true`。forward_attention 和 local_background cell 不计算 GRCI。

$$\text{GRCI} = 0.55 \cdot \text{GRS} + 0.35 \cdot \text{RAI} + 0.10 \cdot \text{GRS} \cdot \text{RAI}$$

交互项 $\text{GRS} \cdot \text{RAI}$ 捕捉地质关注和施工响应同时较高的耦合效应——即地质条件复杂且施工响应也较显著的区段。GRCI 只用于已掘复核，不用于前方风险预测。

### 3.6 DailyConstructionTwin

DailyConstructionTwin $\mathcal{D}_t$ 是在 $\mathcal{C}_t$ 之上构建的面向日报生成的施工状态信息底座。它不是物理仿真数字孪生——不模拟围岩变形、支护受力或 TBM 物理过程——而是将当日 cell 按证据角色组织为结构化视图的信息组织层。

$\mathcal{D}_t$ 的核心组成包括：
- **角色分层视图**：按 daily_review / forward_attention / local_background 三层的 TwinCellView，每层包含关键 cell 列表及完整状态字段
- **证据治理上下文**：每层绑定允许使用的证据角色规则和指标使用权限
- **选择评分与排序**：每层 cell 按选择分（selection_score）排序，不同角色使用不同的选择分计算策略
- **汇总信息**：TwinStateSummary、TwinScope、TraceIndex

### 3.7 Prompt Evidence Pack 构建

Prompt Evidence Pack $\mathcal{E}_t$ 是 LLM 生成日报的唯一结构化输入。LLM 不直接读取原始 PLC CSV，不直接读取完整 evidence_db，不自行计算 RAI/GRS/GRCI。

$\mathcal{E}_t$ 包含以下证据模块：report_scope（报告日期、里程范围、10 m 对齐复核范围、实际推进量）、operation_evidence（工况统计、停机分析）、gas_evidence（气体监测统计与阈值分析）、geology_evidence（key_cells 地质证据，含选择分和排序）、coupling_evidence（high_grci_cells 耦合复核证据）、forward_evidence（前方 0-30 m 地质关注提示，按 0-10/10-20/20-30 m 分层）、background_context_evidence（局部背景上下文）、source_trace（所有证据的来源追溯信息）、generation_constraints（生成约束规则）。

---

**Algorithm 2: Evidence Pack 构建与角色约束**

```
Input:  D_t (DailyConstructionTwin)
Output: E_t (Prompt Evidence Pack)

1.  E_t ← empty Evidence Pack
2.  E_t.report_scope ← extract_scope(D_t)
3.  E_t.operation_evidence ← extract_operation(D_t)
4.  E_t.gas_evidence ← extract_gas(D_t)
5.
6.  // Cell selection with role-specific scoring
7.  for each role in {daily_review, forward_attention, local_background} do
8.    cells_role ← D_t.cells(cell_role == role)
9.    for each c in cells_role do
10.     if role == daily_review then
11.       c.selection_score ← w₁·c.GRCI + w₂·c.RAI + w₃·c.GRS + w₄·c.trace_completeness
12.     else if role == forward_attention then
13.       // GRCI excluded from forward selection
14.       c.selection_score ← w₁·c.GRS + w₂·c.forward_distance_weight
15.                           + w₃·c.evidence_confidence + w₄·c.trace_completeness
16.     else  // local_background
17.       c.selection_score ← w₁·c.GRS + w₂·c.trace_completeness
18.     end if
19.     c.selection_rank ← rank(c.selection_score, cells_role)
20.   end for
21.   E_t.key_cells[role] ← top_k(cells_role, k_role, by = selection_score)
22. end for
23.
24. E_t.generation_constraints ← load_constraints()  // GRCI usage, forward boundary, etc.
25. return E_t
```

### 3.8 LLM Report Planner

在生成日报正文前，LLM Report Planner 先规划 9 个标准章节的生成方案。规划内容包括每章允许使用的证据角色和禁止使用的指标（例如，前方关注章节禁止使用 GRCI）。Plan Validation 自动检查：是否误将 GRCI 用于前方关注章节；是否误将 forward_attention 证据用于已掘复核章节；是否遗漏必要章节。验证未通过的计划返回 LLM 重新规划。

### 3.9 证据约束生成与校核修订

经 Plan Validation 通过的 $\mathcal{P}_t$ 和 $\mathcal{E}_t$ 共同输入 LLM 生成日报初稿 $R_t^{(0)}$。生成过程中的核心约束包括：实际推进范围只能使用 `daily_plc_range`；10 m 对齐复核范围必须标注为"已掘复核范围"而非"实际推进范围"；GRCI 限定在已掘复核章节，描述为"耦合关注度"；前方内容使用提示性而非确定性表述；PLC proxy 标注为代理值而非真实物理量。

初稿生成后进入校核与修订闭环。

---

**Algorithm 3: 证据约束生成、校核与 Trace-Guided Revision**

```
Input:  E_t (Prompt Evidence Pack), P_t (Report Plan)
Output: R_t_final (TBM daily report, final version)

1.  // Step 1: Evidence-constrained generation
2.  R_0 ← LLM_Generate(E_t, P_t, constraints = E_t.generation_constraints)
3.
4.  // Step 2: Quality / Trace / Boundary check
5.  claims ← ClaimExtractor(R_0)
6.  Q ← empty QualityReport
7.  for each claim ∈ claims do
8.    match ← TraceMatcher(claim, E_t.source_trace, E_t.key_cells)
9.    if match.found then
10.     Q.grounded_claims.add(claim, match.source)
11.   else
12.     Q.unsupported_claims.add(claim)
13.   end if
14. end for
15. Q.numeric_errors ← detect_numeric_mismatch(claims, E_t)
16. Q.boundary_violations ← BoundaryChecker(claims, E_t.generation_constraints)
17.   // Check: E14 scope misuse, GRCI probability misuse, forward fact misuse, etc.
18. Q.section_completeness ← check_sections(R_0, 9)
19. Q.quality_score ← compute_quality(Q)
20.
21. // Step 3: Trace-guided revision
22. if Q.unsupported_claims not empty or Q.boundary_violations not empty then
23.   revision_feedback ← build_feedback(Q)
24.   R_1 ← LLM_Revise(R_0, revision_feedback, E_t)
25.   // Section guard: ensure 9 sections preserved
26.   if section_count(R_1) < 9 then
27.     R_1 ← SectionGuard(R_1, R_0, required_sections = 9)
28.   end if
29. else
30.   R_1 ← R_0
31. end if
32.
33. return R_1
```

校核体系中的关键错误类型包括：

- **E3（GRCI 概率误用）**：将 GRCI 表述为灾害发生概率
- **E10（数值无支撑）**：数值、日期、里程等表达在 Evidence Pack 中无对应证据
- **E13（停机原因过度推解）**：将停机比例高直接解释为明确的异常原因
- **E14（对齐范围误写为实际推进范围）**：将 10 m 对齐复核范围写为 PLC 实测推进范围或实际日进尺
- **前方事实误用**：将超前地质预报的未来信息写成现场已揭露事实
- **PLC proxy 物理解释**：将增强代理指标表述为真实物理量

修订的核心原则：（1）Section Guard 确保修订不通过删章来减少错误；（2）对无证据支撑的表述优先降级表达（确定句→提示句）或删除；（3）按违规类型分别采取对应的改写策略。

### 3.10 P3 旁路式候选证据模块

P3 模块从地质报告原文中抽取候选结构化证据，但不进入正式日报主链路。其输出标记为 `candidate_only=true`、`requires_manual_review=true`，不写入正式 evidence_db，不进入时空门控，不参与 GRS/RAI/GRCI 计算，不进入 Evidence Pack。P3 作为独立的候选证据扩展模块，其输出需经人工审核后方可考虑纳入正式证据链路。

---

## 4 实验与结果

### 4.1 实验设置

#### 4.1.1 数据

实验基于某实际 TBM 隧道工程数据，涵盖 2023 年 9 月至 12 月共 91 个可用施工日。数据基础：PLC 可用日期 91 天，日均推进量 13.86 m；正式 evidence_db 共 484 条（TSP 139 条、HSP/sonic 176 条、掌子面素描 169 条）。在 LLM 对比实验之前，已完成 91 天 no-LLM 模板流水线稳定性测试（Exp01）：91 天全部运行成功，验证了 ConstructionStateCell、DailyConstructionTwin 和 Evidence Pack 导出链路的全量稳定性。

#### 4.1.2 对比方法

设置五种递进式生成模式，构成消融实验：

| 模式 | 方法 | 消融含义 |
|------|------|----------|
| M0 | 模板生成（no-LLM） | 非 LLM 基线，验证模板的结构稳定性 |
| M1 | 直接 LLM（少量基础信息） | 验证直接 LLM 生成的风险 |
| M2 | M1 + 原始/半结构化施工证据 | 验证"仅给材料"是否足够 |
| M3 | M2 + Twin Evidence Pack 结构化证据 | 验证证据组织的作用 |
| M4 | M3 + Quality/Trace/Boundary + Revision | 验证本文完整方法的综合效果 |

#### 4.1.3 实验规模与 LLM 配置

91 个日期 × 5 种模式 = 455 次真实 LLM 生成运行。所有 LLM 模式（M1-M4）统一使用 deepseek-chat。实验采用固定的 v3.1 评价口径，全程不修改主流程、提示词、检查规则或评价指标。

#### 4.1.4 评价指标

- **综合质量分**（quality_score）：满分 100，综合 forbidden terms、GRCI misuse、gas semantics、role consistency、section completeness 扣分
- **证据支撑率**（grounding_rate）：有证据支撑的 claim 占总有效 claim 的比例
- **未支撑表述数量**（unsupported_claim_count）
- **数值错误数量**（numeric_error_count）
- **边界违规数量**（boundary_violation_count）：含 forward_fact_misuse、grci_probability_misuse、plc_proxy_misuse、stop_causality_misuse、local_background_scope_misuse
- **E14 数量**：10 m 对齐复核范围误写为实际推进范围的次数
- **缺失章节数**：9 个标准章节中缺失的数量

### 4.2 研究问题

本文围绕以下五个研究问题（RQ）组织实验分析：

- **RQ1**：完整闭环方法 M4 在质量分和证据支撑率上是否优于直接 LLM 生成（M1）？
- **RQ2**：结构化 Evidence Pack（M3）相比原始证据输入（M2）是否能减少边界违规和数值错误？
- **RQ3**：在 M3 基础上引入 Quality / Trace / Boundary + Revision（即 M4）是否能进一步降低未支撑表述？
- **RQ4**：M4 方法的表现在 15/30/91 天样本规模下是否稳定？
- **RQ5**：RAI/GRS/GRCI 的启发式公式对权重配置和公式形式是否敏感？

### 4.3 RQ1：M4 是否优于直接 LLM 生成？

91 天全量实验结果如表 2 所示。全部 455 次运行均成功完成，失败次数为 0。

**表 2  91 天五种生成模式全量对比**

| 模式 | 运行数 | 成功数 | 平均质量分 | 平均证据支撑率 | 未支撑表述 | 数值错误 | E14 | 边界违规 | 缺失章节总数 |
|------|:------:|:------:|:----------:|:--------------:|:----------:|:--------:|:---:|:--------:|:------------:|
| M0 模板 | 91 | 91 | 76.00 | 1.0000 | 0 | 0 | 0 | 0 | 273 |
| M1 直接LLM | 91 | 91 | 69.99 | 0.7289 | 1129 | 431 | 0 | 8 | 182 |
| M2 原始证据LLM | 91 | 91 | 72.79 | 0.7207 | 1257 | 340 | 0 | 30 | 182 |
| M3 Twin证据包LLM | 91 | 91 | 72.04 | 0.7653 | 1248 | 185 | 0 | 4 | 188 |
| M4 完整闭环 | 91 | 91 | **93.02** | **0.9109** | **381** | **92** | **0** | **3** | **0** |

针对 RQ1，M4 的质量分（93.02）和证据支撑率（0.9109）在指标上明显高于 M1（69.99 和 0.7289）。M4 的未支撑表述（381 条）和数值错误（92 条）相较 M1（1 129 条和 431 条）大幅减少。这些差异在量级上较大，但尚未进行统计显著性检验——91 天逐日配对检验（如 Wilcoxon signed-rank test）可进一步确认差异的统计可靠性（TODO：补充统计检验，报告 M4 vs M1 在 quality_score、grounding_rate、unsupported、numeric_error 上的逐日配对检验的 p 值、效应量和置信区间）。

M2 相比 M1，虽增加了原始证据输入，但未支撑表述反而从 1 129 上升至 1 257，边界违规从 8 升至 30。这一现象说明仅向 LLM 提供更多材料而不加以结构化和约束，可能诱发更多无证据自由扩写和边界越界，并不一定带来改善。

M0 模板生成的证据支撑率为 1.0000，因为它仅填充结构化字段，不产生自由文本，但缺失章节总数高达 273（91 天 × 日均 3 个缺失章节），说明模板的稳定性以牺牲表达完整性为代价。M0 的质量分（76.00）高于 M1-M3 但低于 M4，反映出模板"有缺无错"的特点。

### 4.4 RQ2：结构化 Evidence Pack 是否减少边界违规和数值错误？

如表 2 所示，M3 的边界违规（4 条）明显少于 M1（8 条）和 M2（30 条），数值错误（185 条）也少于 M1（431 条）和 M2（340 条）。这表明将证据按角色分层组织为结构化 Evidence Pack，并在 LLM 输入中明确区分 daily_review 和 forward_attention 的指标使用权限，能够降低 LLM 在边界语义和数值表达方面的越界。

但 M3 的未支撑表述（1 248 条）与 M2（1 257 条）基本持平，证据支撑率（0.7653）仅略高于 M2（0.7207）。这说明结构化证据包改善了边界安全性——LLM 更清楚什么指标用在哪里——但并未有效减少无证据扩写。原因可能在于：在没有明确的"此句是否有证据支撑"检查和反馈时，LLM 仍然倾向于在结构化材料的基础上扩展额外的综合判断。

### 4.5 RQ3：校核修订是否能进一步降低未支撑表述？

**表 3  M4 相比各基线的提升幅度**

| 基线 | 未支撑降低 | 数值错误降低 | 边界违规降低 | 质量分提升 | 证据支撑率提升 |
|------|:----------:|:----------:|:----------:|:----------:|:-------------:|
| M1 | 66.3% | 78.7% | 62.5%（8→3） | +23.03 | +0.1820 |
| M2 | 69.7% | 72.9% | 90.0%（30→3） | +20.23 | +0.1902 |
| M3 | 69.5% | 50.3% | 25.0%（4→3） | +20.98 | +0.1456 |

M4 相比 M3 的未支撑表述从 1 248 降至 381（降低 69.5%）。考虑到 M3 和 M4 的 Evidence Pack 构建过程相同，输入 LLM 的证据材料一致，M4 的优势在于增加了 Quality/Trace 检查和 Trace-Guided Revision。这说明仅有结构化证据包不足以保证生成质量，校核与修订闭环是必需的互补机制。

M4 修订阶段的整体效果：91 天全量中，初稿未支撑表述合计 666 条，修订后降至 381 条，减少 285 条，降低率 42.8%。修订不是简单润色，而是基于校核反馈对无证据表述进行删除、降级表达或改写，且 Section Guard 机制确保了修订后 9 个章节全部保留。

### 4.6 RQ4：方法在不同样本规模下是否稳定？

**表 4  M4 在 15/30/91 天样本规模下的指标**

| 样本规模 | 平均质量分 | 平均证据支撑率 | 未支撑表述 | 数值错误 | E14 | 边界违规 | 缺失章节 |
|---------|:----------:|:-------------:|:----------:|:--------:|:---:|:--------:|:--------:|
| 15 天 | 96.67 | 0.9093 | 64 | 16 | 0 | 0 | 0 |
| 30 天 | 92.50 | 0.9205 | 118 | 22 | 0 | 1 | 0 |
| 91 天 | 93.02 | 0.9109 | 381 | 92 | 0 | 3 | 0 |

**表 5  M4 日均错误指标在不同样本规模下的比较**

| 样本规模 | 日均未支撑 | 日均数值错误 | 日均边界违规 |
|---------|:----------:|:------------:|:------------:|
| 15 天 | 4.27 | 1.07 | 0.00 |
| 30 天 | 3.93 | 0.73 | 0.03 |
| 91 天 | 4.19 | 1.01 | 0.03 |

M4 的日均错误指标在三个样本规模下基本一致（日均未支撑 3.93-4.27 条，日均数值错误 0.73-1.07 条，日均边界违规 0.00-0.03 条），未出现随样本量增大而退化的趋势。E14 始终为 0，缺失章节始终为 0，说明这两个方面的控制是稳定的。

### 4.7 RQ5：启发式指标的权重和公式是否敏感？

以 91 天全量的 175 个可计算 GRCI 的 daily_review cell 为对象，构建 6 个指标变体分析鲁棒性。V0 为当前公式；V1 为百分位标准化后等权；V2-V4 分别采用交互项、熵权和 CRITIC 权；V5 为保守的 min(RAI, GRS) 形式。

**表 6  六种指标变体与 V0 的一致性**

| 变体 | 与 V0 的 Spearman 相关 | Top-10 Jaccard | Top-20 Jaccard | Forward GRCI 泄漏 |
|------|:----------------------:|:--------------:|:--------------:|:-----------------:|
| V1（百分位等权） | 0.9317 | 0.538 | 0.667 | 0 |
| V2（百分位交互项） | 0.8772 | 0.429 | 0.538 | 0 |
| V3（熵权） | 0.8787 | 0.429 | 0.538 | 0 |
| V4（CRITIC） | 0.8886 | 0.429 | 0.538 | 0 |
| V5（严格 min） | 0.8168 | 0.250 | 0.333 | 0 |

所有变体的 forward GRCI 泄漏均为 0，确认 GRCI 的前方禁用在代码层面是稳定的。V1-V4 与 V0 的 Spearman 相关系数在 0.877-0.932 之间，说明各变体在整体排序层面与当前公式保持合理的一致性。V5（严格 min）的 Top-10 Jaccard 仅为 0.250，说明当采用更保守的耦合方式时，高关注 cell 的选择发生较大变化——这反映出高关注 cell 的排序对公式形式仍存在敏感性。在当前缺乏监督标签（无灾害事件记录、无异常原因标注、无现场复核标签）的条件下，无法对何种公式形式更"正确"做出判断。这是启发式方法的固有局限，也是后续引入专家标签进行校准的主要动机。

### 4.8 典型案例分析

#### 4.8.1 案例选择与背景

从 91 天中选取 2023-09-19 作为主案例、2023-09-28 作为辅助案例。这两个日期的共同特征是 M1 或 M2 中未支撑表述和数值错误较突出，而 M4 在同一日上指标明显改善且无 E14、无 boundary violation、无缺失章节，适合用于在文本层面揭示"不同模式生成的日报具体差在哪里"。

**表 7  典型案例评价结果对比**

| 日期 | 模式 | 质量分 | 证据支撑率 | 未支撑表述 | 数值错误 | 缺失章节 | 边界违规 |
|------|------|:------:|:----------:|:----------:|:--------:|:--------:|:--------:|
| 09-19 | M1 | 59 | 0.5517 | 26 | 15 | 2 | 0 |
| 09-19 | M2 | 74 | 0.6852 | 17 | 10 | 2 | 0 |
| 09-19 | M4 | 100 | 0.9388 | 3 | 0 | 0 | 0 |
| 09-28 | M1 | 69 | 0.7234 | 13 | 5 | 2 | 0 |
| 09-28 | M2 | 64 | 0.5616 | 32 | 8 | 2 | 0 |
| 09-28 | M4 | 100 | 0.9750 | 1 | 1 | 0 | 0 |

#### 4.8.2 M1/M2 中典型错误的文本呈现

**（a）对话式开场。** 2023-09-19 的 M1 报告以"以下是根据您提供的输入数据生成的 TBM 施工日报"开头——LLM 以问答助手模式回应，而非输出正式施工日报正文。这类非正式开场在 M4 中不再出现，M4 直接以"综合摘要"开始。

**（b）无证据综合判断。** M1 中"本日 PLC 数据质量良好，共采集 2 233 条记录，时间序列连续无中断"——这一综合判断在 Evidence Pack 中无法逐条追溯支撑。M4 不保留此扩展判断，而是集中呈现 PLC 实测推进范围、停机时长和异常扭矩事件等可追踪的证据内容。

**（c）前方提示过于确定。** 2023-09-19 M2 中"当前掌子面前方 0-20 米范围……施工风险高"——将超前预报的未来推测性信息表达为确定的风险判断。2023-09-28 M2 中"前方 0-30 米范围预报为Ⅴ级围岩，存在围岩极破碎、稳定性差等风险，需重点关注"同样表现出过度确定性。M4 在两个日期上分别使用"前方 0-20 m 范围综合关注等级为高""建议保持审慎掘进"等提示性表述。

**（d）GRCI 使用边界问题。** 2023-09-28 M1 中出现"前方 30 米范围内，GRCI 数据可用数量为 2 个"——GRCI 不应出现在前方关注提示中。M4 严格将 GRCI 限定在 daily_review 章节。

#### 4.8.3 M4 如何通过证据约束避免这些错误

**（a）实际推进范围与对齐复核范围的区分。** 2023-09-19 M4 报告将推进量表述为"DK1013+219 至 DK1013+224，实际日进尺 5.0 m"，同时将复核范围表述为"用于已掘复核的 10m 对齐单元范围为 DK1013+210 至 DK1013+230"。两句话在同一段中出现但语义清晰分开，从文本层面规避了 E14 误写。

**（b）前方内容保持提示语义。** M4 的 forward_attention 章节在生成约束和校核反馈的双重作用下，自然使用"提示""关注""建议"等措辞。这不是靠 prompt 中一句"前方不得写为事实"就能稳定实现的——M2 和 M3 也有类似约束，但缺少自动校核和修订反馈时，该约束在 LLM 实际生成中难以被严格遵守。

**（c）Evidence Pack 对关键 claim 的支撑。** 2023-09-19 M4 共 49 条有效 claim，46 条获得 Trace 支撑。关键 trace 链路示例："当日 PLC 实测推进范围为 DK1013+219 至 DK1013+224"← `daily_plc_range`；"cell_1013220_1013230 呈现中等耦合关注度（GRCI=0.69）"← coupling review evidence；"前方 0-20 m 范围综合关注等级为高"← forward attention evidence。不同类型的表述分别由不同角色的证据支撑，并非 LLM 从多条来源混编后自由输出。

**（d）修订的效果。** 2023-09-19 M4 初稿 7 条未支撑表述 → 修订后 3 条（降低 57.1%）。2023-09-28 M4 初稿 7 条 → 修订后 1 条（降低 85.7%）。两个案例中 Section Guard 均未触发，说明修订保留了完整章节结构。

---

## 5 讨论

### 5.1 方法的核心价值

本文方法的价值不来自任何一个单一模块，而来自**证据组织、角色治理、生成约束和校核修订四个环节形成的完整链路**。这条链路的工程逻辑是：先将多源异构数据组织为空间对齐、角色分层的施工状态，再以此为基础约束 LLM 的文本生成，最后通过独立于 LLM 的自动校核机制检验生成结果并驱动修订。LLM 在这条链路中的角色是"在结构化证据和边界规则内的文本组织者"，而非"地质风险判断者"或"施工决策者"。

### 5.2 方法的局限性

**（1）单一工程数据，无跨工程泛化证据。** 91 天实验全部基于一个隧道项目。不同地质条件、不同 TBM 类型、不同施工单位配置下，本方法的性能是否保持，目前无实证支持。这是本文最重要的局限性。

**（2）指标权重为经验赋值，缺乏监督标定。** RAI（0.40/0.25/0.20/0.10/0.05）、GRS（0.45/0.45/0.10）、GRCI（0.55/0.35/0.10）的权重基于工程经验设定。Exp03 表明高关注 cell 排序对公式形式存在敏感性。在缺乏灾害事件记录、异常原因标签或现场复核标签的条件下，无法进行监督校准。这是启发式方法的固有局限。

**（3）自动评价不能替代人工专家评估。** 所有实验评价均为自动指标。自动 checker 判断"此 claim 在 Evidence Pack 中找不到匹配"与工程专家判断"此表述在工程意义上是否合理"，是两个不同层面的问题。尚未进行工程专家对 M1 和 M4 报告的盲评。

**（4）Trace 匹配存在粒度问题。** M4 的 381 条 unsupported claims（日均 4.19 条）中包含三类无法区分的情况：真正的无证据表述，证据存在但 trace 匹配算法未命中，以及合理的工程判断但无显式证据记录。这影响了 unsupported 指标的精确解释。

**（5）缺少外部基线和多模型对比。** M0-M4 为内部消融实验，未引入 RAG 基线、人工日报基线或多模型对比。消融实验可说明模块的相对贡献，但不直接等同于对所有替代方案的优势。所有 LLM 实验基于单一模型（deepseek-chat），模型行为差异未分析。

**（6）前方关注证据结构性薄弱。** 前方 cell 无 PLC 响应数据，完全依赖 TSP/HSP 地质预报。预报稀疏或置信度低时，M4 在前方章节的优势更多体现为"不将推测写成事实"而非"提供充分判断内容"。

### 5.3 后续工作

基于以上局限性，后续研究可沿以下方向开展：（1）在至少一个额外的 TBM 工程上部署本方法验证跨工程泛化能力；（2）邀请 2-3 位 TBM 施工领域专家对 M1 和 M4 生成的日报进行盲评，校准自动评价指标的生态效度；（3）引入 RAG 基线和人工日报基线扩展外部对比；（4）在获得专家标注的 cell 级关注标签后，对指标权重进行监督校准或贝叶斯更新；（5）探索 M0（常规统计章节）+M4（解释性章节）的混合生成策略，平衡稳定性和表达力；（6）优化 Trace 匹配算法粒度，降低误匹配导致的 unsupported 计数偏误。

---

## 6 结论

本文针对 TBM 施工日报自动生成中多源证据难以有效组织和约束的问题，提出了一种多源证据约束生成与可追溯校核方法。方法的核心是在 LLM 与多源数据之间建立两层中间结构——ConstructionStateCell 和 DailyConstructionTwin——将异构数据统一组织为空间对齐、角色分层的可追溯施工状态，并通过 Prompt Evidence Pack、Report Planner、Quality/Trace/Boundary Checker 和 Trace-Guided Revision 形成生成—校核—修订闭环。

基于 91 个施工日 × 5 种模式共 455 次真实 LLM 生成实验，完整闭环方法（M4）在质量分和证据支撑率上均明显优于直接 LLM 生成和原始证据输入等方法，未支撑表述降低 66.3%，数值错误降低 78.7%，E14 和缺失章节数均为 0，且 15/30/91 天稳定性一致。消融实验表明，结构化证据组织与校核修订闭环是保障生成质量的两个不可或缺的环节。

本文的工作存在单一工程数据、启发式权重和缺乏人工评估等局限。尽管如此，当前实验结果为"先组织证据、再约束生成、然后自动校核"这一工程生成方法论在 TBM 施工日报场景中的有效性提供了较为系统的实证支持，为工程文档的自动化可追溯生成提供了一条可行的技术路线。

---

## 附录：参考文献处理建议

### A. 可核实文献方向

以下方向存在真实文献，但需逐篇检索确认具体条目后替换当前引用：

- TBM 工况识别：基于推进速度、扭矩、推力的聚类/SVM 分类方法
- TBM 运行参数预测：深度神经网络预测推进速度、集成学习预测刀盘磨损
- 地质-TBM 耦合分析：围岩等级与运行参数统计关联研究
- 地下工程数字孪生：BIM 与 IoT 融合、隧道施工数字孪生框架
- LLM 工程文本生成：GPT 在施工日志/安全报告生成中的应用
- RAG：Lewis et al. (2020) Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks, NeurIPS
- 事实一致性/约束生成：FActScore (Min et al., 2023), NeuroLogic (Lu et al., 2021)

### B. 待系统检索与补充的方向

以下领域文献需根据目标期刊的学科定位进行系统检索：

- Tunnelling and Underground Space Technology / Automation in Construction 中 TBM 自动化、数字孪生、AI 应用方向文献
- 中文期刊（岩石力学与工程学报、隧道建设、岩土力学等）中 TBM 数据分析文献
- ACL/EMNLP/NAACL 中约束生成和事实一致性方向文献

---

## TODO 清单

1. [ ] 补充统计显著性检验：对 M4 vs M1 在 quality_score、grounding_rate、unsupported、numeric_error 上的逐日配对检验（建议 Wilcoxon signed-rank test），报告 p 值、效应量、置信区间
2. [ ] 绘制方法总体框架图（Figure 1）
3. [ ] 补充 M4 日均指标的均值 ± 标准差（Mean ± SD）
4. [ ] 完成 M4 boundary 3 案例的人工逐条复核并记录
5. [ ] 根据目标期刊调整参考文献格式和数量
6. [ ] 若目标期刊为英文，翻译全文；若为中文期刊，调整中英文摘要长度比例
7. [ ] 完成人工专家评估实验，补充评估结果
8. [ ] 根据目标期刊整理提交材料清单（图表源文件、补充材料等）
