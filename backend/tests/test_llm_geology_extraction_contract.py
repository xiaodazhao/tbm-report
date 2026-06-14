from __future__ import annotations

import csv
from pathlib import Path

from geology_text.geology_extraction_validator import validate_candidate
from geology_text.llm_geology_extractor import RawTextChunk, extract_from_chunks
from geology_text.geology_extraction_writer import write_extraction_outputs
from scripts.run_geology_text_extraction import collect_chunks


SAMPLE_TEXT = (
    "DyK1014+545~DyK1014+645 section, grade III. "
    "\u56f4\u5ca9\u6781\u7834\u788e\uff0c\u88c2\u9699\u5bc6\u96c6\uff0c"
    "\u5b58\u5728\u6389\u5757\u73b0\u8c61\uff0c\u663e\u793a\u660e\u663e\u53cd\u5c04\u5f02\u5e38\u3002"
)


def test_mock_extraction_parses_chainage_and_hazards():
    result = extract_from_chunks(
        [RawTextChunk(source_id="sample", source_type="HSP", text=SAMPLE_TEXT, file_name="sample.txt")],
        mock_llm=True,
    )
    candidates = result["validated_candidates"]
    assert len(candidates) == 1
    item = candidates[0]
    assert item["start_chainage"] == 1014545.0
    assert item["end_chainage"] == 1014645.0
    assert "extremely_broken_rock" in item["hazard_tags"]
    assert "dense_fractures" in item["hazard_tags"]
    assert "block_fall" in item["hazard_tags"]
    assert "abnormal_reflection" in item["hazard_tags"]
    assert item["candidate_only"] is True
    assert item["requires_manual_review"] is True
    assert item["not_used_by_main_pipeline"] is True


def test_validator_detects_invalid_chainage():
    item = _valid_candidate()
    item["start_chainage"] = 2
    item["end_chainage"] = 1
    checked = validate_candidate(item)
    assert not checked["validation_passed"]
    assert "start_chainage_greater_than_end_chainage" in checked["validation_errors"]


def test_validator_detects_missing_original_text_span():
    item = _valid_candidate()
    item["original_text_span"] = ""
    checked = validate_candidate(item)
    assert not checked["validation_passed"]
    assert "missing_original_text_span" in checked["validation_errors"]


def test_validator_detects_invalid_hazard_tags():
    item = _valid_candidate()
    item["hazard_tags"] = ["not_a_standard_tag"]
    checked = validate_candidate(item)
    assert not checked["validation_passed"]
    assert any(err.startswith("invalid_hazard_tags") for err in checked["validation_errors"])
    assert "not_a_standard_tag" in checked["unmapped_hazard_tags"]


def test_validator_detects_candidate_safety_flags():
    for flag in ["candidate_only", "requires_manual_review", "not_used_by_main_pipeline"]:
        item = _valid_candidate()
        item[flag] = False
        checked = validate_candidate(item)
        assert not checked["validation_passed"]
        assert f"{flag}_must_be_true" in checked["validation_errors"]


def test_unknown_fields_warn_but_do_not_crash():
    item = _valid_candidate()
    item["source_type"] = "unknown"
    item["evidence_role"] = "unknown"
    item["surrounding_rock_grade"] = "unknown"
    checked = validate_candidate(item)
    assert checked["validation_passed"]
    assert "source_type_unknown" in checked["validation_warnings"]
    assert "evidence_role_unknown" in checked["validation_warnings"]


def test_no_api_key_or_disallowed_external_llm_does_not_crash(monkeypatch):
    monkeypatch.delenv("ALLOW_EXTERNAL_LLM", raising=False)
    result = extract_from_chunks(
        [RawTextChunk(source_id="sample", source_type="HSP", text=SAMPLE_TEXT, file_name="sample.txt")],
        provider_name="openai_or_compatible",
        mock_llm=False,
        allow_external_llm=False,
    )
    assert result["summary"]["candidate_count"] == 0
    assert result["summary"]["failed_file_count"] == 1
    assert "External LLM is not allowed" in str(result["summary"]["error_message"])


def test_writer_outputs_candidate_db_without_touching_official_evidence(tmp_path: Path):
    result = extract_from_chunks(
        [RawTextChunk(source_id="sample", source_type="HSP", text=SAMPLE_TEXT, file_name="sample.txt")],
        mock_llm=True,
    )
    paths = write_extraction_outputs(tmp_path, result)
    candidate_path = Path(paths["candidate_evidence_db_csv"])
    assert candidate_path.exists()
    with candidate_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert rows[0]["candidate_only"] == "True"
    assert rows[0]["requires_manual_review"] == "True"
    assert rows[0]["not_used_by_main_pipeline"] == "True"
    assert not (tmp_path / "evidence_db.csv").exists()


def test_source_list_text_column_is_supported(tmp_path: Path):
    source_list = tmp_path / "sources.csv"
    source_list.write_text("source_id,source_type,raw_text\nr1,HSP,\"DyK1014+545~DyK1014+645 \u6389\u5757\"\n", encoding="utf-8")
    chunks, errors = collect_chunks(
        input_file=None,
        input_dir=None,
        source_list=str(source_list),
        source_type="auto",
        text_column="raw_text",
        out_dir=tmp_path,
    )
    assert not errors
    assert len(chunks) == 1
    assert chunks[0].source_id == "r1"


def _valid_candidate() -> dict:
    return {
        "candidate_id": "cand_1",
        "source_id": "src_1",
        "source_type": "HSP",
        "report_date": "2023-12-24",
        "start_chainage": 1014545.0,
        "end_chainage": 1014645.0,
        "face_chainage": None,
        "chainage_text": "DyK1014+545~DyK1014+645",
        "surrounding_rock_grade": "III",
        "hazards": ["broken"],
        "hazard_tags": ["broken_rock"],
        "unmapped_hazard_tags": [],
        "water_condition": "unknown",
        "fracture_condition": "unknown",
        "broken_rock_condition": "unknown",
        "evidence_role": "forecast",
        "confidence": "medium",
        "original_text_span": "DyK1014+545~DyK1014+645 broken rock",
        "source_trace": {"file_name": "sample.txt", "file_path": None},
        "candidate_only": True,
        "requires_manual_review": True,
        "not_used_by_main_pipeline": True,
    }
