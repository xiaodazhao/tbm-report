# 面向 TBM 施工日报的多源工程证据治理与可追溯大语言模型生成方法

> 论文完整初稿 v2。本文按 Automation in Construction / Advanced Engineering Informatics 类期刊 full-length article 的结构组织，重点突出“多源工程证据治理、施工状态孪生、Evidence Pack、结构化追溯、边界约束与大模型修订闭环”。  
> 当前版本用于论文主体逻辑审阅和后续英文翻译，不是最终投稿稿。参考文献编号、图表编号和部分人工复核材料仍需后续统一。

---

## 摘要

TBM 施工日报是连接现场感知数据、地质解释、施工管理和工程留痕的重要文档。随着 PLC 运行数据、超前地质预报、掌子面素描和气体监测等多源数据不断积累，传统依赖人工整理的日报编制方式面临效率低、证据追溯困难和表达边界不稳定等问题。大语言模型为施工日报自动生成提供了新的可能，但直接将施工数据输入模型生成报告，容易产生无证据表述、数值错误、前方预报事实化、地质关注指标概率化以及章节结构不稳定等问题。针对上述问题，本文提出一种面向 TBM 施工日报的多源工程证据治理与可追溯大语言模型生成方法。

该方法首先对 PLC 日运行数据进行时间与里程质量检查、停机识别、非停机样本异常过滤、有效掘进样本识别、连续工作区间切分和稳态段提取，在 10 m 里程单元内构建可解释的施工响应证据；同时对 TSP、HSP、掌子面素描等地质资料建立正式 evidence database，并通过时间可用过滤、空间相关筛选和证据角色分层，将地质证据划分为已掘复核、前方关注和局部背景三类。随后，系统以 10 m 里程单元为基本载体构建 ConstructionStateCell，并进一步形成 DailyConstructionTwin，用于组织当日施工范围、全部状态单元、高关注复核单元、前方关注单元、局部背景单元、治理规则和来源追踪。在此基础上，本文定义施工响应关注度 RAI、地质证据关注度 GRS 和地质-施工响应耦合关注度 GRCI 三类启发式指标，并明确 GRCI 仅用于已掘区段复核，不用于前方预测。

为了约束大语言模型生成，系统从 DailyConstructionTwin 中构建角色感知 Evidence Pack，使模型只消费经过筛选、压缩和边界标注的证据，而不直接读取原始 PLC CSV 或完整 evidence database。生成后，系统通过 Quality Checker、Grounding Checker、Boundary Checker 和 Structured Trace 对报告中的主张、数值、章节、证据支撑和语义边界进行自动核验，并将检查结果反馈给模型进行约束性修订。基于某 TBM 工程 91 个可用施工日期开展五种生成模式的真实大模型回归实验。结果表明，完整治理链路 M4 在所有 LLM 模式中取得最高平均质量分 94.18 和最高证据支撑率 0.9153，unsupported claims 总数为 376，numeric errors 总数为 78，E14 范围误写、boundary violations 和 missing sections 均为 0。与直接 LLM、原始证据输入 LLM 和仅 Evidence Pack LLM 相比，M4 分别将 unsupported claims 降低 67.1%、69.2% 和 70.1%，将 numeric errors 降低 82.5%、76.6% 和 65.5%。M4 自动修订机制将 unsupported claims 由 637 降至 376，降低 40.97%。指标稳健性实验进一步表明，当前 RAI/GRS/GRCI 与多种替代指标在整体排序上具有较高相关性，但 Top-K 高关注单元对耦合公式仍具有敏感性，因此 GRCI 应被限定为已掘复核关注指标，而非灾害概率或风险预测模型。

研究结果说明，将大语言模型置于多源工程证据治理、施工状态孪生、角色边界约束和结构化追溯评价框架内，可以显著提升 TBM 施工日报生成的稳定性、证据支撑性和工程表达安全性。本文方法并不将 LLM 作为地质风险判断器，而是将其作为受证据约束和可审计反馈驱动的工程文档生成接口。

**关键词**：TBM；施工日报；工程证据治理；施工状态孪生；大语言模型；Evidence Pack；结构化追溯；质量评价

---

## 1. 引言

TBM 施工过程具有数据来源多、施工状态变化快、地质条件不确定性强和现场决策链条长等特点。施工日报作为工程管理中的基础文档，需要记录当日推进范围、设备运行状态、地质揭露或预报信息、气体监测结果、施工异常和后续建议。与一般文本记录不同，TBM 施工日报中的关键表述通常具有明确的证据来源和工程边界。例如，实际日推进范围应来自 PLC 实测里程，前方关注提示应来自当前掌子面前方可用地质证据，已掘区段复核应同时结合施工响应和地质证据，而局部背景资料不能直接写成当日施工结论。

传统日报编制高度依赖工程人员人工读取 PLC 数据、地质报告和现场记录，再将其整理为自然语言文本。这种方式具有较强经验性，但也存在三个问题。第一，多源数据规模不断增大，人工逐日整理效率较低。第二，日报中每条结论和原始证据之间的追溯关系往往不显式，后续复盘和审计困难。第三，不同类型证据的空间和时间边界容易混用，例如将 10 m 里程单元对齐后的复核范围误写为实际推进范围，或将前方预报写成现场已揭露事实。

近年来，大语言模型在专业文本生成、信息组织和报告撰写中表现出较强能力。已有研究尝试将施工现场视频经计算机视觉提取的生产率信息输入 ChatGPT 自动生成施工日报，证明了“工程信息抽取 + 大语言模型生成”在施工文档自动化中的可行性。然而，施工日报生成并非普通自然语言生成任务。大语言模型虽擅长组织文字，但如果缺少结构化证据约束，容易生成看似合理但缺乏证据支撑的判断，或在数值、里程、前方提示和指标语义上产生错误。已有自动日报研究也指出，ChatGPT 可能出现信息不可靠、格式随机和历史信息受 token 限制等问题。对 TBM 场景而言，这些问题更加突出，因为 PLC 施工响应、地质预报、掌子面素描和气体监测具有不同的时空属性和证据角色。

