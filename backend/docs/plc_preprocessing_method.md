# PLC 施工响应预处理增强方法

本文档说明当前新增的 PLC preprocessing enhancement。该模块只增强 PLC 施工响应证据，不改变 RAI / GRS / GRCI 公式，不进入 forward_attention，不调用 LLM。

## 1. 方法定位

新增模块：

```text
backend/plc/paper_based_preprocessing.py
```

它参考 TBM 运行参数研究中的数据清洗和稳态段提取思想，但不做参数预测模型，不做地质风险预测。

当前定位：

```text
raw PLC
→ paper-based preprocessing labels
→ steady-state PLC response metrics
→ cell_response_df / ConstructionStateCell.plc_metrics / DailyConstructionTwin.response_state
```

## 2. Wang-style shutdown removal

参考 Wang 2021 中基于推力和刀盘扭矩识别停机段的思路。

对样本 i：

```text
F_i = thrust
T_i = torque
```

工程实现：

```text
shutdown_i = (F_i <= eps_thrust) OR (T_i <= eps_torque)
```

默认：

```text
eps_thrust = 0
eps_torque = 0
```

输出字段：

```text
is_shutdown_segment
shutdown_reason
shutdown_sample_count
shutdown_ratio
```

## 3. 3σ abnormal point filtering

只对 non-shutdown samples 做 3σ 异常点标记。

对每个核心参数 x：

```text
lower_x = mean(x) - 3 * std(x)
upper_x = mean(x) + 3 * std(x)
```

如果：

```text
x_i < lower_x OR x_i > upper_x
```

则：

```text
is_outlier = True
```

当前只标记，不删除原始记录。后续稳态统计排除 outlier。

样本不足时：

```text
n_valid < 30
```

跳过该字段的 3σ filtering，并记录 skipped fields。

## 4. valid excavation mask

有效掘进样本定义为：

```text
NOT is_shutdown_segment
AND NOT is_outlier
AND thrust > eps_thrust
AND torque > eps_torque
AND advance_speed > eps_speed, if speed exists
AND rpm > eps_rpm, if rpm exists
AND chainage_valid
AND is_working=True, if existing is_working exists
```

这个逻辑替代原先简单的：

```text
推进速度 > 0
推力 > 0
扭矩 > 0
转速 > 0
```

但只用于 PLC enhanced metrics，不改变 RAI 公式。

## 5. continuous working interval

连续有效掘进样本会被组合成 working interval。

新 interval 开始条件：

```text
当前样本 valid_excavation=True
AND (
    前一个 valid 样本不存在
    OR 前一个样本 invalid
    OR 出现 time gap
    OR 里程反向跳变
)
```

过短区间标记为：

```text
short_transition_interval
```

默认阈值：

```text
min_interval_sample_count = 20
min_interval_duration_seconds = 30
```

## 6. Shan-style steady-state extraction

参考 Shan 2024 中稳态段识别思想。

检测信号优先级：

```text
advance_speed
→ penetration value fallback, only if advance_speed is unavailable
```

说明：当前 PLC 表头中的“贯入度”字段语义更接近贯入度值（如 mm/r），不是已经确认的 penetration rate。因此稳态段检测不再优先使用 `penetration`，而是优先使用推进速度 `advance_speed`。只有当推进速度缺失或不可用时，才把 `penetration` 作为辅助 fallback 信号，并在输出中标记为：

```text
steady_detection_signal = penetration_value_fallback_not_rate
```

该 fallback 不能解释为 penetration rate，也不能用于推导严格物理比能。

在每个 valid working interval 内计算 rolling mean：

```text
y20_i = rolling_mean(y_i, window=20)
threshold = 0.8 * median(y20_i)
steady_candidate_i = y20_i >= threshold
```

如果有多个 candidate segment：

```text
优先最长 sample_count
再比较 duration
再比较 chainage_length
最后取最早出现
```

默认阈值：

```text
steady_window = 20
steady_threshold_factor = 0.8
min_steady_sample_count = 20
min_steady_duration_seconds = 30
```

## 7. steady-state cell metrics

对每个 cell 输出：

```text
steady_state_available
steady_sample_count
steady_ratio
steady_to_working_ratio

steady_speed_mean/std/cv
steady_thrust_mean/std/cv
steady_torque_mean/std/cv
steady_rpm_mean/std/cv
steady_penetration_mean/std/cv

steady_cutterhead_power_proxy
steady_thrust_per_penetration
steady_torque_per_penetration

steady_state_fallback_used
steady_state_fallback_reason
steady_detection_signal
plc_preprocessing_quality_grade
plc_preprocessing_quality_reason
```

## 8. 质量等级

`plc_preprocessing_quality_grade` 只表示 PLC response evidence 可用性，不表示施工风险或地质风险。

规则：

| 等级 | 规则 |
|---|---|
| A | 有 steady-state，steady_sample_count >= 50，steady_to_working_ratio >= 0.5，speed/thrust/torque 均可用 |
| B | 有 steady-state，steady_sample_count >= 20，speed/thrust/torque 至少两项可用 |
| C | steady-state 不可用，但 working-only fallback 可用且 working_sample_count >= 20 |
| D | 其他情况 |

## 9. 语义边界

必须遵守：

```text
steady_cutterhead_power_proxy 不是真实物理功率
steady_thrust_per_penetration 不是严格比能
steady_torque_per_penetration 不是严格比能
steady-state metrics 只用于已掘区段施工响应证据
steady-state metrics 不进入 forward_attention
steady-state metrics 不改变 RAI / GRS / GRCI
```

## 10. 验证脚本

新增旁路验证脚本：

```text
experiments/exp_plc_preprocessing_validation/run_plc_preprocessing_validation.py
```

示例：

```bash
python experiments/exp_plc_preprocessing_validation/run_plc_preprocessing_validation.py --dates 2023-12-30,2023-12-28 --out-dir experiments/exp_plc_preprocessing_validation/outputs
```

输出：

```text
plc_preprocessing_daily_summary.csv
plc_preprocessing_cell_summary.csv
plc_preprocessing_coverage_summary.csv
plc_preprocessing_quality_grade_summary.csv
plc_preprocessing_overall_summary.json
plc_preprocessing_report.md
```
