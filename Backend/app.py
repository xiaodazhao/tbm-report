from fastapi import FastAPI
import pandas as pd
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

from dataprocess import load_and_process, segments_to_text, compute_stats, stats_to_text
from lithology import (
    detect_lithology,
    lithology_segments,
    lithology_to_text,
    lithology_efficiency,
    efficiency_to_text,
)
from gas_analysis import compute_gas_stats, gas_stats_to_text
from prompt_builder import build_prompt
from llm_api import call_llm

# =========================
# FastAPI 初始化
# =========================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 本地开发 OK，生产环境建议收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CSV 路径（后端私有）
# =========================
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "tbm_data_20231024.csv"

# =========================
# API 1：运行摘要
# =========================
@app.get("/api/tbm/summary")
def tbm_summary():
    df = pd.read_csv(CSV_PATH)
    df["运行时间-time"] = pd.to_datetime(df["运行时间-time"])

    segments = load_and_process(CSV_PATH)
    stats = compute_stats(segments)

    return {
        "work_count": stats["work_count"],
        "stop_count": stats["stop_count"],
        "work_total_min": stats["work_total_min"],
        "stop_total_min": stats["stop_total_min"],
    }

# =========================
# API 2：岩性分析
# =========================
@app.get("/api/tbm/lithology")
def lithology_api():
    df = pd.read_csv(CSV_PATH)
    df["运行时间-time"] = pd.to_datetime(df["运行时间-time"])

    df, labels = detect_lithology(df)

    segs_raw = lithology_segments(df)
    eff_df = lithology_efficiency(df).reset_index()

    segments = []
    for litho_label, pairs in segs_raw.items():
        for start, end in pairs:
            duration = (end - start).total_seconds()
            segments.append({
                "label": float(litho_label),
                "start": start.strftime("%H:%M:%S"),
                "end": end.strftime("%H:%M:%S"),
                "duration": duration
            })

    return {
        "segments": segments,
        "efficiency": eff_df.to_dict(orient="records"),
    }

# =========================
# API 3：气体分析
# =========================
@app.get("/api/tbm/gas")
def gas_api():
    df = pd.read_csv(CSV_PATH)
    df["运行时间-time"] = pd.to_datetime(df["运行时间-time"])

    gas_stats = compute_gas_stats(df)
    print("DEBUG:", gas_stats)
    return gas_stats

# =========================
# API 4：生成报告（核心）
# =========================
@app.post("/api/tbm/report")
def generate_report():
    print("📄 生成报告，使用 CSV =", CSV_PATH)

    df = pd.read_csv(CSV_PATH)
    df["运行时间-time"] = pd.to_datetime(df["运行时间-time"])

    # 掘进/停机分段
    segments = load_and_process(CSV_PATH)
    seg_text = segments_to_text(segments)

    stats = compute_stats(segments)
    stats_text = stats_to_text(stats)

    # 岩性分析
    df, labels = detect_lithology(df)
    litho_segs = lithology_segments(df)
    litho_text = lithology_to_text(litho_segs)

    eff_df = lithology_efficiency(df)
    eff_text = efficiency_to_text(eff_df)

    # 气体分析
    gas_stats = compute_gas_stats(df)
    gas_text = gas_stats_to_text(gas_stats)

    # Prompt + LLM
    prompt = build_prompt(
        seg_text,
        stats_text,
        litho_text,
        eff_text,
        gas_text
    )

    report = call_llm(prompt)

    return {"report": report}

# 启动方式：
# uvicorn app:app --reload --port 8000
