# Exp02：真实 LLM 生成模式对比实验

Exp02 用于比较不同证据输入和治理约束强度下，TBM 施工日报自动生成的稳定性、证据支撑性和边界安全性。当前最终口径为 `structured_trace_v1`，最终结果目录为：

```text
experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/
```

该结果是当前论文采用的 Exp02 主结果。历史 3 天、15 天、30 天、重试过程和失败过程只作为运行过程记录，不再作为论文最终结论入口。

## 实验目标

Exp02 回答三个问题：

1. 直接调用 LLM 生成 TBM 施工日报是否可靠；
2. 仅增加原始证据输入是否足以提升报告质量；
3. Evidence Pack、Planning、Boundary、Structured Trace 和 Reviser 闭环是否能显著提升证据支撑、数值一致性和边界稳定性。

## 五种生成模式

| 模式 | 中文说明 | 是否调用 LLM | 作用 |
|---|---|---:|---|
| `M0_template_only` | 确定性模板基线 | 否 | 提供稳定格式基准，不代表自由生成能力 |
| `M1_direct_llm` | 基础统计直接 LLM | 是 | 只给日期、施工范围、PLC 工况摘要和气体摘要 |
| `M2_raw_evidence_llm` | 原始证据输入 LLM | 是 | 在 M1 基础上增加地质证据摘要、前方提示和高关注区段预览 |
| `M3_twin_evidence_pack_llm` | 结构化证据包 LLM | 是 | 使用 ConstructionStateCell / Evidence Pack，但不做自动修订 |
| `M4_full_twin_governance_trace_boundary_reviser` | 完整闭环方法 | 是 | Twin + Evidence Pack + Planning + Boundary + Structured Trace + Reviser |

M1-M4 是递进式设计，可作为模块贡献分析。M0 是模板基线，不参与自由生成能力比较。

## 最终实验规模

```text
selected_date_count = 91
mode_count = 5
expected_run_count = 455
failed_count = 0
```

## 91 天最终结果

| mode | quality mean | grounding mean | unsupported total | numeric total | E14 total | boundary total | missing sections total |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0_template_only | 100.00 | 1.0000 | 0 | 0 | 0 | 0 | 0 |
| M1_direct_llm | 70.76 | 0.7295 | 1143 | 445 | 0 | 10 | 182 |
| M2_raw_evidence_llm | 72.96 | 0.7253 | 1221 | 334 | 0 | 23 | 182 |
| M3_twin_evidence_pack_llm | 68.93 | 0.7592 | 1256 | 226 | 0 | 2 | 184 |
| M4_full_twin_governance_trace_boundary_reviser | 94.18 | 0.9153 | 376 | 78 | 0 | 0 | 0 |

M4 在 LLM 生成模式中取得最高平均质量分和最高证据支撑率，同时 unsupported、numeric、boundary 和缺章数量均显著低于 M1/M2/M3。

## M4 修订效果

```text
revision_applied_count = 91
pre_revision_unsupported_total = 637
post_revision_unsupported_total = 376
reduction_count = 261
reduction_rate = 40.97%
```

该修订不是简单润色，而是基于 Quality、Grounding、Boundary 和 Structured Trace 反馈，对证据不足、数值不一致和边界不安全表述进行约束性改写。

## 重要结果文件

最终结果目录中保留以下关键文件：

| 文件 | 说明 |
|---|---|
| `structured_trace_v1_final_mode_metrics.csv/.md` | 五种模式最终汇总 |
| `structured_trace_v1_m4_revision_summary.csv/.md` | M4 修订前后统计 |
| `structured_trace_v1_m4_daily_metrics.csv/.md` | M4 每日期指标 |
| `structured_trace_v1_integrity_check.json` | 完整性检查 |
| `structured_trace_v1_final_report.md` | 91 天实验总结 |
| `exp02_selected_91_dates.csv/.md` | 91 天日期清单 |

论文可用材料已整理到：

```text
paper_materials/01_exp02_results/
paper_materials/02_statistics/
paper_materials/03_case_studies/
```

## 复现命令

真实 LLM 运行前必须设置数据路径和 LLM 配置，并先执行 dry-run。不要打印或提交 API key。

```powershell
$env:DATA_ROOT="G:/我的云端硬盘/TBM9"
$env:DATA_DIR="G:/我的云端硬盘/TBM9/TBM9_2023"
$env:EVIDENCE_DB_PATH="G:/我的云端硬盘/TBM9/DB/evidence_db.csv"

$env:LLM_PROVIDER="openai_compatible"
$env:LLM_API_BASE="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"
$env:LLM_TEMPERATURE="0.2"
$env:LLM_MAX_TOKENS="4096"
$env:LLM_API_KEY="YOUR_API_KEY"
```

dry-run：

```powershell
python experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --dry-run-real-config `
  --llm-mode real `
  --all-available-dates `
  --modes M0_template_only M1_direct_llm M2_raw_evidence_llm M3_twin_evidence_pack_llm M4_full_twin_governance_trace_boundary_reviser `
  --out-dir experiments\exp02_llm_generation_modes\outputs_real_91dates_structured_trace_v1
```

真实运行：

```powershell
python experiments\exp02_llm_generation_modes\run_exp02_llm_generation_modes.py `
  --llm-mode real `
  --all-available-dates `
  --modes M0_template_only M1_direct_llm M2_raw_evidence_llm M3_twin_evidence_pack_llm M4_full_twin_governance_trace_boundary_reviser `
  --out-dir experiments\exp02_llm_generation_modes\outputs_real_91dates_structured_trace_v1
```

如遇 API 500/503、连接中断或超时，应只补跑失败项并合并结果，不要修改评价规则或 prompt。

## 论文写作边界

- M0 的高分来自确定性模板填充，不代表自由生成能力。
- M4 的优势应表述为“在本工程 91 个可用施工日中表现稳定”，不要写成跨工程泛化结论。
- LLM 不承担地质风险判断任务，只在结构化证据约束下组织、表达和修订文本。
- GRCI 不是灾害概率，forward_attention 不是已发生事实。
- 当前自动评价指标不能完全替代人工复核，论文中仍需配合案例分析和人工评价说明。
