# Exp02：LLM 生成模式对比实验

Exp02 用于比较不同 LLM 输入约束强度下，TBM 施工状态报告的证据越界、可追溯性和稳定性。

本实验以 Exp01 已冻结结果为基础：

- `experiments/exp01_twin_full_run/outputs_fix02/`
- commit `b8de803 Fix Exp01 quality metric cleanup`

## 实验边界

Exp02 不修改主 pipeline，不修改 RAI / GRS / GRCI，不修改 evidence_scope，不修改 PLC enhanced metrics，不做旧 Evidence Pack 对比，不做消融实验，不做 91 天真实 LLM 全量调用。

真实 LLM 运行会把本实验构造的 prompt 发送到外部兼容接口。仓库内脚本不会打印 API key；运行真实 LLM 前建议先执行 dry-run 配置检查。

## 五种模式

- `M0_template_only`：当前 template / no-LLM 报告，作为稳定基线，不调用 LLM。
- `M1_direct_llm`：只给日期和基础统计信息，模拟直接让 LLM 写报告。
- `M2_raw_evidence_llm`：给粗略 PLC / 地质 / 气体 / 前方摘要，但不提供完整 governance。
- `M3_twin_evidence_pack_llm`：给 DailyConstructionTwin Evidence Pack 和 governance，但不做自动修订。
- `M4_full_twin_governance_trace_boundary_reviser`：给 DailyConstructionTwin Evidence Pack，生成后经过 Quality / Trace / Boundary Check，再用反馈 prompt 修订一次。

## Mock 运行

```powershell
$env:DATA_ROOT='G:/我的云端硬盘/TBM9'
$env:DATA_DIR='G:/我的云端硬盘/TBM9/TBM9_2023'
$env:EVIDENCE_DB_PATH='G:/我的云端硬盘/TBM9/DB/evidence_db.csv'

& 'C:\Users\22923\anaconda3\envs\LLMenv\python.exe' `
  experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --llm-mode mock `
  --dates 2023-12-30 2023-12-28 2023-09-15 `
  --out-dir experiments\exp02_llm_generation_modes\outputs_test
```

## 真实 LLM 运行前 dry-run 检查

该命令只检查环境变量、输出目录、日期可用性和 prompt 模板文件，不发送任何 LLM 请求，不输出 API key。

```powershell
$env:DATA_ROOT='G:/我的云端硬盘/TBM9'
$env:DATA_DIR='G:/我的云端硬盘/TBM9/TBM9_2023'
$env:EVIDENCE_DB_PATH='G:/我的云端硬盘/TBM9/DB/evidence_db.csv'

$env:LLM_PROVIDER='openai_compatible'
$env:LLM_API_KEY='<your_api_key>'
$env:LLM_API_BASE='<your_api_base>'
$env:LLM_MODEL='<your_model>'
$env:LLM_TEMPERATURE='0.2'
$env:LLM_MAX_TOKENS='4096'

& 'C:\Users\22923\anaconda3\envs\LLMenv\python.exe' `
  experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --dry-run-real-config `
  --llm-mode real `
  --dates 2023-12-30 2023-12-28 2023-09-15 `
  --modes M0_template_only M1_direct_llm M2_raw_evidence_llm M3_twin_evidence_pack_llm M4_full_twin_governance_trace_boundary_reviser `
  --out-dir experiments\exp02_llm_generation_modes\outputs_real_3dates
```

检查结果保存到：

- `experiments/exp02_llm_generation_modes/outputs_real_3dates/exp02_real_config_dry_run.json`

## 真实 LLM 小样本运行

确认允许外发 Evidence Pack / prompt 后，再运行：

```powershell
$env:DATA_ROOT='G:/我的云端硬盘/TBM9'
$env:DATA_DIR='G:/我的云端硬盘/TBM9/TBM9_2023'
$env:EVIDENCE_DB_PATH='G:/我的云端硬盘/TBM9/DB/evidence_db.csv'

$env:LLM_PROVIDER='openai_compatible'
$env:LLM_API_KEY='<your_api_key>'
$env:LLM_API_BASE='<your_api_base>'
$env:LLM_MODEL='<your_model>'
$env:LLM_TEMPERATURE='0.2'
$env:LLM_MAX_TOKENS='4096'

& 'C:\Users\22923\anaconda3\envs\LLMenv\python.exe' `
  experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --llm-mode real `
  --dates 2023-12-30 2023-12-28 2023-09-15 `
  --modes M0_template_only M1_direct_llm M2_raw_evidence_llm M3_twin_evidence_pack_llm M4_full_twin_governance_trace_boundary_reviser `
  --out-dir experiments\exp02_llm_generation_modes\outputs_real_3dates
```

`LLM_PROVIDER` 可写 `openai_compatible` 或 `openai_or_compatible`，脚本会统一规范到当前后端 provider 名。

## 主要输出

汇总文件：

- `exp02_selected_dates.csv` / `.md`
- `exp02_generation_summary.csv` / `.md`
- `exp02_mode_comparison_summary.csv` / `.md`
- `exp02_revision_effect_summary.csv` / `.md`
- `exp02_boundary_violation_samples.csv`
- `exp02_unsupported_claim_samples.csv`
- `exp02_numeric_error_samples.csv`
- `exp02_failed_runs.csv`
- `exp02_overall_summary.json`
- `exp02_experiment_report.md`

每个日期和模式的结果保存到：

```text
outputs/reports/{date}/{mode}/
```

其中包括：

- `prompt.md`
- `report.md`
- `llm_response_raw.txt`
- `quality_summary.json`
- `trace_summary.json`
- `boundary_summary.json`
- `mode_summary.json`
- M4 额外输出 `revision_prompt.md`、`revision_response_raw.txt`、`revised_report.md`

## 失败隔离

脚本按 date/mode 独立捕获异常。单个日期或模式失败会写入：

- `exp02_failed_runs.csv`
- 对应 summary row 的 `error_message`

其他日期和模式会继续运行。

## 真实运行失败时优先检查

1. `LLM_API_KEY` 是否存在，但不要把 key 打印到日志里。
2. `LLM_API_BASE` 是否是 OpenAI-compatible chat completions base URL。
3. `LLM_MODEL` 是否正确，例如 `deepseek-chat`。
4. `LLM_MAX_TOKENS` 是否足够。
5. 输出目录是否可写。
6. `exp02_failed_runs.csv`、`mode_summary.json`、`llm_response_raw.txt`、`quality_summary.json`、`boundary_summary.json`。
