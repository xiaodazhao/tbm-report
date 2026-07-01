# Exp02：LLM 生成模式对比实验

本目录用于记录 **Exp02：TBM 施工报告 LLM 生成模式对比实验**。

当前推荐采用的固定结果版本为：

```text
experiments/exp02_llm_generation_modes/outputs_real_win_15dates_fixed_v31/
```

该版本是当前 15 个样本日期真实 LLM 小样本实验的 fixed baseline。它不代表所有工程场景的泛化结论，但可以作为后续论文实验章节中“生成模式对比”的当前稳定结果。

---

## 1. 实验目标

Exp02 的目标是比较不同 LLM 输入约束强度下，TBM 施工日报自动生成在以下方面的表现：

- 报告章节完整性；
- evidence grounding / 可追溯支撑；
- unsupported claim 数量；
- numeric / E14 数值语义错误；
- forward fact misuse 等边界违规；
- M4 revision 闭环的修订效果。

这里的核心问题不是“直接让 LLM 判断地质风险”，而是比较：

```text
证据组织方式 + governance 边界约束 + Quality / Trace / Revision 闭环
```

是否能让报告生成更稳定、更可追溯、更少越界。

---

## 2. 方法主线边界

Exp02 基于当前后端主流程和 Exp01 已冻结结果：

```text
PLC / TSP / HSP / sketch
-> time_valid + spatial_relevant
-> 10m ConstructionStateCell
-> RAI / GRS / GRCI
-> Prompt Evidence Pack
-> Planner / Generator / Revision
-> Quality / Trace
-> TBM 施工日报
```

必须明确：

- LLM 不判断地质风险；
- GRCI 不是灾害概率；
- RAI / GRS / GRCI 是启发式关注指标，不是监督学习风险预测模型；
- `forward_attention` 不是已发生事实；
- 前方提示只能写成“关注/提示/需复核”，不能写成现场已揭露事实；
- `daily_excavated_scope` / `aligned_scope` 是 10m cell 对齐后的已掘复核范围，不是实际推进范围；
- 实际推进范围只能来自 `daily_plc_range`；
- 实际日进尺只能来自 `daily_advance_m`；
- M4 的核心不是“让 LLM 直接写日报”，而是 Evidence Pack 约束、边界控制、Quality / Trace 反馈和 Reviser 闭环。

---

## 3. 五种生成模式

| 模式 | 含义 | 是否调用 LLM | 约束强度 |
|---|---|---:|---|
| `M0_template_only` | 模板基线，不调用 LLM，直接按结构化证据填充报告 | 否 | 固定模板 |
| `M1_direct_llm` | 只给日期和基础信息，模拟直接让 LLM 写报告 | 是 | 最弱 |
| `M2_raw_evidence_llm` | 给较粗粒度 PLC / 地质 / 气体 / 前方摘要 | 是 | 弱 |
| `M3_twin_evidence_pack_llm` | 给 DailyConstructionTwin / Evidence Pack 和 governance，但不做自动修订 | 是 | 强 |
| `M4_full_twin_governance_trace_boundary_reviser` | 完整方法：Twin Evidence Pack + governance + Quality / Trace / Boundary Checker + Reviser | 是 | 最强 |

M4 是当前论文方法候选主模式。

---

## 4. 版本演进记录

### 4.1 初始问题

早期 M4 出现过以下问题：

```text
report 过短；
章节缺失；
revision 过度压缩；
quality_score 很低；
最终报告只保留前几章。
```

主要原因：

```text
revision 阶段 draft_report 被截断；
reviser 只看到前半部分报告；
导致后 4 章丢失。
```

### 4.2 v2 修复

v2 修复内容：

- M4 revision prompt 不再截断完整 draft report；
- 增加 deterministic section guard；
- 修复部分 boundary false positive；
- 修复 grounding checker fake zero；
- 统一 9 个标准章节标题。

v2 解决了结构问题，但出现新的问题：

```text
M4 revision 大多 no-op；
pre_unsupported 接近 post_unsupported；
M4 unsupported / numeric 数量偏高。
```

v2 M4 主要结果：

```text
M4 avg_quality = 76.33
M4 avg_grounding = 0.6189
M4 total_unsupported = 604
M4 total_numeric = 534
M4 total_E14 = 0
M4 total_boundary = 0
M4 missing_sections = 0
M4 section_completeness = 1.0
```

### 4.3 v3 修复

v3 修复内容：

