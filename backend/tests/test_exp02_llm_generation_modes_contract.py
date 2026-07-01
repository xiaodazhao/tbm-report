from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "experiments" / "exp02_llm_generation_modes" / "run_exp02_llm_generation_modes.py"


def _load_exp02():
    spec = importlib.util.spec_from_file_location("exp02_modes", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_exp02_prompt_templates_have_expected_governance_boundaries():
    exp02 = _load_exp02()

    m1 = exp02._load_prompt_template("M1_direct_llm")
    m3 = exp02._load_prompt_template("M3_twin_evidence_pack_llm")
    m4 = exp02._load_prompt_template("M4_full_twin_governance_trace_boundary_reviser")

    assert "evidence_governance" not in m1
    assert "allowed_claims" not in m1
    assert "forbidden_claims" not in m1
    assert "evidence_governance" in m3
    assert "allowed_claims" in m3
    assert "forbidden_claims" in m4
    assert "GRCI 不是灾害概率" in m4


def test_exp02_mock_reports_cover_all_modes():
    exp02 = _load_exp02()

    for mode in exp02.MODES:
        if mode == "M0_template_only":
            continue
        report = exp02._mock_llm_report(mode, purpose="report_generation")
        assert "TBM 施工日报" in report
        assert "当前掌子面前方" in report or "前方" in report

    revised = exp02._mock_llm_report(
        "M4_full_twin_governance_trace_boundary_reviser",
        purpose="report_revision",
    )
    assert "耦合关注度指标仅用于已掘区段复核" in revised
    assert "不表示已发生事实" in revised


def test_exp02_summary_columns_include_required_metrics():
    exp02 = _load_exp02()
    required = {
        "date",
        "mode",
        "quality_score",
        "grounding_rate_effective",
        "unsupported_claim_count_effective",
        "boundary_violation_count",
        "revision_error_reduction_rate",
    }

    assert required.issubset(set(exp02.SUMMARY_COLUMNS))


def test_exp02_selection_prioritizes_typical_dates_when_available():
    exp02 = _load_exp02()
    rows = [
        {"date": "2023-10-01", "high_grci_cells_count": 5, "forward_attention_cells_count": 3},
        {"date": "2023-12-30", "high_grci_cells_count": 1, "forward_attention_cells_count": 3},
        {"date": "2023-12-28", "high_grci_cells_count": 1, "forward_attention_cells_count": 3},
        {"date": "2023-09-15", "high_grci_cells_count": 1, "forward_attention_cells_count": 3},
    ]
    original = exp02.pd.read_csv
    exp02.pd.read_csv = lambda *_args, **_kwargs: exp02.pd.DataFrame(rows)
    try:
        dates = exp02._select_dates(explicit_dates=[], max_dates=3)
    finally:
        exp02.pd.read_csv = original

    assert dates == ["2023-12-30", "2023-12-28", "2023-09-15"]


def test_exp02_real_provider_alias_openai_compatible(monkeypatch):
    exp02 = _load_exp02()
    monkeypatch.setenv("LLM_API_KEY", "secret-test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    provider = exp02._build_provider(
        llm_mode="real",
        provider="openai_compatible",
        model=None,
        temperature=None,
        max_tokens=None,
    )

    assert provider.provider == "openai_or_compatible"
    assert provider.model == "deepseek-chat"


def test_exp02_dry_run_real_config_does_not_log_api_key(tmp_path, monkeypatch):
    exp02 = _load_exp02()
    monkeypatch.setenv("LLM_API_KEY", "secret-test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    result = exp02._dry_run_real_config(
        selected_dates=["2023-12-30"],
        modes=["M0_template_only", "M3_twin_evidence_pack_llm"],
        out_dir=tmp_path,
        provider_arg="openai_compatible",
        model_arg=None,
        temperature=None,
        max_tokens=None,
    )
    serialized = exp02.json.dumps(result, ensure_ascii=False)

    assert result["dry_run"] is True
    assert result["no_external_request_sent"] is True
    assert result["api_key_present"] is True
    assert result["api_key_value_logged"] is False
    assert "secret-test-key" not in serialized
    assert result["checks"]["output_writable"] is True
    assert result["prompt_files"]["M3_twin_evidence_pack_llm"].endswith("M3_twin_evidence_pack_llm_prompt.md")


def test_exp02_revision_prompt_preserves_full_draft_report():
    exp02 = _load_exp02()
    full_report = "\n\n".join(
        f"## {title}\n" + ("段落内容。" * 120)
        for title in exp02.M4_REQUIRED_SECTION_TITLES
    )

    payload = {"draft_report": full_report}
    prompt_json = exp02._prompt_json(payload)

    assert "<truncated" not in prompt_json
    for title in exp02.M4_REQUIRED_SECTION_TITLES:
        assert f"## {title}" in prompt_json


def test_exp02_m4_section_guard_uses_placeholder_for_missing_revision_sections():
    exp02 = _load_exp02()
    draft = "\n\n".join(
        f"## {title}\n初稿 {title} 内容。"
        for title in exp02.M4_REQUIRED_SECTION_TITLES
    )
    revised = "\n\n".join(
        f"## {title}\n修订 {title} 内容。"
        for title in exp02.M4_REQUIRED_SECTION_TITLES[:5]
    )

    repaired = exp02._ensure_m4_required_sections(
        revised_report=revised,
        draft_report=draft,
    )

    for title in exp02.M4_REQUIRED_SECTION_TITLES:
        assert f"## {title}" in repaired
    assert "初稿 已掘区段地质-施工响应复核 内容。" not in repaired
    assert "当前 Evidence Pack 未提供足够证据，不作扩展判断。" in repaired
    assert "修订 综合摘要 内容。" in repaired


def test_exp02_m4_section_guard_reports_metadata_for_added_sections():
    exp02 = _load_exp02()
    revised = f"## {exp02.M4_REQUIRED_SECTION_TITLES[0]}\n修订后内容。"

    repaired, meta = exp02._ensure_m4_required_sections_with_meta(
        revised_report=revised,
        draft_report="",
        pre_eval={},
    )

    assert meta["section_guard_applied"] is True
    assert exp02.M4_REQUIRED_SECTION_TITLES[1] in meta["guard_added_sections"]
    assert meta["guard_strategy"] == "placeholder_for_missing_sections"
    assert "当前 Evidence Pack 未提供足够证据，不作扩展判断。" in repaired


def test_exp02_revision_feedback_contains_actionable_sentence_and_section():
    exp02 = _load_exp02()
    draft = "\n\n".join(
        [
            "## 总体概况\nPLC 实测日进尺：1.0m。",
            "## 前方地质关注提示\n前方关注范围：DK1013+200 至 DK1013+230。",
        ]
    )
    quality = {
        "claim_results": [
            {
                "grounded": False,
                "claim_text": "0m",
                "error_type": "E10_NUMERIC_VALUE_UNGROUNDED",
            },
            {
                "grounded": False,
                "claim_text": "前方关注范围：DK1013+200 至 DK1013+230。",
                "error_type": "E1_UNSUPPORTED_CLAIM",
            },
        ]
    }

    feedback = exp02._build_revision_feedback(
        draft_report=draft,
        quality=quality,
        boundary={},
    )

    assert feedback
    first = feedback[0]
    assert first["section"] == "总体概况"
    assert first["sentence_text"] == "PLC 实测日进尺：1.0m。"
    assert first["error_type"] == "E10_NUMERIC_VALUE_UNGROUNDED"
    assert first["suggested_action"]


def test_exp02_revision_feedback_has_specific_actions_for_e14_and_forward_boundary():
    exp02 = _load_exp02()

    e14_action = exp02._suggested_revision_action("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE")
    forward_action = exp02._suggested_revision_action("boundary:forward_fact_misuse")

    assert "用于已掘复核的 10m 对齐单元范围" in e14_action
    assert "实际推进范围" in e14_action
    assert "前方提示" in forward_action
    assert "后续现场揭露进行复核" in forward_action
