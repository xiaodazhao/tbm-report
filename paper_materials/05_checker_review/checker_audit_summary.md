# Exp02 checker 抽样复核材料

## 1. 目的

本材料用于复核自动评价体系的可靠性。样本来自 91 天 structured_trace_v1 真实 LLM 回归结果，覆盖 unsupported/mismatch、numeric error、boundary violation、grounded control 和 M4 residual errors。本步骤不重新运行 LLM，不修改 prompt、checker 或评价规则。

## 2. 总体样本池统计

| sample_group            | mode_short   |   count |
|:------------------------|:-------------|--------:|
| boundary_violation      | M1           |      10 |
| boundary_violation      | M2           |      23 |
| boundary_violation      | M3           |       2 |
| grounded_control        | M1           |    2766 |
| grounded_control        | M2           |    2785 |
| grounded_control        | M3           |    3601 |
| grounded_control        | M4           |    3550 |
| numeric_error           | M1           |     445 |
| numeric_error           | M2           |     334 |
| numeric_error           | M3           |     226 |
| numeric_error           | M4           |      78 |
| other_checker_flag      | M1           |     272 |
| other_checker_flag      | M2           |     339 |
| other_checker_flag      | M3           |     371 |
| other_checker_flag      | M4           |     492 |
| unsupported_or_mismatch | M1           |     698 |
| unsupported_or_mismatch | M2           |     887 |
| unsupported_or_mismatch | M3           |    1030 |
| unsupported_or_mismatch | M4           |     298 |

## 3. 错误类型分布

| error_type                       | mode_short   |   count |
|:---------------------------------|:-------------|--------:|
| E10_NUMERIC_VALUE_UNGROUNDED     | M1           |     445 |
| E10_NUMERIC_VALUE_UNGROUNDED     | M2           |     334 |
| E10_NUMERIC_VALUE_UNGROUNDED     | M3           |     226 |
| E10_NUMERIC_VALUE_UNGROUNDED     | M4           |      78 |
| E11_HEADING_FALSE_POSITIVE       | M1           |     554 |
| E11_HEADING_FALSE_POSITIVE       | M2           |     473 |
| E11_HEADING_FALSE_POSITIVE       | M3           |     562 |
| E11_HEADING_FALSE_POSITIVE       | M4           |     231 |
| E12_METHOD_BOUNDARY_STATEMENT    | M2           |      64 |
| E12_METHOD_BOUNDARY_STATEMENT    | M3           |      22 |
| E12_METHOD_BOUNDARY_STATEMENT    | M4           |       6 |
| E1_UNSUPPORTED_CLAIM             | M1           |     134 |
| E1_UNSUPPORTED_CLAIM             | M2           |     413 |
| E1_UNSUPPORTED_CLAIM             | M3           |     446 |
| E1_UNSUPPORTED_CLAIM             | M4           |      67 |
| E4_FORWARD_AS_EXCAVATED_REVIEW   | M1           |       7 |
| E4_FORWARD_AS_EXCAVATED_REVIEW   | M3           |      16 |
| E5_BACKGROUND_AS_DAILY_RESPONSE  | M3           |       3 |
| E6_GAS_FIELD_MISUSE              | M1           |       3 |
| E6_GAS_FIELD_MISUSE              | M2           |       1 |
| E6_GAS_FIELD_MISUSE              | M3           |       3 |
| boundary:forward_fact_misuse     | M1           |       9 |
| boundary:forward_fact_misuse     | M2           |      22 |
| boundary:grci_probability_misuse | M1           |       1 |
| boundary:grci_probability_misuse | M3           |       1 |
| boundary:plc_proxy_misuse        | M3           |       1 |
| boundary:stop_causality_misuse   | M2           |       1 |

## 4. 抽样复核表规模

| sample_group            | mode_short   |   sample_count |
|:------------------------|:-------------|---------------:|
| boundary_violation      | M1           |              3 |
| boundary_violation      | M2           |              5 |
| boundary_violation      | M3           |              2 |
| grounded_control        | M1           |              1 |
| grounded_control        | M2           |              2 |
| grounded_control        | M3           |              1 |
| grounded_control        | M4           |              1 |
| numeric_error           | M1           |              2 |
| numeric_error           | M2           |              3 |
| numeric_error           | M3           |              3 |
| numeric_error           | M4           |              5 |
| other_checker_flag      | M1           |              1 |
| other_checker_flag      | M2           |              1 |
| other_checker_flag      | M3           |              1 |
| other_checker_flag      | M4           |              8 |
| unsupported_or_mismatch | M1           |              3 |
| unsupported_or_mismatch | M2           |              3 |
| unsupported_or_mismatch | M3           |              3 |
| unsupported_or_mismatch | M4           |              9 |

## 5. 人工复核建议

人工复核时建议填写 `human_is_checker_correct`、`human_correct_label` 和 `human_comment` 三列。`human_is_checker_correct` 可填写 yes/no/uncertain；`human_correct_label` 可填写 supported、unsupported、numeric_error、boundary_violation、false_positive、not_a_claim 等。

## 6. 论文使用方式

该抽样表可用于后续说明自动 checker 的可靠性边界。如果人工复核显示大部分样本与 checker 判断一致，可作为自动评价指标可信度的辅助证据；如果误伤较多，则应在论文局限性中说明 checker 粒度和文本切分策略的影响。
