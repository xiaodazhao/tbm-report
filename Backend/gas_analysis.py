#gas_analysis.py
import pandas as pd
import numpy as np

# ========== 1. 气体字段 ==========
GAS_COLUMNS = [
    "氧气浓度", "一氧化碳浓度", "硫化氢浓度", "粉尘含量",
    "主驱动甲烷含量", "连接桥甲烷含量", "除尘风机出口甲烷含量",
    "二氧化碳含量", "一氧化氮含量", "二氧化硫含量"
]

# 安全阈值，可按规范修改
THRESHOLDS = {
    "氧气浓度": (19.5, 23.5),       # 正常范围
    "一氧化碳浓度": 24,             # mg/m3 (可改)
    "硫化氢浓度": 10,               # ppm
    "粉尘含量": 10,                 # mg/m3 (示例)
    "主驱动甲烷含量": 0.5,          # %
    "连接桥甲烷含量": 0.5,
    "除尘风机出口甲烷含量": 0.5,
    "二氧化碳含量": 0.5,           # %
    "一氧化氮含量": 20,             # ppm
    "二氧化硫含量": 2               # ppm
}

# ========== 2. 主函数：计算气体统计 ==========
def compute_gas_stats(df):
    results = {}

    for gas in GAS_COLUMNS:
        if gas not in df.columns:
            continue

        series = df[gas].dropna()
        if len(series) == 0:
            continue

        # 基础统计
        stats = {
            "min": float(series.min()),
            "max": float(series.max()),
            "mean": float(series.mean()),
        }

        # 超标检测
        threshold = THRESHOLDS.get(gas)
        if threshold is not None:
            if isinstance(threshold, tuple):  # 氧气浓度
                low, high = threshold
                exceed_mask = (series < low) | (series > high)
            else:
                exceed_mask = series > threshold

            stats["exceed_count"] = int(exceed_mask.sum())

            # 查找超标区间
            df_temp = df.copy()
            df_temp["exceed"] = exceed_mask.astype(int)
            df_temp["group"] = (df_temp["exceed"] != df_temp["exceed"].shift()).cumsum()

            segments = []

            for g, part in df_temp.groupby("group"):
                if part["exceed"].iloc[0] == 1:
                    start = part["运行时间-time"].iloc[0]
                    end = part["运行时间-time"].iloc[-1]
                    duration = (end - start).total_seconds()
                    segments.append({
                        "start": start,
                        "end": end,
                        "duration_sec": duration
                    })

            stats["exceed_segments"] = segments

        results[gas] = stats

    return results


# ========== 3. 文本化（给 LLM 用）==========
def gas_stats_to_text(stats):
    lines = []

    for gas, s in stats.items():
        line = f"{gas}: 平均 {s['mean']:.3f}, 最大 {s['max']:.3f}"

        if "exceed_count" in s:
            line += f"，超标 {s['exceed_count']} 次"

            if s["exceed_count"] > 0:
                segs = [
                    f"{seg['start'].strftime('%H:%M:%S')}~{seg['end'].strftime('%H:%M:%S')}（{seg['duration_sec']:.1f} 秒）"
                    for seg in s["exceed_segments"]
                ]
                line += f"\n  超标时段：{', '.join(segs)}"

        lines.append(line)

    return "\n".join(lines)
