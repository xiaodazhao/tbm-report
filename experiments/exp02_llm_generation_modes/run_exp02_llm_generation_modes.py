from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from llm.llm_provider import LLMProvider, resolve_llm_provider_config  # noqa: E402
from llm.report_quality_checker import check_report_quality  # noqa: E402
from llm.report_trace_builder import build_report_trace, summarize_report_trace  # noqa: E402
from llm.twin_boundary_checker import check_twin_boundary_violations  # noqa: E402
from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402


EXP_DIR = Path(__file__).resolve().parent
PROMPT_DIR = EXP_DIR / "prompts"
EXP01_FIX02 = REPO_ROOT / "experiments" / "exp01_twin_full_run" / "outputs_fix02"

MODES = [
    "M0_template_only",
    "M1_direct_llm",
    "M2_raw_evidence_llm",
    "M3_twin_evidence_pack_llm",
    "M4_full_twin_governance_trace_boundary_reviser",
]

PROMPT_TEMPLATE_FILES = {
    "M1_direct_llm": "M1_direct_llm_prompt.md",
    "M2_raw_evidence_llm": "M2_raw_evidence_llm_prompt.md",
    "M3_twin_evidence_pack_llm": "M3_twin_evidence_pack_llm_prompt.md",
    "M4_full_twin_governance_trace_boundary_reviser": "M4_full_generation_prompt.md",
}

TYPICAL_DATES = ["2023-12-30", "2023-12-28", "2023-09-15"]

