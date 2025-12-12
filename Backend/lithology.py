# lithology.py

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA


# 1. 围岩识别（聚类分析）
def detect_lithology(df, features=["贯入度", "总推进力", "刀盘转矩", "推进速度"], n_clusters=3):

    df2 = df[features].copy()
    df2 = df2[(df2["贯入度"] > 0) & (df2["总推进力"] > 0)]
    df2 = df2.dropna()

    scaler = StandardScaler()
    df_scaled = scaler.fit_transform(df2)

    kmeans = KMeans(n_clusters=n_clusters, random_state=0)
    labels = kmeans.fit_predict(df_scaled)

    df.loc[df2.index, "岩性编码"] = labels

    return df, labels


# ============================================================
# 2. 岩性分段
# ============================================================
def lithology_segments(df):
    segments = {}

    for label in sorted(df["岩性编码"].dropna().unique()):
        label = int(label)
        segs = []

        in_seg = False
        start = None

        for i in range(len(df)):
            cur = df["岩性编码"].iloc[i]
            cur_t = df["运行时间-time"].iloc[i]

            if cur == label and not in_seg:
                in_seg = True
                start = cur_t

            if in_seg and cur != label:
                end = df["运行时间-time"].iloc[i - 1]
                segs.append((start, end))
                in_seg = False

        if in_seg:
            end = df["运行时间-time"].iloc[-1]
            segs.append((start, end))

        segments[label] = segs

    return segments


# ============================================================
# 3. 岩性段落 → 文本
# ============================================================
def lithology_to_text(segments):
    lines = []

    for label, segs in segments.items():
        if len(segs) == 0:
            continue

        lines.append(f"\n{label}号岩段：")

        for s, e in segs:
            dur = e - s
            lines.append(f"- {s.strftime('%H:%M:%S')} ~ {e.strftime('%H:%M:%S')}（持续 {dur}）")

    return "\n".join(lines)


# ============================================================
# 4. 岩性推进效率统计
# ============================================================
def lithology_efficiency(df):
    eff = df.groupby("岩性编码").agg({
        "贯入度": "mean",
        "推进速度": "mean",
        "总推进力": "mean"
    }).rename(columns={
        "贯入度": "平均贯入度",
        "推进速度": "平均推进速度",
        "总推进力": "平均推力"
    })

    eff["单位能耗_推力除贯入度"] = eff["平均推力"] / eff["平均贯入度"]

    return eff


# ============================================================
# 5. 岩性统计（专业工程师版）★新增★
# ============================================================
def lithology_stats(df, segments):
    """
    统计专业指标：
    - 每个岩性的累计时长
    - 占总体时长的比例
    - 最大连续时段
    - 岩性切换次数
    """

    stats = {}

    total_time = df["运行时间-time"].iloc[-1] - df["运行时间-time"].iloc[0]

    # 岩性序列（用于统计切换）
    lith_seq = list(df["岩性编码"].dropna())

    # 切换次数
    switches = sum(1 for i in range(1, len(lith_seq)) if lith_seq[i] != lith_seq[i - 1])

    for label, segs in segments.items():
        total_dur = sum((e - s).total_seconds() for s, e in segs)
        max_seg = max(segs, key=lambda x: (x[1] - x[0]).total_seconds()) if len(segs) else None

        stats[label] = {
            "累计时长_s": total_dur,
            "累计时长_min": total_dur / 60,
            "占比": total_dur / total_time.total_seconds(),
            "最大连续段": max_seg,
        }

    stats["岩性切换次数"] = switches
    return stats


# ============================================================
# 6. 岩性效率 → 文本（LLM可读）
# ============================================================
def efficiency_to_text(eff_df):
    lines = []
    lines.append("不同岩性的推进效率统计如下：\n")

    for label, row in eff_df.iterrows():
        avg_pen = row["平均贯入度"]
        avg_speed = row["平均推进速度"]
        avg_force = row["平均推力"]
        ratio = row["单位能耗_推力除贯入度"]

        lines.append(
            f"岩性 {label}：平均贯入度 {avg_pen:.2f}，平均推进速度 {avg_speed:.2f}，"
            f"平均推力 {avg_force:.2f}，单位能耗（推力/贯入度）{ratio:.2f}。"
        )

    return "\n".join(lines)


# ============================================================
# 7. 岩性总体统计 → 文本（LLM可读）★新增★
# ============================================================
def lithology_stats_to_text(stats):
    lines = []
    lines.append("\n围岩总体统计：")

    for label in sorted([k for k in stats.keys() if isinstance(k, int)]):

        d = stats[label]
        dur = d["累计时长_min"]
        percent = d["占比"] * 100

        if d["最大连续段"]:
            s, e = d["最大连续段"]
            longest = f"{s.strftime('%H:%M:%S')}~{e.strftime('%H:%M:%S')}"
        else:
            longest = "无"

        lines.append(
            f"\n岩性 {label}：\n"
            f"- 累计掘进时长：{dur:.1f} 分钟（占比 {percent:.1f}%）\n"
            f"- 最大连续岩段：{longest}\n"
        )

    lines.append(f"\n岩性切换次数：{stats['岩性切换次数']} 次。")

    return "\n".join(lines)
