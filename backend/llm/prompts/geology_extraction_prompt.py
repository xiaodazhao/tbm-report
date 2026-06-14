from __future__ import annotations

import json
from typing import Any

from geology_text.geology_extraction_schema import HAZARD_TAGS


def build_geology_extraction_prompt(
    *,
    source_id: str,
    source_type: str,
    text: str,
) -> str:
    """Build a strict JSON-only extraction prompt for side-channel geology text."""
    schema = {
        "source_id": source_id,
        "source_type": source_type,
        "candidates": [
            {
                "report_date": "YYYY-MM-DD or null",
                "start_chainage": 1014545.0,
                "end_chainage": 1014645.0,
                "face_chainage": None,
                "chainage_text": "exact chainage phrase from the source text",
                "surrounding_rock_grade": "I/II/III/IV/V/unknown",
                "hazards": ["original geology terms from the text"],
                "hazard_tags": ["standard tags only"],
                "unmapped_hazard_tags": [],
                "water_condition": "none/weak/medium/strong/unknown",
                "fracture_condition": "none/weak/medium/strong/unknown",
                "broken_rock_condition": "none/weak/medium/strong/unknown",
                "evidence_role": "observed/forecast/background/unknown",
                "confidence": "low/medium/high/unknown",
                "original_text_span": "verbatim source span supporting this candidate",
            }
        ],
    }
    return "\n".join(
        [
            "You are extracting candidate geology evidence from raw source text.",
            "This is a side-channel extraction task. The output is candidate-only and must not be described as official evidence.",
            "",
            "Hard rules:",
            "1. Extract only from the provided text.",
            "2. Do not fill missing information from common sense.",
            "3. Do not infer chainage values that are not present in the source text.",
            "4. Do not compute or mention GRS, RAI, GRCI, risk probability, or report conclusions.",
            "5. Do not write a TBM daily report.",
            "6. Use null or unknown when the source text is uncertain.",
            "7. Every candidate must preserve original_text_span.",
            "8. Return strict JSON only; no markdown fences.",
            "9. If no geology evidence is extractable, return an empty candidates list.",
            "10. Do not rewrite forecast evidence as observed field exposure.",
            "11. Do not mark any candidate as already used by the main pipeline.",
            "",
            "Allowed hazard_tags:",
            json.dumps(sorted(HAZARD_TAGS), ensure_ascii=False),
            "",
            "Expected JSON shape:",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "",
            f"source_id: {source_id}",
            f"source_type: {source_type}",
            "",
            "source_text:",
            text,
        ]
    )


def extraction_request_payload(source_id: str, source_type: str, text: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "prompt": build_geology_extraction_prompt(source_id=source_id, source_type=source_type, text=text),
    }

