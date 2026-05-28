import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


VALID_SOURCE_TYPES = {"tsp", "sonic", "sketch", "hsp", "drill", "unknown"}
VALID_SOURCE_LEVELS = {"overview", "report_conclusion", "segment", "point", "unknown"}


def canonical_source_type(value: str | None) -> str:
    """Normalize source type naming."""
    text = (value or "unknown").strip().lower()
    aliases = {
        "hsp": "sonic",
        "horizontal_sonic": "sonic",
        "horizontal-sound-wave": "sonic",
        "水平声波": "sonic",
        "掌子面素描": "sketch",
    }
    return aliases.get(text, text if text in VALID_SOURCE_TYPES else "unknown")


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_type: str
    source_level: str
    report_id: str
    report_date: Optional[str]
    issue_date: Optional[str]
    tunnel_name: Optional[str]
    start_num: float
    end_num: float
    face_num: Optional[float]
    next_forecast_num: Optional[float]
    confidence: str
    attrs_json: str
    raw_text: Optional[str] = None

    def attrs(self) -> Dict[str, Any]:
        """Load attrs_json safely."""
        try:
            obj = json.loads(self.attrs_json or "{}")
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def patch_attrs(self, **kwargs: Any) -> "EvidenceRecord":
        """Patch attrs_json in place and return self for parser convenience."""
        attrs = self.attrs()
        attrs.update(kwargs)
        self.attrs_json = json.dumps(attrs, ensure_ascii=False)
        return self

    def validate_basic(self) -> list[str]:
        """Return schema/field warnings without raising."""
        warnings: list[str] = []
        if not self.evidence_id:
            warnings.append("missing evidence_id")
        if canonical_source_type(self.source_type) == "unknown":
            warnings.append(f"unknown source_type: {self.source_type}")
        if (self.source_level or "unknown").strip().lower() not in VALID_SOURCE_LEVELS:
            warnings.append(f"unknown source_level: {self.source_level}")
        if self.start_num is None or self.end_num is None:
            warnings.append("missing start_num/end_num")
        else:
            try:
                if float(self.start_num) > float(self.end_num):
                    warnings.append("start_num greater than end_num")
            except Exception:
                warnings.append("start_num/end_num not numeric")
        if not isinstance(self.attrs(), dict):
            warnings.append("attrs_json is not a valid object")
        return warnings

    def normalized(self) -> "EvidenceRecord":
        """Normalize source naming and add validation warnings into attrs_json."""
        self.source_type = canonical_source_type(self.source_type)
        warnings = self.validate_basic()
        if warnings:
            attrs = self.attrs()
            existing = attrs.get("parse_warnings", [])
            if not isinstance(existing, list):
                existing = [str(existing)]
            attrs["parse_warnings"] = list(dict.fromkeys(existing + warnings))
            self.attrs_json = json.dumps(attrs, ensure_ascii=False)
        return self