# 结构化证据、报告主张与可追溯核验增强说明

本文档说明本轮新增的结构化证据核验能力。该增强不改变 TBM 日报主流程、不改变 RAI / GRS / GRCI 公式、不改变原有 `quality_score` 评分口径，也不替换既有 Evidence Pack 字段；它是在现有系统旁边增加一层更细的审计结构，用于支撑论文中“证据约束生成与可追溯质量评价”的方法表述。

## 1. 增强目标

原系统已经可以完成：

```text
ConstructionStateCell
-> Evidence Pack
-> 报告生成
-> Quality / Grounding / Trace
```

但原有核验结构偏工程化，主要判断某个句子是否 `grounded`，以及使用哪类 `support_type`。对于论文方法表达来说，还需要进一步回答：

```text
1. 报告中的一个句子具体声称了什么？
2. 它指向哪个实体、数值、时间范围和空间范围？
3. 哪些证据单元支撑了它？
4. 如果不支撑，究竟是缺证据、范围不匹配、角色混用，还是数值不匹配？
5. 这个错误属于高、中、低哪一类严重性？
6. 报告是否覆盖了 Evidence Pack 中应当出现的关键事实？
```

因此本轮新增四类结构：

```text
EvidenceUnit
ReportClaim
ClaimEvidenceTrace
Error severity / required fact coverage
```

## 2. 新增结构一：EvidenceUnit

`EvidenceUnit` 是从 Evidence Pack 中派生出来的“原子证据单元”。它不是替代原 Evidence Pack，而是把原来分散在 `daily_review`、`forward_attention`、`local_background` 中的 cell 证据整理成统一格式。

### 2.1 字段含义

| 字段 | 中文含义 | 说明 |
|---|---|---|
| `evidence_id` | 证据单元编号 | 例如 `daily_review:cell_...` |
| `source_type` | 证据来源类型 | 来自 source_trace，如 HSP、TSP、face sketch；没有时为 `cell_state` |
| `time_scope` | 时间范围 | 当前主要记录报告日期和 time available |
| `spatial_scope` | 空间范围 | cell id、起止里程、中心里程、距掌子面距离 |
| `role` | 证据角色 | `daily_review`、`forward_attention`、`local_background` |
| `entity` | 证据实体 | 已掘复核 cell、前方关注 cell、本地背景 cell |
| `state` | 证据状态 | coupling level、forward attention、background 等 |
| `certainty` | 确定性等级 | 根据 confidence 粗分为 high / medium / low / unknown |
| `support_value` | 支撑值 | 保存 GRS、RAI、GRCI、hazards、distance 等关键数值 |
| `allowed_expression` | 允许表达 | 说明该证据能支持什么类型的文字表达 |
| `source_ref` | 来源引用 | supporting evidence ids、trace refs、source trace |

### 2.2 三类证据角色

| 角色 | 可以支撑什么 | 不能支撑什么 |
|---|---|---|
| `daily_review` | 已掘区段复核、GRCI 耦合关注、PLC 施工响应证据 | 前方已发生事实、灾害概率 |
| `forward_attention` | 当前掌子面前方关注提示、GRS / source_trace 支撑的前方提示 | GRCI、高风险事实、PLC 响应异常 |
| `local_background` | 本地地质背景说明 | 当日施工异常、当日高 GRCI 结论 |

### 2.3 对主流程的影响

`evidence_units` 已加入 Evidence Pack 输出，但没有替换：

```text
geology_evidence.key_cells
geology_evidence.selected_cells
daily_review_evidence
forward_attention_evidence
local_background_evidence
coupling_evidence
source_trace
```

同时，当前 `render_evidence_pack_text()` 没有把完整 `evidence_units` 渲染进 prompt，因此不会突然增大 prompt，也不会改变已有 LLM 实验口径。

## 3. 新增结构二：ReportClaim

原 claim extractor 主要输出：

```text
claim_id
text
claim_type
range_dk
relative_range
hazards
metrics
gases
spatial_scope
sentence_index
warnings
```

本轮在保留这些旧字段的基础上新增结构化字段：

| 字段 | 中文含义 | 作用 |
|---|---|---|
| `claim_text` | 主张文本 | 与旧字段 `text` 保持一致，作为正式字段 |
| `entity` | 主张实体 | 如 GRCI、RAI、PLC、气体、hazard、metric |
| `value` | 数值 | 从句子中提取第一个显著数值 |
| `unit` | 单位 | 如 m、%、min、kN、rpm 等 |
| `time_scope` | 时间范围 | daily、report date、forward available evidence、unspecified |
| `spatial_scope_detail` | 细化空间范围 | 包含原 spatial scope、DK 范围、相对前方范围 |
| `claim_role` | 主张角色 | daily review、forward attention、statistical summary、recommendation 等 |
| `certainty` | 表达确定性 | asserted、cautious、policy boundary |
| `source_sentence_index` | 原句序号 | 与旧字段 `sentence_index` 兼容 |

## 4. 新增结构三：Claim-Evidence Trace

原 grounding checker 已经输出：

```text
grounded
support_type
trace_support_type
supporting_evidence_ids
source_trace
messages
suggestions
severity
```

本轮新增：