因此，本文认为 TBM 施工日报自动生成的核心不应被简单理解为“让 LLM 写日报”，而应被建模为“多源工程证据约束下的可信知识生成与可审计文档生成”。在这一任务中，大语言模型不应直接读取原始数据并自由判断，而应在经过治理的证据包、明确的语义边界和自动化质量反馈下完成报告组织与修订。

为此，本文提出一种面向 TBM 施工日报的多源工程证据治理与可追溯大语言模型生成方法。其基本思想是：先将 PLC 日运行数据和多源地质资料转换为统一的 10 m 施工状态单元，再以 DailyConstructionTwin 组织当日施工范围、已掘复核、前方关注和局部背景证据；然后从 Twin 中构建角色感知 Evidence Pack，约束模板或大语言模型生成日报；最后通过 Quality、Grounding、Boundary 和 Structured Trace 对生成结果进行自动审计，并将错误反馈给模型完成修订。

本文主要贡献如下。

1. 提出面向 TBM 施工日报的多源工程证据治理框架，将 PLC、地质、气体和里程范围信息统一组织到 10 m 施工状态单元中，使日报生成建立在可追溯证据对象之上。
2. 构建 DailyConstructionTwin，将当日施工状态划分为已掘复核、前方关注和局部背景三类角色，避免地质背景、前方预报和当日复核事实在生成文本中混用。
3. 设计角色感知 Evidence Pack 和受控 LLM 生成机制，使模型只消费经过筛选、压缩和边界标注的证据，而不直接读取原始 PLC CSV 或完整 evidence database。
4. 构建 Quality、Grounding、Boundary 和 Structured Trace 协同评价体系，对 unsupported claims、numeric errors、E14 范围误写、边界违规和章节缺失进行自动检查，并驱动 LLM 修订。
5. 基于 91 个真实施工日期和五种生成模式开展实验，验证完整治理闭环相比直接 LLM、原始证据 LLM 和仅 Evidence Pack LLM 能显著提升报告质量和证据支撑性。

---

## 2. 相关工作

### 2.1 TBM 运行参数分析与施工状态识别

TBM 运行参数分析是隧道智能建造中的重要研究方向。已有研究通常围绕推进速度、推力、刀盘扭矩、刀盘转速、贯入度等关键参数开展运行状态识别、参数预测、异常检测和施工效率分析。相关研究表明，TBM 原始运行数据中包含停机、换步、辅助作业、低速过渡和异常采样等复杂状态，直接对全样本进行日均统计会掩盖真实掘进状态。因此，在构建施工响应指标之前，需要进行停机段剔除、异常值处理、有效掘进识别和稳态段提取。

本文吸收上述研究中关于运行数据清洗和稳态识别的思想，但不构建 TBM 参数预测模型，也不将 PLC 指标用于地质灾害监督学习预测。本文关注的是如何从 PLC 日运行数据中提取可用于日报生成和已掘复核的施工响应证据。换言之，PLC 处理的目标不是预测未来参数，而是在里程单元内区分停机、过渡、有效掘进和稳态掘进样本，形成可解释的施工响应证据。

### 2.2 多源地质证据与施工记录融合

TBM 施工地质信息通常来自 TSP、HSP、掌子面素描和现场揭露记录。不同证据具有不同来源、发布时间、空间范围、置信度和适用边界。若直接将地质资料整体输入报告生成系统，容易造成未来信息泄漏、远距离证据误用和前方预报事实化。因此，地质证据进入日报生成之前，需要完成标准化、时间可用性过滤、空间相关性筛选和角色分层。

本文将地质证据治理分为正式 evidence database 建立、证据记录标准化、时间过滤、空间投影和角色划分几个步骤。系统将证据划分为 daily_review、forward_attention 和 local_background 三类。其中，daily_review 用于当日已掘区段复核，forward_attention 仅用于当前掌子面前方关注提示，local_background 仅提供局部背景上下文。这种分层是后续 Evidence Pack 和边界检查的基础。

### 2.3 LLM 施工日报生成与可信评价

大语言模型具有较强的自然语言组织能力，已被用于施工文档生成、问答、合规检查和报告撰写等任务。Xiao 等提出了基于施工视频、计算机视觉和 ChatGPT 的施工日报自动生成框架，其流程为“现场视频 -> CV 活动识别与生产率分析 -> Prompt -> ChatGPT 日报生成 -> Web 系统展示”。该研究证明了 LLM 在施工日报生成中的可行性，但其重点是视频生产率信息抽取和用户体验评价，对工程证据边界、claim-level grounding、数值一致性和自动修订闭环的讨论相对有限。

从高风险文本生成场景看，医学报告、法律文书和工程报告均要求生成内容必须受到证据约束，并通过自动或人工复核验证 factual consistency。对 TBM 施工日报而言，评价重点不只是语言流畅性，还包括施工范围准确性、数值可追溯性、地质证据角色一致性、前方提示谨慎性和章节完整性。因此，本文不将 LLM 视为独立推理器，而将其嵌入“Evidence Pack 输入约束 + Quality/Grounding/Boundary 检查 + Structured Trace + Reviser”的闭环中。

### 2.4 研究缺口

综合已有研究，当前仍存在以下不足。第一，已有自动日报研究多关注单一来源信息抽取与自然语言生成，缺少面向 TBM 多源工程证据的统一治理框架。第二，已有 LLM 报告生成多依赖 prompt 约束和人工评价，缺少细粒度的证据角色、空间范围和数值边界检查。第三，已有方法较少将报告生成结果拆解为 claims，并自动判断每条 claim 是否具有结构化证据支撑。第四，对 TBM 场景特有的前方预报事实化、对齐复核范围误写、GRCI 概率化和 PLC proxy 误用等问题缺少专门控制。

