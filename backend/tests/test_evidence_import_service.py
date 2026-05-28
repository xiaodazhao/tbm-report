from pathlib import Path

import pandas as pd

from schemas.schemas import EvidenceRecord
from services import evidence_import_service as eis


def _record(evidence_id: str, *, start_num: float, end_num: float) -> EvidenceRecord:
    """Internal helper for record."""
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_type="tsp",
        source_level="segment",
        report_id="sample_report",
        report_date="2023年12月30日",
        issue_date="2023年12月30日",
        tunnel_name="伯舒拉岭隧道进口右线",
        start_num=start_num,
        end_num=end_num,
        face_num=36640.0,
        next_forecast_num=36690.0,
        confidence="high",
        attrs_json="{}",
        raw_text="sample",
    )


def test_import_evidence_files_skips_existing_and_collects_errors(monkeypatch, tmp_path):
    """Test import evidence files skips existing and collects errors."""
    pdf_ok = tmp_path / "sample_tsp.pdf"
    pdf_fail = tmp_path / "sample_hsp.pdf"
    pdf_ok.write_text("ok", encoding="utf-8")
    pdf_fail.write_text("fail", encoding="utf-8")

    existing_csv = tmp_path / "evidence_db.csv"
    pd.DataFrame(
        [
            {
                "evidence_id": "dup_1",
                "source_type": "tsp",
                "source_level": "segment",
                "report_id": "old",
                "report_date": "2023-01-01",
                "issue_date": "2023-01-01",
                "tunnel_name": "old",
                "start_num": 36000.0,
                "end_num": 36010.0,
                "face_num": 36005.0,
                "next_forecast_num": 36020.0,
                "confidence": "high",
                "attrs_json": "{}",
                "raw_text": "old",
            }
        ]
    ).to_csv(existing_csv, index=False, encoding="utf-8-sig")

    synced = {}

    monkeypatch.setattr(eis, "collect_pdf_paths", lambda paths, recursive=False: [pdf_ok, pdf_fail])

    def fake_parse(pdf_path, source_type=None):
        """Handle fake parse."""
        if pdf_path == pdf_ok:
            return "tsp", [
                _record("dup_1", start_num=36100.0, end_num=36110.0),
                _record("new_1", start_num=36200.0, end_num=36220.0),
            ]
        raise RuntimeError("parse failed")

    monkeypatch.setattr(eis, "parse_evidence_pdf", fake_parse)
    monkeypatch.setattr(eis, "sync_evidence_dataframe_to_db", lambda df: synced.setdefault("rows", len(df)))

    result = eis.import_evidence_files([tmp_path], evidence_db_path=existing_csv)

    assert result["ok"] is False
    assert result["pdf_count"] == 2
    assert result["parsed_record_count"] == 2
    assert result["clean_record_count"] == 2
    assert result["inserted_count"] == 1
    assert result["skipped_existing_count"] == 1
    assert result["skipped_existing_ids"] == ["dup_1"]
    assert len(result["errors"]) == 1
    assert result["written"] is True
    assert synced["rows"] == 2

    final_df = pd.read_csv(existing_csv)
    assert set(final_df["evidence_id"]) == {"dup_1", "new_1"}


def test_import_evidence_files_replace_existing_refreshes_rows(monkeypatch, tmp_path):
    """Test import evidence files replace existing refreshes rows."""
    pdf_ok = tmp_path / "sample_tsp.pdf"
    pdf_ok.write_text("ok", encoding="utf-8")
    existing_csv = tmp_path / "evidence_db.csv"
    pd.DataFrame(
        [
            {
                "evidence_id": "dup_1",
                "source_type": "tsp",
                "source_level": "segment",
                "report_id": "old",
                "report_date": "2023-01-01",
                "issue_date": "2023-01-01",
                "tunnel_name": "old",
                "start_num": 36000.0,
                "end_num": 36010.0,
                "face_num": 36005.0,
                "next_forecast_num": 36020.0,
                "confidence": "high",
                "attrs_json": "{}",
                "raw_text": "old",
            }
        ]
    ).to_csv(existing_csv, index=False, encoding="utf-8-sig")

    monkeypatch.setattr(eis, "collect_pdf_paths", lambda paths, recursive=False: [pdf_ok])
    monkeypatch.setattr(
        eis,
        "parse_evidence_pdf",
        lambda pdf_path, source_type=None: ("tsp", [_record("dup_1", start_num=36620.0, end_num=36640.0)]),
    )
    monkeypatch.setattr(eis, "sync_evidence_dataframe_to_db", lambda df: None)

    result = eis.import_evidence_files(
        [pdf_ok],
        evidence_db_path=existing_csv,
        replace_existing=True,
    )

    assert result["ok"] is True
    assert result["replaced_count"] == 1
    assert result["inserted_count"] == 1
    final_df = pd.read_csv(existing_csv)
    assert len(final_df) == 1
    assert float(final_df.loc[0, "start_num"]) == 36620.0