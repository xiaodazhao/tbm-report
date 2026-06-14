from __future__ import annotations

import re
from typing import Any

from geology_text.geology_extraction_schema import (
    HAZARD_TAGS,
    VALID_CONFIDENCE,
    VALID_EVIDENCE_ROLES,
    VALID_GRADES,
    VALID_LEVELS,
    VALID_SOURCE_TYPES,
    canonical_source_type,
)


DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


def validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate one candidate evidence dict without raising."""
    item = dict(candidate or {})
    errors: list[str] = []
    warnings: list[str] = []

    source_type = canonical_source_type(item.get("source_type"))
    item["source_type"] = source_type
    if source_type not in VALID_SOURCE_TYPES:
        errors.append("invalid_source_type")
    if source_type == "unknown":
        warnings.append("source_type_unknown")

    start = _float_or_none(item.get("start_chainage"))
    end = _float_or_none(item.get("end_chainage"))
    item["start_chainage"] = start
    item["end_chainage"] = end
    if start is None or end is None:
        errors.append("missing_chainage")
    elif start > end:
        errors.append("start_chainage_greater_than_end_chainage")

    role = str(item.get("evidence_role") or "unknown").strip().lower()
    item["evidence_role"] = role if role in VALID_EVIDENCE_ROLES else "unknown"
    if item["evidence_role"] == "unknown":
        warnings.append("evidence_role_unknown")

    report_date = item.get("report_date")
    if report_date in {"", "null"}:
        report_date = None
    item["report_date"] = report_date
    if report_date is not None and not DATE_RE.match(str(report_date)):
        errors.append("invalid_report_date")

    grade = str(item.get("surrounding_rock_grade") or "unknown").strip()
    item["surrounding_rock_grade"] = grade if grade in VALID_GRADES else "unknown"
    if item["surrounding_rock_grade"] == "unknown":
        warnings.append("surrounding_rock_grade_unknown")

    for field in ["water_condition", "fracture_condition", "broken_rock_condition"]:
        value = str(item.get(field) or "unknown").strip().lower()
        item[field] = value if value in VALID_LEVELS else "unknown"
        if item[field] == "unknown":
            warnings.append(f"{field}_unknown")

    confidence = str(item.get("confidence") or "unknown").strip().lower()
    item["confidence"] = confidence if confidence in VALID_CONFIDENCE else "unknown"
    if item["confidence"] == "unknown":
        warnings.append("confidence_unknown")

    hazard_tags = [str(tag).strip() for tag in _as_list(item.get("hazard_tags")) if str(tag).strip()]
    invalid_tags = [tag for tag in hazard_tags if tag not in HAZARD_TAGS]
    item["hazard_tags"] = [tag for tag in hazard_tags if tag in HAZARD_TAGS]
    item["unmapped_hazard_tags"] = list(dict.fromkeys(_as_list(item.get("unmapped_hazard_tags")) + invalid_tags))
    if invalid_tags:
        errors.append("invalid_hazard_tags:" + ",".join(invalid_tags))

    if not str(item.get("original_text_span") or "").strip():
        errors.append("missing_original_text_span")

    source_trace = item.get("source_trace")
    if not isinstance(source_trace, dict) or not source_trace.get("file_name"):
        errors.append("missing_source_trace")

    for flag in ["candidate_only", "requires_manual_review", "not_used_by_main_pipeline"]:
        if item.get(flag) is not True:
            errors.append(f"{flag}_must_be_true")

    for field in ["candidate_id", "source_id"]:
        if not str(item.get(field) or "").strip():
            errors.append(f"missing_{field}")

    item["validation_passed"] = not errors
    item["validation_errors"] = errors
    item["validation_warnings"] = list(dict.fromkeys(warnings))
    return item


def validate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [validate_candidate(candidate) for candidate in candidates]


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]

