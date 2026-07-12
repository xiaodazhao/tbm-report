# 实验目录

本目录保存论文实验脚本、最终结果和少量必要说明。当前不再保留失败过程文档、过渡版本报告和旧实验草稿；大体量逐日中间结果仍按 `.gitignore` 规则保留在本地或由脚本重新生成。

## 当前实验

| 实验 | 目的 | 当前状态 | 说明 |
|---|---|---|---|
| [`exp01_twin_full_run/`](exp01_twin_full_run/) | no-LLM 主流程、DailyConstructionTwin、Evidence Pack、Quality/Trace/Boundary 稳定性验证 | 已完成 | 作为后端主流程可用性验证 |
| [`exp02_llm_generation_modes/`](exp02_llm_generation_modes/) | M0-M4 真实 LLM 生成模式对比 | 已完成 | 当前最终结果为 `structured_trace_v1` 91 天 merged |
| [`exp03_indicator_robustness/`](exp03_indicator_robustness/) | RAI / GRS / GRCI 指标稳健性与变体排序对比 | 已完成 | 旁路复算，不改变主流程和 Exp02 |

## 最终结果入口

| 内容 | 路径 |
|---|---|
| Exp01 结果 | `experiments/exp01_twin_full_run/outputs_fix02/` |
| Exp02 最终 91 天结果 | `experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/` |
| Exp03 输出 | `experiments/exp03_indicator_robustness/outputs/` |
| 论文材料整理 | [`../paper_materials/`](../paper_materials/) |

## 使用约定

- 实验脚本可以读取 `backend/` 主流程，但实验目录本身不参与运行时 import。
- 不要为了优化实验结果修改 prompt、checker、主流程或评价指标。
- 真实 LLM 实验必须先 dry-run，不得打印或提交 API key。
- 论文中采用最终 merged 结果，不再引用失败重试过程、15 天过渡版本或旧 v3.1 结果作为最终结论。
