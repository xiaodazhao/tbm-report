from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from scripts.audit_evidence_db import audit_evidence_db
from scripts.audit_plc_dates import audit_plc_dates
from scripts.classify_experiment_dates import classify_experiment_dates
from scripts.run_batch_llm_generation import run_batch_llm_generation
from scripts.run_batch_pipeline import run_batch_pipeline


def test_audit_plc_dates_survives_bad_file_and_outputs_advance(tmp_path):
    good = tmp_path / "tbm_data_20231230.csv"
    bad = tmp_path / "tbm_data_20231231.csv"
    pd.DataFrame(
        {
            "运行时间-time": ["2023-12-30 00:00:00", "2023-12-30 00:10:00"],
            "导向盾首里程": [1014601.0, 1014616.0],
            "推进速度": [1.0, 1.2],
            "刀盘扭矩": [10.0, 11.0],
            "推力": [100.0, 110.0],
            "CH4检测": [0.0, 0.0],
        }
    ).to_csv(good, index=False, encoding="utf-8-sig")
    bad.write_text("not,a,valid\n\"unterminated", encoding="utf-8")

    payload = audit_plc_dates(data_dir=tmp_path)
    rows = {row["date"]: row for row in payload["rows"]}

    assert rows["2023-12-30"]["usable_for_report"] is True
    assert rows["2023-12-30"]["daily_advance_m"] == 15.0
    assert rows["2023-12-31"]["usable_for_report"] is False
    assert "read_or_audit_failed" in rows["2023-12-31"]["exclude_reason"]


def test_audit_evidence_db_outputs_expected_counts(tmp_path):
    evidence = tmp_path / "evidence_db.csv"
    pd.DataFrame(
        {
            "report_date": ["2023-12-30", "2023-12-30", None],
            "source_type_norm": ["TSP", "HSP", "sketch"],
            "evidence_report_role": ["forecast", "observed", "background"],
            "start_chainage": [100.0, 110.0, 130.0],
            "end_chainage": [105.0, 108.0, 140.0],
        }
    ).to_csv(evidence, index=False, encoding="utf-8-sig")

    payload = audit_evidence_db(evidence_path=evidence)
    rows = {row["date"]: row for row in payload["rows"]}

    assert rows["2023-12-30"]["total_evidence_count"] == 2
    assert rows["2023-12-30"]["TSP_count"] == 1
    assert rows["2023-12-30"]["HSP_count"] == 1
    assert rows["2023-12-30"]["invalid_geometry_count"] == 1
    assert rows["unknown_date"]["sketch_count"] == 1


def test_classify_experiment_dates_produces_labels(monkeypatch, tmp_path):
    plc_path = tmp_path / "plc.csv"
    ev_path = tmp_path / "ev.csv"
    pd.DataFrame(
        [
            {"date": "2023-12-30", "usable_for_report": True, "daily_advance_m": 15.0, "exclude_reason": ""},
            {"date": "2023-12-31", "usable_for_report": False, "daily_advance_m": None, "exclude_reason": "missing_required_columns"},
        ]
    ).to_csv(plc_path, index=False)
    pd.DataFrame([{"date": "unknown_date", "total_evidence_count": 2}]).to_csv(ev_path, index=False)

    import scripts.classify_experiment_dates as mod

    monkeypatch.setattr(mod, "run_daily_report_pipeline", lambda *args, **kwargs: _fake_pipeline_result())
    payload = classify_experiment_dates(plc_audit_path=plc_path, evidence_audit_path=ev_path)
    labels = {row["date"]: row["class_label"] for row in payload["rows"]}

    assert labels["2023-12-30"] == "A"
    assert labels["2023-12-31"] == "D"


def test_run_batch_pipeline_continue_on_error_and_summary(monkeypatch, tmp_path):
    import scripts.run_batch_pipeline as mod

    def fake_pipeline(date, **kwargs):
        if date == "bad":
            raise RuntimeError("boom")
        return _fake_pipeline_result()

    monkeypatch.setattr(mod, "run_daily_report_pipeline", fake_pipeline)
    payload = run_batch_pipeline(dates=["good", "bad"], out_dir=tmp_path, continue_on_error=True)

    assert payload["summary"]["passed_count"] == 1
    assert payload["summary"]["failed_count"] == 1
    assert (tmp_path / "good" / "method_metrics.json").exists()


def test_run_batch_llm_generation_defaults_to_mock_and_summarizes(monkeypatch, tmp_path):
    import scripts.run_batch_llm_generation as mod

    monkeypatch.setattr(mod, "run_daily_report_pipeline", lambda *args, **kwargs: _fake_pipeline_result())
    monkeypatch.setattr(mod, "generate_llm_report", lambda **kwargs: _fake_llm_result())
    payload = run_batch_llm_generation(
        dates=["2023-12-30"],
        out_dir=tmp_path,
        generation_mode="evidence_pack_llm_with_revision",
        mock_llm=True,
        enable_revision=True,
    )

    row = payload["summary_rows"][0]
    assert row["provider"] == "mock"
    assert row["revision_enabled"] is True
    assert row["revision_improved"] is True
    assert (tmp_path / "2023-12-30" / "llm_summary.json").exists()


def _fake_pipeline_result():
    cell = SimpleNamespace(GRCI_available=True)
    return SimpleNamespace(
        scope_summary={
            "spatial_relevant_evidence_count": 3,
            "daily_review_cell_count": 1,
            "forward_attention_cell_count": 1,
            "GRCI_available_count": 1,
        },
        construction_state_cells=[cell],
        daily_review_cells=[{"cell_id": "a"}],
        forward_attention_cells=[{"cell_id": "b"}],
        local_background_cells=[],
        prompt_evidence_pack={"ok": True},
        quality={"error_type_counts": {"E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE": 0}},
        quality_summary={"quality_score": 100, "grounding_rate": 1.0, "unsupported_claim_count": 0},
        trace={"ok": True},
        method_metrics={"passed": True},
        warnings=[],
        date="2023-12-30",
        twin_state={},
        report_text="report",
    )


def _fake_llm_result():
    return {
        "generation_mode": "evidence_pack_llm_with_revision",
        "provider": "mock",
        "revision_enabled": True,
        "passed": True,
        "error_message": None,
        "report_final": "final",
        "summary": {
            "draft_quality_score": 90,
            "final_quality_score": 100,
            "draft_grounding_rate": 0.9,
            "final_grounding_rate": 1.0,
            "draft_unsupported_claim_count": 1,
            "final_unsupported_claim_count": 0,
            "draft_error_type_counts": {"E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE": 1},
            "final_error_type_counts": {"E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE": 0},
        },
    }
