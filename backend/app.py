from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ALLOW_CREDENTIALS, CORS_ALLOW_ORIGINS
from routes.report import register_report_routes


# =========================
# FastAPI 初始化
# =========================
app = FastAPI(title="TBM Analysis Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# API 路由注册：只保留日报主 pipeline 接口
# =========================
register_report_routes(app)


# 启动：
# uvicorn app:app --reload --port 8000
