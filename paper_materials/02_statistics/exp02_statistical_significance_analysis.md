# Exp02 91 天 M4 对比统计显著性检验

本检验基于同一施工日期内的配对结果，比较 M4 与 M1/M2/M3 在 quality、grounding、unsupported 和 numeric 四类指标上的差异。quality 与 grounding 越高越好，unsupported 与 numeric 越低越好。采用单侧 Wilcoxon signed-rank test；rank-biserial effect size 为正表示 M4 优于对照模式。

| comparison   | baseline_mode             | metric      | direction_expected   |   n_pairs |   baseline_mean |   M4_mean |   mean_expected_improvement |   median_expected_improvement |   improved_days |   worse_days |   tie_days |   wilcoxon_statistic |   p_value_one_sided |   rank_biserial_effect_size | interpretation   |
|:-------------|:--------------------------|:------------|:---------------------|----------:|----------------:|----------:|----------------------------:|------------------------------:|----------------:|-------------:|-----------:|---------------------:|--------------------:|----------------------------:|:-----------------|
| M4 vs M1     | M1_direct_llm             | quality     | M4 higher            |        91 |         70.7582 |   94.1758 |                     23.4176 |                       26      |              86 |            5 |          0 |               4133   |         2.02751e-16 |                      0.9747 | 显著；效应量极强 |
| M4 vs M1     | M1_direct_llm             | grounding   | M4 higher            |        91 |          0.7295 |    0.9153 |                      0.1858 |                        0.187  |              90 |            1 |          0 |               4185   |         6.16065e-17 |                      0.9995 | 显著；效应量极强 |
| M4 vs M1     | M1_direct_llm             | unsupported | M4 lower             |        91 |         12.5604 |    4.1319 |                      8.4286 |                        8      |              86 |            3 |          2 |               3993.5 |         1.79014e-16 |                      0.9943 | 显著；效应量极强 |
| M4 vs M1     | M1_direct_llm             | numeric     | M4 lower             |        91 |          4.8901 |    0.8571 |                      4.033  |                        4      |              87 |            1 |          3 |               3911.5 |         1.71872e-16 |                      0.9977 | 显著；效应量极强 |
| M4 vs M2     | M2_raw_evidence_llm       | quality     | M4 higher            |        91 |         72.956  |   94.1758 |                     21.2198 |                       26      |              85 |            6 |          0 |               4042   |         4.17295e-15 |                      0.9312 | 显著；效应量极强 |
| M4 vs M2     | M2_raw_evidence_llm       | grounding   | M4 higher            |        91 |          0.7253 |    0.9153 |                      0.1899 |                        0.2011 |              90 |            1 |          0 |               4183   |         6.58522e-17 |                      0.9986 | 显著；效应量极强 |
| M4 vs M2     | M2_raw_evidence_llm       | unsupported | M4 lower             |        91 |         13.4176 |    4.1319 |                      9.2857 |                        9      |              84 |            4 |          3 |               3888.5 |         4.60247e-16 |                      0.986  | 显著；效应量极强 |
| M4 vs M2     | M2_raw_evidence_llm       | numeric     | M4 lower             |        91 |          3.6703 |    0.8571 |                      2.8132 |                        2      |              72 |            9 |         10 |               3147   |         1.04151e-12 |                      0.8952 | 显著；效应量极强 |
| M4 vs M3     | M3_twin_evidence_pack_llm | quality     | M4 higher            |        91 |         68.9341 |   94.1758 |                     25.2418 |                       26      |              85 |            6 |          0 |               4056   |         3.30268e-15 |                      0.9379 | 显著；效应量极强 |
| M4 vs M3     | M3_twin_evidence_pack_llm | grounding   | M4 higher            |        91 |          0.7592 |    0.9153 |                      0.156  |                        0.1574 |              89 |            2 |          0 |               4153   |         1.77071e-16 |                      0.9842 | 显著；效应量极强 |
| M4 vs M3     | M3_twin_evidence_pack_llm | unsupported | M4 lower             |        91 |         13.8022 |    4.1319 |                      9.6703 |                       10      |              89 |            2 |          0 |               4176.5 |         7.6138e-17  |                      0.9955 | 显著；效应量极强 |
| M4 vs M3     | M3_twin_evidence_pack_llm | numeric     | M4 lower             |        91 |          2.4835 |    0.8571 |                      1.6264 |                        1      |              72 |            9 |         10 |               2995.5 |         1.04758e-10 |                      0.804  | 显著；效应量极强 |

## 结论

- M4 相比 M1：4 个指标中 4 个达到 p < 0.05；unsupported 和 numeric 的降低幅度可用于支撑 M4 在错误控制方面的优势。
- M4 相比 M2：4 个指标中 4 个达到 p < 0.05；unsupported 和 numeric 的降低幅度可用于支撑 M4 在错误控制方面的优势。
- M4 相比 M3：4 个指标中 4 个达到 p < 0.05；unsupported 和 numeric 的降低幅度可用于支撑 M4 在错误控制方面的优势。

注意：该检验仍基于自动评价指标，不能替代人工工程评价。
