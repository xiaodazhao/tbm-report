# Exp02 实验结果与分析（论文正文草稿）

## 1. 实验设置简述

为验证多源工程证据约束下 TBM 施工日报自动生成方法的有效性，本文基于本工程 91 个可用施工日期开展真实 LLM 回归实验。每个日期分别采用五种生成模式生成日报，共形成 455 个 date-mode 组合。实验过程中未修改主流程、提示词、评价规则或指标计算口径，所有生成结果均保存至固定结果目录。完整性检查表明，455 次运行全部成功，failed count 为 0，各模式均包含 91 条结果，无缺失 date-mode 组合，也无重复组合。

## 2. M0-M4 模式说明

五种模式构成递进式对比关系。M0 为确定性模板基线，不调用 LLM，主要用于提供稳定格式参照；M1 为直接 LLM 生成，代表最弱证据约束的自由生成方式；M2 在生成时提供原始证据摘要，用于检验单纯增加输入材料的效果；M3 引入 ConstructionStateCell 和 Evidence Pack，使模型能够接收结构化施工状态与证据包；M4 在 M3 基础上进一步加入 planning、boundary constraint、structured trace 和 reviser，形成完整的证据治理与自动修订链路。需要强调的是，LLM 在本实验中不承担地质风险判断任务，而是在结构化证据约束下完成报告组织和修订。

## 3. 91 天完整性说明

本次实验覆盖 91 个施工日期和 5 种生成模式，预期运行 455 次，实际完成 455 次，失败次数为 0。各模式均包含 91 条结果，说明本实验数据完整，可用于后续模式对比和论文统计分析。M0 的结果应作为确定性模板基线理解，不参与自由生成能力的直接比较。

## 4. 主结果分析

91 天结果显示，M4 在所有 LLM 模式中取得最高平均质量分和最高证据支撑率。M4 的 quality mean 为 94.18，grounding mean 为 0.9153，显著高于 M1、M2 和 M3。与此同时，M4 的 unsupported total 为 376，numeric total 为 78，均明显低于其他 LLM 模式。M4 的 E14 total、boundary total 和 missing sections total 均为 0，说明完整治理链路在控制实际推进范围误写、边界违规和章节缺失方面表现稳定。

从错误降低幅度看，M4 相比 M1/M2/M3 的 unsupported 降低幅度分别为 67.1%、69.2% 和 70.1%；numeric error 降低幅度分别为 82.5%、76.6% 和 65.5%。这表明 M4 的改进并非仅体现在文本格式上，而是在证据支撑和数值表达两个关键方面均产生了明显效果。

## 5. M4 修订效果分析

M4 的自动修订机制在 91 天样本中全部触发并成功执行。修订前 unsupported claims 总数为 637，修订后降至 376，减少 261 条，降低率为 40.97%。该结果说明，修订阶段不是简单润色，而是基于 quality checker、grounding checker、boundary checker 和 structured trace 反馈，对证据不足、数值不严谨或表达边界不清的内容进行约束性改写。

## 6. M3 与 M4 的差异分析

M3 已经引入 ConstructionStateCell 和 Evidence Pack，其 grounding mean 高于 M1/M2，说明结构化证据包能够增强报告与证据之间的关联。然而，M3 的 quality mean 低于 M1/M2/M4，unsupported total 和 missing sections total 仍较高。这表明，仅将结构化证据提供给 LLM 并不足以保证最终报告质量。相比之下，M4 进一步加入规划、边界约束、structured trace 和自动修订机制，能够抑制无证据扩展、降低数值错误，并保持章节完整。因此，M3 与 M4 的差异体现了后处理治理链路对 LLM 生成质量的重要贡献。

## 7. M0 模板基线解释

M0 的 quality mean 为 100.00，grounding mean 为 1.0000，unsupported、numeric、E14、boundary 和 missing sections 均为 0。这一结果主要来自确定性模板的固定规则和字段填充机制，不能被解释为模板方法具有更强的自然语言生成能力。M0 的意义在于提供一个可控、稳定、无自由发挥的基线，用于对照 LLM 模式中证据约束和治理链路的作用。

## 8. 异常日期与残余错误分析

尽管 M4 在整体上表现最佳，仍存在少数低分或残余错误日期。例如，2023-09-29、2023-10-02、2023-10-12 和 2023-11-11 等日期在 quality、unsupported 或 numeric 指标上表现相对偏弱。这些日期并非运行失败，而是报告内容中仍存在残余无支撑表述或数值表达问题。后续可选取这些日期开展 case study，进一步分析残余错误是来自模型表达、证据粒度、trace 匹配还是评价规则边界。

## 9. 小结

综合 91 天真实 LLM 回归结果，M4 完整治理链路在本工程内表现出较好的稳定性和有效性。与直接 LLM、原始证据输入 LLM 和仅 Evidence Pack 生成相比，M4 在平均质量分、证据支撑率、unsupported claims、numeric errors、边界违规和章节完整性方面均具有优势。该实验支持本文提出的 evidence-grounded、structured trace、boundary constraint 和 revision 协同治理思路。需要说明的是，本实验仍基于单一工程 91 天数据，不能直接外推为跨工程泛化结论；自动评价结果也不能完全替代人工复核，后续仍需结合典型案例与人工评价进一步验证工程可读性。
