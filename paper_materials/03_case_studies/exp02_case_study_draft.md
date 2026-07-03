# Exp02 典型案例分析草稿

## 1. 案例选择

本文选择 `2023-12-13` 作为主案例，选择 `2023-09-29` 作为辅助残余问题案例。`2023-12-13` 的特点是：M1/M2/M3 均存在缺章、数值无支撑或证据定位不充分问题，而 M4 在保持章节完整的同时，将 unsupported claim 降至 1 条，quality score 达到 100，grounding rate 达到 0.9783，且 E14、boundary violation 和 missing sections 均为 0。该日期适合展示完整治理链路相对直接生成和仅 Evidence Pack 生成的改进作用。

`2023-09-29` 的特点是：M4 虽然相对 M1/M2/M3 仍有改善，但 quality score 仅为 45，仍保留 5 条 unsupported claim 和 3 条 numeric error。该日期适合作为残余错误案例，用于说明自动治理链路并不等于完全消除错误，仍需要 case-level 分析和人工复核。

## 2. 主案例：2023-12-13

### 2.1 模式结果对比

| 模式 | quality | grounding | unsupported | numeric | boundary | missing sections |
|---|---:|---:|---:|---:|---:|---:|
| M1 | 74 | 0.7091 | 16 | 6 | 0 | 2 |
| M2 | 74 | 0.7333 | 16 | 3 | 0 | 2 |
| M3 | 74 | 0.7037 | 16 | 2 | 0 | 2 |
| M4 | 100 | 0.9783 | 1 | 1 | 0 | 0 |

### 2.2 直接生成和原始证据输入的主要问题

M1 直接 LLM 生成在该日期出现 16 条 unsupported claim，其中数值类错误 6 条，并缺少 2 个标准章节。典型问题包括将报告日期、掘进里程范围、采样间隔和均值等数字写入正文，但这些数值未能被 grounding checker 在结构化证据中稳定命中。M2 虽然提供了原始证据摘要，但仍存在 16 条 unsupported claim 和 3 条数值错误，说明“给模型更多材料”并不必然带来更可靠的日报。

### 2.3 仅 Evidence Pack 生成的不足

M3 引入 ConstructionStateCell 和 Evidence Pack 后，报告能够更多围绕里程单元和证据包组织内容，但仍出现 16 条 unsupported claim 和 2 条数值错误，并缺少 2 个标准章节。典型问题是模型复述具体里程区段和 GRCI 值时，未能与 key cell 精确对齐，导致 checker 判定为未找到对应结构化证据。这说明 Evidence Pack 能提高证据相关性，但如果没有规划、边界约束和修订机制，最终文本仍可能产生证据定位误差。

### 2.4 M4 完整治理链路的改进

M4 在该日期中取得 quality score 100、grounding rate 0.9783，仅剩 1 条 numeric error，且无 E14、无 boundary violation、无缺章。该结果说明，在 Evidence Pack 基础上加入 planning、boundary constraint、structured trace 和 reviser 后，模型输出更接近“证据可追溯的工程日报”要求。M4 的剩余问题主要是“当日 PLC 数据聚类识别出 3 个施工状态”这一数值句未被完全支撑，属于残余数值支撑问题，而不是前方事实误用或 GRCI 概率化等边界错误。

## 3. 辅助案例：2023-09-29

### 3.1 模式结果对比

| 模式 | quality | grounding | unsupported | numeric | boundary | missing sections |
|---|---:|---:|---:|---:|---:|---:|
| M1 | 64 | 0.725 | 11 | 4 | 0 | 2 |
| M2 | 64 | 0.5833 | 20 | 4 | 0 | 2 |
| M3 | 69 | 0.74 | 13 | 1 | 0 | 2 |
| M4 | 45 | 0.8864 | 5 | 3 | 0 | 0 |

### 3.2 残余问题分析

`2023-09-29` 中，M4 保持了章节完整，且 E14 和 boundary violation 为 0，但 quality score 仅为 45。其残余问题主要包括：日期、过渡时长占比、连续掘进时间段等数值句未能被证据稳定支撑；同时，前方 30 米范围的关注提示虽未触发 boundary checker，但仍被 grounding checker 判为未找到对应前方分段结构化证据。该案例说明，完整治理链路能够降低错误，但在证据粒度、前方分段匹配和数值句抽取方面仍存在残余问题。

## 4. 案例结论

两个案例共同表明：M4 的优势不只是总体统计上的质量提升，也体现在具体日期中对章节结构、数值表达和工程边界的控制能力。`2023-12-13` 展示了完整治理链路在典型日期上的明显改善；`2023-09-29` 则说明该方法仍不是完全自动可靠的最终工程审查工具，残余错误需要结合 trace 结果和人工复核进一步分析。因此，本文应将 M4 定位为 evidence-grounded report generation and audit framework，而不是替代工程师判断的自动决策系统。