本文即围绕上述缺口展开。

---

## 3. 方法

### 3.1 任务定义

给定施工日期 \(d\)，系统输入包括当日 PLC 日运行数据 \(P_d\)、截至该日可用的地质证据集合 \(G_{\le d}\)、气体监测字段和工程配置。目标是生成一份 TBM 施工日报 \(R_d\)，并同时输出质量评价、证据追踪和边界检查结果。

本文将该任务定义为证据约束文本生成问题，而非自由文本生成问题。对于报告中的任意关键主张 \(c_i\)，系统应能够回答：

1. 该主张是否来自可用证据；
2. 该主张涉及的时间、里程、数值和证据角色是否匹配；
3. 该主张是否混淆已掘复核、前方关注和局部背景；
4. 该主张是否越过方法边界，例如将 GRCI 写成灾害概率；
5. 如果主张存在问题，是否能通过反馈修订降低错误。

### 3.2 总体框架

本文方法由七层组成：

```text
----------------------------------------------------------------+
| 第 7 层：质量审计与反馈修订                                     |
| Quality / Grounding / Boundary / Structured Trace / Reviser     |
+----------------------------------------------------------------+
                              ↑
+----------------------------------------------------------------+
| 第 6 层：受控报告生成                                           |
| Template / LLM Generator / Prompt-level Planning / Revision      |
+----------------------------------------------------------------+
                              ↑
+----------------------------------------------------------------+
| 第 5 层：角色感知 Evidence Pack                                  |
| daily_review / forward_attention / local_background / constraints |
+----------------------------------------------------------------+
                              ↑
+----------------------------------------------------------------+
| 第 4 层：DailyConstructionTwin 日施工状态孪生                    |
| scope / cells / summaries / trace_index / governance             |
+----------------------------------------------------------------+
                              ↑
+----------------------------------------------------------------+
| 第 3 层：ConstructionStateCell 施工状态单元                      |
| position / operation / response / geology / gas / coupling / trace|
+----------------------------------------------------------------+
                 ↑                                ↑
+-------------------------------+  +-------------------------------+
| 第 2A 层：PLC 施工响应证据       |  | 第 2B 层：地质证据治理          |
| preprocessing / steady metrics |  | evidence_db / role filtering   |
+-------------------------------+  +-------------------------------+
                 ↑                                ↑
+----------------------------------------------------------------+
| 第 1 层：原始数据层                                               |
| PLC daily CSV / TSP / HSP / face sketch / gas fields              |
+----------------------------------------------------------------+
```

该框架的核心在于先治理证据，再生成文本。LLM 不直接读取原始 PLC CSV 或完整 evidence database，而只消费经过角色筛选、边界标注和压缩后的 Evidence Pack。

### 3.3 PLC 施工响应证据构建

#### 3.3.1 PLC 样本向量

对施工日期 \(d\)，原始 PLC 样本序列可表示为：

\[
P_d=\{p_i\}_{i=1}^{N_d}
\]

其中第 \(i\) 条样本为：

\[
p_i=(t_i,m_i,v_i,F_i,T_i,\omega_i,q_i,s_i,\mathbf{g}_i)
\]

表 1 给出各变量含义。

| 符号 | 中文含义 | 英文字段或工程含义 | 用途 |
|---|---|---|---|
| \(t_i\) | 运行时间 | time | 时间排序、时间间隔检查 |
| \(m_i\) | 里程 | chainage | 投影到 10 m cell |
| \(v_i\) | 推进速度 | advance speed | 稳态识别和速度统计 |
| \(F_i\) | 推力 | thrust | 停机识别和负载统计 |
| \(T_i\) | 刀盘扭矩 | cutterhead torque | 停机识别和负载统计 |
| \(\omega_i\) | 刀盘转速 | cutterhead rpm | 有效掘进识别和 proxy 计算 |
| \(q_i\) | 贯入度 | penetration | 贯入效率 proxy |
| \(s_i\) | 掘进状态 | operating state | 工作状态辅助判断 |
| \(\mathbf{g}_i\) | 气体字段 | gas readings | 气体监测分析 |

#### 3.3.2 时间与里程质量检查

时间质量检查用于识别时间倒序、长时间断点和异常采样间隔。相邻样本时间间隔为：

\[
\Delta t_i=t_i-t_{i-1}
\]

系统取正时间间隔的中位数 \(\widetilde{\Delta t}\)，并定义时间断点阈值：

\[
\tau_t=\max(3\widetilde{\Delta t},10)
\]

若 \(\Delta t_i>\tau_t\)，则将该位置标记为时间断点。时间断点不代表异常原因，但会触发连续有效掘进区间切分。

里程质量检查用于识别里程反向和里程突跳。相邻样本里程增量为：

\[
\Delta m_i=m_i-m_{i-1}
\]

当前规则采用：

\[
\epsilon_m=0.01,\quad J_m=5.0
\]

若 \(\Delta m_i<-\epsilon_m\)，标记为里程反向；若 \(|\Delta m_i|>J_m\)，标记为里程突跳。无法通过里程质量检查的样本不应参与 cell 聚合。

#### 3.3.3 停机识别与语义边界

PLC 中推力和刀盘扭矩为 0 或不可用时，该样本不应被视为有效掘进响应样本。因此定义：

\[
shutdown_i=(F_i\le0)\lor(T_i\le0)
\]

同时，推进速度和刀盘转速可辅助识别非有效掘进状态：

\[
auxiliary\_shutdown_i=(v_i\le0)\lor(\omega_i\le0)
\]

需要强调的是，当前 PLC 字段未可靠区分计划停机与非计划停机。因此，停机比例 stop_ratio 只能作为施工响应关注信号，不能直接解释为异常停机原因，也不能单独作为地质异常或设备故障的因果证据。

