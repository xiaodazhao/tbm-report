# LLM 生成模式

当前报告生成支持五种 `generation_mode`。默认工程回归模式是 `template`，不会调用外部模型。

| generation_mode | 是否用 LLM | 是否用 planner | 是否 revision | 适用场景 |
|---|---:|---:|---:|---|
| `template` | 否 | 否 | 否 | no-LLM 回归、接口稳定性、基准模板 |
| `evidence_pack_llm` | 是 | 否 | 否 | 验证 Evidence Pack 约束生成 |
| `evidence_pack_llm_with_revision` | 是 | 否 | 是 | 验证 Quality / Trace 反馈修订 |
| `evidence_pack_planner_llm` | 是 | 是 | 否 | 验证章节计划和证据角色约束 |
| `evidence_pack_planner_llm_with_revision` | 是 | 是 | 是 | 当前完整 LLM 研究链路 |

## 输入与输出

所有 LLM 模式的输入都来自 Prompt Evidence Pack，不允许 LLM 直接读取原始 PLC CSV 或完整 evidence_db。

常见输出文件：

- `llm_prompt.txt`
- `llm_request.json`
- `llm_raw_response.txt`
- `llm_report_draft.txt`
- `llm_quality_before_revision.json`
- `llm_trace_before_revision.json`
- `llm_revision_prompt.txt`
- `llm_report_final.txt`
- `llm_quality_after_revision.json`
- `llm_trace_after_revision.json`
- `llm_summary.json`

planner 模式额外输出：

- `llm_report_plan_prompt.txt`
- `llm_report_plan_request.json`
- `llm_report_plan_raw_response.txt`
- `llm_report_plan.json`
- `llm_report_plan_validation.json`

## 外部模型安全边界

开发与测试默认使用 mock。真实 DeepSeek / OpenAI-compatible 调用必须显式允许外发：

```powershell
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_planner_llm_with_revision --provider openai_or_compatible --model deepseek-chat --enable-planner --enable-revision --allow-external-llm --out-dir outputs/llm_exports
```

在 Codex 或其他自动化环境中，默认不应外发 Evidence Pack。只有在确认 API key、数据脱敏、外发许可和实验记录方式后，才允许真实模型调用。

## 推荐命令

mock planner + revision：

```powershell
python scripts/run_llm_report_generation.py --dates 2023-12-30 --generation-mode evidence_pack_planner_llm_with_revision --mock-llm --enable-planner --enable-revision --out-dir outputs/llm_exports
```

批量 mock LLM：

```powershell
python scripts/run_batch_llm_generation.py --date-file outputs/audit/date_classification.csv --class-filter A,B --generation-mode evidence_pack_llm_with_revision --mock-llm --enable-revision --out-dir outputs/batch_llm --continue-on-error
```