- sentence splitter 不再把 `1.0m`、`67.5%`、`2023-09-15`、`DK1013+198` 切成碎片 claim；
- 增强 scope / metadata grounding；
- `report date`、`daily_plc_range`、`daily_advance_m`、`current_face`、`forward_scope`、`daily_excavated_scope`、`local_background_scope` 可以被正确支撑；
- M4 revision feedback 从碎片 claim 改为完整句子 + section + error_type + suggested_action；
- M4 revision prompt 强制逐条处理 `revision_feedback`；
- section guard 缺章时补保守占位句，不再默认补回初稿正文。

v3 结果明显改善：

```text
M4 avg_quality = 88.33
M4 avg_grounding = 0.8881
M4 total_unsupported = 86
M4 total_numeric = 33
M4 total_E14 = 3
M4 total_boundary = 1
M4 missing_sections = 0
M4 section_completeness = 1.0
```

说明：

```text
M4 revision no-op 基本解决；
unsupported / numeric 显著下降；
但仍有 3 条 E14 和 1 条 boundary 残留。
```

### 4.4 v3.1 最小修复

v3.1 只处理 v3 残留的 3 条 E14 和 1 条 boundary，没有修改主 pipeline、RAI/GRS/GRCI 或 Evidence Pack 语义。

修改文件：

```text
backend/llm/report_quality_checker.py
backend/llm/twin_boundary_checker.py
experiments/exp02_llm_generation_modes/prompts/M4_revision_prompt.md
experiments/exp02_llm_generation_modes/run_exp02_llm_generation_modes.py
backend/tests/test_quality_error_taxonomy_contract.py
backend/tests/test_twin_boundary_checker.py
backend/tests/test_exp02_llm_generation_modes_contract.py
```

核心修复：

- E14 更精确识别；
- 避免把 `cell_1013940_1013950`、`10m 对齐复核单元`、`用于已掘复核的范围`误判为实际推进范围；
- boundary checker 放行“需结合后续现场揭露进行复核/核查/验证”等安全句式；
- M4 revision prompt 要求把“前方揭示 / 前方已揭露 / 前方现场揭露”改为“前方提示 / 前方关注提示 / 超前预报提示”；
- revision feedback 中 `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE` 和 `boundary:forward_fact_misuse` 的 `suggested_action` 更具体。

v3.1 测试：

```text
针对性测试：70 passed
全量后端测试：140 passed
```

v3.1 dry-run：

```text
checks_passed: true
no_external_request_sent: true
api_key_value_logged: false
```

v3.1 real run：

```text
输出目录：experiments/exp02_llm_generation_modes/outputs_real_win_15dates_fixed_v31

run_count = 75
failed_count = 0
selected_date_count = 15
```

v3.1 M4 结果：

```text
M4 avg_quality = 96.6667
M4 avg_grounding = 0.909253
M4 total_unsupported = 64
M4 total_numeric = 16
M4 total_E14 = 0
M4 total_boundary = 0
M4 missing_sections = 0
```

v3 到 v3.1 的改善：

```text
M4 E14: 3 -> 0
M4 boundary: 1 -> 0
M4 unsupported: 86 -> 64
M4 numeric: 33 -> 16
M4 avg_quality: 88.33 -> 96.67
```

---

## 5. 当前 fixed 15 dates v3.1 结论

当前可以将 `outputs_real_win_15dates_fixed_v31/` 作为 Exp02 的 15 天真实 LLM fixed 结果。

在本工程 15 个样本日期的真实 LLM 实验中，`M4_full_twin_governance_trace_boundary_reviser` 是综合表现最好的 LLM 模式：

- quality 最高；
- grounding 最高；
- unsupported 最低；
- numeric 最低；
- `missing_sections = 0`；
- `E14 = 0`；
- `boundary = 0`；
- report length 合理；
- revision 闭环有效。

### 5.1 v3.1 模式汇总

| mode | run_count | success_count | avg_quality | avg_grounding | unsupported_total | boundary_total |
|---|---:|---:|---:|---:|---:|---:|
| M0_template_only | 15 | 15 | 76.00 | 1.0000 | 0 | 0 |
| M1_direct_llm | 15 | 15 | 69.67 | 0.7110 | 192 | 2 |
| M2_raw_evidence_llm | 15 | 15 | 68.67 | 0.7222 | 189 | 3 |
| M3_twin_evidence_pack_llm | 15 | 15 | 74.00 | 0.7729 | 205 | 0 |
| M4_full_twin_governance_trace_boundary_reviser | 15 | 15 | 96.67 | 0.9093 | 64 | 0 |

