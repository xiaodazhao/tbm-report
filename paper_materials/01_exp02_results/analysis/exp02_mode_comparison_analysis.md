# Exp02 生成模式对比分析

## 1. M4 相比其他 LLM 模式的错误降低幅度

在 91 天真实 LLM 回归中，M4 完整治理链路在 unsupported claims 和 numeric errors 两类关键错误上均明显低于 M1/M2/M3。

| 对比 | unsupported 降低幅度 | numeric 降低幅度 |
|---|---:|---:|
| M4 vs M1 | 67.1% | 82.5% |
| M4 vs M2 | 69.2% | 76.6% |
| M4 vs M3 | 70.1% | 65.5% |

## 2. 对 M3 的解释

M3 的 grounding mean 为 0.7592，高于 M1 和 M2，但其 quality mean 仅为 68.93，且 unsupported total 为 1256。这说明，仅提供 ConstructionStateCell 和 Evidence Pack 可以增强报告与证据之间的关联，但不足以保证最终报告质量。LLM 在没有规划、边界约束、structured trace 和修订机制时，仍可能复述过多细节、扩展无支撑判断，或出现章节结构不稳定问题。

## 3. 对 M0 的解释

M0 是确定性模板基线，其 quality mean 和 grounding mean 均较高，主要来自模板规则的可控性和字段填充的确定性。该结果不能解释为模板方法具有更强的自由文本生成能力，也不能直接说明模板报告在表达完整性、自然性和工程可读性上优于受控 LLM 方法。M0 的作用是提供稳定格式基准，用于衡量 LLM 自由生成和治理链路带来的变化。

## 4. 综合判断

M4 的 quality mean 为 94.18，grounding mean 为 0.9153，unsupported total 为 376，numeric total 为 78，boundary total 和 E14 total 均为 0。结果表明，Twin + Evidence Pack + Planning + Boundary + Structured Trace + Reviser 的完整治理链路能够在 91 天单工程样本中显著提升证据支撑性、章节稳定性和数值表达安全性。