#### 3.3.4 非停机样本 3σ 异常过滤

异常点过滤只在非停机样本上进行。对核心参数：

\[
x\in\{v,F,T,\omega,q\}
\]

计算均值和标准差：

\[
\mu_x=\frac{1}{n}\sum x_i,\quad
\sigma_x=\sqrt{\frac{1}{n-1}\sum(x_i-\mu_x)^2}
\]

若有效样本数 \(n<30\)，则跳过该字段的 3σ 过滤。否则定义：

\[
outlier_{i,x}=
\begin{cases}
1, & x_i<\mu_x-3\sigma_x\ \text{or}\ x_i>\mu_x+3\sigma_x\\
0, & otherwise
\end{cases}
\]

样本级异常标记为：

\[
outlier_i=\bigvee_x outlier_{i,x}
\]

该步骤用于减少极端采样值对稳态指标的污染，不解释为工程异常原因。

#### 3.3.5 有效掘进样本识别

有效掘进样本定义为：

\[
\begin{aligned}
valid_i = &\neg shutdown_i \land \neg outlier_i \land chainage\_valid_i \\
&\land (F_i>0) \land (T_i>0) \\
&\land (v_i>0 \ \text{if available}) \\
&\land (\omega_i>0 \ \text{if available}) \\
&\land (is\_working_i=True \ \text{if existing})
\end{aligned}
\]

该规则不是简单判断“速度、推力、扭矩、转速大于 0”，而是在停机识别、异常过滤和里程质量检查之后再确定有效掘进样本。

#### 3.3.6 连续有效掘进区间与稳态段识别

有效样本进一步被切分为连续工作区间。当样本有效且前一有效样本不存在、前一样本无效、出现时间断点或里程反向时，开启新的工作区间：

\[
new\_interval_i=\neg valid_{i-1}\lor time\_gap_i\lor chainage\_reverse_i
\]

连续区间 \(I_k\) 的样本数和持续时间为：

\[
n_k=|I_k|,\quad D_k=\sum_{i\in I_k}\Delta t_i
\]

当前最小有效区间要求为：

\[
n_k\ge20,\quad D_k\ge30s
\]

在连续有效区间内，系统优先使用推进速度 \(v_i\) 作为稳态检测信号；若推进速度不可用，则使用贯入度 \(q_i\) 作为备用信号。设：

\[
y_i=v_i
\]

或在 fallback 情况下：

\[
y_i=q_i
\]

滚动均值为：

\[
\bar{y}^{(w)}_i=\frac{1}{w}\sum_{j=i-w+1}^{i}y_j
\]

其中 \(w=20\)，最小窗口样本数为 5。稳态候选阈值定义为：

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

若存在多个候选稳态段，则按样本数最多、持续时间最长、覆盖里程最长、出现时间最早的优先级选择。稳态段最低要求同样为 \(n_{steady}\ge20\) 且 \(D_{steady}\ge30s\)。若无稳态段但有效工作样本足够，则使用 working-only fallback，并记录降级标记。

#### 3.3.7 10 m cell 稳态施工响应指标

以 \(L=10m\) 为默认 cell 长度，第 \(c\) 个里程单元为：

\[
C_c=[a_c,b_c),\quad b_c-a_c=L
\]

属于该 cell 的样本集合为：

\[
P_c=\{p_i|m_i\in C_c\}
\]

有效掘进样本集合和稳态样本集合分别为：

\[
W_c=\{p_i\in P_c|valid_i=1\}
\]

\[
S_c=\{p_i\in P_c|paper\_plc\_stage_i=steady\_state\}
\]

主要覆盖指标包括：

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
\frac{\sigma_{c,x}}{|\mu_{c,x}|}, & |\mu_{c,x}|>10^{-6}\\
null, & otherwise
\end{cases}
\]

负载与贯入关系 proxy 定义为：

\[
power\_proxy_c=\mu_{c,T}\cdot\mu_{c,\omega}
\]

\[
thrust\_per\_penetration_c=\frac{\mu_{c,F}}{\mu_{c,q}},\quad \mu_{c,q}>10^{-6}
\]

\[
torque\_per\_penetration_c=\frac{\mu_{c,T}}{\mu_{c,q}},\quad \mu_{c,q}>10^{-6}
\]

上述 proxy 仅用于解释已掘区段施工响应，不能写成严格物理功率、严格比能或地质异常因果证据。

### 3.4 地质证据库建立与证据治理

本文中的 evidence database 不是原始输入，而是由 TSP、HSP、掌子面素描等地质资料经解析、清洗、去重和标准化后形成的正式证据库。每条地质证据可表示为：

\[
g_j=(id_j,type_j,t_j,[s_j,e_j],text_j,conf_j)
\]

其中 \(id_j\) 为证据编号，\(type_j\) 为来源类型，\(t_j\) 为证据可用时间，\([s_j,e_j]\) 为空间范围，\(text_j\) 为证据文本，\(conf_j\) 为置信度或可靠性描述。

时间可用约束为：

\[
time\_valid(g_j,d)=
\begin{cases}
1, & t_j\le d\\
0, & t_j>d
\end{cases}
\]

空间重叠长度定义为：

\[
L_{j,c}=\max(0,\min(e_j,b_c)-\max(s_j,a_c))
\]

cell 归一化重叠比为：

\[
R_{j,c}^{cell}=\frac{L_{j,c}}{b_c-a_c}
\]

证据角色根据其与当日已掘复核范围、当前掌子面前方范围和局部背景范围的关系划分：

\[
role(g_j)=
\begin{cases}
daily\_review, & overlap(g_j,daily\_scope_d)\\
forward\_attention, & overlap(g_j,forward\_scope_d)\\
local\_background, & overlap(g_j,background\_scope_d)\\
excluded, & otherwise
\end{cases}
\]