### 5.2 需要保留的限制

当前结论只来自本工程 15 个样本日期，不能直接泛化到所有 TBM 项目。

不能写成：

- LLM 能判断地质风险；
- M4 已证明工程泛化有效；
- GRCI 是灾害概率；
- 所有错误已经消失。

应写成：

```text
在本工程 15 个样本日期的真实 LLM 小样本实验中，基于 DailyConstructionTwin、Evidence Pack、governance、Quality / Trace 和 revision 闭环的 M4 模式，相比直接生成和粗粒度 evidence 输入模式，表现出更高的章节完整性、grounding rate 和边界稳定性。
```

M4 仍有少量 unsupported / numeric，主要来自细粒度 grounding 匹配和 LLM 表述问题，不建议为了追求 0 继续反复调 prompt。

---

## 6. Windows 运行命令

### 6.1 进入项目

```powershell
cd C:\Users\22923\Desktop\tbm-report
conda activate LLMenv
```

### 6.2 设置数据路径

```powershell
$env:DATA_ROOT="G:/我的云端硬盘/TBM9"
$env:DATA_DIR="G:/我的云端硬盘/TBM9/TBM9_2023"
$env:EVIDENCE_DB_PATH="G:/我的云端硬盘/TBM9/DB/evidence_db.csv"
```

### 6.3 设置 LLM 参数

不要在 README 或日志中写真实 API key。

```powershell
$env:LLM_PROVIDER="openai_compatible"
$env:LLM_API_BASE="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"
$env:LLM_TEMPERATURE="0.2"
$env:LLM_MAX_TOKENS="4096"
$env:LLM_API_KEY="YOUR_API_KEY"
```

注意：

- DeepSeek OpenAI-compatible endpoint 使用 `https://api.deepseek.com`；
- 不要使用 `https://api.deepseek.com/anthropic`；
- 不要打印 API key；
- 建议真实运行前先执行 dry-run。

### 6.4 Mock 运行

Mock 运行不调用外部 LLM，用于检查脚本和输出结构。

```powershell
python experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --llm-mode mock `
  --dates 2023-12-30 2023-12-28 2023-09-15 `
  --out-dir experiments\exp02_llm_generation_modes\outputs_test
```

### 6.5 v3.1 15 天 dry-run

该命令只检查环境变量、输出目录、日期可用性和 prompt 模板文件，不发送任何 LLM 请求，不输出 API key。

```powershell
python experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --dry-run-real-config `
  --llm-mode real `
  --dates 2023-09-15 2023-09-23 2023-09-29 2023-10-02 2023-10-10 2023-10-16 2023-10-25 2023-11-01 2023-11-10 2023-11-20 2023-11-29 2023-12-08 2023-12-18 2023-12-28 2023-12-30 `
  --modes M0_template_only M1_direct_llm M2_raw_evidence_llm M3_twin_evidence_pack_llm M4_full_twin_governance_trace_boundary_reviser `
  --out-dir experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31
```

dry-run 必须确认：

```text
checks_passed: true
no_external_request_sent: true
api_key_value_logged: false
```

### 6.6 v3.1 15 天真实 LLM 运行

确认允许外发 Evidence Pack / prompt 后，再运行：

```powershell
python experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --llm-mode real `
  --dates 2023-09-15 2023-09-23 2023-09-29 2023-10-02 2023-10-10 2023-10-16 2023-10-25 2023-11-01 2023-11-10 2023-11-20 2023-11-29 2023-12-08 2023-12-18 2023-12-28 2023-12-30 `
  --modes M0_template_only M1_direct_llm M2_raw_evidence_llm M3_twin_evidence_pack_llm M4_full_twin_governance_trace_boundary_reviser `
  --out-dir experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31
