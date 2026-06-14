# 方法增强说明：解释性字段、Evidence Pack selection 与旁路实验

本文是当前方法增强第一稳定版的主说明文档。它记录已经冻结在当前后端中的解释性字段、Evidence Pack selection 和旁路实验脚本。本文不提出新的主流程模块，也不表示 claim-first generation 已接入默认生成流程。

当前默认主线仍然是：

```text
PLC 与多源地质证据
-> ConstructionStateCell
-> RAI / GRS / GRCI 启发式关注指标
-> daily_review / forward_attention / local_background
-> Evidence Pack
-> Report
-> Quality / Trace
```

## 1. 方法增强的目标

本阶段增强服务三个目标：

1. 让每个 cell 为什么进入 Evidence Pack 更可解释；
2. 让后续论文实验能从导出文件直接统计、复盘和画图；
3. 在不改变 RAI / GRS / GRCI 默认公式的前提下，补充 overlap、trace、forward distance 等解释性字段。

这些增强不是新的预测模型。当前没有灾害发生标签、异常原因标签或现场复核标签，因此不做监督学习式权重校准。

## 2. cell size

字段：`cell_size_m`

目的：

- 标记本次 pipeline 使用的 cell 尺度；
- 支持 5m/10m 尺度敏感性分析；
- 让导出结果可复现。

边界：

- 默认 cell 为 10m；
- 10m 是当前日报复核的最大推荐尺度；
- 5m/10m 用于尺度敏感性分析；
- 不默认使用 20m；
- `daily_excavated_scope` 会随 cell 尺度变化，但它不是实际推进范围。

实际推进范围和推进量只能来自：

```text
daily_plc_range
daily_advance_m
```

## 3. evidence-cell overlap

字段：

- `evidence_overlap_length`
- `evidence_overlap_ratio`
- `max_overlap_ratio`
- `mean_overlap_ratio`
- `total_overlap_length`

目的：

- 解释地质证据和 cell 的空间交叠程度；
- 支撑“为什么该证据可以投影到该 cell”的复盘；
- 为论文中 source trace 和 evidence grounding 的可解释性提供表格字段。

边界：

- overlap 不改变 GRS 公式；
- overlap 不让远距离旧 TSP 重新进入主链路；
- time-valid 和 spatial-relevant 仍是 evidence 进入日报范围的前置门控。

## 4. evidence confidence 与 source reliability

字段：

- `evidence_confidence`
- `evidence_confidence_method`
- `source_reliability`
- `source_reliability_method`
- `manual_review_status`

目的：

- 保留 evidence 原始字段中已有的置信度或可靠性信息；
- 在 source trace 中说明证据支撑质量；
- 为后续人工复核或专家评价提供字段。

边界：

- 没有来源字段时不伪造 confidence；
- P3 candidate evidence 必须保持 `candidate_only=true` 和 `requires_manual_review=true`；
- P3 candidate evidence 不进入正式 Evidence Pack，不参与 RAI / GRS / GRCI。

## 5. trace completeness

字段：

- `trace_completeness`
- `trace_completeness_method`

目的：

- 评估一个 cell 的 `source_trace` 是否包含 evidence_id、source type、里程范围等可追溯信息；
- 支撑 Quality / Trace 对报告 claim 的追溯核验；
- 为 batch metrics 提供 trace 完整度统计。

边界：

- trace completeness 是解释性指标，不是风险指标；
- trace completeness 不改变 RAI、GRS、GRCI 数值。

## 6. forward distance

字段：

- `distance_to_face_m`
- `forward_distance_band`
- `forward_distance_weight`

距离分层：

```text
0-10m   -> near_0_10m
10-20m  -> mid_10_20m
20-30m  -> far_20_30m
```

目的：

- 解释 forward_attention cell 离当前掌子面的距离；
- 支撑前方关注提示排序；
- 为论文中的前方提示案例复盘提供字段。

边界：

- forward_attention 不使用正式 GRCI；
- forward_attention 只能写“当前掌子面前方关注提示”；
- 不能把前方证据写成已发生事实。

## 7. Evidence Pack selection

字段：

- `selection_score`
- `selection_rank`
- `selection_reason`
- `selection_method`
- `selected_by_score`

目的：

- 让 Evidence Pack 中的 key cells 可排序、可解释；
- 明确 cell 被选入日报证据包的原因；
- 支持生成模式对比和典型日期案例复盘。

角色规则：

| 证据角色 | selection 可使用信息 | 禁止事项 |
|---|---|---|
| `daily_review` | GRCI、RAI、GRS、trace completeness | 不能写成灾害概率 |
| `forward_attention` | GRS、forward distance、evidence confidence、trace completeness | 不使用 GRCI，不写已发生事实 |
| `local_background` | GRS、confidence、trace completeness | 不作为当日复核结论 |

selection 只影响 Evidence Pack 中关键 cell 的排序和说明，不改变 RAI / GRS / GRCI 默认公式。

## 8. Quality / Trace 语义边界

当前 Quality / Trace 重点检查：

- GRCI 是否被写成灾害概率；
- forward_attention 是否被写成已发生事实；
- `daily_excavated_scope` 是否被写成实际推进范围；
- `stop_ratio` 是否被直接解释为异常停机原因；
- claim 是否能被 Evidence Pack 或 policy constraints 支撑。

`stop_ratio` 的固定边界为：

```text
当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。
```

## 9. 可选 claim-first 导出

脚本：

```powershell
python scripts/export_allowed_claims.py --dates 2023-12-30 --out-dir outputs/allowed_claims
```

作用：

- 从 Evidence Pack 导出 allowed claims；
- 为后续 claim-first generation 研究提供候选材料。

边界：

- 当前只导出 `allowed_claims.json`；
- `enable_claim_first=false`；
- 不接入默认生成流程；
- 不改变 template、LLM、planner 或 revision 行为。

## 10. 论文实验用途

这些增强字段可以支撑：

- 91 天批量运行稳定性统计；
- 5m/10m cell 尺度敏感性；
- GRCI 权重敏感性；
- generation mode 对比；
- 典型日期案例复盘；
- 可选人工评价中的 evidence trace 检查。

这些实验评价的是方法稳定性、证据约束能力、报告 grounding 和可追溯性，不是灾害预测准确率。