其中，forward_attention 范围为当前掌子面前方 0-30 m，并进一步划分为 0-10 m、10-20 m 和 20-30 m 三个距离带。该角色划分保证了前方地质证据只作为关注提示，不被写成当日已发生事实。

### 3.5 ConstructionStateCell

ConstructionStateCell 是本文的核心中间对象。每个 10 m cell 可表示为状态向量：

\[
C_c=(P_c,O_c,R_c,G_c,F_c,A_c,Q_c,T_c)
\]

各分量含义如下。

| 分量 | 中文含义 | 主要内容 |
|---|---|---|
| \(P_c\) | 位置状态 | 起止里程、中心里程、与掌子面距离、cell 角色 |
| \(O_c\) | 运行状态 | 停机、异常、聚类或运行状态摘要 |
| \(R_c\) | 施工响应状态 | PLC 指标、稳态指标、RAI |
| \(G_c\) | 地质状态 | 地质证据、GRS、hazards、source trace |
| \(F_c\) | 前方状态 | forward distance band、前方距离权重 |
| \(A_c\) | 气体状态 | 气体监测与报警上下文 |
| \(Q_c\) | 耦合状态 | GRCI、耦合等级、可用性 |
| \(T_c\) | 追踪状态 | evidence ids、source_trace、trace completeness |

cell 角色决定不同证据和指标的使用边界。

| 指标或证据 | daily_review | forward_attention | local_background |
|---|---:|---:|---:|
| PLC 稳态指标 | 可用 | 禁止 | 不作为当日结论 |
| RAI | 可用 | 禁止 | 不作为当日结论 |
| GRS | 可用 | 可用于前方关注提示 | 可作背景 |
| GRCI | 可用 | 禁止 | 禁止 |
| source_trace | 可用 | 可用 | 可用 |
| 报告语气 | 复核 | 提示 | 背景 |

### 3.6 DailyConstructionTwin

DailyConstructionTwin 是某一施工日期的状态容器，包括：

```text
scope
cells
daily_review_cells
forward_attention_cells
local_background_cells
high_grci_cells
summaries
trace_index
governance
```

其中 scope 描述实际 PLC 推进范围和 10 m 对齐复核范围。需要明确区分：

\[
daily\_advance_m=m_{max}-m_{min}
\]

\[
daily\_excavated\_scope=
\left[
\left\lfloor \frac{m_{min}}{10}\right\rfloor 10,
\left\lceil \frac{m_{max}}{10}\right\rceil 10
\right]
\]

daily_plc_range 和 daily_advance_m 才表示 PLC 实测推进范围和推进量；daily_excavated_scope 只是 10 m cell 对齐后的已掘复核范围，不得写成实际推进范围。

### 3.7 RAI、GRS 和 GRCI

#### 3.7.1 RAI：施工响应关注度

RAI 表示已掘 cell 内 PLC 施工响应关注程度，公式为：

\[
RAI=0.40S+0.25A+0.20D+0.10V_T+0.05V_v
\]

其中：

| 符号 | 中文含义 | 字段 |
|---|---|---|
| \(S\) | 停机比例 | stop_ratio |
| \(A\) | 异常样本比例 | abnormal_ratio |
| \(D\) | 速度下降分数 | speed_drop_score |
| \(V_T\) | 扭矩波动分数 | torque_volatility_score |
| \(V_v\) | 速度波动分数 | speed_volatility_score |

RAI 是施工响应关注信号，不是故障概率、地质风险概率或异常原因判断。

#### 3.7.2 GRS：地质证据关注度

GRS 表示 cell 内地质证据关注程度：

\[
GRS=0.45G+0.45H+0.10C
\]

其中 \(G\) 为围岩或地质等级分量，\(H\) 为 hazard 标签分量，\(C\) 为证据置信分量。若 cell 缺少空间相关地质证据，则 GRS_available 为 false。此时 GRS=0 不能解释为地质关注低，而应解释为缺少可用地质证据。

#### 3.7.3 GRCI：已掘区段地质-施工响应耦合关注度

GRCI 用于 daily_review cell 的已掘复核排序：

\[
GRCI=0.55GRS+0.35RAI+0.10GRS\cdot RAI
\]

GRCI 可用条件为：

\[
GRCI\_available=daily\_review\land RAI\_available\land GRS\_available
\]

若 cell 为 forward_attention 或 local_background，则：

\[
GRCI\_available=False
\]

GRCI 不是灾害概率、不是前方风险预测、不是因果判断，只是已掘区段地质证据和施工响应共同偏高时的复核关注指标。

### 3.8 Evidence Pack 选择机制

Evidence Pack 不是原始数据堆叠，而是从 DailyConstructionTwin 中选择可用于报告生成的角色化证据。daily_review cell 的选择分数为：

\[
Score_{review}=
\frac{0.40GRCI+0.25RAI+0.25GRS+0.10TC}{\sum w_{available}}
\]

其中 \(TC\) 为 trace completeness。

forward_attention cell 不使用 RAI 和 GRCI，其选择分数为：

\[
Score_{forward}=
\frac{0.45GRS+0.25W_f+0.20C_e+0.10TC}{\sum w_{available}}
\]

其中 \(W_f\) 为前方距离权重，\(C_e\) 为证据置信度。当前距离权重为：

| 距掌子面距离 | 中文含义 | 权重 |
|---|---|---:|
| 0-10 m | 近前方 | 1.0 |
| 10-20 m | 短前方 | 0.7 |
| 20-30 m | 扩展前方 | 0.4 |

local_background 选择分数为：

\[
Score_{background}=
\frac{0.50GRS+0.25C_e+0.25TC}{\sum w_{available}}
\]