SUMMARY_COLUMNS = [
    "date",
    "mode",
    "llm_model",
    "generation_success",
    "quality_score",
    "grounding_rate_raw",
    "grounding_rate_effective",
    "unsupported_claim_count_raw",
    "unsupported_claim_count_effective",
    "heading_fragment_false_positive_count",
    "claim_count",
    "claim_trace_rate",
    "numeric_error_count",
    "boundary_violation_count",
    "forward_fact_misuse_count",
    "grci_probability_misuse_count",
    "plc_proxy_misuse_count",
    "stop_causality_misuse_count",
    "local_background_scope_misuse_count",
    "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count",
    "section_completeness_score",
    "required_section_missing_count",
    "high_attention_cell_coverage",
    "report_length_chars",
    "generation_time_seconds",
    "revision_applied",
    "pre_revision_boundary_violation_count",
    "post_revision_boundary_violation_count",
    "pre_revision_unsupported_claim_count_effective",
    "post_revision_unsupported_claim_count_effective",
    "revision_error_reduction_rate",
    "error_message",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Exp02 LLM generation mode comparison.")
    parser.add_argument("--dates", nargs="*", help="Dates as space-separated and/or comma-separated values.")
    parser.add_argument("--max-dates", type=int, default=15)
    parser.add_argument("--modes", nargs="*", choices=MODES, default=MODES)
    parser.add_argument("--llm-mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--provider", default=None, help="Provider for real mode, e.g. openai_or_compatible.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument(
        "--dry-run-real-config",
        action="store_true",
        help="Check real LLM environment/output/date readiness without sending any request.",
    )
    parser.add_argument("--out-dir", default=str(EXP_DIR / "outputs"))
    args = parser.parse_args()

    out_dir = _resolve_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    selected_dates = _select_dates(
        explicit_dates=_parse_dates(args.dates),
        max_dates=args.max_dates,
    )

    if args.dry_run_real_config:
        result = _dry_run_real_config(
            selected_dates=selected_dates,
            modes=args.modes,
            out_dir=out_dir,
            provider_arg=args.provider,
            model_arg=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        _write_json(out_dir / "exp02_real_config_dry_run.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print("[exp02] dry-run only: no external LLM request was sent.")
        return

    selected_rows = []
    summary_rows = []
    boundary_samples = []
    unsupported_samples = []
    numeric_samples = []
    revision_rows = []
    failures = []

    provider = _build_provider(
        llm_mode=args.llm_mode,
        provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    for index, date in enumerate(selected_dates, start=1):
        print(f"[exp02] {index}/{len(selected_dates)} loading baseline {date}")
        try:
            baseline = run_daily_report_pipeline(date, use_llm=False, generation_mode="template")
            selected_rows.append(_selected_date_row(date, baseline))
        except Exception as exc:
            failures.append(_failure_row(date=date, mode="baseline", exc=exc))
            continue

        for mode in args.modes:
            print(f"[exp02] {date} {mode}")
            try:
                run_result = _run_mode(
                    date=date,
                    mode=mode,
                    baseline=baseline,
                    provider=provider,
                    llm_mode=args.llm_mode,
                    retry_count=args.retry_count,
                    target_dir=reports_dir / date / mode,
                )
                summary_rows.append(run_result["summary_row"])
                boundary_samples.extend(run_result["boundary_samples"])
                unsupported_samples.extend(run_result["unsupported_samples"])
                numeric_samples.extend(run_result["numeric_samples"])
                if run_result.get("revision_row"):
                    revision_rows.append(run_result["revision_row"])
            except Exception as exc:
                failures.append(_failure_row(date=date, mode=mode, exc=exc))
                summary_rows.append(_failed_summary_row(date, mode, exc))

    mode_summary = _mode_comparison_rows(summary_rows)
    revision_summary = _revision_effect_rows(revision_rows)
    overall = _overall_summary(
        selected_rows=selected_rows,
        summary_rows=summary_rows,
        failures=failures,
        llm_mode=args.llm_mode,
        modes=args.modes,
        provider=provider,
    )
    report = _experiment_report(
        selected_rows=selected_rows,
        mode_summary=mode_summary,
        revision_summary=revision_summary,
        overall=overall,
        out_dir=out_dir,
    )

    _write_csv(out_dir / "exp02_selected_dates.csv", selected_rows)
    _write_text(out_dir / "exp02_selected_dates.md", _markdown_table(selected_rows))
    _write_csv(out_dir / "exp02_generation_summary.csv", summary_rows, columns=SUMMARY_COLUMNS)
    _write_text(out_dir / "exp02_generation_summary.md", _markdown_table(summary_rows, columns=SUMMARY_COLUMNS))
    _write_csv(out_dir / "exp02_mode_comparison_summary.csv", mode_summary)
    _write_text(out_dir / "exp02_mode_comparison_summary.md", _markdown_table(mode_summary))
    _write_csv(out_dir / "exp02_revision_effect_summary.csv", revision_summary)
    _write_text(out_dir / "exp02_revision_effect_summary.md", _markdown_table(revision_summary))
    _write_csv(out_dir / "exp02_boundary_violation_samples.csv", boundary_samples)
    _write_csv(out_dir / "exp02_unsupported_claim_samples.csv", unsupported_samples)
    _write_csv(out_dir / "exp02_numeric_error_samples.csv", numeric_samples)
    _write_csv(out_dir / "exp02_failed_runs.csv", failures)
    _write_json(out_dir / "exp02_overall_summary.json", overall)
    _write_text(out_dir / "exp02_experiment_report.md", report)

    print(json.dumps(overall, ensure_ascii=False, indent=2, default=str))
    print(f"[exp02] outputs: {out_dir}")


def _run_mode(
    *,
    date: str,
    mode: str,
    baseline: Any,
    provider: LLMProvider,
    llm_mode: str,
    retry_count: int,
    target_dir: Path,
) -> dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()
    prompt = ""
    raw_response = ""
    revised_report = ""
    revision_prompt = ""
    revision_raw_response = ""
    error_message = ""
    revision_applied = False

    if mode == "M0_template_only":
        report = baseline.report_text
        generation_success = True
        llm_model = "template"
        prompt = "M0_template_only uses the pipeline template report and does not call LLM."
    else:
        prompt = _build_prompt_for_mode(mode, baseline)
        generation = _generate_with_retry(
            prompt=prompt,
            mode=mode,
            provider=provider,
            llm_mode=llm_mode,
            retry_count=retry_count,
            purpose="report_generation",
        )
        generation_success = bool(generation.get("ok"))
        raw_response = str(generation.get("raw_response") or generation.get("text") or "")
        error_message = str(generation.get("error_message") or "")
        report = _clean_llm_text(str(generation.get("text") or ""))
        llm_model = str(generation.get("model") or provider.model)
        if llm_mode == "mock" and mode == "M3_twin_evidence_pack_llm":
            report = baseline.report_text
            raw_response = baseline.report_text
        if not report:
            report = baseline.report_text
            error_message = error_message or "empty LLM response; template fallback used"

    pre_eval = _evaluate_report(report, baseline)
    final_report = report
    post_eval = pre_eval

    if mode == "M4_full_twin_governance_trace_boundary_reviser":
        revision_prompt = _build_revision_prompt(
            baseline=baseline,
            draft_report=report,
            quality=pre_eval["quality"],
            trace=pre_eval["trace"],
            boundary=pre_eval["boundary"],
        )
        revision = _generate_with_retry(
            prompt=revision_prompt,
            mode=mode,
            provider=provider,
            llm_mode=llm_mode,
            retry_count=retry_count,
            purpose="report_revision",
        )
        revision_raw_response = str(revision.get("raw_response") or revision.get("text") or "")
        if revision.get("ok") and str(revision.get("text") or "").strip():
            final_report = (
                baseline.report_text
                if llm_mode == "mock"
                else _clean_llm_text(str(revision.get("text") or ""))
            )
            revision_applied = True
        else:
            error_message = error_message or str(revision.get("error_message") or "")
        post_eval = _evaluate_report(final_report, baseline)
        revised_report = final_report

    elapsed = time.time() - start
    row = _summary_row(
        date=date,
        mode=mode,
        llm_model=llm_model,
        generation_success=generation_success,
        eval_result=post_eval,
        pre_eval_result=pre_eval,
        report=final_report,
        elapsed=elapsed,
        revision_applied=revision_applied,
        error_message=error_message,
        high_grci_cells=baseline.high_grci_cells,
    )
    revision_row = None
    if mode == "M4_full_twin_governance_trace_boundary_reviser":
        revision_row = _revision_row(date, mode, pre_eval, post_eval, revision_applied)

    _write_text(target_dir / "report.md", final_report)
    _write_text(target_dir / "prompt.md", prompt)
    _write_text(target_dir / "llm_response_raw.txt", raw_response)
    _write_json(target_dir / "quality_summary.json", post_eval["quality"])
    _write_json(target_dir / "trace_summary.json", post_eval["trace_summary"])
    _write_json(target_dir / "boundary_summary.json", post_eval["boundary"])
    if revised_report:
        _write_text(target_dir / "revised_report.md", revised_report)
    if revision_prompt:
        _write_text(target_dir / "revision_prompt.md", revision_prompt)
        _write_text(target_dir / "revision_response_raw.txt", revision_raw_response)
    _write_json(target_dir / "mode_summary.json", row)

    return {
        "summary_row": row,
        "revision_row": revision_row,
        "boundary_samples": _boundary_samples(date, mode, post_eval["boundary"]),
        "unsupported_samples": _unsupported_samples(date, mode, post_eval["quality"]),
        "numeric_samples": _numeric_samples(date, mode, post_eval["quality"]),
    }


def _evaluate_report(report: str, baseline: Any) -> dict[str, Any]:
    quality = check_report_quality(
        report,
        twin_state=baseline.twin_state,
        prompt_evidence_pack=baseline.prompt_evidence_pack,
        include_claim_results=True,
    )
    grounding_result = {
        "claim_results": quality.get("claim_results") or [],
        **(quality.get("grounding_summary") or {}),
    }
    trace = build_report_trace(
        report,
        grounding_result=grounding_result,
        twin_state=baseline.twin_state,
        prompt_evidence_pack=baseline.prompt_evidence_pack,
    )
    trace_summary = summarize_report_trace(trace)
    boundary = check_twin_boundary_violations(
        report,
        evidence_pack=baseline.prompt_evidence_pack,
        twin=baseline.daily_construction_twin,
    )
    return {
        "quality": quality,
        "trace": trace,
        "trace_summary": trace_summary,
        "boundary": boundary,
    }


def _build_prompt_for_mode(mode: str, baseline: Any) -> str:
    if mode == "M1_direct_llm":
        payload = {
            "date": baseline.date,
            "scope_summary": baseline.scope_summary,
            "operation_summary": _compact_dict(baseline.operation_summary, max_items=20),
            "gas_summary": _compact_dict(baseline.gas_summary, max_items=20),
            "note": "本模式不提供完整 Evidence Governance、allowed_claims、forbidden_claims 或 evidence role 约束。",
        }
    elif mode == "M2_raw_evidence_llm":
        payload = {
            "date": baseline.date,
            "operation_summary": _compact_dict(baseline.operation_summary, max_items=30),
            "gas_summary": _compact_dict(baseline.gas_summary, max_items=30),
            "normalized_evidence_summary": baseline.normalized_evidence_summary,
            "forward_profile": baseline.forward_profile,
            "high_grci_cells_preview": _preview_list(baseline.high_grci_cells, 5),
            "geology_records_preview": _preview_list(baseline.geo_state_records, 6),
            "note": "本模式是 raw evidence baseline，不提供完整 governance、metric_boundaries、allowed_claims 或 forbidden_claims。",
        }
    elif mode in {"M3_twin_evidence_pack_llm", "M4_full_twin_governance_trace_boundary_reviser"}:
        payload = _pack_prompt_view(baseline.prompt_evidence_pack)
    else:
        raise ValueError(f"unsupported mode for prompt: {mode}")

    template = _load_prompt_template(mode)
    return template.replace("{{INPUT_JSON}}", _prompt_json(payload))


def _build_revision_prompt(
    *,
    baseline: Any,
    draft_report: str,
    quality: dict[str, Any],
    trace: dict[str, Any],
    boundary: dict[str, Any],
) -> str:
    payload = {
        "draft_report": draft_report,
        "quality": {
            "quality_score": quality.get("quality_score"),
            "error_type_counts": quality.get("error_type_counts", {}),
            "unsupported_claim_count": quality.get("unsupported_claim_count"),
            "unsupported_claims": [
                item for item in (quality.get("claim_results") or [])
                if isinstance(item, dict) and not item.get("grounded")
            ],
        },
        "trace": {
            "trace_coverage": trace.get("trace_coverage"),
            "support_type_distribution": trace.get("support_type_distribution", {}),
        },
        "boundary": boundary,
        "evidence_pack_constraints": {
            "evidence_governance": baseline.prompt_evidence_pack.get("evidence_governance"),
            "metric_boundaries": baseline.prompt_evidence_pack.get("metric_boundaries"),
            "generation_constraints": baseline.prompt_evidence_pack.get("generation_constraints"),
            "forbidden_claims": baseline.prompt_evidence_pack.get("forbidden_claims"),
        },
    }
    template = (PROMPT_DIR / "M4_revision_prompt.md").read_text(encoding="utf-8")
    return template.replace("{{INPUT_JSON}}", _prompt_json(payload))


def _generate_with_retry(
    *,
    prompt: str,
    mode: str,
    provider: LLMProvider,
    llm_mode: str,
    retry_count: int,
    purpose: str,
) -> dict[str, Any]:
    if llm_mode == "mock":
        return {
            "ok": True,
            "provider": "mock",
            "model": "mock-exp02",
            "text": _mock_llm_report(mode, purpose=purpose),
            "raw_response": _mock_llm_report(mode, purpose=purpose),
            "error_message": "",
            "warnings": [],
        }

    last: dict[str, Any] = {}
    for _ in range(max(retry_count, 1)):
        last = provider.generate(prompt, purpose=purpose)
        if last.get("ok"):
            return last
    return last


def _mock_llm_report(mode: str, *, purpose: str) -> str:
    if purpose == "report_revision":
        return _safe_mock_report("M4 修订后报告")
    if mode == "M1_direct_llm":
        return "\n".join([
            "# TBM 施工日报",
            "## 1. 综合结论摘要",
            "本日施工整体平稳，但 GRCI 表示灾害概率较高。",
            "## 2. 今日施工运行概况",
            "报告根据输入摘要生成。",
            "## 3. PLC 工况统计分析",
            "cutterhead_power_proxy 是真实物理功率，可直接说明负载。",
            "## 4. 气体监测分析",
            "涉及气体以输入摘要为准。",
            "## 5. 已掘区段地质-施工响应复核",
            "stop_ratio 说明设备异常。",
            "## 6. 当前掌子面前方关注提示",
            "前方已经发生异常，应立即处置。",
            "## 7. 结论与建议",
            "建议现场复核。",
        ])
    if mode == "M2_raw_evidence_llm":
        return "\n".join([
            "# TBM 施工日报",
            "## 1. 综合结论摘要",
            "根据 PLC 与地质证据摘要，施工状态需要关注。",
            "## 2. 今日施工运行概况",
            "当日推进和运行信息以输入为准。",
            "## 3. PLC 工况统计分析",
            "PLC 响应可作为已掘区段施工响应证据。",
            "## 4. 气体监测分析",
            "气体监测结论以输入摘要为准。",
            "## 5. 已掘区段地质-施工响应复核",
            "local_background 证明当日异常。",
            "## 6. 当前掌子面前方关注提示",
            "前方关注提示应结合现场复核。",
            "## 7. 结论与建议",
            "建议对关注区段持续复核。",
        ])
    if mode == "M4_full_twin_governance_trace_boundary_reviser":
        return "\n".join([
            "# TBM 施工日报",
            "## 1. 综合结论摘要",
            "本报告依据 Twin Evidence Pack 生成，但草稿中错误地称 GRCI 表示灾害概率。",
            "## 2. 今日施工运行概况",
            "PLC 实测推进范围和推进量以 daily_plc_range 为准。",
            "## 3. PLC 工况统计分析",
            "PLC enhanced metrics 仅作为已掘区段施工响应证据。",
            "## 4. 气体监测分析",
            "气体监测结论以 gas_evidence 为准。",
            "## 5. 已掘区段地质-施工响应复核",
            "daily_review cells 用于已掘复核。",
            "## 6. 当前掌子面前方关注提示",
            "forward_attention 仅表示当前掌子面前方关注提示。",
            "## 7. 结论与建议",
            "建议按证据包列出的 trace 进行现场复核。",
        ])
    return _safe_mock_report("M3 Twin Evidence Pack 报告")


def _safe_mock_report(title: str) -> str:
    return "\n".join([
        "# TBM 施工日报",
        "## 1. 综合结论摘要",
        f"{title}仅依据输入 Evidence Pack 生成，不补充证据包之外的工程事实。",
        "耦合关注度指标仅用于已掘区段复核，不用于概率判断。",
        "## 2. 今日施工运行概况",
        "PLC 实测推进范围和推进量以 daily_plc_range 为准；daily_excavated_scope 仅表示 10m cell 对齐后的已掘复核范围。",
        "## 3. PLC 工况统计分析",
        "PLC enhanced metrics 仅作为已掘区段施工响应证据；cutterhead_power_proxy 不是实际物理功率。",
        "stop_ratio 仅作为施工响应关注信号，不能直接解释为异常停机原因。",
        "## 4. 气体监测分析",
        "气体监测结论以 gas_evidence 为准，不补充字段含义之外的信息。",
        "## 5. 已掘区段地质-施工响应复核",
        "daily_review cells 用于已掘区段复核，high GRCI cells 只在 GRCI_available 为 true 时使用。",
        "## 6. 当前掌子面前方关注提示",
        "forward_attention 仅表示当前掌子面前方关注提示，不表示已发生事实，也不使用 GRCI。",
        "## 7. 结论与建议",
        "建议结合 source_trace 和现场记录复核已掘区段响应，并持续关注前方提示区段。",
    ])


def _summary_row(
    *,
    date: str,
    mode: str,
    llm_model: str,
    generation_success: bool,
    eval_result: dict[str, Any],
    pre_eval_result: dict[str, Any],
    report: str,
    elapsed: float,
    revision_applied: bool,
    error_message: str,
    high_grci_cells: list[dict[str, Any]],
) -> dict[str, Any]:
    quality = eval_result["quality"]
    trace_summary = eval_result["trace_summary"]
    boundary = eval_result["boundary"]
    stats = quality.get("stats") or {}
    error_counts = quality.get("error_type_counts") or {}
    boundary_counts = _boundary_type_counts(boundary)
    missing = _safe_int(stats.get("missing_section_count"))
    section_count = _safe_int(stats.get("section_count"))
    pre_boundary = pre_eval_result["boundary"].get("violation_count") or 0
    post_boundary = boundary.get("violation_count") or 0
    pre_unsupported = pre_eval_result["quality"].get("unsupported_claim_count") or 0
    post_unsupported = quality.get("unsupported_claim_count") or 0
    return {
        "date": date,
        "mode": mode,
        "llm_model": llm_model,
        "generation_success": bool(generation_success),
        "quality_score": quality.get("quality_score"),
        "grounding_rate_raw": quality.get("grounding_rate"),
        "grounding_rate_effective": quality.get("grounding_rate"),
        "unsupported_claim_count_raw": quality.get("unsupported_claim_count"),
        "unsupported_claim_count_effective": quality.get("unsupported_claim_count"),
        "heading_fragment_false_positive_count": stats.get("excluded_non_technical_claim_count"),
        "claim_count": quality.get("claim_count"),
        "claim_trace_rate": trace_summary.get("trace_coverage"),
        "numeric_error_count": error_counts.get("E10_NUMERIC_VALUE_UNGROUNDED", 0) + error_counts.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0),
        "boundary_violation_count": boundary.get("violation_count"),
        "forward_fact_misuse_count": boundary_counts.get("forward_fact_misuse", 0),
        "grci_probability_misuse_count": boundary_counts.get("grci_probability_misuse", 0),
        "plc_proxy_misuse_count": boundary_counts.get("plc_proxy_misuse", 0),
        "stop_causality_misuse_count": boundary_counts.get("stop_causality_misuse", 0),
        "local_background_scope_misuse_count": boundary_counts.get("local_background_scope_misuse", 0),
        "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count": error_counts.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0),
        "section_completeness_score": (1 - missing / section_count) if section_count else None,
        "required_section_missing_count": missing,
        "high_attention_cell_coverage": _high_cell_coverage(report, high_grci_cells),
        "report_length_chars": len(report or ""),
        "generation_time_seconds": round(elapsed, 3),
        "revision_applied": bool(revision_applied),
        "pre_revision_boundary_violation_count": pre_boundary,
        "post_revision_boundary_violation_count": post_boundary,
        "pre_revision_unsupported_claim_count_effective": pre_unsupported,
        "post_revision_unsupported_claim_count_effective": post_unsupported,
        "revision_error_reduction_rate": _reduction_rate(pre_boundary + pre_unsupported, post_boundary + post_unsupported),
        "error_message": error_message,
    }


def _revision_row(date: str, mode: str, pre_eval: dict[str, Any], post_eval: dict[str, Any], applied: bool) -> dict[str, Any]:
    pre_boundary = _safe_int(pre_eval["boundary"].get("violation_count"))
    post_boundary = _safe_int(post_eval["boundary"].get("violation_count"))
    pre_unsupported = _safe_int(pre_eval["quality"].get("unsupported_claim_count"))
    post_unsupported = _safe_int(post_eval["quality"].get("unsupported_claim_count"))
    return {
        "date": date,
        "mode": mode,
        "revision_applied": applied,
        "pre_revision_boundary_violation_count": pre_boundary,
        "post_revision_boundary_violation_count": post_boundary,
        "pre_revision_unsupported_claim_count_effective": pre_unsupported,
        "post_revision_unsupported_claim_count_effective": post_unsupported,
        "revision_error_reduction_rate": _reduction_rate(pre_boundary + pre_unsupported, post_boundary + post_unsupported),
    }


def _boundary_samples(date: str, mode: str, boundary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "date": date,
            "mode": mode,
            "violation_type": item.get("violation_type") or item.get("type"),
            "matched_text": item.get("matched_text"),
            "severity": item.get("severity"),
        }
        for item in (boundary.get("violations") or [])
        if isinstance(item, dict)
    ]


def _unsupported_samples(date: str, mode: str, quality: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in quality.get("claim_results") or []:
        if isinstance(item, dict) and item.get("grounded") is False:
            rows.append({
                "date": date,
                "mode": mode,
                "claim_text": item.get("claim_text") or item.get("text"),
                "claim_type": item.get("claim_type"),
                "support_type": item.get("support_type"),
                "trace_support_type": item.get("trace_support_type"),
                "error_type": item.get("error_type"),
            })
    return rows


def _numeric_samples(date: str, mode: str, quality: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in quality.get("violations") or []:
        if not isinstance(item, dict):
            continue
        if item.get("error_type") == "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE" or item.get("type") == "aligned_scope_as_actual_advance":
            rows.append({
                "date": date,
                "mode": mode,
                "error_type": item.get("error_type") or "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE",
                "message": item.get("message"),
                "phrase": item.get("phrase"),
            })
    return rows


def _select_dates(*, explicit_dates: list[str], max_dates: int) -> list[str]:
    if explicit_dates:
        return explicit_dates[:max_dates] if max_dates else explicit_dates

    path = EXP01_FIX02 / "exp01_daily_run_summary.csv"
    if not path.exists():
        return TYPICAL_DATES[:max_dates]

    rows = pd.read_csv(path).fillna("").to_dict(orient="records")
    dates: list[str] = []
    available = {str(row.get("date")) for row in rows}
    for date in TYPICAL_DATES:
        if date in available and date not in dates:
            dates.append(date)
    scored = sorted(rows, key=_selection_score, reverse=True)
    for row in scored:
        date = str(row.get("date"))
        if date and date not in dates:
            dates.append(date)
        if max_dates and len(dates) >= max_dates:
            break
    return dates[:max_dates] if max_dates else dates


def _selection_score(row: dict[str, Any]) -> float:
    return (
        10 * _safe_int(row.get("high_grci_cells_count"))
        + 3 * _safe_int(row.get("forward_attention_cells_count"))
        + 2 * _safe_int(row.get("grci_available_count"))
        + _safe_int(row.get("daily_review_cells_count"))
    )


def _selected_date_row(date: str, baseline: Any) -> dict[str, Any]:
    return {
        "date": date,
        "selection_reason": _selection_reason(baseline),
        "has_high_grci_cells": bool(baseline.high_grci_cells),
        "high_grci_cell_count": len(baseline.high_grci_cells),
        "has_forward_attention": bool(baseline.forward_attention_cells),
        "forward_attention_cell_count": len(baseline.forward_attention_cells),
        "daily_review_cell_count": len(baseline.daily_review_cells),
        "has_plc_enhanced_metrics": _has_plc_enhanced_metrics(baseline.daily_review_cells),
        "has_geology_evidence": any(bool(cell.get("has_geology_evidence")) for cell in baseline.daily_review_cells + baseline.forward_attention_cells),
        "has_gas_evidence": bool(baseline.gas_summary),
    }


def _selection_reason(baseline: Any) -> str:
    reasons = []
    if baseline.high_grci_cells:
        reasons.append("high_grci_cells 非空")
    if baseline.forward_attention_cells:
        reasons.append("forward_attention_cells 非空")
    if _has_plc_enhanced_metrics(baseline.daily_review_cells):
        reasons.append("PLC enhanced metrics 可用")
    if any(bool(cell.get("has_geology_evidence")) for cell in baseline.daily_review_cells + baseline.forward_attention_cells):
        reasons.append("存在地质证据参与")
    if baseline.date in TYPICAL_DATES:
        reasons.append("典型日期")
    return "；".join(reasons) or "普通低关注日期"


def _has_plc_enhanced_metrics(cells: list[dict[str, Any]]) -> bool:
    fields = {"working_sample_count", "working_ratio", "working_speed_cv", "penetration_mean", "cutterhead_power_proxy"}
    for cell in cells:
        plc = cell.get("plc_metrics") if isinstance(cell, dict) else {}
        if isinstance(plc, dict) and any(plc.get(field) is not None for field in fields):
            return True
    return False


def _dry_run_real_config(
    *,
    selected_dates: list[str],
    modes: list[str],
    out_dir: Path,
    provider_arg: str | None,
    model_arg: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> dict[str, Any]:
    provider = _build_provider(
        llm_mode="real",
        provider=provider_arg,
        model=model_arg,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    available_dates = set(_available_exp01_dates())
    missing_dates = [date for date in selected_dates if available_dates and date not in available_dates]
    prompt_files = {
        mode: str((PROMPT_DIR / PROMPT_TEMPLATE_FILES[mode]).relative_to(REPO_ROOT))
        for mode in modes
        if mode in PROMPT_TEMPLATE_FILES
    }
    missing_prompt_files = [
        path for path in prompt_files.values()
        if not (REPO_ROOT / path).exists()
    ]
    output_writable = _check_output_writable(out_dir)
    api_key_present = bool(provider.config.api_key)
    base_url_configured = bool(provider.config.base_url)
    checks = {
        "provider_enabled": provider.provider != "disabled",
        "api_key_present": api_key_present,
        "base_url_configured": base_url_configured,
        "model_configured": bool(provider.model),
        "output_writable": output_writable,
        "dates_selected": bool(selected_dates),
        "dates_available_in_exp01_fix02": not missing_dates,
        "prompt_files_exist": not missing_prompt_files,
    }
    return {
        "experiment": "exp02_llm_generation_modes",
        "dry_run": True,
        "no_external_request_sent": True,
        "api_key_value_logged": False,
        "provider": provider.provider,
        "model": provider.model,
        "base_url_configured": base_url_configured,
        "api_key_present": api_key_present,
        "temperature": provider.config.temperature,
        "max_tokens": provider.config.max_tokens,
        "timeout_sec": provider.config.timeout_sec,
        "selected_dates": selected_dates,
        "missing_dates_in_exp01_fix02": missing_dates,
        "modes": modes,
        "prompt_files": prompt_files,
        "missing_prompt_files": missing_prompt_files,
        "out_dir": str(out_dir),
        "output_writable": output_writable,
        "checks": checks,
        "checks_passed": all(checks.values()),
        "next_step": "Run again without --dry-run-real-config only after confirming external LLM use is allowed.",
    }


def _available_exp01_dates() -> list[str]:
    path = EXP01_FIX02 / "exp01_daily_run_summary.csv"
    if not path.exists():
        return []
    try:
        rows = pd.read_csv(path).fillna("").to_dict(orient="records")
    except Exception:
        return []
    return [str(row.get("date")) for row in rows if str(row.get("date") or "").strip()]


def _check_output_writable(out_dir: Path) -> bool:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".exp02_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _normalize_provider_name(provider: str | None) -> str | None:
    if provider is None:
        return None
    value = str(provider).strip().lower().replace("-", "_")
    aliases = {
        "openai_compatible": "openai_or_compatible",
        "openai_or_compatible": "openai_or_compatible",
        "compatible": "openai_or_compatible",
        "deepseek": "openai_or_compatible",
        "openai": "openai_or_compatible",
        "mock": "mock",
        "disabled": "disabled",
    }
    return aliases.get(value, value)


def _build_provider(
    *,
    llm_mode: str,
    provider: str | None,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> LLMProvider:
    provider_name = "mock" if llm_mode == "mock" else _normalize_provider_name(provider or os.getenv("LLM_PROVIDER"))
    config = resolve_llm_provider_config(
        provider=provider_name,
        model=model or os.getenv("LLM_MODEL"),
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=os.getenv("LLM_API_BASE") or os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL"),
    )
    return LLMProvider(config)


def _load_prompt_template(mode: str) -> str:
    file_name = PROMPT_TEMPLATE_FILES.get(mode)
    if not file_name:
        raise ValueError(f"mode has no prompt template: {mode}")
    return (PROMPT_DIR / file_name).read_text(encoding="utf-8")


def _parse_dates(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        out.extend(item.strip() for item in str(value).split(",") if item.strip())
    return list(dict.fromkeys(out))


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def _compact_dict(value: Any, *, max_items: int) -> Any:
    if isinstance(value, dict):
        return {k: _compact_dict(v, max_items=max_items) for k, v in list(value.items())[:max_items]}
    if isinstance(value, list):
        return [_compact_dict(item, max_items=max_items) for item in value[:max_items]]
    return value


def _preview_list(values: list[Any], limit: int) -> list[Any]:
    return [json.loads(json.dumps(item, ensure_ascii=False, default=str)) for item in (values or [])[:limit]]


def _pack_prompt_view(pack: dict[str, Any]) -> dict[str, Any]:
    geology = pack.get("geology_evidence") or {}
    daily_review = pack.get("daily_review_evidence") or {}
    forward = pack.get("forward_attention_evidence") or pack.get("forward_evidence") or {}
    background = pack.get("local_background_evidence") or pack.get("background_context_evidence") or {}
    coupling = pack.get("coupling_evidence") or {}
    return {
        "schema_version": pack.get("schema_version"),
        "evidence_pack_source": pack.get("evidence_pack_source"),
        "report_scope": pack.get("report_scope"),
        "operation_evidence": pack.get("operation_evidence"),
        "cluster_evidence": pack.get("cluster_evidence"),
        "gas_evidence": pack.get("gas_evidence"),
        "geology_evidence": {
            "key_cells": _brief_cells(geology.get("key_cells") or geology.get("selected_cells") or [], 8),
            "selected_cells": _brief_cells(geology.get("selected_cells") or [], 8),
            "excavated_review_cells": _brief_cells(geology.get("excavated_review_cells") or [], 8),
            "forward_attention_cells": _brief_cells(geology.get("forward_attention_cells") or [], 6),
            "background_context_cells": _brief_cells(geology.get("background_context_cells") or [], 4),
        },
        "daily_review_evidence": {
            "daily_review_cells": _brief_cells(daily_review.get("daily_review_cells") or daily_review.get("review_cells") or [], 8),
            "high_priority_cells": _brief_cells(daily_review.get("high_priority_cells") or [], 6),
            "note": daily_review.get("note"),
        },
        "forward_attention_evidence": {
            "forward_profile": forward.get("forward_profile"),
            "forward_attention_cells": _brief_cells(forward.get("forward_attention_cells") or [], 6),
            "note": forward.get("note"),
        },
        "local_background_evidence": {
            "local_background_cells": _brief_cells(background.get("local_background_cells") or background.get("background_context_cells") or [], 4),
            "note": background.get("note"),
        },
        "coupling_evidence": {
            "high_grci_cells": _brief_cells(coupling.get("high_grci_cells") or [], 6),
            "review_priority_cells": _brief_cells(coupling.get("review_priority_cells") or [], 8),
            "note": coupling.get("note"),
        },
        "quality_evidence": pack.get("quality_evidence"),
        "source_trace": _brief_traces(pack.get("source_trace") or [], 12),
        "evidence_governance": pack.get("evidence_governance"),
        "source_role_boundaries": pack.get("source_role_boundaries"),
        "metric_boundaries": pack.get("metric_boundaries"),
        "allowed_claims": pack.get("allowed_claims"),
        "forbidden_claims": pack.get("forbidden_claims"),
        "generation_constraints": pack.get("generation_constraints"),
        "warnings": pack.get("warnings"),
    }


def _brief_cells(cells: list[Any], limit: int) -> list[dict[str, Any]]:
    out = []
    for cell in (cells or [])[:limit]:
        if not isinstance(cell, dict):
            continue
        item = {
            key: cell.get(key)
            for key in [
                "cell_id",
                "cell_start",
                "cell_end",
                "cell_center",
                "cell_role",
                "GRS_geo_base",
                "RAI",
                "GRCI",
                "GRCI_available",
                "coupling_level",
                "main_hazards",
                "supporting_evidence_ids",
                "source_trace",
                "distance_to_face_m",
                "forward_distance_band",
                "selection_score",
                "selection_rank",
                "selection_reason",
                "attention_reason",
                "coupling_explanation",
            ]
            if key in cell
        }
        if "source_trace" in cell:
            item["source_trace"] = _brief_traces(cell.get("source_trace") or [], 3)
        out.append(item)
    if len(cells or []) > limit:
        out.append({"_truncated_items": len(cells) - limit})
    return out


def _brief_traces(traces: list[Any], limit: int) -> list[dict[str, Any]]:
    out = []
    for trace in (traces or [])[:limit]:
        if not isinstance(trace, dict):
            continue
        out.append({
            key: trace.get(key)
            for key in [
                "evidence_id",
                "report_id",
                "source_type",
                "evidence_role",
                "evidence_report_role",
                "cell_id",
                "chainage",
            ]
            if key in trace
        })
    if len(traces or []) > limit:
        out.append({"_truncated_items": len(traces) - limit})
    return out


def _prompt_json(payload: Any) -> str:
    return json.dumps(_compact_for_prompt(payload), ensure_ascii=False, indent=2, default=str)


def _compact_for_prompt(value: Any, *, depth: int = 0, key_name: str = "") -> Any:
    """Keep experiment prompts reproducible without sending megabyte-scale raw evidence."""
    if depth > 8:
        return "<truncated_depth>"
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {
                "raw_response",
                "llm_response_raw",
                "raw_text",
                "raw_text_excerpt",
                "attrs_json",
                "prompt_text",
                "report_text",
            }:
                continue
            out[key_text] = _compact_for_prompt(item, depth=depth + 1, key_name=key_text)
        return out
    if isinstance(value, list):
        limit = 10 if depth <= 2 else 4
        if key_name in {"source_trace", "local_background", "local_background_cells"}:
            limit = 4
        if key_name in {"key_cells", "selected_cells", "daily_review_cells", "forward_attention_cells"}:
            limit = 8
        compacted = [_compact_for_prompt(item, depth=depth + 1, key_name=key_name) for item in value[:limit]]
        if len(value) > limit:
            compacted.append({"_truncated_items": len(value) - limit})
        return compacted
    if isinstance(value, str):
        if len(value) > 1200:
            return value[:1200].rstrip() + f"...<truncated {len(value) - 1200} chars>"
        return value
    return value


def _boundary_type_counts(boundary: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in boundary.get("violations") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("violation_type") or item.get("type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _high_cell_coverage(report: str, high_grci_cells: list[dict[str, Any]]) -> float | None:
    if not high_grci_cells:
        return None
    mentioned = 0
    for cell in high_grci_cells:
        cell_id = str(cell.get("cell_id") or "")
        start = str(cell.get("cell_start") or "")
        end = str(cell.get("cell_end") or "")
        if (cell_id and cell_id in report) or (start and end and start in report and end in report):
            mentioned += 1
    return mentioned / len(high_grci_cells)


def _mode_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for mode in MODES:
        subset = [row for row in rows if row.get("mode") == mode]
        if not subset:
            continue
        out.append({
            "mode": mode,
            "run_count": len(subset),
            "success_count": sum(1 for row in subset if _as_bool(row.get("generation_success"))),
            "average_quality_score": _mean(row.get("quality_score") for row in subset),
            "average_grounding_rate_effective": _mean(row.get("grounding_rate_effective") for row in subset),
            "unsupported_claim_count_effective_total": sum(_safe_int(row.get("unsupported_claim_count_effective")) for row in subset),
            "boundary_violation_count_total": sum(_safe_int(row.get("boundary_violation_count")) for row in subset),
            "forward_fact_misuse_total": sum(_safe_int(row.get("forward_fact_misuse_count")) for row in subset),
            "grci_probability_misuse_total": sum(_safe_int(row.get("grci_probability_misuse_count")) for row in subset),
            "plc_proxy_misuse_total": sum(_safe_int(row.get("plc_proxy_misuse_count")) for row in subset),
            "stop_causality_misuse_total": sum(_safe_int(row.get("stop_causality_misuse_count")) for row in subset),
            "local_background_scope_misuse_total": sum(_safe_int(row.get("local_background_scope_misuse_count")) for row in subset),
        })
    return out


def _revision_effect_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if rows:
        return rows
    return [{
        "date": None,
        "mode": "M4_full_twin_governance_trace_boundary_reviser",
        "revision_applied": False,
        "pre_revision_boundary_violation_count": None,
        "post_revision_boundary_violation_count": None,
        "pre_revision_unsupported_claim_count_effective": None,
        "post_revision_unsupported_claim_count_effective": None,
        "revision_error_reduction_rate": None,
    }]


def _overall_summary(
    *,
    selected_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    llm_mode: str,
    modes: list[str],
    provider: LLMProvider,
) -> dict[str, Any]:
    return {
        "experiment": "exp02_llm_generation_modes",
        "llm_mode": llm_mode,
        "provider": provider.provider,
        "model": provider.model,
        "selected_date_count": len(selected_rows),
        "selected_dates": [row.get("date") for row in selected_rows],
        "modes": modes,
        "run_count": len(summary_rows),
        "failed_count": len(failures) + sum(1 for row in summary_rows if not _as_bool(row.get("generation_success"))),
        "average_quality_score": _mean(row.get("quality_score") for row in summary_rows),
        "average_grounding_rate_effective": _mean(row.get("grounding_rate_effective") for row in summary_rows),
        "unsupported_claim_count_effective_total": sum(_safe_int(row.get("unsupported_claim_count_effective")) for row in summary_rows),
        "boundary_violation_count_total": sum(_safe_int(row.get("boundary_violation_count")) for row in summary_rows),
        "notes": [
            "Exp02 does not modify the main pipeline.",
            "M0 is template/no-LLM.",
            "M3/M4 use Twin Evidence Pack governance.",
        ],
    }


def _experiment_report(
    *,
    selected_rows: list[dict[str, Any]],
    mode_summary: list[dict[str, Any]],
    revision_summary: list[dict[str, Any]],
    overall: dict[str, Any],
    out_dir: Path,
) -> str:
    return "\n".join([
        "# Exp02: LLM 生成模式对比实验报告",
        "",
        "## 1. 样本日期",
        "",
        _markdown_table(selected_rows),
        "",
        "## 2. 各生成模式输入差异",
        "",
        "- M0_template_only：现有 no-LLM/template 报告。",
        "- M1_direct_llm：仅日期和基础统计，不提供完整 governance。",
        "- M2_raw_evidence_llm：提供粗略 PLC / 地质 / 气体 / 前方摘要，不提供完整 governance。",
        "- M3_twin_evidence_pack_llm：提供 Twin Evidence Pack 和 governance，不自动修订。",
        "- M4_full_twin_governance_trace_boundary_reviser：提供 Twin Evidence Pack，生成后进行 Quality / Trace / Boundary 反馈修订。",
        "",
        "## 3. 模式对比汇总",
        "",
        _markdown_table(mode_summary),
        "",
        "## 4. Revision 效果",
        "",
        _markdown_table(revision_summary),
        "",
        "## 5. 总体结论",
        "",
        f"- LLM 模式：{overall.get('llm_mode')}",
        f"- 运行组合数：{overall.get('run_count')}",
        f"- 失败数：{overall.get('failed_count')}",
        f"- 平均 quality_score：{_fmt(overall.get('average_quality_score'))}",
        f"- 平均 grounding_rate_effective：{_fmt(overall.get('average_grounding_rate_effective'))}",
        f"- effective unsupported claim 总数：{overall.get('unsupported_claim_count_effective_total')}",
        f"- boundary violation 总数：{overall.get('boundary_violation_count_total')}",
        "",
        "## 6. 是否建议进入消融实验",
        "",
        "若 M3/M4 相比 M1/M2 在 unsupported claim、boundary violation 和 trace coverage 上更稳定，则可进入下一阶段消融实验；本实验本身不做消融。",
        "",
        f"输出目录：`{out_dir}`",
    ])


def _failed_summary_row(date: str, mode: str, exc: Exception) -> dict[str, Any]:
    row = {column: None for column in SUMMARY_COLUMNS}
    row.update({
        "date": date,
        "mode": mode,
        "generation_success": False,
        "error_message": str(exc),
    })
    return row


def _failure_row(date: str, mode: str, exc: Exception) -> dict[str, Any]:
    return {
        "date": date,
        "mode": mode,
        "error_message": str(exc),
        "traceback_summary": traceback.format_exc(limit=5),
    }


def _clean_llm_text(text: str) -> str:
    cleaned = str(text or "").strip()
    for prefix in ["好的，以下是", "以下是", "遵照您的要求", "好的，遵照您的指示"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip(" ：:\n\r\t")
    lines = [line.rstrip() for line in cleaned.splitlines() if line.strip() not in {"***", "---"}]
    return "\n".join(lines).strip()


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _mean(values: Any) -> float | None:
    nums = [_safe_float(value) for value in values]
    nums = [value for value in nums if value is not None]
    return sum(nums) / len(nums) if nums else None


def _reduction_rate(before: Any, after: Any) -> float | None:
    before_num = _safe_float(before)
    after_num = _safe_float(after)
    if before_num is None or after_num is None or before_num <= 0:
        return None
    return (before_num - after_num) / before_num


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _fmt(value: Any) -> str:
    num = _safe_float(value)
    if num is None:
        return "null"
    return f"{num:.4f}"


def _markdown_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return "无"
    columns = columns or list(rows[0].keys())
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(row.get(col)) for col in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", " ")[:240]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns:
        pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
