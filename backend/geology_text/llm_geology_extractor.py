from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from geology_text.geology_extraction_schema import (
    CandidateEvidence,
    GRADE_TAG_MAP,
    HAZARD_KEYWORD_MAP,
    SourceTrace,
    candidate_id_for,
    canonical_source_type,
    normalize_hazard_tags,
    parse_chainage_range,
)
from geology_text.geology_extraction_validator import validate_candidates
from llm.llm_provider import LLMProvider, resolve_llm_provider_config
from llm.prompts.geology_extraction_prompt import build_geology_extraction_prompt


@dataclass
class RawTextChunk:
    source_id: str
    text: str
    source_type: str = "unknown"
    file_name: str = "inline_text"
    file_path: str | None = None
    page_or_section: str | None = None


def extract_from_chunks(
    chunks: list[RawTextChunk],
    *,
    provider_name: str | None = None,
    model: str | None = None,
    mock_llm: bool = True,
    allow_external_llm: bool = False,
) -> dict[str, Any]:
    """Extract candidate evidence from raw text chunks.

    The result is candidate-only and is not connected to the daily report
    pipeline.
    """
    provider_name = "mock" if mock_llm else (provider_name or "mock")
    allow_external_llm = bool(allow_external_llm or os.getenv("ALLOW_EXTERNAL_LLM", "").strip().lower() in {"1", "true", "yes"})
    raw_responses: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for chunk in chunks:
        try:
            result = _extract_one(
                chunk,
                provider_name=provider_name,
                model=model,
                mock_llm=mock_llm or provider_name == "mock",
                allow_external_llm=allow_external_llm,
            )
            raw_responses.append(result["raw_response"])
            candidates.extend(result["candidates"])
            if result.get("error_message"):
                errors.append({"source_id": chunk.source_id, "error_message": result.get("error_message")})
        except Exception as exc:
            errors.append({"source_id": chunk.source_id, "error_message": str(exc)})

    validated = validate_candidates(candidates)
    return {
        "raw_llm_response": raw_responses,
        "extracted_candidates": candidates,
        "validated_candidates": validated,
        "errors": errors,
        "summary": _summary(
            chunks=chunks,
            validated=validated,
            errors=errors,
            provider=provider_name,
            model=model,
            used_external_llm=bool(provider_name not in {"mock", "disabled"} and allow_external_llm),
        ),
    }


def _extract_one(
    chunk: RawTextChunk,
    *,
    provider_name: str,
    model: str | None,
    mock_llm: bool,
    allow_external_llm: bool,
) -> dict[str, Any]:
    source_type = canonical_source_type(chunk.source_type)
    if mock_llm:
        candidates = _mock_extract(chunk, source_type=source_type)
        return {
            "raw_response": {
                "source_id": chunk.source_id,
                "provider": "mock",
                "model": model or "mock-geology-extractor",
                "ok": True,
                "text": json.dumps({"source_id": chunk.source_id, "source_type": source_type, "candidates": candidates}, ensure_ascii=False),
                "error_message": None,
            },
            "candidates": candidates,
            "error_message": None,
        }

    if provider_name not in {"mock", "disabled"} and not allow_external_llm:
        message = "External LLM is not allowed. Use --allow-external-llm or ALLOW_EXTERNAL_LLM=true."
        return {
            "raw_response": {
                "source_id": chunk.source_id,
                "provider": provider_name,
                "model": model,
                "ok": False,
                "text": "",
                "error_message": message,
            },
            "candidates": [],
            "error_message": message,
        }

    provider = LLMProvider(resolve_llm_provider_config(provider=provider_name, model=model))
    prompt = build_geology_extraction_prompt(source_id=chunk.source_id, source_type=source_type, text=chunk.text)
    response = provider.generate(prompt, purpose="geology_extraction")
    if not response.get("ok"):
        return {
            "raw_response": {
                "source_id": chunk.source_id,
                "provider": response.get("provider"),
                "model": response.get("model"),
                "ok": False,
                "text": "",
                "raw_response": response.get("raw_response", ""),
                "request": response.get("request", {}),
                "error_message": response.get("error_message"),
            },
            "candidates": [],
            "error_message": response.get("error_message"),
        }
    parsed = _parse_llm_json(str(response.get("text") or ""))
    candidates = _normalize_llm_candidates(parsed, chunk, source_type=source_type)
    return {
        "raw_response": {
            "source_id": chunk.source_id,
            "provider": response.get("provider"),
            "model": response.get("model"),
            "ok": True,
            "text": response.get("text", ""),
            "raw_response": response.get("raw_response", ""),
            "request": response.get("request", {}),
            "error_message": None,
        },
        "candidates": candidates,
        "error_message": None,
    }


