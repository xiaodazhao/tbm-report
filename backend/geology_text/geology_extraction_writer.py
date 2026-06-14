from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_extraction_outputs(out_dir: Path, result: dict[str, Any]) -> dict[str, str]:
    """Write P3 candidate extraction outputs.

    This writer never touches the official evidence_db path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = result.get("raw_llm_response", [])
    extracted = result.get("extracted_candidates", [])
    validated = result.get("validated_candidates", [])
    summary = result.get("summary", {})
    errors = result.get("errors", [])

    paths = {
        "raw_llm_response": str(out_dir / "raw_llm_response.json"),
        "extracted_evidence_candidates_json": str(out_dir / "extracted_evidence_candidates.json"),
        "extracted_evidence_candidates_csv": str(out_dir / "extracted_evidence_candidates.csv"),
        "validated_evidence_candidates_json": str(out_dir / "validated_evidence_candidates.json"),
        "validated_evidence_candidates_csv": str(out_dir / "validated_evidence_candidates.csv"),
        "candidate_evidence_db_csv": str(out_dir / "candidate_evidence_db.csv"),
        "extraction_summary": str(out_dir / "extraction_summary.json"),
        "extraction_errors": str(out_dir / "extraction_errors.csv"),
    }
    _write_json(Path(paths["raw_llm_response"]), raw)
    _write_json(Path(paths["extracted_evidence_candidates_json"]), extracted)
    _write_csv(Path(paths["extracted_evidence_candidates_csv"]), extracted)
    _write_json(Path(paths["validated_evidence_candidates_json"]), validated)
    _write_csv(Path(paths["validated_evidence_candidates_csv"]), validated)
    _write_csv(Path(paths["candidate_evidence_db_csv"]), _candidate_rows(validated))
    _write_json(Path(paths["extraction_summary"]), summary)
    _write_csv(Path(paths["extraction_errors"]), errors)
    return paths


def _candidate_rows(validated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in validated:
        row = dict(item)
        row["candidate_only"] = True
        row["requires_manual_review"] = True
        row["not_used_by_main_pipeline"] = True
        rows.append(row)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    frame = pd.DataFrame([_csv_safe(row) for row in rows])
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _csv_safe(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple, set)):
            out[key] = json.dumps(_json_safe(value), ensure_ascii=False, default=str)
        else:
            out[key] = value
    return out

