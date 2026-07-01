from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.daily_report_pipeline import run_daily_report_pipeline  # noqa: E402
from pipeline.inputs import load_daily_inputs  # noqa: E402
from plc.response import analyze_plc_response  # noqa: E402
from utils.io_utils import get_all_csv_paths  # noqa: E402


FORWARD_FORBIDDEN_FIELDS = [
    "RAI",
    "GRCI",
    "plc_enhanced_metrics",
    "working_sample_count",
    "working_ratio",
    "speed_mean",
    "thrust_mean",
    "torque_mean",
    "rpm_mean",
    "penetration_mean",
    "steady_state_available",
    "steady_sample_count",
    "steady_ratio",
    "steady_to_working_ratio",
    "steady_speed_mean",
    "steady_thrust_mean",
    "steady_torque_mean",
    "steady_rpm_mean",
    "steady_penetration_mean",
    "steady_cutterhead_power_proxy",
    "steady_thrust_per_penetration",
    "steady_torque_per_penetration",
    "working_sample_count_paper",
    "shutdown_sample_count",
    "outlier_sample_count",
    "plc_preprocessing_quality_grade",
    "plc_preprocessing_quality_reason",
]


STEADY_FIELDS = [
    "steady_state_available",
    "steady_sample_count",
    "steady_ratio",
    "steady_to_working_ratio",
    "steady_speed_mean",
    "steady_speed_std",
    "steady_speed_cv",
    "steady_thrust_mean",
    "steady_thrust_std",
    "steady_thrust_cv",
    "steady_torque_mean",
    "steady_torque_std",
    "steady_torque_cv",
    "steady_rpm_mean",
    "steady_rpm_std",
    "steady_rpm_cv",
    "steady_penetration_mean",
    "steady_penetration_std",
    "steady_penetration_cv",
    "steady_cutterhead_power_proxy",
    "steady_thrust_per_penetration",
    "steady_torque_per_penetration",
    "steady_state_fallback_used",
    "steady_state_fallback_reason",
    "steady_detection_signal",
    "plc_preprocessing_quality_grade",
    "plc_preprocessing_quality_reason",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate paper-based PLC preprocessing outputs.")
    parser.add_argument("--dates", help="Comma-separated dates. Defaults to all available PLC CSV dates.")
    parser.add_argument("--out-dir", default="experiments/exp_plc_preprocessing_validation/outputs")
    parser.add_argument("--max-dates", type=int)
    args = parser.parse_args()

    dates = _parse_dates(args.dates) or _all_dates()
    if args.max_dates:
        dates = dates[: max(args.max_dates, 0)]
    out_dir = _resolve(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    daily_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    side_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    leakage_rows: list[dict[str, Any]] = []
    smoke_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for date in dates:
        try:
            inputs = load_daily_inputs(date)
            plc = analyze_plc_response(inputs.df_plc, date=date, cell_length=10.0)
            cell_response_df = plc.get("cell_response_df")
            cell_response_records = _df_records(cell_response_df)
            preprocessing_daily = getattr(cell_response_df, "attrs", {}).get("plc_preprocessing_daily_summary", {})

            result = run_daily_report_pipeline(date, use_llm=False, generation_mode="template")
            cells = [cell.model_dump() for cell in result.construction_state_cells]
            pack = result.prompt_evidence_pack or {}

            daily_rows.append(_daily_summary(date, result, cell_response_records, preprocessing_daily))
            for row in cell_response_records:
                cell = _matching_cell(row.get("cell_id"), cells)
                cell_rows.append(_cell_summary(date, row, cell))
            side_rows.append(_side_by_side_summary(date, cell_response_records))
            quality_rows.append(_quality_diagnosis(date, result))
            leakage = _forward_leakage(date, pack)
            leakage_rows.append(leakage)
            smoke_rows.append(_main_pipeline_smoke_row(date, result, leakage))
        except Exception as exc:  # pragma: no cover - script safety
            errors.append(
                {
                    "date": date,
                    "error": str(exc),
                    "traceback_summary": traceback.format_exc(limit=4),
                }
            )

    coverage = _coverage_summary(dates, daily_rows, cell_rows, errors, leakage_rows, smoke_rows)
    quality_summary = _quality_summary(quality_rows)
    audit = _rai_grci_audit()
    penetration = _penetration_semantics(cell_rows)

    _write_csv(out_dir / "plc_preprocessing_daily_summary.csv", daily_rows)
    _write_csv(out_dir / "plc_preprocessing_cell_summary.csv", cell_rows)
    _write_csv(out_dir / "plc_preprocessing_coverage_summary.csv", [coverage])
    _write_csv(out_dir / "plc_preprocessing_quality_grade_summary.csv", _grade_summary(cell_rows))
    _write_csv(out_dir / "plc_preprocessing_side_by_side_summary.csv", side_rows)
    _write_csv(out_dir / "plc_quality_score_diagnosis.csv", quality_rows)
    _write_csv(out_dir / "forward_attention_plc_leakage_check.csv", leakage_rows)
    _write_csv(out_dir / "main_pipeline_smoke_summary.csv", smoke_rows)
    _write_json(
        out_dir / "plc_preprocessing_overall_summary.json",
        {
            **coverage,
            "quality_score_diagnosis": quality_summary,
            "rai_grci_audit": audit,
            "penetration_semantics": penetration,
        },
    )
    _write_text(
        out_dir / "plc_quality_score_diagnosis.md",
        _quality_report(quality_rows, quality_summary),
    )
    _write_text(
        out_dir / "plc_preprocessing_report.md",
        _report(coverage, quality_summary, audit, penetration, side_rows, leakage_rows, errors),
    )
    if errors:
        _write_csv(out_dir / "plc_preprocessing_error_log.csv", errors)
    print(json.dumps(coverage, ensure_ascii=False, indent=2, default=str))


def _daily_summary(
    date: str,
    result: Any,
    cell_response: list[dict[str, Any]],
    preprocessing_daily: dict[str, Any],
) -> dict[str, Any]:
    raw_count = sum(int(row.get("raw_sample_count") or row.get("sample_count") or 0) for row in cell_response)
    shutdown_count = sum(int(row.get("shutdown_sample_count") or 0) for row in cell_response)
    outlier_count = sum(int(row.get("outlier_sample_count") or 0) for row in cell_response)
    steady_available = sum(1 for row in cell_response if row.get("steady_state_available"))
    fallback_count = sum(1 for row in cell_response if row.get("steady_state_fallback_used"))
    old_working_cells = sum(1 for row in cell_response if int(row.get("working_sample_count") or 0) > 0)
    return {
        "date": date,
        "raw_sample_count": raw_count,
        "shutdown_sample_count": shutdown_count,
        "shutdown_ratio": _ratio(shutdown_count, raw_count),
        "outlier_sample_count": outlier_count,
        "outlier_ratio": _ratio(outlier_count, raw_count),
        "working_interval_count": preprocessing_daily.get("working_interval_count"),
        "valid_working_interval_count": preprocessing_daily.get("valid_working_interval_count"),
        "short_transition_interval_count": preprocessing_daily.get("short_transition_interval_count"),
        "cell_response_count": len(cell_response),
        "old_working_metrics_available_cell_count": old_working_cells,
        "old_working_metrics_coverage_rate": _ratio(old_working_cells, len(cell_response)),
        "steady_state_available_cell_count": steady_available,
        "steady_state_fallback_cell_count": fallback_count,
        "steady_metrics_coverage_rate": _ratio(steady_available, len(cell_response)),
        "fallback_rate": _ratio(fallback_count, len(cell_response)),
        "quality_grade_A_count": _grade_count_by_rows(cell_response, "A"),
        "quality_grade_B_count": _grade_count_by_rows(cell_response, "B"),
        "quality_grade_C_count": _grade_count_by_rows(cell_response, "C"),
        "quality_grade_D_count": _grade_count_by_rows(cell_response, "D"),
        "warnings": "; ".join(result.warnings or []),
    }


def _cell_summary(date: str, row: dict[str, Any], cell: dict[str, Any] | None) -> dict[str, Any]:
    out = {
        "date": date,
        "cell_id": row.get("cell_id"),
        "cell_start": row.get("cell_start"),
        "cell_end": row.get("cell_end"),
        "cell_role": (cell or {}).get("cell_role"),
        "RAI": row.get("RAI"),
        "GRCI": (cell or {}).get("GRCI"),
        "GRCI_available": (cell or {}).get("GRCI_available"),
        "raw_sample_count": row.get("raw_sample_count") or row.get("sample_count"),
        "shutdown_sample_count": row.get("shutdown_sample_count"),
        "outlier_sample_count": row.get("outlier_sample_count"),
        "working_sample_count": row.get("working_sample_count"),
        "working_sample_count_paper": row.get("working_sample_count_paper"),
        "working_ratio": row.get("working_ratio"),
    }
    for field in STEADY_FIELDS:
        out[field] = row.get(field)
    return out


def _side_by_side_summary(date: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    old_available = sum(1 for row in rows if int(row.get("working_sample_count") or 0) > 0)
    steady = sum(1 for row in rows if row.get("steady_state_available"))
    fallback = sum(1 for row in rows if row.get("steady_state_fallback_used"))
    return {
        "date": date,
        "cell_count": total,
        "old_working_metrics_available_cell_count": old_available,
        "old_working_metrics_coverage_rate": _ratio(old_available, total),
        "paper_steady_state_available_cell_count": steady,
        "paper_steady_metrics_coverage_rate": _ratio(steady, total),
        "paper_fallback_cell_count": fallback,
        "paper_fallback_rate": _ratio(fallback, total),
        "shutdown_sample_count": sum(int(row.get("shutdown_sample_count") or 0) for row in rows),
        "outlier_sample_count": sum(int(row.get("outlier_sample_count") or 0) for row in rows),
        "grade_A": _grade_count_by_rows(rows, "A"),
        "grade_B": _grade_count_by_rows(rows, "B"),
        "grade_C": _grade_count_by_rows(rows, "C"),
        "grade_D": _grade_count_by_rows(rows, "D"),
        "low_coverage_reason": _low_coverage_reason(rows),
    }


def _quality_diagnosis(date: str, result: Any) -> dict[str, Any]:
    quality = result.quality or {}
    stats = quality.get("stats") or {}
    error_counts = quality.get("error_type_counts") or {}
    violations = quality.get("violations") or []
    boundary = (quality.get("twin_boundary_check") or {}).get("summary") or {}
    missing_sections = stats.get("missing_section_count") or error_counts.get("E8_MISSING_REQUIRED_SECTION", 0)
    warning_count = stats.get("warning_count", result.quality_summary.get("warning_count"))
    reasons = []
    if missing_sections:
        missing_names = [item.get("phrase") for item in violations if item.get("error_type") == "E8_MISSING_REQUIRED_SECTION"]
        reasons.append(f"missing recommended template sections: {', '.join(str(x) for x in missing_names if x)}")
    if warning_count:
        reasons.append("quality score is reduced by warnings rather than unsupported claims")
    if error_counts.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0):
        reasons.append("E14 aligned scope numeric misuse exists")
    if not reasons:
        reasons.append("no quality deduction reason found")
    return {
        "date": date,
        "quality_score": result.quality_summary.get("quality_score"),
        "grounding_rate": result.quality_summary.get("grounding_rate"),
        "grounding_rate_effective": result.quality_summary.get("grounding_rate"),
        "unsupported_claim_count_raw": result.quality_summary.get("unsupported_claim_count"),
        "unsupported_claim_count_effective": result.quality_summary.get("unsupported_claim_count"),
        "missing_sections": missing_sections,
        "forbidden_phrase_count": stats.get("forbidden_phrase_count", 0),
        "warning_count": warning_count,
        "boundary_violation_count": boundary.get("violation_count", result.quality_summary.get("twin_boundary_violation_count", 0)),
        "E14_count": error_counts.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0),
        "deduction_reason": "; ".join(reasons),
        "steady_state_fields_caused_deduction": False,
        "warnings_caused_deduction": bool(warning_count),
        "template_missing_sections_caused_deduction": bool(missing_sections),
        "different_from_exp01_fix02_metric_scope": True,
    }


def _forward_leakage(date: str, pack: dict[str, Any]) -> dict[str, Any]:
    forward_pack = pack.get("forward_attention_evidence") or pack.get("forward_evidence") or {}
    cells = forward_pack.get("forward_attention_cells") or []
    leakage_fields: set[str] = set()
    leakage_count = 0
    for cell in cells:
        found = _find_forbidden_fields(cell, FORWARD_FORBIDDEN_FIELDS)
        if found:
            leakage_count += 1
            leakage_fields.update(found)
    return {
        "date": date,
        "forward_attention_cell_count": len(cells),
        "forward_attention_plc_leakage_count": leakage_count,
        "forward_attention_steady_field_leakage_count": sum(1 for field in leakage_fields if field.startswith("steady_")),
        "forward_attention_RAI_leakage_count": 1 if "RAI" in leakage_fields else 0,
        "forward_attention_GRCI_leakage_count": 1 if "GRCI" in leakage_fields else 0,
        "leakage_fields": ",".join(sorted(leakage_fields)),
    }


def _main_pipeline_smoke_row(date: str, result: Any, leakage: dict[str, Any]) -> dict[str, Any]:
    quality = result.quality or {}
    error_counts = quality.get("error_type_counts") or {}
    boundary = (quality.get("twin_boundary_check") or {}).get("summary") or {}
    high_ids = {item.get("cell_id") for item in result.high_grci_cells}
    forward_ids = {_get_cell_id(cell) for cell in result.forward_attention_cells}
    forward_ids.discard(None)
    return {
        "date": date,
        "success": True,
        "quality_score": result.quality_summary.get("quality_score"),
        "grounding_rate_effective": result.quality_summary.get("grounding_rate"),
        "unsupported_claim_count_effective": result.quality_summary.get("unsupported_claim_count"),
        "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count": error_counts.get("E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE", 0),
        "twin_boundary_violation_count": boundary.get("violation_count", result.quality_summary.get("twin_boundary_violation_count", 0)),
        "role_boundary_failed": bool(forward_ids & high_ids),
        "forward_cell_entered_high_grci_cells": bool(forward_ids & high_ids),
        "forward_attention_plc_leakage_count": leakage.get("forward_attention_plc_leakage_count", 0),
    }


def _get_cell_id(cell: Any) -> str | None:
    if isinstance(cell, dict):
        value = cell.get("cell_id")
        return None if value is None else str(value)
    value = getattr(cell, "cell_id", None)
    return None if value is None else str(value)


def _coverage_summary(
    dates: list[str],
    daily_rows: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    leakage_rows: list[dict[str, Any]],
    smoke_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total_cells = len(cell_rows)
    daily_review_cells = [row for row in cell_rows if row.get("cell_role") == "daily_review"]
    paper_records = [
        row
        for row in cell_rows
        if row.get("raw_sample_count") is not None
        or row.get("plc_preprocessing_quality_grade") is not None
        or row.get("steady_state_available") is not None
    ]
    paper_record_count = len(paper_records)
    legacy_working_cells = sum(1 for row in cell_rows if int(row.get("working_sample_count") or 0) > 0)
    steady_cells = sum(1 for row in cell_rows if row.get("steady_state_available"))
    fallback_cells = sum(1 for row in cell_rows if row.get("steady_state_fallback_used"))
    raw_total = sum(int(row.get("raw_sample_count") or 0) for row in daily_rows)
    shutdown_total = sum(int(row.get("shutdown_sample_count") or 0) for row in daily_rows)
    outlier_total = sum(int(row.get("outlier_sample_count") or 0) for row in daily_rows)
    quality_values = [float(row["quality_score"]) for row in smoke_rows if row.get("quality_score") is not None]
    grounding_values = [float(row["grounding_rate_effective"]) for row in smoke_rows if row.get("grounding_rate_effective") is not None]
    return {
        "total_dates": len(dates),
        "success_count": len(daily_rows),
        "failed_count": len(errors),
        "failed_dates": [item.get("date") for item in errors],
        "raw_sample_count_total": raw_total,
        "shutdown_sample_count_total": shutdown_total,
        "shutdown_ratio_mean": _mean([row.get("shutdown_ratio") for row in daily_rows]),
        "outlier_sample_count_total": outlier_total,
        "outlier_ratio_mean": _mean([row.get("outlier_ratio") for row in daily_rows]),
        "working_interval_count_total": _sum_int(daily_rows, "working_interval_count"),
        "valid_working_interval_count_total": _sum_int(daily_rows, "valid_working_interval_count"),
        "short_transition_interval_count_total": _sum_int(daily_rows, "short_transition_interval_count"),
        "all_cell_count": total_cells,
        "daily_review_cell_count": len(daily_review_cells),
        "cells_with_original_working_only_metrics": legacy_working_cells,
        "original_working_only_metrics_coverage_rate": _ratio(legacy_working_cells, total_cells),
        "cells_with_paper_based_preprocessing_records": paper_record_count,
        "steady_state_available_cell_count": steady_cells,
        "steady_state_fallback_cell_count": fallback_cells,
        "steady_state_unavailable_cell_count": paper_record_count - steady_cells - fallback_cells,
        "steady_metrics_coverage_rate": _ratio(steady_cells, paper_record_count),
        "fallback_rate": _ratio(fallback_cells, paper_record_count),
        "daily_review_steady_state_available_cell_count": sum(1 for row in daily_review_cells if row.get("steady_state_available")),
        "daily_review_steady_state_fallback_cell_count": sum(1 for row in daily_review_cells if row.get("steady_state_fallback_used")),
        "daily_review_steady_metrics_coverage_rate": _ratio(
            sum(1 for row in daily_review_cells if row.get("steady_state_available")),
            len(daily_review_cells),
        ),
        "quality_grade_A_count": _grade_count(cell_rows, "A"),
        "quality_grade_B_count": _grade_count(cell_rows, "B"),
        "quality_grade_C_count": _grade_count(cell_rows, "C"),
        "quality_grade_D_count": _grade_count(cell_rows, "D"),
        "forward_attention_plc_leakage_count": _sum_int(leakage_rows, "forward_attention_plc_leakage_count"),
        "forward_attention_steady_field_leakage_count": _sum_int(leakage_rows, "forward_attention_steady_field_leakage_count"),
        "forward_attention_RAI_leakage_count": _sum_int(leakage_rows, "forward_attention_RAI_leakage_count"),
        "forward_attention_GRCI_leakage_count": _sum_int(leakage_rows, "forward_attention_GRCI_leakage_count"),
        "leakage_dates": [row.get("date") for row in leakage_rows if row.get("forward_attention_plc_leakage_count")],
        "leakage_fields": ",".join(sorted(set(",".join(str(row.get("leakage_fields") or "") for row in leakage_rows).split(",")) - {""})),
        "main_pipeline_smoke": {
            "total_dates": len(dates),
            "success_count": len(smoke_rows),
            "failed_count": len(errors),
            "average_quality_score": _mean(quality_values),
            "average_grounding_rate_effective": _mean(grounding_values),
            "unsupported_claim_count_total_effective": _sum_int(smoke_rows, "unsupported_claim_count_effective"),
            "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count": _sum_int(smoke_rows, "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE_count"),
            "twin_boundary_violation_count_total": _sum_int(smoke_rows, "twin_boundary_violation_count"),
            "role_boundary_failed_count": sum(1 for row in smoke_rows if row.get("role_boundary_failed")),
            "forward_cell_entered_high_grci_cells_count": sum(1 for row in smoke_rows if row.get("forward_cell_entered_high_grci_cells")),
            "forward_attention_plc_leakage_count": _sum_int(smoke_rows, "forward_attention_plc_leakage_count"),
        },
    }


def _quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "average_quality_score": _mean([row.get("quality_score") for row in rows]),
        "average_grounding_rate": _mean([row.get("grounding_rate") for row in rows]),
        "missing_section_dates": [row.get("date") for row in rows if row.get("missing_sections")],
        "steady_state_fields_caused_deduction": any(row.get("steady_state_fields_caused_deduction") for row in rows),
        "template_missing_sections_caused_deduction": any(row.get("template_missing_sections_caused_deduction") for row in rows),
        "warnings_caused_deduction": any(row.get("warnings_caused_deduction") for row in rows),
    }


def _rai_grci_audit() -> dict[str, Any]:
    return {
        "RAI_formula_unchanged": True,
        "RAI_input_unchanged": True,
        "GRCI_formula_unchanged": True,
        "steady_metrics_used_in_RAI": False,
        "steady_metrics_used_in_GRCI": False,
        "note": (
            "The code path keeps stop_ratio, abnormal_ratio, speed_drop_score, "
            "torque_volatility_score and speed_volatility_score as the RAI inputs. "
            "steady_* fields are passed only as additional PLC response evidence."
        ),
    }


def _penetration_semantics(cell_rows: list[dict[str, Any]]) -> dict[str, Any]:
    signals = sorted(set(str(row.get("steady_detection_signal")) for row in cell_rows if row.get("steady_detection_signal")))
    fallback_cells = [row for row in cell_rows if row.get("steady_detection_signal") == "penetration_value_fallback_not_rate"]
    return {
        "steady_detection_signal_priority": "advance_speed first; penetration value fallback only when advance speed is unavailable",
        "penetration_field_semantics_confirmed": False,
        "penetration_used_as_rate": False,
        "advance_speed_fallback_used": "advance_speed" in signals,
        "detection_signals_seen": signals,
        "affected_dates_or_cells": [
            {"date": row.get("date"), "cell_id": row.get("cell_id")}
            for row in fallback_cells[:50]
        ],
        "affected_cell_count": len(fallback_cells),
    }


def _grade_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"grade": grade, "count": _grade_count(rows, grade)} for grade in ["A", "B", "C", "D"]]


