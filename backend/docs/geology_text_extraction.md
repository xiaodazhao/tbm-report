# P3：旁路式 LLM 地质文本结构化

P3 是独立 sidecar 模块，用于从 raw_text / source_text / original_text_span 等原始地质文本片段中抽取候选结构化 evidence。

## 1. 模块定位

```text
raw_text / source_text / original_text_span
-> LLM geology extraction
-> candidate evidence
-> schema validation
-> candidate_evidence_db
```

P3 不替代现有规则化地质证据解析，不写入正式 `evidence_db`，不被日报主 pipeline 自动读取。

## 2. 输入优先级

1. `raw_text / source_text / original_text_span`
2. 已转换的 txt / md / docx 文本
3. csv / xlsx 中的原文描述字段
4. 只有结构化 evidence_db 时，只使用其中的原文字段，不把结构化字段当作 LLM 原文输入
5. PDF OCR 不在本轮实现范围内，需先独立转换为文本

## 3. 输出 schema

候选 evidence 至少包含：

- `candidate_id`
- `source_id`
- `source_type`
- `report_date`
- `start_chainage`
- `end_chainage`
- `face_chainage`
- `chainage_text`
- `surrounding_rock_grade`
- `hazards`
- `hazard_tags`
- `unmapped_hazard_tags`
- `water_condition`
- `fracture_condition`
- `broken_rock_condition`
- `evidence_role`
- `confidence`
- `original_text_span`
- `source_trace`
- `candidate_only`
- `requires_manual_review`
- `not_used_by_main_pipeline`
- `validation_passed`
- `validation_errors`
- `validation_warnings`

## 4. hazard_tags 词表

标准 tags 包括：

```text
broken_rock
extremely_broken_rock
fracture_developed
dense_fractures
block_fall
water_rich
water_inflow
soft_hard_uneven
weak_interlayer
fault_zone
karst
high_geo_stress
rock_burst
large_deformation
abnormal_reflection
surrounding_rock_grade_III
surrounding_rock_grade_IV
surrounding_rock_grade_V
unknown
```

LLM 输出中不在词表内的 tag 必须进入 `unmapped_hazard_tags`。

## 5. validation 规则

validator 检查：

- `source_type` 合法；
- `start_chainage <= end_chainage`；
- `evidence_role` 合法；
- `hazard_tags` 均在标准词表；
- `report_date` 为 `YYYY-MM-DD` 或 null；
- `original_text_span` 不为空；
- `source_trace` 不为空；
- `candidate_only = true`；
- `requires_manual_review = true`；
- `not_used_by_main_pipeline = true`。

`unknown` 字段允许存在，但会产生 warning。

## 6. 输出文件

```text
outputs/geology_extraction/raw_llm_response.json
outputs/geology_extraction/extracted_evidence_candidates.json
outputs/geology_extraction/extracted_evidence_candidates.csv
outputs/geology_extraction/validated_evidence_candidates.json
outputs/geology_extraction/validated_evidence_candidates.csv
outputs/geology_extraction/candidate_evidence_db.csv
outputs/geology_extraction/extraction_summary.json
outputs/geology_extraction/extraction_errors.csv
```

`candidate_evidence_db.csv` 只是候选 evidence，不得覆盖正式 `evidence_db`。

## 7. mock 运行命令

```powershell
python scripts/run_geology_text_extraction.py --input-file outputs/geology_extraction/sample_geology_text.txt --source-type HSP --mock-llm --out-dir outputs/geology_extraction
```

当前 mock 结果：

```text
candidate_count = 1
validation_passed_count = 1
validation_failed_count = 0
used_external_llm = false
start_chainage = 1014545.0
end_chainage = 1014645.0
```

## 8. 与正式 evidence_db 的边界

P3 输出必须始终带有：

```text
candidate_only = true
requires_manual_review = true
not_used_by_main_pipeline = true
```

如果后续要进入正式主链路，必须另开任务实现：

```text
candidate_evidence_db
-> manual_review / rule_review
-> reviewed_evidence_db
-> optional official pipeline input
```

当前版本没有这条接入链路。
