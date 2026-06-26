from __future__ import annotations

import argparse
import json
import math
import re
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from llm.twin_boundary_checker import check_twin_boundary_violations  # noqa: E402
from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from utils.io_utils import get_all_csv_paths  # noqa: E402


REQUIRED_EXPORT_FILES = [
    "daily_construction_twin.json",
    "twin_summary.json",
    "twin_boundary_summary.json",
    "twin_cell_views.json",
    "twin_cell_views.csv",
    "evidence_pack.json",
    "construction_state_cells.json",
    "high_grci_cells.json",
]

PLC_ENHANCED_FIELDS = [
    "speed_mean",
    "thrust_mean",
    "torque_mean",
    "rpm_mean",
    "working_sample_count",
    "working_ratio",
    "insufficient_working_samples",
    "working_speed_cv",
    "working_thrust_cv",
    "working_torque_cv",
    "penetration_mean",
    "cutterhead_power_proxy",
    "thrust_per_penetration",
    "torque_per_penetration",
]
MANUAL_BOUNDARY_TESTS = [
    ("GRCI 表示灾害概率", "grci_probability_misuse"),
    ("PLC 证明前方异常", "forward_fact_misuse"),
    ("cutterhead_power_proxy 是真实功率", "plc_proxy_misuse"),
    ("stop_ratio 说明设备异常", "stop_causality_misuse"),
    ("local_background 证明当日异常", "local_background_scope_misuse"),
    ("GRCI indicates disaster probability", "grci_probability_misuse"),
    ("PLC proves forward abnormal geology", "forward_fact_misuse"),
    ("cutterhead_power_proxy is true physical power", "plc_proxy_misuse"),
    ("stop_ratio proves equipment failure", "stop_causality_misuse"),
    ("local background proves today's abnormal condition", "local_background_scope_misuse"),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run exp01: full-date no-LLM DailyConstructionTwin stability and coverage experiment."
    )
    parser.add_argument("--dates", help="Optional comma-separated dates. Default: all PLC dates.")
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parent / "outputs"),
        help="Experiment output directory.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    date_export_dir = out_dir / "date_exports"
    date_export_dir.mkdir(parents=True, exist_ok=True)

    dates = _parse_dates(args.dates) if args.dates else _discover_dates()
    if not dates:
        raise SystemExit("No PLC dates found.")

    run_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    role_rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    unsupported_claim_rows: list[dict[str, Any]] = []
    review_metric_values: dict[str, list[Any]] = {field: [] for field in PLC_ENHANCED_FIELDS}
    review_metric_contexts: list[dict[str, Any]] = []
    boundary_type_counts: dict[str, int] = {}

    for idx, date in enumerate(dates, start=1):
        print(f"[exp01] {idx}/{len(dates)} running {date}")
        try:
            result = run_daily_report_pipeline(
                date,
                use_llm=False,
                generation_mode="template",
            )
            cells = [cell.model_dump() for cell in result.construction_state_cells]
            twin_cells = (result.daily_construction_twin or {}).get("cells", [])
            daily_review_cells = [
                item for item in cells
                if item.get("cell_role") == "daily_review" or item.get("is_excavated_today")
            ]
            _export_date_outputs(date_export_dir / date, result, cells, twin_cells)

            missing_exports = [
                name for name in REQUIRED_EXPORT_FILES
                if not (date_export_dir / date / name).exists()
            ]
            twin_boundary = result.twin_boundary_summary or {}
            for violation in twin_boundary.get("violations", []) or []:
                vtype = violation.get("violation_type") or violation.get("type") or "unknown"
                boundary_type_counts[vtype] = boundary_type_counts.get(vtype, 0) + 1

            role_check = _build_role_boundary_row(date, result, cells)
            role_rows.append(role_check)
            unsupported_claim_rows.extend(_extract_unsupported_claim_rows(date, result))

            for cell in daily_review_cells:
                metric_row = {"date": date, "cell_id": cell.get("cell_id")}
                for field in PLC_ENHANCED_FIELDS:
                    value = _cell_metric(cell, field)
                    metric_row[field] = value
                    review_metric_values[field].append(value)
                review_metric_contexts.append(metric_row)

            run_row = {
                "date": date,
                "pipeline_success": True,
                "construction_state_cells_count": len(cells),
                "daily_review_cells_count": sum(1 for item in cells if item.get("cell_role") == "daily_review"),
                "forward_attention_cells_count": sum(1 for item in cells if item.get("cell_role") == "forward_attention"),
                "local_background_cells_count": sum(1 for item in cells if item.get("cell_role") == "local_background"),
                "high_grci_cells_count": len(result.high_grci_cells),
                "grci_available_count": sum(1 for item in cells if item.get("GRCI_available")),
                "twin_export_success": not missing_exports,
                "missing_export_files": ";".join(missing_exports),
                "evidence_pack_source": result.prompt_evidence_pack.get("evidence_pack_source"),
                "twin_boundary_has_violation": bool(twin_boundary.get("has_violation")),
                "twin_boundary_violation_count": int(twin_boundary.get("violation_count") or 0),
                "violation_types": ";".join(sorted({
                    (item.get("violation_type") or item.get("type") or "unknown")
                    for item in twin_boundary.get("violations", []) or []
                })),
                "quality_score": result.quality_summary.get("quality_score"),
                "grounding_rate": result.quality_summary.get("grounding_rate"),
                "unsupported_claim_count": result.quality_summary.get("unsupported_claim_count"),
                "forward_cell_entered_high_grci_cells": bool(role_check["high_grci_forward_cell_count"]),
                "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count": _error_count(result, "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE"),
                "warnings": ";".join(str(item) for item in result.warnings),
            }
            run_rows.append(run_row)
            coverage_rows.append({
                key: run_row[key]
                for key in [
                    "date",
                    "pipeline_success",
                    "construction_state_cells_count",
                    "daily_review_cells_count",
                    "forward_attention_cells_count",
                    "local_background_cells_count",
                    "high_grci_cells_count",
                    "grci_available_count",
                    "twin_export_success",
                    "evidence_pack_source",
                    "twin_boundary_violation_count",
                    "quality_score",
                    "grounding_rate",
                    "unsupported_claim_count",
                ]
            })
        except Exception as exc:
            traceback_summary = traceback.format_exc(limit=5)
            failed = {
                "date": date,
                "pipeline_success": False,
                "error": str(exc),
                "traceback_summary": traceback_summary,
            }
            print(f"[exp01] failed {date}: {exc}")
            run_rows.append(failed)
            failed_rows.append(failed)

    manual_rows = _run_manual_boundary_tests()
    plc_coverage_rows, plc_extra_summary = _build_plc_coverage_rows(
        review_metric_values,
        review_metric_contexts,
    )

    summary = _build_overall_summary(run_rows, role_rows)
    unsupported_audit_rows = _build_unsupported_claim_audit_rows(out_dir, unsupported_claim_rows)
    previous_summary = _load_previous_overall_summary(out_dir)
    raw_unsupported_count = _safe_int(
        previous_summary.get("unsupported_claim_count_total"),
        default=sum(int(row.get("count") or 0) for row in unsupported_audit_rows),
    )
    heading_false_positive_count = sum(
        int(row.get("count") or 0)
        for row in unsupported_audit_rows
        if _is_heading_fragment_false_positive(row.get("claim_text"))
        or row.get("error_type") == "E11_HEADING_FALSE_POSITIVE"
    )
    summary.update(
        {
            "unsupported_claim_count_total_raw": raw_unsupported_count,
            "unsupported_claim_count_total_effective": summary.get("unsupported_claim_count_total"),
            "heading_fragment_false_positive_count": heading_false_positive_count,
            "average_grounding_rate_raw": previous_summary.get(
                "average_grounding_rate",
                summary.get("average_grounding_rate"),
            ),
            "average_grounding_rate_effective": summary.get("average_grounding_rate"),
        }
    )
    report_text = _build_report(
        summary=summary,
        run_rows=run_rows,
        plc_coverage_rows=plc_coverage_rows,
        plc_extra_summary=plc_extra_summary,
        role_rows=role_rows,
        manual_rows=manual_rows,
        failed_rows=failed_rows,
        unsupported_claim_rows=unsupported_claim_rows,
        boundary_type_counts=boundary_type_counts,
        out_dir=out_dir,
    )

    _write_csv(out_dir / "exp01_daily_run_summary.csv", run_rows)
    _write_text(out_dir / "exp01_daily_run_summary.md", _markdown_table(run_rows))
    _write_csv(out_dir / "exp01_twin_coverage_summary.csv", coverage_rows)
    _write_csv(out_dir / "exp01_plc_enhanced_metrics_coverage.csv", plc_coverage_rows)
    _write_csv(out_dir / "exp01_plc_enhanced_metrics_extra_summary.csv", plc_extra_summary)
    _write_csv(out_dir / "exp01_role_boundary_check.csv", role_rows)
    _write_csv(out_dir / "exp01_boundary_checker_manual_tests.csv", manual_rows)
    _write_csv(out_dir / "exp01_failed_dates.csv", failed_rows)
    _write_csv(out_dir / "exp01_unsupported_claim_samples.csv", unsupported_claim_rows)
    _write_csv(out_dir / "exp01_unsupported_claim_audit.csv", unsupported_audit_rows)
    _write_text(out_dir / "exp01_unsupported_claim_audit.md", _markdown_table(unsupported_audit_rows))
    _write_csv(out_dir / "exp01_effective_unsupported_claim_samples.csv", unsupported_claim_rows)
    _write_json(out_dir / "exp01_overall_summary.json", summary)
    _write_text(out_dir / "exp01_experiment_report.md", report_text)

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"[exp01] outputs: {out_dir}")


