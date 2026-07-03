# 论文材料整理包

本目录集中存放当前 TBM 施工日报论文写作可用材料。所有文件均复制自已有实验结果或分析输出，不包含 API key，不重新运行 LLM，不修改主流程。

## 目录结构

- `01_exp02_results/`：91 天 structured_trace_v1 主实验表格、图表和结果章节草稿。
- `02_statistics/`：M4 vs M1/M2/M3 配对显著性检验、效应量和分布图。
- `03_case_studies/`：典型案例分析草稿和错误样本。
- `04_indicator_robustness/`：RAI / GRS / GRCI 指标稳健性分析。
- `05_checker_review/`：checker 抽样复核表和审计说明。

## 推荐使用顺序

1. 先阅读 `01_exp02_results/analysis/exp02_results_section_draft.md`。
2. 再阅读 `02_statistics/exp02_statistical_significance_analysis.md`。
3. 然后阅读 `03_case_studies/exp02_case_study_draft.md`。
4. 指标质疑部分参考 `04_indicator_robustness/paper_exp03_indicator_robustness_analysis.md`。
5. 人工复核准备参考 `05_checker_review/checker_manual_review_samples.csv`。

## 注意事项

- M0 是确定性模板基线，不代表自由生成能力。
- M4 是完整治理链路，不应被写成 LLM 自主判断地质风险。
- GRCI 是已掘区段地质-施工响应耦合关注度，不是灾害概率。
- forward_attention 只能写前方关注提示，不表示已发生事实。
