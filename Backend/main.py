from dataprocess import load_and_process, segments_to_text, compute_stats, stats_to_text
from lithology import detect_lithology, lithology_segments, lithology_to_text, lithology_efficiency, efficiency_to_text
from prompt_builder import build_prompt
from llm_api import call_llm
from gas_analysis import compute_gas_stats, gas_stats_to_text

import pandas as pd

csv_path = r"Backend\tbm_data_20231024.csv"

# 1) 载入数据
df = pd.read_csv(csv_path)
df["运行时间-time"] = pd.to_datetime(df["运行时间-time"])

# 2) 工况分析
segments = load_and_process(csv_path)
seg_text = segments_to_text(segments)
stats = compute_stats(segments)
stats_text = stats_to_text(stats)
#print(segments)

# 3) 围岩识别
df, labels = detect_lithology(df)

# 围岩分段
litho_segments = lithology_segments(df)
litho_text = lithology_to_text(litho_segments)
#print(litho_text)
# 围岩推进效率
eff_df = lithology_efficiency(df)
eff_text = efficiency_to_text(eff_df)

# 4) 气体报告
gas_stats = compute_gas_stats(df)
gas_text = gas_stats_to_text(gas_stats)
#print(gas_stats)
# 5) 构造 Prompt（新增围岩内容）
prompt = build_prompt(seg_text, stats_text, litho_text, eff_text, gas_text)
#print(prompt)

# 6) 调用 LLM 生成报告
#report = call_llm(prompt)
#print(report)