def _discover_dates() -> list[str]:
    dates = []
    for path in get_all_csv_paths():
        name = path.name.replace("tbm_data_", "").replace(".csv", "")
        if len(name) == 8 and name.isdigit():
            dates.append(f"{name[:4]}-{name[4:6]}-{name[6:8]}")
    return sorted(dict.fromkeys(dates))


def _parse_dates(raw: str | None) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _export_date_outputs(target: Path, result: Any, cells: list[dict[str, Any]], twin_cells: list[dict[str, Any]]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    _write_json(target / "daily_construction_twin.json", result.daily_construction_twin)
    _write_json(target / "twin_summary.json", result.twin_summary)
    _write_json(target / "twin_boundary_summary.json", result.twin_boundary_summary)
    _write_json(target / "twin_cell_views.json", twin_cells)
    _write_csv(target / "twin_cell_views.csv", [_csv_safe(dict(row)) for row in twin_cells])
    _write_json(target / "evidence_pack.json", result.prompt_evidence_pack)
    _write_json(target / "construction_state_cells.json", cells)
    _write_json(target / "high_grci_cells.json", result.high_grci_cells)
    _write_json(target / "quality_summary.json", result.quality_summary)
    _write_json(target / "trace_summary.json", result.trace_summary)
    _write_json(target / "method_metrics.json", result.method_metrics)


def _build_role_boundary_row(date: str, result: Any, cells: list[dict[str, Any]]) -> dict[str, Any]:
    forward_cells = [
        item for item in cells
        if item.get("cell_role") == "forward_attention" or item.get("is_forward_cell")
    ]
    local_background_cells = [
        item for item in cells
        if item.get("cell_role") == "local_background"
    ]
    high_cells = result.high_grci_cells or []
    forward_ids = {item.get("cell_id") for item in forward_cells}
    local_ids = {item.get("cell_id") for item in local_background_cells}
    high_ids = {item.get("cell_id") for item in high_cells}
    forward_grci_non_null = [
        item.get("cell_id") for item in forward_cells
        if item.get("GRCI") is not None
    ]
    forward_grci_available = [
        item.get("cell_id") for item in forward_cells
        if item.get("GRCI_available") is True
    ]
    high_forward = sorted(str(item) for item in (high_ids & forward_ids) if item)
    local_in_high = sorted(str(item) for item in (high_ids & local_ids) if item)
    forward_pack_plc_count = _forward_pack_plc_metric_count(result.prompt_evidence_pack)
    return {
        "date": date,
        "forward_attention_grci_non_null_count": len(forward_grci_non_null),
        "forward_attention_grci_available_true_count": len(forward_grci_available),
        "forward_attention_evidence_pack_plc_enhanced_metrics_count": forward_pack_plc_count,
        "high_grci_forward_cell_count": len(high_forward),
        "local_background_in_high_grci_count": len(local_in_high),
        "forward_grci_non_null_cell_ids": ";".join(str(item) for item in forward_grci_non_null if item),
        "forward_grci_available_cell_ids": ";".join(str(item) for item in forward_grci_available if item),
        "high_grci_forward_cell_ids": ";".join(high_forward),
        "local_background_high_grci_cell_ids": ";".join(local_in_high),
        "passed": (
            len(forward_grci_non_null) == 0
            and len(forward_grci_available) == 0
            and forward_pack_plc_count == 0
            and len(high_forward) == 0
            and len(local_in_high) == 0
        ),
    }


def _forward_pack_plc_metric_count(evidence_pack: dict[str, Any]) -> int:
    forward_payload = {
        key: value for key, value in (evidence_pack or {}).items()
        if "forward" in str(key).lower()
    }
    return _count_non_null_plc_metrics(forward_payload)


def _count_non_null_plc_metrics(value: Any) -> int:
    if isinstance(value, dict):
        count = 0
        for key, item in value.items():
            if key in PLC_ENHANCED_FIELDS and _is_non_null(item):
                count += 1
            count += _count_non_null_plc_metrics(item)
        return count
    if isinstance(value, list):
        return sum(_count_non_null_plc_metrics(item) for item in value)
    return 0


def _error_count(result: Any, error_type: str) -> int:
    quality_counts = (result.quality or {}).get("error_type_counts") or {}
    return int(quality_counts.get(error_type) or 0)


def _cell_metric(cell: dict[str, Any], field: str) -> Any:
    if field in cell:
        return cell.get(field)
    plc_metrics = cell.get("plc_metrics") if isinstance(cell.get("plc_metrics"), dict) else {}
    return plc_metrics.get(field)


def _build_plc_coverage_rows(
    values_by_field: dict[str, list[Any]],
    metric_contexts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total = len(metric_contexts)
    rows = []
    for field, values in values_by_field.items():
        non_null_values = [value for value in values if _is_non_null(value)]
        numeric_values = [_to_float(value) for value in non_null_values]
        numeric_values = [value for value in numeric_values if value is not None]
        rows.append({
            "field": field,
            "non_null_cell_count": len(non_null_values),
            "total_daily_review_cell_count": total,
            "coverage_rate": (len(non_null_values) / total) if total else None,
            "mean": _series_stat(numeric_values, "mean"),
            "median": _series_stat(numeric_values, "median"),
            "min": _series_stat(numeric_values, "min"),
            "max": _series_stat(numeric_values, "max"),
            "p25": _series_stat(numeric_values, "p25"),
            "p75": _series_stat(numeric_values, "p75"),
        })

    insufficient_cells = [
        row for row in metric_contexts
        if row.get("insufficient_working_samples") is True
    ]
    insufficient_dates = sorted({row.get("date") for row in insufficient_cells if row.get("date")})
    motion_fields = ["speed_mean", "thrust_mean", "torque_mean", "rpm_mean"]
    dates = sorted({row.get("date") for row in metric_contexts if row.get("date")})
    all_null_dates = []
    for date in dates:
        rows_for_date = [row for row in metric_contexts if row.get("date") == date]
        if rows_for_date and all(not _is_non_null(row.get(field)) for row in rows_for_date for field in motion_fields):
            all_null_dates.append(date)

    penetration_null_reason_count = {
        "penetration_mean_null": sum(1 for row in metric_contexts if not _is_non_null(row.get("penetration_mean"))),
        "thrust_per_penetration_null": sum(1 for row in metric_contexts if not _is_non_null(row.get("thrust_per_penetration"))),
        "torque_per_penetration_null": sum(1 for row in metric_contexts if not _is_non_null(row.get("torque_per_penetration"))),
    }
    extra_summary = [
        {"metric": "insufficient_working_samples_cell_count", "value": len(insufficient_cells)},
        {"metric": "insufficient_working_samples_date_count", "value": len(insufficient_dates)},
        {"metric": "insufficient_working_samples_dates", "value": ";".join(insufficient_dates)},
        {"metric": "motion_fields_all_null_date_count", "value": len(all_null_dates)},
        {"metric": "motion_fields_all_null_dates", "value": ";".join(all_null_dates)},
        {
            "metric": "penetration_ratio_null_reason_count",
            "value": json.dumps(penetration_null_reason_count, ensure_ascii=False),
        },
    ]
    return rows, extra_summary


def _run_manual_boundary_tests() -> list[dict[str, Any]]:
    rows = []
    for sentence, expected in MANUAL_BOUNDARY_TESTS:
        result = check_twin_boundary_violations(sentence)
        violations = result.get("violations") or []
        detected_types = [
            item.get("violation_type") or item.get("type") or ""
            for item in violations
        ]
        rows.append({
            "test_sentence": sentence,
            "expected_violation_type": expected,
            "detected": expected in detected_types,
            "detected_type": ";".join(detected_types),
            "matched_text": ";".join(str(item.get("matched_text") or "") for item in violations),
        })
    return rows


def _extract_unsupported_claim_rows(date: str, result: Any) -> list[dict[str, Any]]:
    rows = []
    quality = result.quality or {}
    trace = result.trace or {}
    for claim in quality.get("claim_results", []) or []:
        if claim.get("grounded") is not False:
            continue
        rows.append({
            "date": date,
            "claim_id": claim.get("claim_id"),
            "claim_text": claim.get("claim_text"),
            "claim_type": claim.get("claim_type"),
            "section": claim.get("section") or "",
            "reason": "; ".join(str(item) for item in claim.get("messages", []) or [])
            or claim.get("error_type")
            or claim.get("severity")
            or "unsupported_by_quality_checker",
            "source": "quality.claim_results",
            "matched_evidence_count": len(claim.get("supporting_evidence_ids") or []),
            "available_trace_keys": ";".join(sorted(str(key) for key in claim.keys())),
            "support_type": claim.get("support_type"),
            "trace_support_type": claim.get("trace_support_type"),
            "error_type": claim.get("error_type"),
        })
    traced_seen = {row.get("claim_id") for row in rows if row.get("claim_id")}
    for claim in trace.get("traced_claims", []) or []:
        if claim.get("grounded") is not False or claim.get("claim_id") in traced_seen:
            continue
        rows.append({
            "date": date,
            "claim_id": claim.get("claim_id"),
            "claim_text": claim.get("claim_text"),
            "claim_type": claim.get("claim_type"),
            "section": claim.get("section") or "",
            "reason": claim.get("support_note") or "unsupported_by_trace",
            "source": "trace.traced_claims",
            "matched_evidence_count": len(claim.get("supporting_evidence_ids") or []),
            "available_trace_keys": ";".join(sorted(str(key) for key in claim.keys())),
            "support_type": claim.get("support_type"),
            "trace_support_type": claim.get("trace_support_type"),
            "error_type": claim.get("error_type"),
        })
    if not rows and int((result.quality_summary or {}).get("unsupported_claim_count") or 0) > 0:
        rows.append({
            "date": date,
            "claim_text": "",
            "reason": "quality_summary reports unsupported claims but detailed claim_results did not expose grounded=false rows",
            "source": "quality_summary",
            "matched_evidence_count": "",
            "available_trace_keys": "",
        })
    return rows


def _build_unsupported_claim_audit_rows(out_dir: Path, current_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_rows = _load_previous_unsupported_samples(out_dir)
    if not source_rows:
        source_rows = current_rows
    grouped: dict[tuple[str, str, str, str], int] = {}
    for row in source_rows:
        key = (
            str(row.get("claim_text") or ""),
            str(row.get("error_type") or ""),
            str(row.get("source") or ""),
            str(row.get("date") or ""),
        )
        grouped[key] = grouped.get(key, 0) + 1
    return [
        {
            "claim_text": claim_text,
            "error_type": error_type,
            "source": source,
            "date": date,
            "count": count,
            "is_heading_fragment_false_positive": _is_heading_fragment_false_positive(claim_text)
            or error_type == "E11_HEADING_FALSE_POSITIVE",
        }
        for (claim_text, error_type, source, date), count in sorted(
            grouped.items(),
            key=lambda item: (-item[1], item[0][0], item[0][3]),
        )
    ]


def _load_previous_unsupported_samples(out_dir: Path) -> list[dict[str, Any]]:
    previous = out_dir.parent / "outputs_fix01" / "exp01_unsupported_claim_samples.csv"
    if not previous.exists():
        return []
    return pd.read_csv(previous).fillna("").to_dict(orient="records")


def _load_previous_overall_summary(out_dir: Path) -> dict[str, Any]:
    previous = out_dir.parent / "outputs_fix01" / "exp01_overall_summary.json"
    if not previous.exists():
        return {}
    try:
        return json.loads(previous.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_heading_fragment_false_positive(value: Any) -> bool:
    text = "" if value is None else str(value)
    text = text.strip().strip("。；;，,：:")
    patterns = [
        r"^涉及气体为[:：]?\s*无$",
        r"^涉及气体[:：]\s*无$",
        r"^气体为[:：]?\s*无$",
        r"^气体[:：]\s*无$",
    ]
    return any(re.match(pattern, text) for pattern in patterns)


def _build_overall_summary(run_rows: list[dict[str, Any]], role_rows: list[dict[str, Any]]) -> dict[str, Any]:
    success_rows = [row for row in run_rows if row.get("pipeline_success") is True]
    failed_rows = [row for row in run_rows if row.get("pipeline_success") is not True]
    quality_values = [_to_float(row.get("quality_score")) for row in success_rows]
    grounding_values = [_to_float(row.get("grounding_rate")) for row in success_rows]
    quality_values = [value for value in quality_values if value is not None]
    grounding_values = [value for value in grounding_values if value is not None]
    return {
        "total_dates": len(run_rows),
        "success_count": len(success_rows),
        "failed_count": len(failed_rows),
        "success_rate": (len(success_rows) / len(run_rows)) if run_rows else 0,
        "average_quality_score": _series_stat(quality_values, "mean"),
        "average_grounding_rate": _series_stat(grounding_values, "mean"),
        "unsupported_claim_count_total": sum(int(row.get("unsupported_claim_count") or 0) for row in success_rows),
        "forward_cell_entered_high_grci_cells_count": sum(
            int(bool(row.get("forward_cell_entered_high_grci_cells"))) for row in success_rows
        ),
        "twin_boundary_violation_count_total": sum(
            int(row.get("twin_boundary_violation_count") or 0) for row in success_rows
        ),
        "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count": sum(
            int(row.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count") or 0) for row in success_rows
        ),
        "role_boundary_failed_count": sum(1 for row in role_rows if not row.get("passed")),
    }


def _build_report(
    *,
    summary: dict[str, Any],
    run_rows: list[dict[str, Any]],
    plc_coverage_rows: list[dict[str, Any]],
    plc_extra_summary: list[dict[str, Any]],
    role_rows: list[dict[str, Any]],
    manual_rows: list[dict[str, Any]],
    failed_rows: list[dict[str, Any]],
    unsupported_claim_rows: list[dict[str, Any]],
    boundary_type_counts: dict[str, int],
    out_dir: Path,
) -> str:
    failed_text = "无" if not failed_rows else "\n".join(
        f"- {row.get('date')}: {row.get('error')}" for row in failed_rows
    )
    role_failed = [row for row in role_rows if not row.get("passed")]
    role_text = (
        "全部通过，未发现 forward/local background 越界进入 high GRCI，"
        "也未发现 forward Evidence Pack 携带 PLC enhanced metrics。"
        if not role_failed
        else "\n".join(f"- {row.get('date')}: {row}" for row in role_failed)
    )
    manual_failed = [row for row in manual_rows if not row.get("detected")]
    manual_text = (
        "全部人工违规句均命中预期类型。"
        if not manual_failed
        else "\n".join(
            f"- {row.get('test_sentence')}: expected={row.get('expected_violation_type')}, "
            f"detected={row.get('detected_type')}"
            for row in manual_failed
        )
    )
    return "\n".join([
        "# Exp01: 91 天全量稳定性实验与 DailyConstructionTwin 覆盖统计",
        "",
        "## 1. 实验目的",
        "",
        "本实验验证当前 no-LLM/template 主流程在全部可用 PLC 日期上的稳定性，并统计 DailyConstructionTwin、Evidence Pack from Twin、Quality/Trace、Twin Boundary Checker 与 PLC enhanced metrics 的覆盖情况。",
        "",
        "## 2. 总体结果",
        "",
        f"- 总日期数：{summary.get('total_dates')}",
        f"- 成功日期数：{summary.get('success_count')}",
        f"- 失败日期数：{summary.get('failed_count')}",
        f"- 成功率：{_fmt(summary.get('success_rate'))}",
        f"- 平均 quality_score：{_fmt(summary.get('average_quality_score'))}",
        f"- 平均 grounding_rate：{_fmt(summary.get('average_grounding_rate'))}",
        f"- unsupported_claim_count_total：{summary.get('unsupported_claim_count_total')}",
        f"- unsupported_claim_count_total_raw：{summary.get('unsupported_claim_count_total_raw')}",
        f"- heading_fragment_false_positive_count：{summary.get('heading_fragment_false_positive_count')}",
        f"- unsupported_claim_count_total_effective：{summary.get('unsupported_claim_count_total_effective')}",
        f"- average_grounding_rate_raw：{_fmt(summary.get('average_grounding_rate_raw'))}",
        f"- average_grounding_rate_effective：{_fmt(summary.get('average_grounding_rate_effective'))}",
        f"- E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count：{summary.get('E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count')}",
        "",
        "## 3. DailyConstructionTwin 导出情况",
        "",
        "每个成功日期均检查 daily_construction_twin.json、twin_summary.json、twin_boundary_summary.json、twin_cell_views.json/csv、evidence_pack.json、construction_state_cells.json 和 high_grci_cells.json 是否导出。详见 exp01_twin_coverage_summary.csv。",
        "",
        "## 4. Evidence Pack from Twin 覆盖情况",
        "",
        "字段 evidence_pack_source 用于确认 Evidence Pack 来源是否为 DailyConstructionTwin。详见 exp01_twin_coverage_summary.csv。",
        "",
        "## 5. PLC enhanced metrics 覆盖率",
        "",
        "PLC enhanced metrics 只在 daily_review cells 中统计；所有 proxy 字段仅表示施工响应证据，不解释为真实物理功率、严格比能或地质风险判断。覆盖率见 exp01_plc_enhanced_metrics_coverage.csv，补充汇总见 exp01_plc_enhanced_metrics_extra_summary.csv。",
        "",
        "## 6. 证据角色边界检查",
        "",
        role_text,
        "",
        "## 7. Twin Boundary Checker 结果",
        "",
        f"- 模板报告 boundary violation 总数：{summary.get('twin_boundary_violation_count_total')}",
        f"- 违规类型计数：{json.dumps(boundary_type_counts, ensure_ascii=False)}",
        f"- 人工违规句测试：{manual_text}",
        "",
        "## 8. 失败日期和原因",
        "",
        failed_text,
        "",
        "## 8.1 Unsupported Claim 样本",
        "",
        f"本次 effective unsupported claim 样本 {len(unsupported_claim_rows)} 条，详见 exp01_unsupported_claim_samples.csv。原始 fix01 unsupported claim 审计见 exp01_unsupported_claim_audit.csv / .md。本轮仅修正 heading / fragment false positive 的统计口径，不放宽真实工程 claim。",
        "",
        "## 9. 是否支撑进入后续 LLM 对比实验",
        "",
        "如果本实验成功率、Evidence Pack from Twin 覆盖和证据角色边界检查均满足预期，则当前结果可以支撑进入下一阶段 LLM 生成模式对比、消融实验和典型日期 case study。",
        "",
        "## 10. 输出文件",
        "",
        f"实验输出目录：`{out_dir}`",
        "",
        "主要统计文件：",
        "",
        "- exp01_daily_run_summary.csv / .md",
        "- exp01_twin_coverage_summary.csv",
        "- exp01_plc_enhanced_metrics_coverage.csv",
        "- exp01_role_boundary_check.csv",
        "- exp01_boundary_checker_manual_tests.csv",
        "- exp01_failed_dates.csv",
        "- exp01_unsupported_claim_audit.csv / .md",
        "- exp01_effective_unsupported_claim_samples.csv",
    ])


def _is_non_null(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if pd.isna(value):
        return False
    return True


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _series_stat(values: list[float], stat: str) -> float | None:
    if not values:
        return None
    series = pd.Series(values, dtype=float)
    if stat == "mean":
        return float(series.mean())
    if stat == "median":
        return float(series.median())
    if stat == "min":
        return float(series.min())
    if stat == "max":
        return float(series.max())
    if stat == "p25":
        return float(series.quantile(0.25))
    if stat == "p75":
        return float(series.quantile(0.75))
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([_csv_safe(row) for row in rows]).to_csv(path, index=False, encoding="utf-8-sig")


def _csv_safe(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple, set)):
            out[key] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            out[key] = value
    return out


def _markdown_table(rows: list[dict[str, Any]], max_rows: int = 120) -> str:
    if not rows:
        return "_鏃犺褰昣\n"
    columns = list(dict.fromkeys(key for row in rows for key in row.keys()))
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows[:max_rows]:
        lines.append("| " + " | ".join(_markdown_cell(row.get(col)) for col in columns) + " |")
    if len(rows) > max_rows:
        lines.append(f"\n_浠呭睍绀哄墠 {max_rows} 琛岋紝鍏?{len(rows)} 琛屻€俖\n")
    return "\n".join(lines) + "\n"


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text[:300] + "..." if len(text) > 300 else text


def _fmt(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "NA"
    return f"{number:.4f}"


if __name__ == "__main__":
    main()
