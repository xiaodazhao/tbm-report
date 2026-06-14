from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


VALID_SOURCE_TYPES = {"TSP", "HSP", "sketch", "unknown"}
VALID_EVIDENCE_ROLES = {"observed", "forecast", "background", "unknown"}
VALID_LEVELS = {"none", "weak", "medium", "strong", "unknown"}
VALID_CONFIDENCE = {"low", "medium", "high", "unknown"}
VALID_GRADES = {
    "I",
    "II",
    "III",
    "IV",
    "V",
    "1",
    "2",
    "3",
    "4",
    "5",
    "\u2160",
    "\u2161",
    "\u2162",
    "\u2163",
    "\u2164",
    "unknown",
}

HAZARD_TAGS = {
    "broken_rock",
    "extremely_broken_rock",
    "fracture_developed",
    "dense_fractures",
    "block_fall",
    "water_rich",
    "water_inflow",
    "soft_hard_uneven",
    "weak_interlayer",
    "fault_zone",
    "karst",
    "high_geo_stress",
    "rock_burst",
    "large_deformation",
    "abnormal_reflection",
    "surrounding_rock_grade_III",
    "surrounding_rock_grade_IV",
    "surrounding_rock_grade_V",
    "unknown",
}

HAZARD_KEYWORD_MAP = {
    "\u56f4\u5ca9\u6781\u7834\u788e": "extremely_broken_rock",
    "\u6781\u7834\u788e": "extremely_broken_rock",
    "\u56f4\u5ca9\u7834\u788e": "broken_rock",
    "\u7834\u788e": "broken_rock",
    "\u88c2\u9699\u5bc6\u96c6": "dense_fractures",
    "\u8282\u7406\u88c2\u9699\u5bc6\u96c6": "dense_fractures",
    "\u88c2\u9699\u53d1\u80b2": "fracture_developed",
    "\u8282\u7406\u88c2\u9699\u53d1\u80b2": "fracture_developed",
    "\u6389\u5757": "block_fall",
    "\u5bcc\u6c34": "water_rich",
    "\u51fa\u6c34": "water_inflow",
    "\u6d8c\u6c34": "water_inflow",
    "\u8f6f\u786c\u4e0d\u5747": "soft_hard_uneven",
    "\u8f6f\u5f31\u5939\u5c42": "weak_interlayer",
    "\u65ad\u5c42": "fault_zone",
    "\u5ca9\u6eb6": "karst",
    "\u9ad8\u5730\u5e94\u529b": "high_geo_stress",
    "\u5ca9\u7206": "rock_burst",
    "\u5927\u53d8\u5f62": "large_deformation",
    "\u53d8\u5f62": "large_deformation",
    "\u660e\u663e\u53cd\u5c04\u5f02\u5e38": "abnormal_reflection",
    "\u53cd\u5c04\u5f02\u5e38": "abnormal_reflection",
}

GRADE_TAG_MAP = {
    "\u2162": "surrounding_rock_grade_III",
    "III": "surrounding_rock_grade_III",
    "3": "surrounding_rock_grade_III",
    "\u2163": "surrounding_rock_grade_IV",
    "IV": "surrounding_rock_grade_IV",
    "4": "surrounding_rock_grade_IV",
    "\u2164": "surrounding_rock_grade_V",
    "V": "surrounding_rock_grade_V",
    "5": "surrounding_rock_grade_V",
}


@dataclass
class SourceTrace:
    file_name: str
    file_path: str | None = None
    page_or_section: str | None = None
    char_start: int | None = None
    char_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "page_or_section": self.page_or_section,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass
class CandidateEvidence:
    candidate_id: str
    source_id: str
    source_type: str = "unknown"
    report_date: str | None = None
    start_chainage: float | None = None
    end_chainage: float | None = None
    face_chainage: float | None = None
    chainage_text: str | None = None
    surrounding_rock_grade: str = "unknown"
    hazards: list[str] = field(default_factory=list)
    hazard_tags: list[str] = field(default_factory=list)
    unmapped_hazard_tags: list[str] = field(default_factory=list)
    water_condition: str = "unknown"
    fracture_condition: str = "unknown"
    broken_rock_condition: str = "unknown"
    evidence_role: str = "unknown"
    confidence: str = "unknown"
    original_text_span: str = ""
    source_trace: dict[str, Any] = field(default_factory=dict)
    candidate_only: bool = True
    requires_manual_review: bool = True
    not_used_by_main_pipeline: bool = True
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "report_date": self.report_date,
            "start_chainage": self.start_chainage,
            "end_chainage": self.end_chainage,
            "face_chainage": self.face_chainage,
            "chainage_text": self.chainage_text,
            "surrounding_rock_grade": self.surrounding_rock_grade,
            "hazards": list(self.hazards),
            "hazard_tags": list(self.hazard_tags),
            "unmapped_hazard_tags": list(self.unmapped_hazard_tags),
            "water_condition": self.water_condition,
            "fracture_condition": self.fracture_condition,
            "broken_rock_condition": self.broken_rock_condition,
            "evidence_role": self.evidence_role,
            "confidence": self.confidence,
            "original_text_span": self.original_text_span,
            "source_trace": dict(self.source_trace),
            "candidate_only": self.candidate_only,
            "requires_manual_review": self.requires_manual_review,
            "not_used_by_main_pipeline": self.not_used_by_main_pipeline,
            "validation_passed": self.validation_passed,
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
        }


def canonical_source_type(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    aliases = {
        "tsp": "TSP",
        "hsp": "HSP",
        "sonic": "HSP",
        "horizontal_sonic": "HSP",
        "sketch": "sketch",
        "face": "sketch",
        "face_sketch": "sketch",
    }
    return aliases.get(text, "unknown")


def candidate_id_for(source_id: str, text: str, index: int = 0) -> str:
    digest = hashlib.sha1(f"{source_id}|{index}|{text}".encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"cand_{digest}"


CHAINAGE_RE = re.compile(
    r"(?:D?y?K)?\s*(\d{3,5})\s*\+\s*(\d+(?:\.\d+)?)\s*[-~\u81f3\u5230\u2014\uff5e]+\s*"
    r"(?:D?y?K)?\s*(\d{3,5})\s*\+\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
NUMBER_RANGE_RE = re.compile(r"\b(10\d{5}(?:\.\d+)?)\s*[-~\u81f3\u5230\u2014\uff5e]+\s*(10\d{5}(?:\.\d+)?)\b")


def chainage_from_dk(prefix: str, offset: str) -> float:
    return float(prefix) * 1000.0 + float(offset)


def parse_chainage_range(text: str) -> tuple[float | None, float | None, str | None]:
    value = str(text or "")
    match = CHAINAGE_RE.search(value)
    if match:
        start = chainage_from_dk(match.group(1), match.group(2))
        end = chainage_from_dk(match.group(3), match.group(4))
        return min(start, end), max(start, end), match.group(0)
    match = NUMBER_RANGE_RE.search(value)
    if match:
        start = float(match.group(1))
        end = float(match.group(2))
        return min(start, end), max(start, end), match.group(0)
    return None, None, None


def normalize_hazard_tags(hazards: list[str]) -> tuple[list[str], list[str]]:
    tags: list[str] = []
    unmapped: list[str] = []
    for hazard in hazards:
        matched = False
        for keyword, tag in HAZARD_KEYWORD_MAP.items():
            if keyword in str(hazard):
                tags.append(tag)
                matched = True
        if not matched and str(hazard).strip():
            unmapped.append(str(hazard).strip())
    return list(dict.fromkeys(tags)), list(dict.fromkeys(unmapped))