| 字段 | 中文含义 | 说明 |
|---|---|---|
| `aligned_evidence_ids` | 对齐证据编号 | 从 supporting evidence 或 source_trace 中整理 |
| `support_status` | 支撑状态 | `supported`、`partially_supported`、`unsupported` |
| `mismatch_type` | 不匹配类型 | `none`、`missing_evidence`、`scope_mismatch`、`role_mismatch`、`numeric_or_metric_mismatch`、`overclaim`、`policy_boundary` |
| `confidence` | 支撑置信度 | 当前为规则化分值：supported=1.0，partial=0.6，unsupported=0.0 |
| `reason` | 判断原因 | 由 grounding messages 汇总得到 |

这一步的意义是把“这句话没有支撑”进一步细分为：

```text
缺少证据
空间范围不匹配
证据角色不匹配
数值或指标不匹配
表达过强
方法边界说明
```

这比单纯统计 unsupported claim 更适合论文中的错误分析和案例复盘。

## 5. Error Taxonomy 严重性分级

原系统已有 E1-E14 错误类型。本轮为每类错误增加了元信息：

```text
taxonomy_severity: high / medium / low
taxonomy_penalty: 审计用 penalty
engineering_significant: 是否属于工程表达关键错误
```

### 5.1 示例

| 错误类型 | 语义 | 严重性 |
|---|---|---|
| E2 | 前方预报写成已发生事实 | high |
| E3 | GRCI 写成灾害概率 | high |
| E4 | forward attention 写成已掘复核 | high |
| E6 | 气体字段误用 | high |
| E14 | 对齐复核范围误写成实际推进范围 | high |
| E1 | 普通无证据主张 | medium |
| E10 | 数值无证据 | medium |
| E12 | 方法边界说明 | low，且 penalty 为 0 |

### 5.2 注意

本轮没有改变原 `quality_score`。新增的 `weighted_error_penalty` 和 `error_severity_distribution` 只是审计字段，用于后续论文分析或辅助统计。

## 6. Required Fact Coverage

本轮新增 `required_fact_coverage`，用于检查报告是否覆盖 Evidence Pack 中的关键事实。

当前检查的事实主要包括：

```text
report date
daily_plc_range
daily_advance_m
current_chainage
forward_attention 是否存在
daily_review cell 是否存在
```

输出包括：

```text
required_fact_count
covered_required_fact_count
missing_required_fact_count
required_fact_coverage
missing_required_facts
facts
```

这项指标只用于审计，不参与原质量分扣分。

## 7. Trace 输出增强

`build_report_trace()` 现在会在每条 traced claim 中输出：

```text
entity
value
unit
time_scope
spatial_scope
claim_role
certainty
source_sentence_index
support_status
mismatch_type
confidence
aligned_evidence_ids
reason
```

同时在 trace summary 中新增：

```text
support_status_distribution
mismatch_type_distribution
```

这样可以直接统计：

```text
多少句完全支撑
多少句部分支撑
多少句无支撑
无支撑主要是缺证据、数值不匹配，还是角色混用
```

## 8. Revision 反馈增强

修订 prompt 现在会额外收到：

```text
error_severity_distribution
weighted_error_penalty
engineering_significant_error_count
required_fact_coverage
support_status_distribution
mismatch_type_distribution
```

这不会改变修订流程本身，但可以让 reviser 更清楚优先处理哪些错误。

## 9. 本轮没有改变什么

本轮明确没有改变：

```text
RAI / GRS / GRCI 公式
ConstructionStateCell 主结构
DailyConstructionTwin 主结构
Evidence Pack 原字段
quality_score 评分口径
grounding_rate 统计口径
unsupported_claim_count 统计口径
Boundary Checker 核心规则
no-LLM template 生成结构
Exp02 已有结果
```

## 10. 论文中可以怎么表述

可以表述为：

```text
为提高报告质量评价的可解释性，本文在 Evidence Pack 的基础上构建了统一的 EvidenceUnit 证据单元，并将生成报告中的自然语言句子解析为结构化 ReportClaim。系统进一步建立 Claim-Evidence Trace，对每条报告主张给出支撑状态、证据编号、不匹配类型和置信度，从而将报告评价由简单的 unsupported claim 统计扩展为可解释的证据对齐审计。
```

也可以表述为：

```text
该增强并不改变施工响应指标或地质-施工耦合指标本身，而是面向报告生成后的质量核验阶段，增强证据追踪、边界错误归因和关键事实覆盖检查能力。
```

## 11. 论文中不能夸大的地方

不能写成：

```text
系统已经实现了语义级自然语言理解
系统能够自动判断所有工程事实真伪
support confidence 是统计学习得到的概率
weighted penalty 是经过专家标定的正式评分
required fact coverage 能替代人工审查
```

当前这些字段仍是规则化、工程审计型指标，不是监督学习模型，也不是概率推断。

## 12. 验证结果

本轮验证包括：

```text
python -m pytest backend/tests -q
```

结果：

```text
151 passed
```

同时运行三日期 no-LLM smoke：

```text
2023-12-30
2023-12-28
2023-09-15
```

结果：

```text
passed_count = 3
failed_count = 0
average_quality_score = 100.0
average_grounding_rate = 1.0
E14 = 0
forward_cell_entered_high_grci_cells = false
```

说明新增审计字段没有破坏当前 no-LLM 主流程。

