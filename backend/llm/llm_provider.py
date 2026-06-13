from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(BACKEND_DIR / ".env")


SUPPORTED_PROVIDERS = {"mock", "openai_or_compatible", "disabled"}


@dataclass
class LLMProviderConfig:
    provider: str = "disabled"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.2
    max_tokens: int = 8192
    timeout_sec: int = 120
    api_key: str | None = field(default=None, repr=False)


def resolve_llm_provider_config(
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    base_url: str | None = None,
) -> LLMProviderConfig:
    """Resolve LLM config from explicit args and env without exposing the key."""
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    active_provider = (provider or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if active_provider in {"deepseek", "openai", "compatible"}:
        active_provider = "openai_or_compatible"
    if not active_provider:
        active_provider = "openai_or_compatible" if api_key else "disabled"

    if active_provider not in SUPPORTED_PROVIDERS:
        active_provider = "disabled"

    resolved_model = (
        model
        or os.getenv("LLM_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
        or "deepseek-chat"
    )
    resolved_base_url = (
        base_url
        or os.getenv("LLM_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    )
    return LLMProviderConfig(
        provider=active_provider,
        model=resolved_model,
        base_url=resolved_base_url.rstrip("/"),
        temperature=float(temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.2")),
        max_tokens=int(max_tokens if max_tokens is not None else os.getenv("LLM_MAX_TOKENS", "8192")),
        timeout_sec=int(os.getenv("LLM_TIMEOUT_SEC", "120")),
        api_key=api_key,
    )


class LLMProvider:
    """Small auditable provider wrapper for evidence-pack constrained reports."""

    def __init__(self, config: LLMProviderConfig | None = None):
        self.config = config or resolve_llm_provider_config()

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def model(self) -> str:
        return self.config.model

    def generate(self, prompt: str, *, purpose: str = "report_generation") -> dict[str, Any]:
        request_payload = self._request_payload(prompt)
        if self.config.provider == "mock":
            text = _mock_response(prompt, purpose=purpose)
            return {
                "ok": True,
                "provider": "mock",
                "model": self.config.model,
                "text": text,
                "raw_response": text,
                "request": _redact_request(request_payload),
                "error_message": None,
                "warnings": [],
            }

        if self.config.provider == "disabled":
            return self._failed("LLM provider is disabled.", request_payload)

        if self.config.provider == "openai_or_compatible":
            if not self.config.api_key:
                return self._failed("LLM API key is not configured.", request_payload)
            return self._call_openai_compatible(request_payload)

        return self._failed(f"Unsupported provider: {self.config.provider}", request_payload)

    def _request_payload(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }

    def _call_openai_compatible(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = f"{self.config.base_url}/chat/completions"
        request = urllib.request.Request(
            url=endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_sec) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            choices = data.get("choices") or []
            text = ((choices[0].get("message") or {}).get("content") if choices else "") or ""
            if not text.strip():
                return self._failed("LLM returned empty content.", payload, raw_response=raw)
            return {
                "ok": True,
                "provider": self.config.provider,
                "model": self.config.model,
                "text": text.strip(),
                "raw_response": raw,
                "request": _redact_request(payload),
                "error_message": None,
                "warnings": [],
            }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            return self._failed(f"HTTP {exc.code}: {detail}", payload)
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            return self._failed(str(exc), payload)

    def _failed(
        self,
        message: str,
        payload: dict[str, Any],
        *,
        raw_response: str = "",
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "provider": self.config.provider,
            "model": self.config.model,
            "text": "",
            "raw_response": raw_response,
            "request": _redact_request(payload),
            "error_message": message,
            "warnings": [message],
        }


def _redact_request(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _mock_response(prompt: str, *, purpose: str) -> str:
    if purpose == "report_revision":
        return _mock_report(prefix="LLM 修订稿")
    return _mock_report(prefix="LLM 初稿")


def _mock_report(*, prefix: str) -> str:
    return "\n".join(
        [
            f"# TBM 施工日报（{prefix}）",
            "",
            "## 1. 综合结论摘要",
            "本报告仅依据 Prompt Evidence Pack 生成，未补充证据包之外的工程事实。",
            "GRCI 仅表示已掘区段地质-施工响应耦合关注度，不表示灾害概率或风险概率。",
            "",
            "## 2. 今日施工运行概况",
            "今日施工运行概况以 operation_evidence 中的 PLC 统计为准。",
            "",
            "## 3. PLC 工况统计分析",
            "stop_ratio 仅作为施工响应关注信号，当前 PLC 字段未区分计划停机与非计划停机。",
            "",
            "## 4. 气体监测分析",
            "气体监测结论仅依据 gas_evidence，不对字段含义之外的信息作推断。",
            "",
            "## 5. 已掘区段地质-施工响应复核",
            "已掘区段复核仅使用 daily_review_evidence 与 coupling_evidence 中的可用 cell。",
            "",
            "## 6. 当前掌子面前方关注提示",
            "前方关注提示仅表示需要关注或复核，不表示已发生事实，也不使用 GRCI。",
            "如无当日可用掌子面素描，不把前方证据写成已揭露事实。",
            "",
            "## 7. 结论与建议",
            "建议结合现场记录复核 Evidence Pack 中列出的已掘复核 cell 和前方关注 cell。",
        ]
    )