def _mock_extract(chunk: RawTextChunk, *, source_type: str) -> list[dict[str, Any]]:
    text = chunk.text or ""
    start, end, chainage_text = parse_chainage_range(text)
    hazards = _extract_hazards(text)
    if start is None and end is None and not hazards:
        return []
    grade = _extract_grade(text)
    hazard_tags, unmapped = normalize_hazard_tags(hazards)
    grade_tag = GRADE_TAG_MAP.get(grade)
    if grade_tag and grade_tag not in hazard_tags:
        hazard_tags.append(grade_tag)
    candidate = CandidateEvidence(
        candidate_id=candidate_id_for(chunk.source_id, text, 0),
        source_id=chunk.source_id,
        source_type=source_type,
        report_date=_extract_date(text),
        start_chainage=start,
        end_chainage=end,
        face_chainage=None,
        chainage_text=chainage_text,
        surrounding_rock_grade=grade,
        hazards=hazards,
        hazard_tags=hazard_tags,
        unmapped_hazard_tags=unmapped,
        water_condition=_condition(text, ["\u5bcc\u6c34", "\u6d8c\u6c34", "\u51fa\u6c34"]),
        fracture_condition="strong" if any(tag in hazard_tags for tag in ["dense_fractures", "fracture_developed"]) else "unknown",
        broken_rock_condition="strong" if any(tag in hazard_tags for tag in ["extremely_broken_rock", "broken_rock"]) else "unknown",
        evidence_role="observed" if source_type == "sketch" else "forecast" if source_type in {"TSP", "HSP"} else "unknown",
        confidence="medium",
        original_text_span=_excerpt(text),
        source_trace=SourceTrace(
            file_name=chunk.file_name,
            file_path=chunk.file_path,
            page_or_section=chunk.page_or_section,
            char_start=0,
            char_end=min(len(text), len(_excerpt(text))),
        ).to_dict(),
        candidate_only=True,
        requires_manual_review=True,
        not_used_by_main_pipeline=True,
    )
    return [candidate.to_dict()]


def _extract_hazards(text: str) -> list[str]:
    hazards = [keyword for keyword in HAZARD_KEYWORD_MAP if keyword in text]
    return list(dict.fromkeys(hazards))


def _extract_grade(text: str) -> str:
    grade_patterns = [
        ("\u2164", ["\u2164", "V\u7ea7", "5\u7ea7"]),
        ("\u2163", ["\u2163", "IV\u7ea7", "4\u7ea7"]),
        ("\u2162", ["\u2162", "III\u7ea7", "3\u7ea7"]),
        ("\u2161", ["\u2161", "II\u7ea7", "2\u7ea7"]),
        ("\u2160", ["\u2160", "I\u7ea7", "1\u7ea7"]),
    ]
    compact = re.sub(r"\s+", "", text)
    for grade, patterns in grade_patterns:
        if any(pattern in compact for pattern in patterns):
            return grade
    return "unknown"


def _extract_date(text: str) -> str | None:
    match = re.search(r"(20\d{2})[-/\.](\d{1,2})[-/\.](\d{1,2})", text)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _condition(text: str, keywords: list[str]) -> str:
    return "medium" if any(keyword in text for keyword in keywords) else "unknown"


def _excerpt(text: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    return json.loads(stripped)


def _normalize_llm_candidates(payload: dict[str, Any], chunk: RawTextChunk, *, source_type: str) -> list[dict[str, Any]]:
    candidates = []
    for index, raw in enumerate(payload.get("candidates") or []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item.setdefault("candidate_id", candidate_id_for(chunk.source_id, json.dumps(item, ensure_ascii=False), index))
        item.setdefault("source_id", chunk.source_id)
        item["source_type"] = canonical_source_type(item.get("source_type") or payload.get("source_type") or source_type)
        item.setdefault("unmapped_hazard_tags", [])
        item.setdefault("candidate_only", True)
        item.setdefault("requires_manual_review", True)
        item.setdefault("not_used_by_main_pipeline", True)
        if not item.get("source_trace"):
            item["source_trace"] = SourceTrace(
                file_name=chunk.file_name,
                file_path=chunk.file_path,
                page_or_section=chunk.page_or_section,
                char_start=None,
                char_end=None,
            ).to_dict()
        candidates.append(item)
    return candidates


def _summary(
    *,
    chunks: list[RawTextChunk],
    validated: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    provider: str,
    model: str | None,
    used_external_llm: bool,
) -> dict[str, Any]:
    return {
        "input_file_count": len(chunks),
        "processed_file_count": len(chunks) - len(errors),
        "failed_file_count": len(errors),
        "candidate_count": len(validated),
        "validation_passed_count": sum(1 for item in validated if item.get("validation_passed")),
        "validation_failed_count": sum(1 for item in validated if not item.get("validation_passed")),
        "missing_chainage_count": sum(1 for item in validated if not item.get("start_chainage") or not item.get("end_chainage")),
        "missing_source_trace_count": sum(1 for item in validated if not item.get("source_trace")),
        "unmapped_hazard_tag_count": sum(len(item.get("unmapped_hazard_tags") or []) for item in validated),
        "provider": provider,
        "model": model or ("mock-geology-extractor" if provider == "mock" else None),
        "used_external_llm": used_external_llm,
        "candidate_only": True,
        "requires_manual_review": True,
        "not_used_by_main_pipeline": True,
        "error_message": "; ".join(str(item.get("error_message")) for item in errors if item.get("error_message")) or None,
    }

