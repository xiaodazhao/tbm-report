from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


# =========================================================
# 1. 初始化配置
# =========================================================
if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(BACKEND_DIR / ".env")

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
DEFAULT_GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash-lite")
DEFAULT_DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
LLM_TIMEOUT_SEC = int(os.getenv("LLM_TIMEOUT_SEC", "120"))

_google_client = None


def _get_google_client():
    """Lazily initialize Gemini client so the backend can start without an API key."""
    global _google_client
    if _google_client is not None:
        return _google_client

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 GOOGLE_API_KEY，请先根据 .env.example 创建 .env 文件。")

    from google import genai

    _google_client = genai.Client(api_key=api_key)
    return _google_client


def _call_google(prompt: str, model: str = DEFAULT_GOOGLE_MODEL) -> str:
    """Call google."""
    client = _get_google_client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"temperature": 0.3, "max_output_tokens": 8192},
    )
    if hasattr(response, "text") and response.text:
        return response.text.strip()
    raise RuntimeError("模型返回了空内容")


def _call_deepseek(prompt: str, model: str = DEFAULT_DEEPSEEK_MODEL) -> str:
    """Call deepseek."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请先根据 .env.example 创建 .env 文件。")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 8192,
        "stream": False,
    }
    request = urllib.request.Request(
        url=f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"DeepSeek API 请求失败：HTTP {e.code} {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"DeepSeek API 连接失败：{e.reason}") from e

    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek 返回了空 choices")
    message = choices[0].get("message") or {}
    text = message.get("content", "")
    if not text:
        raise RuntimeError("DeepSeek 返回了空内容")
    return text.strip()


def _resolve_provider_model(model: str | None, provider: str | None) -> tuple[str, str]:
    active_provider = (provider or DEFAULT_PROVIDER).strip().lower()
    if active_provider == "deepseek":
        return active_provider, model or DEFAULT_DEEPSEEK_MODEL
    if active_provider in {"google", "gemini"}:
        return active_provider, model or DEFAULT_GOOGLE_MODEL
    raise RuntimeError(f"不支持的 LLM_PROVIDER：{active_provider}")


# =========================================================
# 2. 通用 LLM 调用函数
# =========================================================
def call_llm_raw(prompt: str, model: str | None = None, provider: str | None = None) -> str:
    """Call configured LLM and raise on error."""
    active_provider, active_model = _resolve_provider_model(model, provider)
    if active_provider == "deepseek":
        return _call_deepseek(prompt, active_model)
    if active_provider in {"google", "gemini"}:
        return _call_google(prompt, active_model)
    raise RuntimeError(f"不支持的 LLM_PROVIDER：{active_provider}")


def call_llm_result(prompt: str, model: str | None = None, provider: str | None = None) -> dict[str, Any]:
    """Structured LLM call. Prefer this in new route/service code."""
    try:
        active_provider, active_model = _resolve_provider_model(model, provider)
        text = call_llm_raw(prompt, model=active_model, provider=active_provider)
        return {
            "ok": True,
            "provider": active_provider,
            "model": active_model,
            "text": text,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": (provider or DEFAULT_PROVIDER).strip().lower(),
            "model": model,
            "text": "",
            "error": str(exc),
        }


def call_llm(prompt: str, model: str | None = None, provider: str | None = None) -> str:
    """Backward-compatible string-returning LLM call.

    New code should use ``call_llm_result`` so LLM failures are not confused with
    successful report text.
    """
    result = call_llm_result(prompt, model=model, provider=provider)
    if result.get("ok"):
        return str(result.get("text", "")).strip()
    return f"⚠️ LLM 调用失败：{result.get('error', 'unknown error')}"


# =========================================================
# 3. RAG 专用调用
# =========================================================
def call_llm_rag(query: str, context: str, model: str | None = None) -> str:
    """RAG 调用封装：自动把 context 和 query 拼接。"""
    prompt = f"""
你是一名专业的 TBM（隧道掘进机）施工数据分析师。
请根据以下【监测数据背景】回答【分析任务】。

【监测数据背景】
{context}

【分析任务】
{query}

要求：
1. 语言专业、客观、工程化。
2. 若存在异常停机、频繁启停、状态波动或气体异常，应重点指出。
3. 严格依据输入数据，不得虚构。
4. 控制在 2000 字以内。
"""
    return call_llm(prompt, model=model)