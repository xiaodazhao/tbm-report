# Quality / Trace 方法边界句分类说明

本文记录当前版本对“方法边界约束句”的 Quality / Trace 分类规则。该更新只影响报告核验分类，不改变主 pipeline、Evidence Pack 主结构、GRS / RAI / GRCI 计算或导出主链路。

相关文档：

- [当前后端系统说明书](current_backend_system_manual.md)
- [方法定义文档](method_definition.md)
- [指标定义文档](metrics_definition.md)
- [字段契约文档](backend_field_contract.md)
- [方法与计算逻辑白皮书](method_calculation_whitepaper.md)

## 1. 方法边界句是什么

方法边界句用于说明报告生成和指标解释的限制，它不是普通技术事实 claim，也不是无证据技术判断。

当前 checker 会识别以下语义：

```text
不把前方证据写成已揭露事实
不能写成已揭露事实
不将前方预报写成已发生事实
如无当日可用掌子面素描
当前 PLC 字段未区分计划停机与非计划停机
stop_ratio 仅作为施工响应关注信号
GRCI 不表示灾害概率
GRCI 不表示风险概率
前方关注提示不等同于已发生异常
forward_profile 语义为前方关注提示，不是已发生事实
围绕 forward_profile 做前方关注提示复核
```

## 2. Quality / Trace 分类结果

这类句子统一归为：

```text
claim_type = method_boundary
support_type = recommendation_policy
trace_support_type = policy_support
error_type = E12_METHOD_BOUNDARY_STATEMENT
```

含义：

- `method_boundary`：该句是方法边界或生成约束说明。
- `recommendation_policy`：该句由报告生成约束和方法策略支撑。
- `policy_support`：Trace 中不要求它匹配具体地质 evidence 或 PLC cell。
- `E12_METHOD_BOUNDARY_STATEMENT`：错误类型表中保留该类记录，便于审计边界说明数量。

## 3. 不属于 policy_support 的情况

本规则不放宽 checker。以下内容仍不能归为 `policy_support`：

- 真正无证据的地质灾害判断；
- 把前方关注提示写成已发生事实；
- 把 GRCI 写成灾害概率、风险概率或发生概率；
- 把 stop_ratio 高直接写成异常原因；
- 把 local_background cell 写成当日施工响应异常；
- 引用 `excluded_by_distance` evidence 作为报告正文支撑。

这些情况仍分别进入 `E1`、`E3`、`E4`、`E5`、`E9`、`E13` 等对应错误类型。

## 4. 2023-12-30 修正结果

修正前，no-LLM 报告中的句子：

```text
如无当日可用掌子面素描，不把前方证据写成已揭露事实。
```

曾被误识别为：

```text
claim_type = forward_segment
support_type = none
trace_support_type = none
error_type = E11_HEADING_FALSE_POSITIVE
```

修正后，该句被识别为：

```text
claim_type = method_boundary
grounded = true
support_type = recommendation_policy
trace_support_type = policy_support
error_type = E12_METHOD_BOUNDARY_STATEMENT
```

2023-12-30 最新 Quality / Trace 摘要：

```text
quality_score = 100
grounding_rate = 1.0
unsupported_claim_count = 0
E4_FORWARD_AS_EXCAVATED_REVIEW = 0
E11_HEADING_FALSE_POSITIVE = 0
E12_METHOD_BOUNDARY_STATEMENT = 3
policy_support = 3
none = 0
```

## 5. 测试覆盖

新增和更新的测试覆盖：

```text
1. “不把前方证据写成已揭露事实” 归为 method_boundary；
2. 方法边界句获得 policy_support；
3. 方法边界句 error_type 为 E12，不再是 E11；
4. 真正无证据技术 claim 不会被误判为 policy_support；
5. GRCI 概率误用仍归为 E3；
6. stop_ratio 直接解释为异常原因仍归为 E13。
```

当前测试结果：

```text
python -m pytest tests -q
32 passed
```

三日期真实数据 smoke：

```text
passed_count = 3
failed_count = 0
average_quality_score = 100.0
average_grounding_rate = 1.0
```