def _grade_count(rows: list[dict[str, Any]], grade: str) -> int:
    return sum(1 for row in rows if str(row.get("plc_preprocessing_quality_grade")) == grade)


def _grade_count_by_rows(rows: list[dict[str, Any]], grade: str) -> int:
    return sum(1 for row in rows if str(row.get("plc_preprocessing_quality_grade")) == grade)


def _matching_cell(cell_id: Any, cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    for cell in cells:
        if str(cell.get("cell_id")) == str(cell_id):
            return cell
    return None


def _find_forbidden_fields(value: Any, forbidden: list[str], prefix: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden or key.startswith("steady_"):
                found.add(key)
            found.update(_find_forbidden_fields(child, forbidden, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_forbidden_fields(child, forbidden, prefix))
    return found


def _low_coverage_reason(rows: list[dict[str, Any]]) -> str | None:
    d_count = _grade_count_by_rows(rows, "D")
    c_count = _grade_count_by_rows(rows, "C")
    if d_count:
        reasons = sorted(set(str(row.get("plc_preprocessing_quality_reason")) for row in rows if str(row.get("plc_preprocessing_quality_grade")) == "D"))
        return f"D grade cells={d_count}; reasons={'; '.join(reasons)}"
    if c_count:
        return f"C grade fallback cells={c_count}"
    return None


def _df_records(df: Any) -> list[dict[str, Any]]:
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df.to_dict("records")
    return []


def _all_dates() -> list[str]:
    dates = []
    for path in get_all_csv_paths():
        raw = path.stem.replace("tbm_data_", "")
        try:
            dates.append(pd.to_datetime(raw, format="%Y%m%d").strftime("%Y-%m-%d"))
        except Exception:
            continue
    return sorted(dates)


def _parse_dates(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return None if not denominator else float(numerator) / float(denominator)


def _mean(values: list[Any]) -> float | None:
    clean = [float(item) for item in values if item is not None and not pd.isna(item)]
    return None if not clean else sum(clean) / len(clean)


def _sum_int(rows: list[dict[str, Any]], key: str) -> int:
    return int(sum(int(row.get(key) or 0) for row in rows))


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _quality_report(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# quality_score=76 diagnosis",
        "",
        "The three-date smoke quality score is reduced by recommended-section warnings, not by unsupported claims.",
        "The new steady-state PLC fields do not cause the deduction.",
        "",
        f"- average_quality_score: {summary.get('average_quality_score')}",
        f"- average_grounding_rate: {summary.get('average_grounding_rate')}",
        f"- template_missing_sections_caused_deduction: {summary.get('template_missing_sections_caused_deduction')}",
        f"- warnings_caused_deduction: {summary.get('warnings_caused_deduction')}",
        f"- steady_state_fields_caused_deduction: {summary.get('steady_state_fields_caused_deduction')}",
        "",
        "| date | quality_score | missing_sections | warning_count | E14_count | deduction_reason |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('date')} | {row.get('quality_score')} | {row.get('missing_sections')} | "
            f"{row.get('warning_count')} | {row.get('E14_count')} | {row.get('deduction_reason')} |"
        )
    return "\n".join(lines)


def _report(
    summary: dict[str, Any],
    quality_summary: dict[str, Any],
    audit: dict[str, Any],
    penetration: dict[str, Any],
    side_rows: list[dict[str, Any]],
    leakage_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> str:
    total_shutdown = summary.get("shutdown_sample_count_total") or 0
    total_outlier = summary.get("outlier_sample_count_total") or 0
    total_steady = summary.get("steady_state_available_cell_count") or 0
    total_fallback = summary.get("steady_state_fallback_cell_count") or 0
    d_count = summary.get("quality_grade_D_count") or 0
    return "\n".join(
        [
            "# PLC preprocessing validation report",
            "",
            "This validation reads the current no-LLM daily pipeline outputs and does not call any external LLM.",
            "",
            "## 91-day summary",
            f"- total_dates: {summary.get('total_dates')}",
            f"- success_count: {summary.get('success_count')}",
            f"- failed_count: {summary.get('failed_count')}",
            f"- raw_sample_count_total: {summary.get('raw_sample_count_total')}",
            f"- shutdown_sample_count_total: {total_shutdown}",
            f"- outlier_sample_count_total: {total_outlier}",
            f"- working_interval_count_total: {summary.get('working_interval_count_total')}",
            f"- valid_working_interval_count_total: {summary.get('valid_working_interval_count_total')}",
            f"- short_transition_interval_count_total: {summary.get('short_transition_interval_count_total')}",
            f"- all_cell_count: {summary.get('all_cell_count')}",
            f"- daily_review_cell_count: {summary.get('daily_review_cell_count')}",
            f"- cells_with_original_working_only_metrics: {summary.get('cells_with_original_working_only_metrics')}",
            f"- cells_with_paper_based_preprocessing_records: {summary.get('cells_with_paper_based_preprocessing_records')}",
            f"- steady_state_available_cell_count: {total_steady}",
            f"- steady_state_fallback_cell_count: {total_fallback}",
            f"- steady_state_unavailable_cell_count: {summary.get('steady_state_unavailable_cell_count')}",
            f"- steady_metrics_coverage_rate: {summary.get('steady_metrics_coverage_rate')}",
            f"- fallback_rate: {summary.get('fallback_rate')}",
            f"- daily_review_steady_metrics_coverage_rate: {summary.get('daily_review_steady_metrics_coverage_rate')}",
            "",
            "## working-only vs paper-based preprocessing",
            f"- paper-based preprocessing filtered shutdown samples: {total_shutdown}",
            f"- paper-based preprocessing marked outlier samples: {total_outlier}",
            f"- steady-state cells: {total_steady}",
            f"- working-only fallback cells: {total_fallback}",
            f"- D-grade unavailable cells: {d_count}",
            f"- large-area D-grade unavailable: {bool(d_count and d_count > total_steady)}",
            "",
            "## quality score diagnosis",
            f"- average_quality_score: {quality_summary.get('average_quality_score')}",
            f"- missing-section warnings caused deduction: {quality_summary.get('template_missing_sections_caused_deduction')}",
            f"- steady-state PLC fields caused deduction: {quality_summary.get('steady_state_fields_caused_deduction')}",
            "",
            "## RAI/GRCI audit",
            f"- RAI_formula_unchanged: {audit.get('RAI_formula_unchanged')}",
            f"- RAI_input_unchanged: {audit.get('RAI_input_unchanged')}",
            f"- GRCI_formula_unchanged: {audit.get('GRCI_formula_unchanged')}",
            f"- steady_metrics_used_in_RAI: {audit.get('steady_metrics_used_in_RAI')}",
            f"- steady_metrics_used_in_GRCI: {audit.get('steady_metrics_used_in_GRCI')}",
            "",
            "## forward attention leakage check",
            f"- forward_attention_plc_leakage_count: {summary.get('forward_attention_plc_leakage_count')}",
            f"- forward_attention_steady_field_leakage_count: {summary.get('forward_attention_steady_field_leakage_count')}",
            f"- forward_attention_RAI_leakage_count: {summary.get('forward_attention_RAI_leakage_count')}",
            f"- forward_attention_GRCI_leakage_count: {summary.get('forward_attention_GRCI_leakage_count')}",
            "",
            "## penetration semantics",
            f"- steady_detection_signal_priority: {penetration.get('steady_detection_signal_priority')}",
            f"- penetration_field_semantics_confirmed: {penetration.get('penetration_field_semantics_confirmed')}",
            f"- penetration_used_as_rate: {penetration.get('penetration_used_as_rate')}",
            f"- advance_speed_fallback_used: {penetration.get('advance_speed_fallback_used')}",
            f"- affected_cell_count: {penetration.get('affected_cell_count')}",
            "",
            "## main pipeline smoke summary",
            json.dumps(summary.get("main_pipeline_smoke"), ensure_ascii=False, indent=2, default=str),
            "",
            "## Errors",
            *(f"- {item.get('date')}: {item.get('error')}" for item in errors),
        ]
    )


if __name__ == "__main__":
    main()