```

### 6.7 读取结果

```powershell
Get-Content experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31\exp02_failed_runs.csv
Get-Content experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31\exp02_overall_summary.json
Get-Content experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31\exp02_mode_comparison_summary.md
Get-Content experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31\exp02_revision_effect_summary.md
Get-Content experiments\exp02_llm_generation_modes\outputs_real_win_15dates_fixed_v31\exp02_generation_summary.md
```

如果 PowerShell 显示中文乱码，可以优先查看 `.csv` / `.json` 文件，或使用 UTF-8 工具打开。

---

## 7. 输出文件说明

Exp02 汇总输出位于输出目录根部，例如：

```text
experiments/exp02_llm_generation_modes/outputs_real_win_15dates_fixed_v31/
```

主要文件：

| 文件 | 用途 |
|---|---|
| `exp02_failed_runs.csv` | 失败运行记录；如果为空，说明 date/mode 均成功 |
| `exp02_overall_summary.json` | 全局统计，包括 selected dates、run_count、failed_count、平均质量等 |
| `exp02_mode_comparison_summary.md/.csv` | 五种模式聚合对比，用于论文结果表 |
| `exp02_generation_summary.md/.csv` | 每个日期、每个模式的质量明细 |
| `exp02_revision_effect_summary.md/.csv` | M4 revision 前后 unsupported / boundary 对比 |
| `exp02_unsupported_claim_samples.csv` | unsupported claim 样本 |
| `exp02_numeric_error_samples.csv` | numeric / E14 样本 |
| `exp02_boundary_violation_samples.csv` | boundary violation 样本 |
| `exp02_selected_dates.md/.csv` | 本次实验选取的日期 |
| `exp02_experiment_report.md` | 自动生成的实验汇总报告 |

每个日期和模式的详细结果保存到：

```text
reports/{date}/{mode}/
```

常见文件：

| 文件 | 用途 |
|---|---|
| `prompt.md` | 该模式发送给 LLM 的 prompt |
| `report.md` | 最终报告正文 |
| `llm_response_raw.txt` | 原始 LLM 响应 |
| `quality_summary.json` | Quality Checker 输出 |
| `trace_summary.json` | Trace / grounding 输出 |
| `boundary_summary.json` | Boundary Checker 输出 |
| `mode_summary.json` | 单次 date/mode 汇总 |
| `revision_prompt.md` | M4 修订阶段 prompt |
| `revision_response_raw.txt` | M4 修订阶段原始响应 |
| `revised_report.md` | M4 修订后报告 |
| `section_guard_summary.json` | M4 section guard 元信息 |

---

## 8. 失败隔离机制

脚本按 date/mode 独立捕获异常。

单个日期或模式失败会写入：

- `exp02_failed_runs.csv`
- 对应 summary row 的 `error_message`

其他日期和模式会继续运行，不会因为一个 date/mode 失败而中断整个实验。

---

## 9. 真实运行失败时优先检查

1. `LLM_API_KEY` 是否存在，但不要把 key 打印到日志里。
2. `LLM_API_BASE` 是否是 OpenAI-compatible chat completions base URL。
3. `LLM_MODEL` 是否正确，例如 `deepseek-chat`。
4. `LLM_MAX_TOKENS` 是否足够。
5. 输出目录是否可写。
6. `exp02_failed_runs.csv` 中的 `error_message`。
7. 对应 `reports/{date}/{mode}/mode_summary.json`。
8. 对应 `llm_response_raw.txt`、`quality_summary.json`、`boundary_summary.json`。

---

## 10. 当前不建议做什么

当前不建议继续反复调 prompt，只为了追求 `unsupported = 0`。

当前不建议直接跑 91 天真实 LLM。

当前不建议把 M4 残余 unsupported / numeric 全部解释为 LLM 幻觉，因为其中可能包含 checker 粒度、grounding 匹配和证据表达不完全一致的问题。

当前不建议把 15 天结果写成工程泛化结论。

当前不建议改变主 pipeline、RAI / GRS / GRCI、Evidence Pack 语义或 boundary checker 统计口径来适配个别生成结果。

---

## 11. 下一步建议

建议按以下顺序推进：

1. 冻结 `outputs_real_win_15dates_fixed_v31/` 作为 15 天 fixed baseline；
2. 整理 v3.1 的 15 天结果表，放入论文实验章节；
3. 进入 30 天分层样本验证；
4. 如果 30 天仍保持 M4 最优且 E14 / boundary 稳定为 0，再考虑是否跑全 91 天；
5. 后续主要做结果分析，不再频繁修改 prompt/checker，避免实验口径不稳定。

---

## 12. 和主后端的关系

Exp02 不修改当前 TBM 日报主 pipeline，不替换默认 no-LLM/template 模式。

Exp02 是实验目录下的生成模式对比实验，主要用于论文实验分析。主后端仍以 DailyConstructionTwin、ConstructionStateCell、Evidence Pack、Quality / Trace 为稳定底座。

---

## 13. 论文实验章节写作指南

本节用于把当前 Exp02 fixed v3.1 的真实 LLM 小样本实验整理成论文实验章节可直接使用的材料。这里不重新定义方法，不引入新模块，只解释当前实验的定位、问题、指标、结果和写作边界。

### 13.1 本实验在论文中的定位

Exp02 不是主流程有效性实验，也不是地质风险预测实验，而是 **生成模式对比实验**。它用于验证不同 LLM 输入约束和治理机制下，TBM 施工日报生成质量、证据支撑性和边界安全性的差异。

在论文中，Exp02 可用于支撑“证据约束生成与修订闭环有效性”的论证：

- `M0_template_only` 是非 LLM 模板基线；
- `M1_direct_llm`、`M2_raw_evidence_llm`、`M3_twin_evidence_pack_llm` 是对照模式；
- `M4_full_twin_governance_trace_boundary_reviser` 是本文方法候选主模式；
- LLM 的角色是受约束的文本生成与修订模块；
- LLM 不负责判断地质风险；
- 地质关注、施工响应、前方提示等均来自 ConstructionStateCell、Evidence Pack、RAI / GRS / GRCI 和 Quality / Trace 等结构化证据。

建议论文中将本实验表述为：

```text
为评估证据约束与治理闭环对 TBM 施工日报生成质量的影响，本文设置五种生成模式进行对比实验。实验重点考察报告质量、证据支撑、数值语义错误、边界违规和章节完整性，而非评估地质灾害预测准确率。
```

### 13.2 实验问题与假设

建议设置以下研究问题：

```text
RQ1：相比直接 LLM 生成，引入证据输入是否能提升 TBM 日报的 grounding 和质量？
RQ2：相比 raw evidence 输入，引入 DailyConstructionTwin / Evidence Pack 是否能改善报告结构化和证据约束？
RQ3：相比仅使用 Evidence Pack，引入 governance、boundary checker、quality/trace feedback 和 reviser 是否能进一步减少 unsupported claim、numeric error 和边界违规？
```

对应实验假设可写为：

```text
H1：M2/M3/M4 相比 M1 应具有更好的 grounding。
H2：M4 相比 M1/M2/M3 应具有更高的 quality score 和 section completeness。
H3：M4 相比 M1/M2/M3 应减少 unsupported claim、numeric error、E14 和 boundary violation。
H4：M4 revision 应在多数日期上降低 unsupported claim 或 boundary violation。
```

这些假设应保持保守，不应写成“证明方法在所有工程中泛化有效”。

### 13.3 实验对象与样本设置

实验对象是本工程 TBM 施工日报自动生成任务。

当前 fixed baseline 使用 15 个样本日期：

```text
2023-09-15
2023-09-23
2023-09-29
2023-10-02
2023-10-10
2023-10-16
2023-10-25
2023-11-01
2023-11-10
2023-11-20
2023-11-29
2023-12-08
2023-12-18
2023-12-28
2023-12-30
```

运行规模：

```text
15 dates x 5 modes = 75 runs
```

真实 LLM 设置：

```text
provider: OpenAI-compatible API
model: deepseek-chat
temperature: 0.2
max tokens: 4096
```

注意：这 15 天是当前小样本 fixed baseline，不是最终全量实验。

### 13.4 对比模式设计

| 模式 | 输入信息 | 是否使用 Evidence Pack | 是否使用 governance | 是否使用 Trace/Quality feedback | 是否使用 Reviser | 目的 |
|---|---|---:|---:|---:|---:|---|
| M0_template_only | 结构化结果直接填充模板 | 是 | 是 | 否 | 否 | 非 LLM 模板基线，提供格式和证据填充对照 |
| M1_direct_llm | 日期和基础统计信息 | 否 | 否 | 否 | 否 | 模拟无结构约束的直接 LLM 生成 |
| M2_raw_evidence_llm | 粗粒度 PLC / 地质 / 气体 / 前方摘要 | 否 | 否 | 否 | 否 | 测试 raw evidence 输入能否提升生成质量 |
| M3_twin_evidence_pack_llm | DailyConstructionTwin / Evidence Pack | 是 | 是 | 否 | 否 | 测试结构化证据包本身的作用 |
| M4_full_twin_governance_trace_boundary_reviser | Evidence Pack + governance + Quality / Trace / Boundary feedback | 是 | 是 | 是 | 是 | 测试完整证据治理与修订闭环的作用 |

需要强调：M3 与 M4 的差异不是有没有证据，而是有没有完整质量追踪、边界检查和修订闭环。

### 13.5 评价指标定义

| 指标 | 含义 | 越高/越低越好 | 说明 |
|---|---|---|---|
| `avg_quality` | 综合质量分 | 越高越好 | 由 Quality Checker 依据章节完整性、错误类型、边界违规等综合计算 |
| `avg_grounding` | claim 被证据支撑的比例 | 越高越好 | 衡量报告内容与 Evidence Pack / trace 的匹配程度 |
| `unsupported_claim_count` | 未找到有效证据支撑的声明数量 | 越低越好 | 不应简单等同于全部 LLM 幻觉，可能包含 checker 粒度或证据表达匹配问题 |
| `numeric_error_count` | 数值类 grounding 错误数量 | 越低越好 | 包含数值无支撑、范围误写、里程/百分比等数值语义问题 |
| `E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE` | 把 10m 对齐复核范围误写为实际推进范围或实际日进尺 | 越低越好 | 本文特别关注的数值语义边界错误 |
| `boundary_violation_count` | 边界违规数量 | 越低越好 | 包括前方事实误用、GRCI 概率误用、PLC proxy 误用、停机因果误用等 |
| `missing_sections` | 缺失标准章节数 | 越低越好 | 用于识别报告结构不完整或 revision 过度压缩 |
| `section_completeness` | 章节完整性 | 越高越好 | 9 个标准章节的覆盖程度 |
| `report_length` | 报告长度 | 辅助指标 | 用于辅助识别过度压缩或异常短报告 |
| `revision_error_reduction_rate` | M4 修订前后错误降低比例 | 越高越好 | 仅用于 M4 revision 效果分析 |

注意：

- `M0_template_only` 的 grounding 可能为 1.0，但它是模板基线，不代表自由生成能力强；
- `unsupported_claim_count` 和 `numeric_error_count` 不应全部解释为 LLM 幻觉；
- E14 和 boundary 是本文特别关注的安全边界指标。

### 13.6 实验流程

实验流程如下：

1. 对每个样本日期构建 DailyConstructionTwin / Evidence Pack；
2. 对同一日期分别运行 M0-M4 五种模式；
3. 对每个模式输出的日报进行 Quality Checker、Grounding Checker、Boundary Checker 检查；
4. 对 M4 执行 `initial generation -> quality/trace/boundary evaluation -> revision feedback -> revised report -> section guard -> final evaluation`；
5. 汇总每个 date/mode 的 `quality`、`grounding`、`unsupported`、`numeric`、`E14`、`boundary`、`missing_sections`；
6. 形成 mode comparison summary 和 revision effect summary。

M4 的闭环流程可写为：

```text
Evidence Pack
-> initial report
-> quality / grounding / boundary evaluation
-> revision feedback
-> revised report
-> section guard
-> final report
-> final evaluation
```

### 13.7 主要结果表

以下结果来自：

```text
experiments/exp02_llm_generation_modes/outputs_real_win_15dates_fixed_v31/
```

| mode | avg_quality | avg_grounding | total_unsupported | total_numeric | total_E14 | total_boundary | avg_missing_sections | avg_section_completeness | avg_report_length |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M0_template_only | 76.00 | 1.0000 | 0 | 0 | 0 | 0 | 3.00 | 0.6667 | 1120.3 |
| M1_direct_llm | 69.67 | 0.7110 | 192 | 76 | 0 | 2 | 2.00 | 0.7778 | 2002.6 |
| M2_raw_evidence_llm | 68.67 | 0.7222 | 189 | 44 | 1 | 3 | 2.00 | 0.7778 | 2789.6 |
| M3_twin_evidence_pack_llm | 74.00 | 0.7729 | 205 | 45 | 0 | 0 | 2.00 | 0.7778 | 3138.0 |
| M4_full_twin_governance_trace_boundary_reviser | 96.67 | 0.9093 | 64 | 16 | 0 | 0 | 0.00 | 1.0000 | 2339.0 |

从该表可见，在当前 15 个样本日期中，M4 在综合质量、grounding、unsupported、numeric、E14、boundary 和章节完整性方面均表现最好。

### 13.8 结果解读

#### 13.8.1 M4 综合最优

M4 在质量分、grounding、unsupported、numeric、E14、boundary 和章节完整性上综合最优。尤其是 `total_E14 = 0`、`total_boundary = 0` 和 `avg_section_completeness = 1.0`，说明完整 governance 与修订闭环能有效约束关键语义边界。

#### 13.8.2 M1 说明直接 LLM 不够可靠

M1 缺少结构化证据约束，`total_unsupported = 192`，`total_numeric = 76`，且存在 boundary violation。该结果说明直接让 LLM 生成 TBM 施工日报容易产生证据支撑不足或边界不稳定问题。

#### 13.8.3 M2 说明 raw evidence 不等于可靠生成

M2 虽引入证据输入，但 evidence 未经过 ConstructionStateCell / Evidence Pack / role gating 的严格组织，仍出现 `total_unsupported = 189`、`total_numeric = 44`、`total_E14 = 1` 和 `total_boundary = 3`。这说明“给 LLM 更多原始证据”并不自动等于更可靠的报告生成。

#### 13.8.4 M3 说明结构化证据包本身还不够

M3 使用 Twin Evidence Pack 后，边界违规为 0，但 `total_unsupported = 205`、`total_numeric = 45` 仍偏高。这表明结构化 Evidence Pack 能改善边界安全，但如果没有 Quality / Trace feedback 和 Reviser 闭环，仍难以充分减少 unsupported 与 numeric 问题。

#### 13.8.5 M4 说明闭环治理有效

M4 联合使用 Evidence Pack、governance、Boundary Checker、Quality / Trace feedback 和 Reviser，在保持章节完整的同时，显著降低 unsupported、numeric、E14 和 boundary violation。该结果支持本文提出的“证据约束 + 质量核验 + 修订闭环”生成策略。

### 13.9 M4 revision 效果分析

M4 revision summary 来自：

```text
experiments/exp02_llm_generation_modes/outputs_real_win_15dates_fixed_v31/exp02_revision_effect_summary.csv
```

聚合结果：

```text
pre_revision_unsupported_total = 103
post_revision_unsupported_total = 64
pre_revision_boundary_total = 0
post_revision_boundary_total = 0
average_revision_error_reduction_rate = 0.4552
positive_revision_dates = 11
no_change_dates = 2
negative_revision_dates = 2
```

M4 revision 在 15 个日期中的 11 个日期降低了 unsupported claim；2 个日期变化不明显；2 个日期 post unsupported 略高于 pre unsupported。这说明 revision 闭环总体有效，但不是所有日期都能单调改善。

需要注意：当前 revision summary 中没有 pre/post numeric 的完整对比字段，因此不应编造 numeric revision 降低率。numeric 的最终对比应使用最终 generation summary 中的模式聚合结果。

论文中可写：

```text
M4 的修订阶段不是简单润色，而是基于 Quality / Trace / Boundary feedback 对证据不足、数值未支撑和边界表述进行约束性改写。在 15 个样本日期中，M4 revision 将 unsupported claim 总数由 103 降至 64，平均错误降低率约为 45.5%，并保持最终 boundary violation 为 0。
```

### 13.10 版本修复与实验口径说明

v2 / v3 / v3.1 的修复主要集中在实验执行和评价口径的一致性问题上，包括：

- prompt 截断；
- checker false positive；
- sentence splitting；
- metadata grounding；
- revision feedback 可操作性；
- section guard 是否错误补回初稿正文。

这些修复没有改变主 pipeline，没有改变 Evidence Pack 语义，也没有改变 RAI / GRS / GRCI 的定义。因此，v3.1 可以视为修复实验执行与评价口径后的 fixed baseline，而不是重新定义方法。

论文写作中不应将 v1 / v2 / v3 与 v3.1 混合作为最终对比结果。建议：

- 最终结果表使用 fixed v3.1；
- 版本演进放入实验实现说明或附录；
- 不把早期版本的异常结果当作方法本身的最终性能。

### 13.11 可直接写入论文的段落

#### 13.11.1 实验设置段落

为评估不同 LLM 输入约束与治理机制对 TBM 施工日报生成质量的影响，本文设置五种生成模式进行对比实验。实验选取本工程 15 个样本日期，分别在相同日期集合上运行模板基线、直接 LLM 生成、raw evidence 输入生成、Twin Evidence Pack 生成以及完整 governance + revision 闭环生成五种模式。真实 LLM 采用 OpenAI-compatible 接口调用 DeepSeek `deepseek-chat` 模型，温度参数设置为 0.2。所有模式输出均采用相同的 Quality Checker、Grounding Checker 和 Boundary Checker 进行评价。

#### 13.11.2 评价指标段落

本文从报告质量、证据支撑、数值语义安全、边界安全和章节完整性五个方面评价生成结果。质量分用于综合衡量报告是否满足结构与语义要求；grounding rate 用于衡量报告声明获得结构化 Evidence Pack 支撑的比例；unsupported claim count 和 numeric error count 分别反映未支撑声明和数值语义错误；E14 用于识别将 10m 对齐复核范围误写为实际推进范围或实际日进尺的典型错误；boundary violation count 用于检查前方事实误用、GRCI 概率误用、PLC proxy 误用等方法边界问题。

#### 13.11.3 结果分析段落

实验结果表明，在本工程 15 个样本日期上，M4 完整方法模式取得最高综合质量分和最高 grounding rate，同时具有最低 unsupported claim count、numeric error count、E14 count 和 boundary violation count。与直接 LLM 生成和 raw evidence 输入相比，M4 通过 DailyConstructionTwin、Evidence Pack、governance 规则、Quality / Trace feedback 和 Reviser 闭环，将报告生成限制在结构化证据支持范围内，并显著减少了前方事实误用和 aligned scope 误写等关键语义错误。

#### 13.11.4 消融 / 对比分析段落

M1 与 M2 的对比反映了原始证据输入的作用，但 M2 仍存在 unsupported 和 boundary 问题，说明单纯提供更多证据并不足以保证报告可靠。M2 与 M3 的对比体现了结构化 Evidence Pack 对边界安全的贡献，M3 的 boundary violation 为 0，但 unsupported 和 numeric error 仍较高。M3 与 M4 的对比进一步说明，Quality / Trace feedback 与 Reviser 闭环能够在保留章节完整性的同时减少未支撑声明和数值语义错误。因此，完整闭环治理是提升 TBM 施工日报可追溯生成质量的关键环节。

#### 13.11.5 局限性段落

需要指出的是，当前实验仅基于本工程 15 个样本日期，尚不能证明该生成策略在所有 TBM 工程中的泛化有效性。LLM 在本文方法中仅作为受约束的文本生成与修订模块，不承担地质风险判断任务。GRCI 也不是灾害概率，而是已掘区段地质-施工响应耦合关注度指标。此外，M4 仍存在少量 unsupported 和 numeric 问题，后续需要在更大日期样本、典型案例复盘和人工评价中进一步检验其稳定性。

### 13.12 不应夸大的结论

不应写：

- M4 已证明适用于所有 TBM 工程；
- LLM 能自动判断地质风险；
- GRCI 是灾害概率；
- `forward_attention` 表示前方已经发生异常；
- `daily_excavated_scope` 是实际推进范围；
- 15 天实验已经完成最终统计验证；
- unsupported / numeric 剩余错误全部是 LLM 幻觉。

推荐写：

- 在本工程 15 个样本日期上；
- 真实 LLM 小样本实验；
- 表现出更好的 evidence grounding 和 boundary safety；
- 仍需更大样本进一步验证稳定性；
- M4 可作为后续扩展实验的 fixed baseline。

### 13.13 后续扩展实验建议

建议下一步路线：

1. 冻结 v3.1 作为 15 天 fixed baseline；
2. 做 30 天分层样本实验；
3. 观察 M4 是否仍保持 quality / grounding 最优、E14 / boundary 为 0；
4. 如果 30 天稳定，再考虑 91 天全量真实 LLM；
5. 不建议继续反复调 prompt 追求 `unsupported = 0`；
6. 更大的重点应是结果分析、case study 和 human evaluation。

30 天实验应尽量保持 v3.1 代码和评价口径不变，否则不能与 15 天 fixed baseline 直接比较。

### 13.14 建议放入论文的表格和图

建议表格：

- 表 1：五种生成模式对比设计；
- 表 2：评价指标定义；
- 表 3：15 天 fixed v3.1 模式对比结果；
- 表 4：M4 revision 前后对比；
- 表 5：典型错误类型与修订策略。

建议图：

- 图 1：Exp02 实验流程；
- 图 2：M0-M4 生成模式差异示意图；
- 图 3：M4 generation-revision-quality trace 闭环；
- 图 4：不同模式 quality / grounding 对比柱状图；
- 图 5：unsupported / numeric / boundary 错误数量对比图。

这些表和图应服务于“证据约束生成与修订闭环”的实验论证，而不是地质风险预测准确率评价。
