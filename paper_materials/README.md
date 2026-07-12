# 论文材料目录

本目录集中保存当前论文写作可直接使用的表格、图、结果分析和完整草稿。旧草稿、临时插入稿和过程性说明已删除，避免与最终口径混淆。

## 推荐阅读顺序

1. [`01_exp02_results/analysis/exp02_results_section_draft.md`](01_exp02_results/analysis/exp02_results_section_draft.md)  
   Exp02 生成模式对比与消融实验章节草稿。

2. [`01_exp02_results/tables/publication_table_exp02_main.md`](01_exp02_results/tables/publication_table_exp02_main.md)  
   91 天 M0-M4 主结果表。

3. [`01_exp02_results/tables/publication_table_exp02_revision.md`](01_exp02_results/tables/publication_table_exp02_revision.md)  
   M4 自动修订效果表。

4. [`02_statistics/exp02_statistical_significance_analysis.md`](02_statistics/exp02_statistical_significance_analysis.md)  
   M4 相比基线方法的统计检验和效应量分析。

5. [`03_case_studies/exp02_case_study_draft.md`](03_case_studies/exp02_case_study_draft.md)  
   典型日期案例分析草稿。

6. [`04_indicator_robustness/paper_exp03_indicator_robustness_analysis.md`](04_indicator_robustness/paper_exp03_indicator_robustness_analysis.md)  
   RAI / GRS / GRCI 指标稳健性分析。

7. [`05_checker_review/checker_audit_summary.md`](05_checker_review/checker_audit_summary.md)  
   自动评价体系抽样审计说明。

8. [`06_full_paper_draft/full_paper_draft_v2_autcon_style.md`](06_full_paper_draft/full_paper_draft_v2_autcon_style.md)  
   当前完整论文草稿。

## 目录说明

| 目录 | 内容 |
|---|---|
| `01_exp02_results/` | 91 天 structured_trace_v1 主实验表格、图表和结果章节草稿 |
| `02_statistics/` | M4 vs M1/M2/M3 的统计显著性检验、效应量和分布图 |
| `03_case_studies/` | 典型案例分析草稿和错误样本表 |
| `04_indicator_robustness/` | RAI / GRS / GRCI 指标稳健性分析 |
| `05_checker_review/` | checker 抽样复核表和审计说明 |
| `06_full_paper_draft/` | 当前完整论文草稿 |

## 当前采用的实验口径

论文当前采用：

```text
experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/
```

核心结果：

```text
91 dates x 5 modes = 455 runs
failed_count = 0
M4 quality = 94.18
M4 grounding = 0.9153
M4 unsupported = 376
M4 numeric = 78
M4 boundary = 0
M4 missing_sections = 0
M4 revision reduction_rate = 40.97%
```

## 写作边界

- M0 是确定性模板基线，不代表自由生成能力。
- M4 是完整治理链路，不应写成 LLM 自主判断地质风险。
- RAI / GRS / GRCI 是启发式关注指标，不是灾害概率。
- `forward_attention` 只能写前方关注提示，不表示已发生事实。
- 当前实验为单一工程 91 个可用施工日，不应写成跨工程泛化验证。
- 自动评价指标不能完全替代人工复核，论文中需要保留该研究边界。