Evidence Pack 同时包含 generation constraints，用于明确禁止大模型将 forward_attention 写成已发生事实、将 GRCI 写成概率、将 PLC proxy 写成严格物理量、将 daily_excavated_scope 写成实际推进范围。

### 3.9 LLM 生成、追踪与修订闭环

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
根据 Quality/Grounding/Boundary/Structured Trace 反馈修订文本。
```

报告文本可拆解为 claim 集合：

\[
R_d=\{c_i\}_{i=1}^{M}
\]

每条 claim 可表示为：

\[
c_i=(type_i,entity_i,value_i,range_i,time_i,role_i)
\]

若存在证据 \(e_j\in E_d\) 满足内容、范围和角色匹配，则该 claim 被认为 grounded：

\[
grounded(c_i)=
\exists e_j\in E_d:
match(c_i,e_j)=1
\land role(c_i)=role(e_j)
\land scope(c_i)\subseteq scope(e_j)
\]

证据支撑率为：

\[
grounding\_rate=\frac{\sum_i grounded(c_i)}{M}
\]

M4 修订可形式化为：

\[
R_d^{final}=Revise(R_d^{draft},F_d,E_d,C_d)
\]

其中 \(F_d\) 为质量、追踪和边界反馈，\(E_d\) 为 Evidence Pack，\(C_d\) 为生成约束。修订目标是删除无证据句、降级过强判断、纠正数值范围、保留标准章节并避免边界越界。

### 3.10 质量评价体系

Quality score 从 100 分开始，根据错误和缺陷扣分：

\[
Q=100-P_{error}-P_{warning}-P_{section}-P_{grounding}
\]

低 grounding rate 扣分规则为：

\[
P_{grounding}=
\begin{cases}
20, & grounding\_rate<0.6\\
10, & 0.6\le grounding\_rate<0.8\\
0, & grounding\_rate\ge0.8
\end{cases}
\]

Boundary Checker 重点识别以下边界问题：

| 类型 | 含义 |
|---|---|
| forward_fact_misuse | 将前方关注写成已发生事实 |
| grci_probability_misuse | 将 GRCI 写成灾害概率或风险概率 |
| plc_proxy_misuse | 将 proxy 写成严格物理功率或比能 |
| stop_causality_misuse | 将 stop_ratio 直接解释为异常原因 |
| local_background_scope_misuse | 将背景证据写成当日结论 |
| E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE | 将 10 m 对齐复核范围写成实际推进范围 |

---

## 4. 实验设计

### 4.1 数据与研究对象

本文基于某 TBM 工程 91 个具备可用 PLC 日运行数据、并可通过证据治理流程组织当日施工与地质证据的施工日期开展实验。所有实验均在固定数据、固定 prompt、固定 checker 和固定评价指标口径下运行。本文不声称跨工程泛化，实验结论限定在本工程可用日期范围内。

### 4.2 生成模式设计

为分析不同证据治理强度对报告质量的影响，本文设置五种模式：

| 模式 | 中文说明 | 作用 |
|---|---|---|
| M0_template_only | 确定性模板基线 | 提供稳定格式基准，不评价自由生成能力 |
| M1_direct_llm | 直接 LLM 生成 | 检查直接使用 LLM 的风险 |
| M2_raw_evidence_llm | 原始证据输入 LLM | 检查“只给更多材料”是否足够 |
| M3_twin_evidence_pack_llm | ConstructionStateCell + Evidence Pack | 检查结构化证据包的作用 |
| M4_full_twin_governance_trace_boundary_reviser | 完整治理链路 | 验证 Evidence Pack + Boundary + Structured Trace + Reviser 闭环 |

M1 -> M2 -> M3 -> M4 是逐步增加证据输入、结构化证据组织、边界约束、质量检查与自动修订机制的递进式设计，因此该实验不仅是生成模式对比，也可作为模块贡献分析。M0 作为非 LLM 模板基线，不参与自由生成能力比较。

### 4.3 评价指标

评价指标包括：

| 指标 | 中文含义 | 趋势 |
|---|---|---|
| quality mean | 平均质量分 | 越高越好 |
| grounding mean | 平均证据支撑率 | 越高越好 |
| unsupported total | 未支撑表述总数 | 越低越好 |
| numeric total | 数值错误总数 | 越低越好 |
| E14 total | 对齐复核范围误写总数 | 越低越好 |
| boundary total | 边界违规总数 | 越低越好 |
| missing sections total | 缺失章节总数 | 越低越好 |

此外，对 M4 记录修订前后 unsupported claims 变化，用于衡量反馈修订机制是否有效。

### 4.4 指标稳健性实验

由于 RAI/GRS/GRCI 为工程启发式指标，本文另设 Exp03 指标稳健性实验，构建 V0-V5 六种版本：

| 版本 | 含义 |
|---|---|
| V0_current | 当前主流程公式 |
| V1_percentile_equal | 分位数标准化 + 均权 |
| V2_percentile_interaction | 分位数标准化 + 交互耦合 |
| V3_percentile_entropy | 分位数标准化 + 熵权 |
| V4_percentile_critic | 分位数标准化 + CRITIC |
| V5_strict_min | 严格 min 耦合 |

比较指标包括 Top-K Jaccard、Spearman rank correlation、high attention date overlap 和 forward GRCI leakage。

---

## 5. 结果与分析

### 5.1 91 天生成模式对比结果

91 天全量实验共包含 455 个 date-mode 组合，failed_count 为 0。表 2 给出五种模式的总体结果。

| 模式 | 生成设置 | 平均质量分 | 证据支撑率 | 未支撑表述 | 数值错误 | E14 | 边界违规 | 缺失章节 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | 确定性模板基线 | 100.00 | 1.0000 | 0 | 0 | 0 | 0 | 0 |
| M1 | 直接 LLM 生成 | 70.76 | 0.7295 | 1143 | 445 | 0 | 10 | 182 |
| M2 | 原始证据输入 LLM | 72.96 | 0.7253 | 1221 | 334 | 0 | 23 | 182 |
| M3 | ConstructionStateCell + Evidence Pack | 68.93 | 0.7592 | 1256 | 226 | 0 | 2 | 184 |
| M4 | 完整治理链路 | 94.18 | 0.9153 | 376 | 78 | 0 | 0 | 0 |

结果表明，M4 在所有 LLM 模式中取得最高平均质量分和最高证据支撑率，同时在 unsupported claims、numeric errors、boundary violations 和 missing sections 上均显著低于 M1、M2 和 M3。M4 的 E14 为 0，说明完整治理链路有效控制了将 10 m 对齐复核范围误写为实际推进范围的问题。

需要说明的是，M0 模板生成的质量分和证据支撑率最高，主要因为其直接填充结构化字段，不涉及自由文本扩展。该指标不能理解为模板方法具有更强的自然语言生成能力。

### 5.2 M4 相比 LLM 基线的提升

M4 相比 M1/M2/M3 的 unsupported 降低幅度分别为 67.1%、69.2% 和 70.1%；numeric error 降低幅度分别为 82.5%、76.6% 和 65.5%。

| 对比 | unsupported 降低 | numeric 降低 |
|---|---:|---:|
| M4 vs M1 | 67.1% | 82.5% |
| M4 vs M2 | 69.2% | 76.6% |
| M4 vs M3 | 70.1% | 65.5% |

逐日配对统计进一步表明，M4 相比 M1、M2 和 M3 在 quality、grounding、unsupported 和 numeric 四类指标上均呈现显著改善。以 M4 vs M1 为例，quality 平均提升 23.42，grounding 平均提升 0.1858，unsupported 平均每日报告降低 8.43 条，numeric 平均每日报告降低 4.03 条，单侧 Wilcoxon 检验 p 值均远小于 0.001，效应量为极强。

### 5.3 M3 与 M4 的差异

M3 已经引入 ConstructionStateCell 和 Evidence Pack，其 grounding mean 高于 M1/M2，说明结构化证据包能够增强报告与证据之间的关联。然而 M3 的 quality mean 较低，unsupported total 和 missing sections total 仍然偏高。这说明仅将结构化证据提供给 LLM 并不足以保证最终报告质量。模型在复述更多细节时，仍可能产生数值无支撑、过强地质判断或章节缺失。

M4 在 M3 基础上进一步加入 prompt-level planning、boundary constraints、structured trace、quality feedback 和 reviser。结果显示，M4 相比 M3 将 unsupported 降低 70.1%，numeric 降低 65.5%，并将 missing sections 从 184 降至 0。这表明后端治理链路对最终报告质量具有关键贡献。

### 5.4 自动修订效果

M4 自动修订机制在 91 天中全部触发并成功执行。修订前 unsupported claims 总数为 637，修订后为 376，减少 261 条，降低 40.97%。

| 修订触发次数 | 修订前 unsupported | 修订后 unsupported | 减少数量 | 降低率 |
|---:|---:|---:|---:|---:|
| 91 | 637 | 376 | 261 | 40.97% |

该结果说明，M4 的修订阶段不是简单润色，而是基于质量检查和证据追踪反馈，对证据不足、数值不严谨或边界不清的内容进行约束性改写。

### 5.5 边界安全性

M4 在 91 天实验中 E14 total、boundary total 和 missing sections total 均为 0，说明当前版本在三个方面表现稳定。第一，系统没有将 daily_excavated_scope 或 10 m 对齐复核范围写成实际推进范围。第二，系统没有出现前方事实误用、GRCI 概率化、PLC proxy 物理量误用等边界违规。第三，修订后报告保持了标准章节完整性。

这一结果与 M1/M2/M3 形成对比。M1 和 M2 分别出现 10 和 23 条 boundary violations，且均存在 182 个缺失章节；M3 虽然 boundary 降至 2，但仍有 184 个缺失章节。说明 Evidence Pack 有助于减少边界违规，但要保持章节完整和输出稳定，仍需要 M4 的完整治理闭环。

### 5.6 指标稳健性分析

Exp03 结果显示，V1-V5 与当前 V0 的 Spearman 排序相关如下：

| 变体 | 中文解释 | Spearman |
|---|---|---:|
| V1 | 分位数标准化 + 均权 | 0.9317 |
| V2 | 分位数标准化 + 交互耦合 | 0.8772 |
| V3 | 分位数标准化 + 熵权 | 0.8787 |
| V4 | 分位数标准化 + CRITIC | 0.8886 |
| V5 | 严格 min 耦合 | 0.8168 |

整体排序相关性较高，说明当前 V0 指标并非完全依赖某一特定权重形式。然而 Top-K Jaccard 显示，高关注 cell 的精确选择对耦合形式仍较敏感。例如 V1 与 V0 的 Top-50 Jaccard 为 0.7241，而 V5 strict_min 与 V0 的 Top-50 Jaccard 为 0.4286。因此，本文将 GRCI 明确限定为已掘区段复核关注指标，而非灾害概率或经过监督标定的风险预测模型。

### 5.7 典型案例与残余问题

在典型日期中，M4 相比 M1/M2/M3 通常表现出更完整的章节结构、更清晰的证据支撑和更保守的前方提示表达。然而少数日期仍存在残余 unsupported 或 numeric 错误。这些错误可能来自证据粒度不足、trace 匹配严格、数值表达复杂或 LLM 修订不完全。本文方法应被定位为 evidence-grounded report generation and audit framework，而不是完全替代工程师判断的自动决策系统。

---

## 6. 讨论

### 6.1 为什么需要证据治理而不仅是 prompt engineering

已有研究表明，更详细的 prompt 通常能改善 LLM 报告生成质量。但 TBM 日报中的核心问题不是“信息是否足够多”，而是“信息是否被赋予正确角色”。若直接向 LLM 输入大量原始证据，模型仍可能混用远距离地质资料、前方预报和已掘事实。本文实验中 M2 和 M3 的表现说明，输入更多证据或结构化证据并不必然带来更高质量；只有当 Evidence Pack、边界规则、structured trace 和修订反馈共同工作时，生成结果才显著稳定。

### 6.2 LLM 在本文方法中的角色

本文不将 LLM 作为地质风险推理器，而将其作为证据约束下的文档组织与修订接口。所有关键指标和证据角色在 LLM 之前已经由数据治理链路确定。LLM 的任务是在给定 Evidence Pack 中组织自然语言，并根据自动评价反馈删除、降级或改写不合规表述。这种定位可以降低 LLM 幻觉对工程文档的影响。

### 6.3 对施工管理的意义

本文方法的实践价值在于，它不仅输出日报文本，还同时输出 Evidence Pack、DailyConstructionTwin、Quality Summary、Trace Summary 和 Boundary Summary。工程人员可以看到报告中的关键句子来自哪些 cell、哪些地质证据和哪些 PLC 统计结果。这使日报从单纯文本结果转变为可审计工程文档。

### 6.4 局限性

本文仍存在以下局限。第一，实验基于单一 TBM 工程的 91 个可用日期，不能直接外推为跨工程泛化结论。第二，当前缺少灾害发生标签、异常原因标签和现场复核标签，因此 RAI/GRS/GRCI 不能进行监督学习式权重校准，也不能写成预测准确率。第三，自动评价指标依赖文本切分、证据匹配和规则判断，可能存在误伤或漏检，不能完全替代人工工程复核。第四，PLC proxy 指标并非严格物理功率或比能，只能作为施工响应解释变量。第五，当前系统未重新解释 TSP/HSP 原始探测信号，而是基于已整理的地质证据记录开展治理。

---

## 7. 结论

本文提出了一种面向 TBM 施工日报的多源工程证据治理与可追溯大语言模型生成方法。该方法以 PLC 施工响应和多源地质证据为输入，通过 10 m 里程单元构建 ConstructionStateCell，并进一步形成 DailyConstructionTwin 和 Evidence Pack，使大语言模型在结构化证据和明确边界约束下生成日报。针对大模型输出中的无证据表述、数值错误、边界越界和章节缺失问题，本文构建 Quality、Grounding、Boundary 和 Structured Trace 检查机制，并将检查结果反馈给模型进行修订。

91 天真实 LLM 回归实验表明，完整治理链路 M4 在所有 LLM 模式中取得最佳表现。M4 的平均质量分为 94.18，证据支撑率为 0.9153，unsupported total 为 376，numeric total 为 78，E14、boundary 和 missing sections 均为 0。与 M1/M2/M3 相比，M4 显著降低 unsupported 和 numeric 错误。自动修订机制将 unsupported claims 从 637 降至 376，降低 40.97%。

指标稳健性实验表明，当前 RAI/GRS/GRCI 指标在整体排序上与多种替代方案保持较高相关性，但高关注 cell 的精确选择仍受耦合公式影响。因此，本文将其定位为启发式复核关注指标，而不是灾害概率或监督预测模型。

未来工作将补充人工复核与专家评价，进一步验证自动指标与工程可读性的关系；同时在更多工程数据上验证方法泛化能力，并结合现场标签或专家标定优化 RAI/GRS/GRCI 权重。

---

## 参考文献占位说明

正式投稿前需补齐并统一格式化以下文献：

1. TBM 运行参数预测、稳态识别、异常过滤和贯入效率分析相关文献；
2. TSP/HSP/掌子面素描等地质证据在隧道施工中的应用文献；
3. 施工日报自动生成、计算机视觉 + LLM 施工文档生成文献，例如 Xiao et al. 2024；
4. 医学或工程报告中的 factual consistency、grounding、report revision 和自动评价文献；
5. 熵权法、CRITIC 和多指标稳健性分析相关方法文献。

---

## 建议图表清单

| 编号 | 内容 | 当前可用材料 |
|---|---|---|
| 图 1 | 总体框架图 | 需重新绘制 |
| 图 2 | PLC 预处理与稳态施工响应证据构建 | 需重新绘制 |
| 图 3 | 地质证据库建立与角色分层 | 需重新绘制 |
| 图 4 | ConstructionStateCell 与 DailyConstructionTwin 结构 | 需重新绘制 |
| 图 5 | Evidence Pack 与 LLM 治理闭环 | 需重新绘制 |
| 图 6 | M0-M4 平均质量分对比 | `paper_materials/01_exp02_results/figures/fig_exp02_quality_by_mode.png` |
| 图 7 | M0-M4 证据支撑率对比 | `paper_materials/01_exp02_results/figures/fig_exp02_grounding_by_mode.png` |
| 图 8 | M0-M4 unsupported 对比 | `paper_materials/01_exp02_results/figures/fig_exp02_unsupported_by_mode.png` |
| 图 9 | M0-M4 numeric 对比 | `paper_materials/01_exp02_results/figures/fig_exp02_numeric_by_mode.png` |
| 图 10 | M4 修订前后 unsupported 对比 | `paper_materials/01_exp02_results/figures/fig_exp02_m4_revision_pre_post.png` |
| 图 11 | Exp03 Spearman 相关性 | `paper_materials/04_indicator_robustness/figures/fig_exp03_spearman_correlation.png` |
| 表 1 | PLC 样本向量与变量含义 | 本文已给出 |
| 表 2 | 91 天主实验结果 | 本文已给出 |
| 表 3 | M4 相比基线改进幅度 | 本文已给出 |
| 表 4 | M4 修订效果 | 本文已给出 |
| 表 5 | Exp03 指标稳健性结果 | 本文已给出 |
