# 当前 RAI / GRS / GRCI 指标实现审计

本文件只审计当前代码真实实现，不修改主流程。审计对象为 TBM 日报后端中已经进入 `ConstructionStateCell` 和 `DailyConstructionTwin` 的指标字段。

## 1. 实现位置

| 指标/逻辑 | 文件 | 函数/位置 | 当前职责 |
|---|---|---|---|
| PLC cell 响应聚合与 RAI | `backend/plc/cell_response.py` | `project_plc_response_to_cells()` | 将当日 PLC 记录聚合到 10m cell，计算 stop/abnormal/speed/torque 等响应指标和 RAI |
| RAI 公式文本 | `backend/plc/cell_response.py` | `RAI_FORMULA_TEXT` | 固定当前 RAI 分量权重说明 |
| ConstructionStateCell 构建 | `backend/coupling/grs_rai_grci.py` | `build_construction_state_cells()` | 汇合 PLC 响应、地质融合结果、证据 trace 和 cell role |
| GRCI 计算 | `backend/coupling/grs_rai_grci.py` | `compute_cell_grci()` | 只在已掘复核 daily_review 且同时有 RAI/GRS/PLC 响应时计算 GRCI |
| 高关注 cell 输出 | `backend/coupling/grs_rai_grci.py` | `review_cells()` / `high_grci_cells()` | 只筛选 daily_review、非 forward、GRCI_available=True 的 cell |
| Twin 映射 | `backend/twin/construction_twin.py` | `build_daily_construction_twin()` / `_cell_to_twin_view()` | 不重算指标，只将已有 RAI/GRS/GRCI 映射到 TwinCellView |
| schema 字段 | `backend/schemas/pipeline.py` | `ConstructionStateCell` | 定义 RAI、GRS、GRCI 及其分量、可用性和边界字段 |

## 2. 当前 RAI 公式

RAI 当前定义为施工响应关注度，不是设备故障概率或异常原因判断。

```text
RAI = 0.40 * stop_ratio
    + 0.25 * abnormal_ratio
    + 0.20 * speed_drop_score
    + 0.10 * torque_volatility_score
    + 0.05 * speed_volatility_score
```

当前变量含义：

| 字段 | 含义 | 来源 |
|---|---|---|
| `stop_ratio` | cell 内停机时长占比 | PLC 状态/速度推断 |
| `abnormal_ratio` | cell 内异常响应样本或时长占比 | PLC 速度、扭矩、推力组合规则 |
| `speed_drop_score` | 推进速度下降关注分 | cell 平均速度相对当日速度分位基准 |
| `torque_volatility_score` | 扭矩波动关注分 | 扭矩标准差 / 扭矩均值 |
| `speed_volatility_score` | 速度波动关注分 | 速度标准差 / 速度均值 |

当前输出字段包括：

```text
RAI
stop_component
abnormal_component
speed_drop_component
torque_component
speed_volatility_component
dominant_component
RAI_formula_text
stop_reason_available
planned_stop_distinguishable
stop_interpretation_warning
```

停机语义边界：当前 PLC 字段未区分计划停机与非计划停机，因此 `stop_ratio` 只能作为施工响应关注信号，不能直接解释为异常停机原因。

## 3. 当前 GRS 公式

GRS 当前定义为地质证据关注度，不是灾害概率。

```text
GRS = 0.45 * grade_score_component
    + 0.45 * hazard_component
    + 0.10 * confidence_component
```

当前变量含义：

| 字段 | 含义 | 来源 |
|---|---|---|
| `grade_score_component` | 围岩等级相关关注分 | `geology_v2` cell-level 地质融合结果 |
| `hazard_component` | 灾害/不良地质标签关注分 | `geology_v2` 证据标准化、投影和融合 |
| `confidence_component` | 证据置信或支撑强度分 | 地质证据融合/投影结果 |
| `main_hazards` | 主要关注标签 | 地质融合结果 |
| `hazard_scores` | 各 hazard 分项分数 | 地质融合结果 |
| `source_trace` | 支撑证据来源 | 标准化 evidence 与 cell 投影 |

当前输出字段包括：

```text
GRS_geo_base
grade_score_component
hazard_component
confidence_component
GRS_formula_text
GRS_component_method
GRS_available
GRS_unavailable_reason
has_geology_evidence
```

语义边界：`GRS_available=False` 与 `GRS=0` 不是同一含义。无可用空间相关地质证据时，不能解释为“地质关注低”。

## 4. 当前 GRCI 公式

GRCI 当前定义为已掘区段地质-施工响应耦合关注度，不是灾害概率，不是前方风险。

```text
GRCI = 0.55 * GRS_geo_base
     + 0.35 * RAI
     + 0.10 * GRS_geo_base * RAI
```

当前输出字段包括：

```text
GRCI
GRCI_available
GRCI_source
GRCI_unavailable_reason
grs_term
rai_term
interaction_term
GRCI_formula_text
coupling_level
coupling_explanation
```

## 5. GRCI 可用性规则

当前 `compute_cell_grci()` 的核心规则：

1. 如果缺少 PLC response 或 `RAI is None`，则不计算 GRCI：
   - `GRCI = None`
   - `GRCI_source = "unavailable"`
   - `GRCI_unavailable_reason = "missing_plc_response"`
2. 如果缺少 GRS，则不计算 GRCI：
   - `GRCI_unavailable_reason = "missing_geology_evidence"`
3. 只有在 `cell_role == "daily_review"` 且有 PLC 响应时，才将 RAI 传入 GRCI。

## 6. forward_attention 与 GRCI 边界

当前代码明确限制：

- `forward_attention` cell 不使用 GRCI；
- `build_daily_construction_twin()` 中会把 forward cell 的 `GRCI` 置为 `None`，`GRCI_available=False`；
- `review_cells()` / `high_grci_cells()` 只筛选 `daily_review`、非 forward、已掘复核 cell；
- 前方提示使用 `GRS_geo_base`、`main_hazards`、`source_trace` 等地质证据字段，不使用 GRCI 表达前方风险。

## 7. 本审计结论

当前 RAI / GRS / GRCI 是工程启发式关注指标，公式清晰、字段可追踪，但权重和组合形式仍具有主观性。因此 Exp03 不替换当前主流程指标，而是通过分位数标准化、熵权、CRITIC 和严格耦合公式等旁路版本，检查高关注 cell 与高关注日期排序是否稳定。
