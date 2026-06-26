# exp01_twin_full_run

第一阶段实验：91 天全量稳定性实验与 DailyConstructionTwin 覆盖率统计。

## 实验目标

验证当前 DailyConstructionTwin 架构能否在全部可用 PLC 日期上稳定运行，并统计：

- pipeline 成功率；
- DailyConstructionTwin 导出覆盖率；
- Evidence Pack from Twin 覆盖情况；
- Quality / Trace / Boundary Checker 指标；
- PLC enhanced metrics 在 `daily_review` cells 中的覆盖率；
- 证据角色边界是否被破坏。

## 计划输出

本实验目录后续至少保存：

- `exp01_daily_run_summary.csv`
- `exp01_daily_run_summary.md`
- `exp01_twin_coverage_summary.csv`
- `exp01_plc_enhanced_metrics_coverage.csv`
- `exp01_role_boundary_check.csv`
- `exp01_boundary_checker_manual_tests.csv`
- `exp01_failed_dates.csv`
- `exp01_experiment_report.md`
- `exp01_unsupported_claim_audit.csv`
- `exp01_unsupported_claim_audit.md`
- `exp01_effective_unsupported_claim_samples.csv`

## 运行边界

- 只使用 no-LLM / template 模式；
- 不调用真实 LLM；
- 不修改 RAI / GRS / GRCI；
- 不修改 Evidence Pack 语义；
- 不引入 RAI_v2、relation_deviation_score、ppr_proxy 或 energy_load_proxy；
- 不做代码清理和 legacy 迁移。

## fix02 说明

`outputs_fix02/` 用于记录 unsupported claim 统计口径清理后的结果。

本轮仅把 “涉及气体为 无。” 这类 heading / fragment false positive 从有效 unsupported claim 分母中排除，同时保留 raw unsupported 统计和审计表，避免误以为真实工程 claim 被放宽。
