# dataprocess.py
import pandas as pd


# ===== 工况段落解析（核心） =====
def load_and_process(csv_path):
    df = pd.read_csv(csv_path)

    df['运行时间-time'] = pd.to_datetime(df['运行时间-time'])
    df['working'] = df['贯入度'] > 0
    df['group'] = (df['working'] != df['working'].shift()).cumsum()

    segments_df = df.groupby('group').agg(
        start_time=('运行时间-time', 'first'),
        end_time=('运行时间-time', 'last'),
        is_working=('working', 'first')
    )

    segments = []
    for _, row in segments_df.iterrows():
        seg = {
            "start": row["start_time"],
            "end": row["end_time"],
            "state": "work" if row["is_working"] else "stop",
            "duration_sec": (row["end_time"] - row["start_time"]).total_seconds()
        }
        segments.append(seg)

    return segments



# ===== 工况段落 → 文本 =====
def segments_to_text(segments):
    lines = []
    for s in segments:
        start = s["start"].strftime("%Y-%m-%d %H:%M:%S")
        end = s["end"].strftime("%Y-%m-%d %H:%M:%S")

        dur = s["duration_sec"]
        dur_str = f"{int(dur)} 秒" if dur < 60 else f"{dur/60:.1f} 分钟"

        state_cn = "掘进" if s["state"] == "work" else "停机"

        lines.append(f"在 {start} 到 {end} 期间，TBM 处于{state_cn}状态，持续 {dur_str}。")

    return "\n".join(lines)



# ===== 统计计算 =====
def compute_stats(segments):
    work = [x for x in segments if x["state"] == "work"]
    stop = [x for x in segments if x["state"] == "stop"]

    def total(xs): return sum(x["duration_sec"] for x in xs)
    def longest(xs): return max(xs, key=lambda x: x["duration_sec"]) if xs else None

    stats = {
        "work_count": len(work),
        "stop_count": len(stop),
        "work_total_min": total(work) / 60,
        "stop_total_min": total(stop) / 60,
        "longest_work": longest(work),
        "longest_stop": longest(stop),
        "short_works": [x for x in work if x["duration_sec"] < 60],
        "short_stops": [x for x in stop if x["duration_sec"] < 60],
    }

    return stats



# ===== 统计 → 文本 =====
def stats_to_text(stats):
    def fmt_seg(s):
        if not s:
            return "无"
        start = s["start"].strftime("%H:%M:%S")
        end = s["end"].strftime("%H:%M:%S")
        return f"{start}~{end}（约 {s['duration_sec']/60:.1f} 分钟）"

    return f"""
掘进段数量：{stats['work_count']}
停机段数量：{stats['stop_count']}
总掘进时长：{stats['work_total_min']:.1f} 分钟
总停机时长：{stats['stop_total_min']:.1f} 分钟

最长掘进：{fmt_seg(stats['longest_work'])}
最长停机：{fmt_seg(stats['longest_stop'])}

短掘进（<60s）：{len(stats['short_works'])} 段
短停机（<60s）：{len(stats['short_stops'])} 段
""".strip()
