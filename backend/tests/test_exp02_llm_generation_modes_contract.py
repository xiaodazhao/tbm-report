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

