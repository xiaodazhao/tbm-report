# Exp01: 91 天全量稳定性实验与 DailyConstructionTwin 覆盖统计

## 1. 实验目的

本实验验证当前 no-LLM/template 主流程在全部可用 PLC 日期上的稳定性，并统计 DailyConstructionTwin、Evidence Pack from Twin、Quality/Trace、Twin Boundary Checker 与 PLC enhanced metrics 的覆盖情况。

## 2. 总体结果

- 总日期数：91
- 成功日期数：91
- 失败日期数：0
- 成功率：1.0000
- 平均 quality_score：100.0000
- 平均 grounding_rate：1.0000
- unsupported_claim_count_total：0
- unsupported_claim_count_total_raw：42
- heading_fragment_false_positive_count：42
- unsupported_claim_count_total_effective：0
- average_grounding_rate_raw：0.9782
- average_grounding_rate_effective：1.0000
- E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count：0

## 3. DailyConstructionTwin 导出情况

每个成功日期均检查 daily_construction_twin.json、twin_summary.json、twin_boundary_summary.json、twin_cell_views.json/csv、evidence_pack.json、construction_state_cells.json 和 high_grci_cells.json 是否导出。详见 exp01_twin_coverage_summary.csv。

## 4. Evidence Pack from Twin 覆盖情况

字段 evidence_pack_source 用于确认 Evidence Pack 来源是否为 DailyConstructionTwin。详见 exp01_twin_coverage_summary.csv。

## 5. PLC enhanced metrics 覆盖率

PLC enhanced metrics 只在 daily_review cells 中统计；所有 proxy 字段仅表示施工响应证据，不解释为真实物理功率、严格比能或地质风险判断。覆盖率见 exp01_plc_enhanced_metrics_coverage.csv，补充汇总见 exp01_plc_enhanced_metrics_extra_summary.csv。

## 6. 证据角色边界检查

全部通过，未发现 forward/local background 越界进入 high GRCI，也未发现 forward Evidence Pack 携带 PLC enhanced metrics。

## 7. Twin Boundary Checker 结果

- 模板报告 boundary violation 总数：0
- 违规类型计数：{}
- 人工违规句测试：全部人工违规句均命中预期类型。

## 8. 失败日期和原因

无

## 8.1 Unsupported Claim 样本

本次 effective unsupported claim 样本 0 条，详见 exp01_unsupported_claim_samples.csv。原始 fix01 unsupported claim 审计见 exp01_unsupported_claim_audit.csv / .md。本轮仅修正 heading / fragment false positive 的统计口径，不放宽真实工程 claim。

## 9. 是否支撑进入后续 LLM 对比实验

如果本实验成功率、Evidence Pack from Twin 覆盖和证据角色边界检查均满足预期，则当前结果可以支撑进入下一阶段 LLM 生成模式对比、消融实验和典型日期 case study。

## 10. 输出文件

实验输出目录：`C:\Users\22923\Desktop\tbm-report\experiments\exp01_twin_full_run\outputs_fix02`

主要统计文件：

- exp01_daily_run_summary.csv / .md
- exp01_twin_coverage_summary.csv
- exp01_plc_enhanced_metrics_coverage.csv
- exp01_role_boundary_check.csv
- exp01_boundary_checker_manual_tests.csv
- exp01_failed_dates.csv
- exp01_unsupported_claim_audit.csv / .md
- exp01_effective_unsupported_claim_samples.csv