# 批量审计与批量运行

本文说明任务 3 引入的 91 天数据审计、日期分类、批量 pipeline 和批量 mock LLM 脚本。当前方法主线已经冻结；更多面向论文实验的统计、生成模式对比、GRCI 权重敏感性和 cell 尺度敏感性脚本见 [实验与复盘脚本说明](experiment_scripts.md)。

## 1. PLC 审计

脚本：

```powershell
python scripts/audit_plc_dates.py --out-dir outputs/audit
```

输出：

- `outputs/audit/plc_date_audit.csv`
- `outputs/audit/plc_date_audit.json`

核心字段：

- `date`
- `row_count`
- `daily_chainage_min`
- `daily_chainage_max`
- `daily_advance_m`
- `speed_col_exists`
- `torque_col_exists`
- `thrust_col_exists`
- `gas_col_exists`
- `usable_for_report`
- `exclude_reason`

当前结果：

```text
PLC total_dates = 91
PLC usable_dates = 91
excluded_dates = 0
average_daily_advance_m = 13.8571
```

## 2. evidence_db 审计

脚本：

```powershell
python scripts/audit_evidence_db.py --out-dir outputs/audit
```

输出：

- `outputs/audit/evidence_db_audit.csv`
- `outputs/audit/evidence_db_audit.json`

当前结果：

```text
Evidence total_evidence_count = 484
TSP_count = 139
HSP_count = 176
sketch_count = 169
valid_geometry_count = 484
invalid_geometry_count = 0
```

注意：当前 raw source type 中 `sonic` 按 HSP 类超前地质证据计数。

## 3. 日期分类

脚本：

```powershell
python scripts/classify_experiment_dates.py --plc-audit outputs/audit/plc_date_audit.csv --evidence-audit outputs/audit/evidence_db_audit.csv --out-dir outputs/audit
```

输出：

- `outputs/audit/date_classification.csv`
- `outputs/audit/date_classification_summary.json`

当前结果：

```text
A 类日期 = 83
B 类日期 = 8
usable_for_batch_count = 91
usable_for_main_experiment_count = 91
usable_for_case_study_count = 91
```

## 4. 批量 pipeline

脚本：

```powershell
python scripts/run_batch_pipeline.py --date-file outputs/audit/date_classification.csv --class-filter A,B --no-llm --out-dir outputs/batch_pipeline --continue-on-error
```

输出：

- 每个日期目录下的 `scope_summary.json`、`evidence_pack.json`、`quality.json`、`trace.json`、`method_metrics.json`
- `outputs/batch_pipeline/batch_summary.csv`
- `outputs/batch_pipeline/batch_summary.json`
- `outputs/batch_pipeline/batch_error_log.csv`

当前结果：

```text
batch pipeline passed = 91 / 91
```

## 5. 批量 mock LLM

脚本：

```powershell
python scripts/run_batch_llm_generation.py --date-file outputs/audit/date_classification.csv --class-filter A,B --generation-mode evidence_pack_llm_with_revision --mock-llm --enable-revision --out-dir outputs/batch_llm --continue-on-error
```

输出：

- 每个日期目录下的 `llm_summary.json` 和 `llm_report_final.txt`
- `outputs/batch_llm/batch_llm_summary.csv`
- `outputs/batch_llm/batch_llm_summary.json`
- `outputs/batch_llm/batch_llm_error_log.csv`

当前结果：

```text
batch mock LLM passed = 91 / 91
```

## 6. 与主 pipeline 的关系

批量脚本只调用当前单日 pipeline 或 LLM generation 包装层，不改变单日 pipeline 行为，不改 Evidence Pack 主结构，不写入正式 evidence_db。
