from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DailyReportRequest(BaseModel):
    date: str  # YYYY-MM-DD
    use_llm: bool = False
    generation_mode: Literal["template", "evidence_pack_llm", "evidence_pack_llm_with_revision"] | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    mock_llm: bool = False
    enable_revision: bool | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date 必须是 YYYY-MM-DD 格式") from exc
        return value


class TimeWindowRequest(BaseModel):
    start_time: str
    end_time: str

    @model_validator(mode="after")
    def validate_time_window(self):
        start = datetime.fromisoformat(str(self.start_time).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(self.end_time).replace("Z", "+00:00"))
        if start > end:
            raise ValueError("start_time 不能晚于 end_time")
        return self


class AgentRequest(BaseModel):
    query: str = Field(min_length=1)
    date: str | None = None
    session_id: str | None = None
    history_limit: int = Field(default=8, ge=1, le=50)
    use_llm: bool = False
    verbose: bool = False

    @field_validator("date")
    @classmethod
    def validate_optional_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date 必须是 YYYY-MM-DD 格式") from exc
        return value


class EvidenceImportRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    source_type: Literal["tsp", "hsp", "sonic", "sketch"] | None = None
    dry_run: bool = False
    replace_existing: bool = False
    recursive: bool = False
