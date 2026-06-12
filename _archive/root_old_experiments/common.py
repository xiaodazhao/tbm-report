"""Shared helpers for experiment scripts."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from llm.llm_api import call_llm  # noqa: E402
from services.history_memory_service import (  # noqa: E402
    build_history_comparison,
    build_history_record,
    load_history_records,
)
from services.tbm_analysis_service import analyze_tbm_data  # noqa: E402
from utils.io_utils import get_all_csv_paths, load_csv_by_date  # noqa: E402
from utils.serialization import serialize_for_json  # noqa: E402
from utils.time_window_utils import load_df_by_time  # noqa: E402


EXPERIMENTS_DIR = ROOT_DIR / "experiments"
CONFIGS_DIR = EXPERIMENTS_DIR / "configs"
OUTPUTS_DIR = EXPERIMENTS_DIR / "outputs"
CASES_DIR = OUTPUTS_DIR / "cases"
STATES_DIR = OUTPUTS_DIR / "states"
REPORTS_DIR = OUTPUTS_DIR / "reports"
REPORTS_ABLATION_DIR = OUTPUTS_DIR / "reports_ablation"
REPORTS_MULTISOURCE_DIR = OUTPUTS_DIR / "reports_multisource"
METRICS_DIR = OUTPUTS_DIR / "metrics"
TABLES_DIR = OUTPUTS_DIR / "tables"
FIGURES_DIR = OUTPUTS_DIR / "figures"

CASE_COLUMNS = [
    "case_id",
    "date",
    "time_start",
    "time_end",
    "chainage_start",
    "chainage_end",
    "case_type",
    "reason",
]

DEFAULT_METHODS = ["template", "direct_llm", "cst_llm"]
FORWARD_LEVEL_SCORE = {"none": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class CaseContext:
    """Container for a single experiment case."""

    case: dict[str, Any]
    csv_path: Path
    df: pd.DataFrame
    result: dict[str, Any]


def ensure_experiment_dirs() -> None:
    """Create the standard experiment directory layout."""
    for directory in [
        CONFIGS_DIR,
        OUTPUTS_DIR,
        CASES_DIR,
        STATES_DIR,
        REPORTS_DIR,
        REPORTS_ABLATION_DIR,
        REPORTS_MULTISOURCE_DIR,
        METRICS_DIR,
        TABLES_DIR,
        FIGURES_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def available_dates(limit: int | None = None) -> list[str]:
    """List dates inferred from available TBM CSV files."""
    dates: list[str] = []
    for path in get_all_csv_paths():
        match = re.search(r"(\d{8})", path.stem)
        if not match:
            continue
        compact = match.group(1)
        dates.append(f"{compact[:4]}-{compact[4:6]}-{compact[6:]}")
    dates = sorted(set(dates))
    return dates[:limit] if limit else dates


def draft_cases_from_dates(dates: list[str]) -> list[dict[str, Any]]:
    """Build a draft case list from available dates."""
    rows: list[dict[str, Any]] = []
    for index, date in enumerate(dates, start=1):
        rows.append(
            {
                "case_id": f"C{index:02d}",
                "date": date,
                "time_start": "",
                "time_end": "",
                "chainage_start": "",
                "chainage_end": "",
                "case_type": "unspecified",
                "reason": "draft case generated from available CSV date",
            }
        )
    return rows


def write_case_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the case list CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CASE_COLUMNS})


def load_case_csv(path: Path) -> list[dict[str, Any]]:
    """Load experiment cases from CSV."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [normalize_case_row(dict(row)) for row in reader]


def normalize_case_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize case fields read from CSV."""
    normalized = {key: (row.get(key, "") or "").strip() for key in CASE_COLUMNS}
    for key in ["chainage_start", "chainage_end"]:
        value = normalized.get(key, "")
        if value == "":
            normalized[key] = None
        else:
            try:
                normalized[key] = float(value)
            except ValueError:
                normalized[key] = value
    return normalized


def load_case_context(case: dict[str, Any]) -> CaseContext:
    """Load dataframe and analysis result for a single case."""
    csv_path, df = load_csv_by_date(case["date"])
    if case.get("time_start") and case.get("time_end"):
        df = load_df_by_time(df, case["time_start"], case["time_end"])
    result = analyze_tbm_data(
        df,
        context={
            "date": case["date"],
            "analysis_mode": "time_window" if case.get("time_start") and case.get("time_end") else "daily",
            "time_start": case.get("time_start"),
            "time_end": case.get("time_end"),
            "chainage_start": case.get("chainage_start"),
            "chainage_end": case.get("chainage_end"),
            "case_id": case.get("case_id"),
            "source_path": str(csv_path),
            "source_name": csv_path.name,
            "persist_cst": True,
        },
    )
    return CaseContext(case=case, csv_path=csv_path, df=df, result=result)


def build_history_comparison_text(date: str, result: dict[str, Any]) -> str:
    """Build a lightweight history comparison text when history exists."""
    current_record = build_history_record(date, result)
    history_records = load_history_records(limit=5, before_date=date)
    comparison = build_history_comparison(current_record, history_records)
    return comparison.get("comparison_text", "暂无历史分析记忆。")


def _safe_text(value: Any, default: str = "无") -> str:
    """Return a clean string fallback for optional text values."""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _compact_text(value: Any, max_lines: int = 8, max_chars: int = 1800) -> str:
    """Compress long multiline text into a shorter experiment-friendly summary."""
    text = _safe_text(value)
    if text == "无":
        return text
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    compact = "\n".join(lines[:max_lines])
    if len(compact) > max_chars:
        compact = compact[: max_chars - 3].rstrip() + "..."
    return compact


def _format_list(values: Any, default: str = "无") -> str:
    """Format list-like values into a compact comma-separated string."""
    if not values:
        return default
    if isinstance(values, str):
        return values.strip() or default
    if isinstance(values, (list, tuple, set)):
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return "、".join(cleaned) if cleaned else default
    return str(values)


def _format_forward_window(forward_window: list[dict[str, Any]]) -> str:
    """Summarize forward attention windows for prompt consumption."""
    if not forward_window:
        return "前方区段未见明确关注提示。"
    parts: list[str] = []
    for item in forward_window[:2]:
        parts.append(
            "前方{lookahead}m范围 {start}~{end}，关注等级={level}，高关注段={count}，主要风险={hazards}".format(
                lookahead=item.get("lookahead_m", "未知"),
                start=item.get("forward_start_dk") or item.get("forward_start") or "未知",
                end=item.get("forward_end_dk") or item.get("forward_end") or "未知",
                level=item.get("advice_level") or "未知",
                count=item.get("high_risk_count", 0),
                hazards=_format_list(item.get("main_hazards")),
            )
        )
    return "\n".join(parts)


def _format_attention_segments(segments: list[dict[str, Any]]) -> str:
    """Summarize top attention segments without dumping raw dicts."""
    if not segments:
        return "未识别到高关注区段。"
    lines: list[str] = []
    for segment in segments[:3]:
        lines.append(
            "{segment} | GRS={grs:.2f}, RAI={rai:.2f}, GRCI={grci:.2f}, 类型={label}".format(
                segment=segment.get("segment", "未知区段"),
                grs=float(segment.get("GRS") or 0.0),
                rai=float(segment.get("RAI") or 0.0),
                grci=float(segment.get("GRCI") or 0.0),
                label=segment.get("grci_class_label") or segment.get("coupling_label") or "未分类",
            )
        )
    return "\n".join(lines)


def _build_cst_summary_text(state: dict[str, Any]) -> str:
    """Render a concise CST summary block for experiment prompts."""
    temporal = state.get("temporal_state", {})
    spatial = state.get("spatial_state", {})
    operation = state.get("operation_state", {})
    geology = state.get("geological_state", {})
    response = state.get("response_state", {})
    attention = state.get("attention_state", {})
    provenance = state.get("provenance_state", {})

    return f"""
【CST状态摘要】
- 分析模式：{_safe_text(temporal.get('analysis_mode'))}
- 样本数量：{temporal.get('sample_count', 0)}
- 当前掌子面里程：{spatial.get('face_chainage') or '无'}
- 推进长度：{spatial.get('advance_length') or 0}
- 主导工况：{_safe_text(operation.get('main_state'))}
- 工作时长：{operation.get('working_duration_min', 0)} 分钟
- 停机时长：{operation.get('stoppage_duration_min', 0)} 分钟
- 状态切换次数：{operation.get('state_switch_count', 0)}
- 当前掌子面地质：{_safe_text(geology.get('face_condition'))}
- 主要地质关注：{_format_list(geology.get('hazards'))}
- 证据数量：{geology.get('evidence_count', 0)}
- GRS：{float(attention.get('GRS') or 0.0):.2f}
- RAI：{float(response.get('RAI') or 0.0):.2f}
- GRCI：{float(attention.get('GRCI') or 0.0):.2f}
- 前方提示：
{_format_forward_window(spatial.get('forward_window') or [])}
- 高关注区段：
{_format_attention_segments(attention.get('high_attention_segments') or [])}
- 历史对比：{_safe_text(provenance.get('previous_change_summary'))}
""".strip()


def _pick_primary_attention_segment(result: dict[str, Any], coupling_summary: dict[str, Any]) -> dict[str, Any]:
    """Pick the primary high-attention segment from available coupling outputs."""
    candidates = result.get("high_attention_segments") or []
    if not candidates:
        candidates = coupling_summary.get("high_attention_segments") or []
    if not candidates:
        candidates = coupling_summary.get("top_segments") or []
    return deepcopy(candidates[0]) if candidates else {}


def _split_hazard_text(value: Any) -> list[str]:
    """Convert fused hazard text into a lightweight hazard list."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[+?,?;/??\s]+", text) if part.strip()]


def build_cst_state(case: dict[str, Any], context: CaseContext) -> dict[str, Any]:
    """Export a normalized CST state payload for experiments."""
    result = context.result
    if result.get("cst_state"):
        cst_state = deepcopy(result["cst_state"])
        if case.get("case_id") and not cst_state.get("case_id"):
            cst_state["case_id"] = case["case_id"]
        return serialize_for_json(cst_state)

    twin = deepcopy(result.get("digital_twin_state") or {})
    llm_summary = deepcopy(result.get("llm_summary") or {})
    coupling_summary = deepcopy(result.get("coupling_summary") or {})
    geo_summary = deepcopy(result.get("geo_summary_segment") or {})
    geo_record_summary = deepcopy(result.get("geo_summary_record") or {})
    gas_stats = deepcopy(result.get("gas_stats") or {})
    forward_summary = deepcopy(result.get("forward_risk_summary") or {})
    history_text = build_history_comparison_text(case["date"], result)

    position_state = twin.get("position_state", {}) if isinstance(twin, dict) else {}
    operation_state = twin.get("operation_state", {}) if isinstance(twin, dict) else {}
    twin_geo_state = twin.get("geology_state", {}) if isinstance(twin, dict) else {}
    forward_state = twin.get("forward_risk_state", {}) if isinstance(twin, dict) else {}
    primary_segment = _pick_primary_attention_segment(result, coupling_summary)

    hazard_list = (
        geo_summary.get("main_hazards")
        or _split_hazard_text(twin_geo_state.get("current_hazard"))
        or _split_hazard_text(result.get("face_geo_text"))
    )
    evidence_list = geo_record_summary.get("active_sources", [])
    if not isinstance(evidence_list, list):
        evidence_list = []
    time_col = "运行时间-time" if "运行时间-time" in context.df.columns else "杩愯鏃堕棿-time"
    no_data_text = "无"
    no_history_text = "暂无历史分析记忆。"

    forward_window = []
    if forward_summary.get("has_forward_risk"):
        forward_window.append(
            {
                "lookahead_m": forward_summary.get("lookahead_m"),
                "forward_start": forward_summary.get("forward_start"),
                "forward_end": forward_summary.get("forward_end"),
                "forward_start_dk": forward_summary.get("forward_start_dk"),
                "forward_end_dk": forward_summary.get("forward_end_dk"),
                "advice_level": forward_summary.get("advice_level"),
                "main_hazards": forward_summary.get("main_hazards", []),
                "forward_segment_count": forward_summary.get("forward_segment_count", 0),
                "high_risk_count": forward_summary.get("high_risk_count", 0),
            }
        )

    state = {
        "case_id": case["case_id"],
        "date": case["date"],
        "time_window": {
            "start_time": serialize_for_json(context.df[time_col].min()) if not context.df.empty else "",
            "end_time": serialize_for_json(context.df[time_col].max()) if not context.df.empty else "",
            "duration_min": round(
                max(
                    0.0,
                    (context.df[time_col].max() - context.df[time_col].min()).total_seconds() / 60.0,
                ),
                2,
            )
            if len(context.df) >= 2
            else 0.0,
        },
        "temporal_state": {
            "sample_count": int(len(context.df)),
            "analysis_mode": "time_window" if case.get("time_start") and case.get("time_end") else "daily",
        },
        "spatial_state": {
            "chainage_start": case.get("chainage_start") or position_state.get("start_chainage"),
            "chainage_end": case.get("chainage_end") or position_state.get("end_chainage"),
            "face_chainage": position_state.get("current_chainage"),
            "advance_length": position_state.get("advance_length"),
            "forward_window": forward_window,
        },
        "operation_state": {
            "main_state": operation_state.get("dominant_state"),
            "working_duration_min": operation_state.get("work_total_min", 0.0),
            "stoppage_duration_min": operation_state.get("stop_total_min", 0.0),
            "state_switch_count": operation_state.get("state_switch_count", 0),
            "efficiency_summary": llm_summary.get("施工状态效率分析", no_data_text),
        },
        "geological_state": {
            "face_condition": result.get("face_geo_text", no_data_text),
            "segment_grade": twin_geo_state.get("current_grade") or geo_summary.get("segment_grade"),
            "hazards": hazard_list,
            "evidence_count": twin_geo_state.get("current_active_source_count") or geo_summary.get("multi_source_segment_count", 0),
            "uncertainty": geo_summary.get("uncertainty") or geo_record_summary.get("uncertainty"),
        },
        "response_state": {
            "RAI": primary_segment.get("RAI", 0.0),
            "anomaly_type": primary_segment.get("anomaly_type", ""),
            "key_parameters": primary_segment.get("key_parameters", []),
        },
        "attention_state": {
            "GRS": primary_segment.get("GRS", 0.0),
            "GRCI": primary_segment.get("GRCI", 0.0),
            "high_attention_segments": result.get("high_attention_segments", []),
            "forward_attention": serialize_for_json(forward_state or forward_summary),
        },
        "provenance_state": {
            "evidence_list": evidence_list,
            "state_update_sources": [
                {"type": "csv", "path": context.csv_path.name},
                {"type": "history", "available": history_text != no_history_text},
            ],
            "previous_change_summary": history_text,
        },
        "raw_twin_state": twin,
        "llm_summary": llm_summary,
        "warnings": result.get("warnings", []),
        "gas_state": serialize_for_json(gas_stats),
    }
    return serialize_for_json(state)


def write_json(path: Path, payload: Any) -> None:
    """Write JSON with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def flatten_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Build a compact CSV-friendly state summary row."""
    return {
        "case_id": state["case_id"],
        "date": state["date"],
        "analysis_mode": state["temporal_state"]["analysis_mode"],
        "sample_count": state["temporal_state"]["sample_count"],
        "face_chainage": state["spatial_state"].get("face_chainage"),
        "advance_length": state["spatial_state"].get("advance_length"),
        "main_state": state["operation_state"].get("main_state"),
        "working_duration_min": state["operation_state"].get("working_duration_min"),
        "stoppage_duration_min": state["operation_state"].get("stoppage_duration_min"),
        "RAI": state["response_state"].get("RAI"),
        "GRS": state["attention_state"].get("GRS"),
        "GRCI": state["attention_state"].get("GRCI"),
        "high_attention_segment_count": len(state["attention_state"].get("high_attention_segments", [])),
    }


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write generic row dictionaries to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_template_report(case: dict[str, Any], state: dict[str, Any]) -> str:
    """Generate a deterministic template baseline report."""
    op = state["operation_state"]
    geo = state["geological_state"]
    att = state["attention_state"]
    return (
        f"TBM施工报告（模板基线）\n\n"
        f"日期：{case['date']}\n"
        f"案例编号：{case['case_id']}\n\n"
        f"一、施工概况\n"
        f"本次分析窗口主导工况为{op.get('main_state') or '未知'}，"
        f"工作时长约{op.get('working_duration_min', 0)}分钟，"
        f"停机时长约{op.get('stoppage_duration_min', 0)}分钟。\n\n"
        f"二、地质情况\n"
        f"当前掌子面摘要：{geo.get('face_condition') or '无'}\n"
        f"主要关注标签：{', '.join(geo.get('hazards') or []) or '无'}\n\n"
        f"三、区段关注\n"
        f"GRS={att.get('GRS', 0)}，RAI={state['response_state'].get('RAI', 0)}，"
        f"GRCI={att.get('GRCI', 0)}。"
        f"高关注区段数量：{len(att.get('high_attention_segments', []))}。\n\n"
        f"四、结论与建议\n"
        f"建议结合当前施工状态、地质证据和前方关注信息，持续开展现场核查与参数跟踪。"
    )


def build_direct_llm_prompt(case: dict[str, Any], context: CaseContext) -> str:
    """Build a weaker baseline prompt without explicit CST alignment."""
    result = context.result
    return f"""
请根据以下 TBM 施工摘要信息，直接生成一份正式的《TBM综合施工工况分析报告》。

要求：
1. 使用正式工程报告语体；
2. 尽量覆盖施工概况、工况统计、施工状态、地质情况、气体安全和前方提示；
3. 不要虚构未提供的信息；
4. 不需要显式输出指标解释；
5. 不提供统一里程状态组织，请仅依据以下摘要进行综合写作。

案例编号：{case["case_id"]}
日期：{case["date"]}

【基础工况概览】
{_compact_text(result.get("seg_text", "无"), max_lines=10, max_chars=1600)}

【基础统计】
{_compact_text(result.get("stats_text", "无"), max_lines=10, max_chars=1200)}

【施工状态】
{_compact_text(result.get("state_text", "无"), max_lines=8, max_chars=1200)}

【效率统计】
{_compact_text(result.get("eff_text", "无"), max_lines=8, max_chars=1000)}

【地质分析】
{_compact_text(result.get("geo_text", "无"), max_lines=10, max_chars=1400)}

【当前掌子面】
{_compact_text(result.get("face_geo_text", "无"), max_lines=6, max_chars=800)}

【气体分析】
{_compact_text(result.get("gas_text", "无"), max_lines=8, max_chars=800)}

【前方提示】
{_compact_text(result.get("forward_risk_text", "无"), max_lines=6, max_chars=800)}
""".strip()


def build_cst_llm_prompt(context: CaseContext) -> str:
    """Build a concise state-aware CST prompt for the main method."""
    case = context.case
    result = context.result
    state = build_cst_state(case, context)
    return f"""
请基于以下 Construction State Twin（CST）状态摘要，生成一份正式的《TBM综合施工工况分析报告》。

【角色要求】
你是一名 TBM 施工分析工程师，需要面向工程管理与技术人员撰写正式报告。

【写作约束】
1. 仅描述指定日期/时间窗对应的施工情况。
2. 当前掌子面观察与前方区段提示必须分开撰写。
3. 风险相关表述必须使用审慎措辞，如“需关注”“提示”“表明”“建议核查”。
4. 不得宣称输入中没有明确证据支持的灾害已经发生。
5. GRS 表示地质关注度，RAI 表示施工响应异常度，GRCI 表示二者的耦合验证结果，不得写成灾害概率。
6. 如果证据不足或结论受限，应明确说明解释需要谨慎。
7. 请直接输出正式报告正文，不要输出提示词解释。

【输出结构】
一、执行摘要
二、总体运行情况
三、基础工况统计分析
四、施工状态与效率分析
五、当前掌子面地质情况
六、前方地质关注与区段耦合分析
七、气体监测分析
八、结论与建议

案例编号：{case["case_id"]}
日期：{case["date"]}

{_build_cst_summary_text(state)}

【补充状态摘要】
基础统计：
{_compact_text(result.get("stats_text", "无"), max_lines=8, max_chars=1000)}

施工状态摘要：
{_compact_text(result.get("state_text", "无"), max_lines=8, max_chars=1200)}

效率摘要：
{_compact_text(result.get("eff_text", "无"), max_lines=6, max_chars=800)}

当前掌子面说明：
{_compact_text(result.get("face_geo_text", "无"), max_lines=6, max_chars=900)}

前方提示说明：
{_compact_text(result.get("forward_risk_text", "无"), max_lines=6, max_chars=900)}

气体监测说明：
{_compact_text(result.get("gas_text", "无"), max_lines=6, max_chars=800)}
""".strip()


def build_cst_llm_prompt_wo_constraints(context: CaseContext) -> str:
    """Build a CST-based prompt without cautious wording constraints."""
    case = context.case
    result = context.result
    state = build_cst_state(case, context)
    return f"""
请基于以下 Construction State Twin（CST）状态摘要，生成一份正式的《TBM综合施工工况分析报告》。

【角色要求】
你是一名 TBM 施工分析工程师，需要面向工程管理与技术人员撰写正式报告。

【输出结构】
一、执行摘要
二、总体运行情况
三、基础工况统计分析
四、施工状态与效率分析
五、当前掌子面地质情况
六、前方地质关注与区段耦合分析
七、气体监测分析
八、结论与建议

案例编号：{case["case_id"]}
日期：{case["date"]}

{_build_cst_summary_text(state)}

【补充状态摘要】
基础统计：
{_compact_text(result.get("stats_text", "无"), max_lines=8, max_chars=1000)}

施工状态摘要：
{_compact_text(result.get("state_text", "无"), max_lines=8, max_chars=1200)}

效率摘要：
{_compact_text(result.get("eff_text", "无"), max_lines=6, max_chars=800)}

当前掌子面说明：
{_compact_text(result.get("face_geo_text", "无"), max_lines=6, max_chars=900)}

前方提示说明：
{_compact_text(result.get("forward_risk_text", "无"), max_lines=6, max_chars=900)}

气体监测说明：
{_compact_text(result.get("gas_text", "无"), max_lines=6, max_chars=800)}
""".strip()


def build_cst_llm_prompt_wo_alignment(context: CaseContext) -> str:
    """Build a CST prompt without explicit chainage-level alignment details."""
    case = context.case
    result = context.result
    state = build_cst_state(case, context)
    op = state.get("operation_state", {})
    geo = state.get("geological_state", {})
    response = state.get("response_state", {})
    attention = state.get("attention_state", {})
    safety = state.get("gas_state", {})
    forward = state.get("raw_twin_state", {}).get("forward_risk_state", {})
    return f"""
请根据以下 TBM 施工状态摘要，生成一份正式的《TBM综合施工工况分析报告》。

【角色要求】
你是一名 TBM 施工分析工程师，需要面向工程管理与技术人员撰写正式报告。

【写作约束】
1. 仅描述指定日期/时间窗对应的施工情况。
2. 当前掌子面观察与前方区段提示必须分开撰写。
3. 风险相关表述必须使用审慎措辞，如“需关注”“提示”“表明”“建议核查”。
4. 不得宣称输入中没有明确证据支持的灾害已经发生。
5. GRS 表示地质关注度，RAI 表示施工响应异常度，GRCI 表示二者的耦合验证结果，不得写成灾害概率。

【输出结构】
一、执行摘要
二、总体运行情况
三、基础工况统计分析
四、施工状态与效率分析
五、当前掌子面地质情况
六、前方地质关注与区段耦合分析
七、气体监测分析
八、结论与建议

案例编号：{case["case_id"]}
日期：{case["date"]}

【状态摘要】
- 分析模式：{_safe_text(state.get("temporal_state", {}).get("analysis_mode"))}
- 样本数量：{state.get("temporal_state", {}).get("sample_count", 0)}
- 主导工况：{_safe_text(op.get("main_state"))}
- 工作时长：{op.get("working_duration_min", 0)} 分钟
- 停机时长：{op.get("stoppage_duration_min", 0)} 分钟
- 状态切换次数：{op.get("state_switch_count", 0)}
- 当前掌子面地质：{_safe_text(geo.get("face_condition"))}
- 主要地质关注：{_format_list(geo.get("hazards"))}
- GRS：{float(attention.get("GRS") or 0.0):.2f}
- RAI：{float(response.get("RAI") or 0.0):.2f}
- GRCI：{float(attention.get("GRCI") or 0.0):.2f}
- 前方关注等级：{_safe_text(forward.get("advice_level"))}
- 前方主要风险：{_format_list(forward.get("main_hazards"))}
- 气体超阈值类型：{_format_list(safety.get("gas_exceed_types"))}

【补充状态摘要】
基础统计：
{_compact_text(result.get("stats_text", "无"), max_lines=8, max_chars=1000)}

施工状态摘要：
{_compact_text(result.get("state_text", "无"), max_lines=8, max_chars=1200)}

效率摘要：
{_compact_text(result.get("eff_text", "无"), max_lines=6, max_chars=800)}

当前掌子面说明：
{_compact_text(result.get("face_geo_text", "无"), max_lines=6, max_chars=900)}

前方提示说明：
{_compact_text(result.get("forward_risk_text", "无"), max_lines=6, max_chars=900)}

气体监测说明：
{_compact_text(result.get("gas_text", "无"), max_lines=6, max_chars=800)}
""".strip()


def build_cst_llm_prompt_wo_geo(context: CaseContext) -> str:
    """Build a CST-derived prompt without geological evidence state."""
    case = context.case
    result = context.result
    state = build_cst_state(case, context)
    op = state.get("operation_state", {})
    response = state.get("response_state", {})
    safety = state.get("gas_state", {})
    temporal = state.get("temporal_state", {})
    history_text = _safe_text(
        state.get("provenance_state", {}).get("previous_change_summary"),
        "暂无历史变化摘要。",
    )
    return f"""
请基于以下 TBM 施工运行状态摘要，生成一份正式的《TBM综合施工工况分析报告》。
【角色要求】你是一名 TBM 施工分析工程师，需要面向工程管理与技术人员撰写正式报告。
【写作约束】1. 仅描述指定日期或时间窗对应的施工情况。2. 当前输入不提供地质证据状态，请不要虚构围岩、前方风险或掌子面地质细节。3. 风险相关表述必须审慎，若证据不足，应明确说明结论受限。4. 可以基于施工参数、工况切换、效率、气体和历史变化给出运行侧判断与建议。
【输出结构】一、执行摘要
二、总体运行情况
三、基础工况统计分析
四、施工状态与效率分析
五、运行异常与安全监测分析
六、结论与建议

案例编号：{case["case_id"]}
日期：{case["date"]}

【状态摘要】
- 分析模式：{_safe_text(temporal.get("analysis_mode"))}
- 样本数量：{temporal.get("sample_count", 0)}
- 主导工况：{_safe_text(op.get("main_state"))}
- 工作时长：{op.get("working_duration_min", 0)} 分钟
- 停机时长：{op.get("stoppage_duration_min", 0)} 分钟
- 状态切换次数：{op.get("state_switch_count", 0)}
- RAI：{float(response.get("RAI") or 0.0):.2f}
- 施工异常类型：{_safe_text(response.get("anomaly_type"))}
- 关键异常参数：{_format_list(response.get("key_parameters"))}
- 气体超阈值类型：{_format_list(safety.get("gas_exceed_types"))}
- 历史变化摘要：{history_text}

【补充状态摘要】基础统计：{_compact_text(result.get("stats_text", "无"), max_lines=8, max_chars=1000)}

施工状态摘要：
{_compact_text(result.get("state_text", "无"), max_lines=8, max_chars=1200)}

效率摘要：{_compact_text(result.get("eff_text", "无"), max_lines=6, max_chars=800)}

气体监测说明：{_compact_text(result.get("gas_text", "无"), max_lines=6, max_chars=800)}
""".strip()


def build_cst_llm_prompt_plc_geo(context: CaseContext) -> str:
    """Build a reduced prompt that keeps PLC and geological state but omits gas details."""
    case = context.case
    result = context.result
    state = build_cst_state(case, context)
    op = state.get("operation_state", {})
    geo = state.get("geological_state", {})
    response = state.get("response_state", {})
    attention = state.get("attention_state", {})
    temporal = state.get("temporal_state", {})
    spatial = state.get("spatial_state", {})
    history_text = _safe_text(
        state.get("provenance_state", {}).get("previous_change_summary"),
        "暂无历史变化摘要。",
    )
    return f"""
请基于以下 TBM 施工状态摘要，生成一份正式的《TBM综合施工工况分析报告》。
【角色要求】你是一名 TBM 施工分析工程师，需要面向工程管理与技术人员撰写正式报告。
【写作约束】1. 仅描述指定日期或时间窗对应的施工情况。2. 当前掌子面观察与前方区段提示必须分开撰写。3. 风险相关表述必须使用审慎措辞，如“需关注”“提示”“表明”。4. 本变体不单独展开气体监测结论，除非输入摘要中明确提供。
【输出结构】一、执行摘要
二、总体运行情况
三、基础工况统计分析
四、施工状态与效率分析
五、当前掌子面地质情况
六、前方地质关注与区段耦合分析
七、结论与建议

案例编号：{case["case_id"]}
日期：{case["date"]}

【状态摘要】
- 分析模式：{_safe_text(temporal.get("analysis_mode"))}
- 样本数量：{temporal.get("sample_count", 0)}
- 主导工况：{_safe_text(op.get("main_state"))}
- 工作时长：{op.get("working_duration_min", 0)} 分钟
- 停机时长：{op.get("stoppage_duration_min", 0)} 分钟
- 状态切换次数：{op.get("state_switch_count", 0)}
- 当前掌子面里程：{spatial.get("face_chainage") or "N/A"}
- 当前掌子面地质：{_safe_text(geo.get("face_condition"))}
- 主要地质关注：{_format_list(geo.get("hazards"))}
- GRS：{float(attention.get("GRS") or 0.0):.2f}
- RAI：{float(response.get("RAI") or 0.0):.2f}
- GRCI：{float(attention.get("GRCI") or 0.0):.2f}
- 前方提示：
{_format_forward_window(spatial.get("forward_window") or [])}
- 高关注区段：
{_format_attention_segments(attention.get("high_attention_segments") or [])}
- 历史变化摘要：{history_text}

【补充状态摘要】基础统计：
{_compact_text(result.get("stats_text", "暂无"), max_lines=8, max_chars=1000)}

施工状态摘要：
{_compact_text(result.get("state_text", "暂无"), max_lines=8, max_chars=1200)}

效率摘要：{_compact_text(result.get("eff_text", "暂无"), max_lines=6, max_chars=800)}

当前掌子面说明：
{_compact_text(result.get("face_geo_text", "暂无"), max_lines=6, max_chars=900)}

前方提示说明：{_compact_text(result.get("forward_risk_text", "暂无"), max_lines=6, max_chars=900)}
""".strip()


def maybe_call_llm(prompt: str, mode: str, provider: str | None = None) -> str:
    """Optionally call the configured LLM provider."""
    if mode == "prompt_only":
        return ""
    return call_llm(prompt, provider=provider)


def evaluation_sheet_rows(cases: list[dict[str, Any]], methods: list[str]) -> list[dict[str, Any]]:
    """Create blank evaluation sheet rows."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        for method in methods:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "method": method,
                    "reviewer_id": "",
                    "ICS_operation": "",
                    "ICS_geology": "",
                    "ICS_gas": "",
                    "ICS_forward": "",
                    "factual_errors_count": "",
                    "key_facts_count": "",
                    "unsupported_claims_count": "",
                    "key_claims_count": "",
                    "risk_overstatement_count": "",
                    "RDR_score": "",
                    "EOR_score": "",
                    "comments": "",
                }
            )
    return rows


def aggregate_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate method-level metrics from manual evaluation rows."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["method"], []).append(row)

    output: list[dict[str, Any]] = []
    for method, items in grouped.items():
        ics_values: list[float] = []
        fcs_values: list[float] = []
        ts_values: list[float] = []
        rdr_values: list[float] = []
        eor_values: list[float] = []
        for item in items:
            ics_parts = [
                safe_float(item.get("ICS_operation")),
                safe_float(item.get("ICS_geology")),
                safe_float(item.get("ICS_gas")),
                safe_float(item.get("ICS_forward")),
            ]
            valid_ics = [part for part in ics_parts if part is not None]
            if valid_ics:
                ics_values.append(sum(valid_ics) / (2.0 * len(valid_ics)))

            factual_errors = safe_float(item.get("factual_errors_count"))
            key_facts = safe_float(item.get("key_facts_count"))
            unsupported_claims = safe_float(item.get("unsupported_claims_count"))
            key_claims = safe_float(item.get("key_claims_count"))
            if factual_errors is not None and key_facts and key_facts > 0:
                fcs_values.append(1.0 - factual_errors / key_facts)
            if unsupported_claims is not None and key_claims and key_claims > 0:
                ts_values.append(1.0 - unsupported_claims / key_claims)

            rdr = safe_float(item.get("RDR_score"))
            eor = safe_float(item.get("EOR_score"))
            if rdr is not None:
                rdr_values.append(rdr)
            if eor is not None:
                eor_values.append(eor)

        output.append(
            {
                "method": method,
                "ICS_mean": round(sum(ics_values) / len(ics_values), 4) if ics_values else "",
                "FCS_mean": round(sum(fcs_values) / len(fcs_values), 4) if fcs_values else "",
                "TS_mean": round(sum(ts_values) / len(ts_values), 4) if ts_values else "",
                "RDR_mean": round(sum(rdr_values) / len(rdr_values), 4) if rdr_values else "",
                "EOR_mean": round(sum(eor_values) / len(eor_values), 4) if eor_values else "",
                "n_rows": len(items),
            }
        )
    return output


def summarize_case_metrics(case: dict[str, Any], context: CaseContext, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build compact metrics for case selection and experiment bookkeeping."""
    result = context.result
    state = state or build_cst_state(case, context)
    coupling = result.get("coupling_summary") or {}
    forward = result.get("forward_risk_summary") or {}
    geo = result.get("geo_summary_segment") or {}
    twin = result.get("digital_twin_state") or {}
    safety_state = twin.get("safety_state", {}) if isinstance(twin, dict) else {}
    top_segment = (coupling.get("high_attention_segments") or [{}])[0]
    return {
        "case_id": case["case_id"],
        "date": case["date"],
        "sample_count": state["temporal_state"]["sample_count"],
        "analysis_mode": state["temporal_state"]["analysis_mode"],
        "work_min": state["operation_state"].get("working_duration_min", 0.0),
        "stop_min": state["operation_state"].get("stoppage_duration_min", 0.0),
        "GRS_top": top_segment.get("GRS", coupling.get("GRS_max", 0.0)),
        "RAI_top": top_segment.get("RAI", coupling.get("RAI_max", 0.0)),
        "GRCI_top": top_segment.get("GRCI", coupling.get("GRCI_max", 0.0)),
        "high_attention_segment_count": len(result.get("high_attention_segments", [])),
        "high_risk_segment_count": geo.get("high_risk_segment_count", 0),
        "multi_source_segment_count": geo.get("multi_source_segment_count", 0),
        "forward_advice_level": forward.get("advice_level", "none"),
        "forward_high_risk_count": forward.get("high_risk_count", 0),
        "gas_exceed_type_count": safety_state.get("gas_exceed_type_count", 0),
        "gas_exceed_types": ",".join(safety_state.get("gas_exceed_types", [])),
        "top_segment": top_segment.get("segment", ""),
        "top_segment_class": top_segment.get("grci_class_label", ""),
    }


def classify_case_type(metrics: dict[str, Any]) -> tuple[str, str, float]:
    """Assign a candidate case type using simple heuristic rules."""
    grs = float(metrics.get("GRS_top") or 0.0)
    rai = float(metrics.get("RAI_top") or 0.0)
    grci = float(metrics.get("GRCI_top") or 0.0)
    gas_count = int(metrics.get("gas_exceed_type_count") or 0)
    high_risk_count = int(metrics.get("high_risk_segment_count") or 0)
    forward_level = str(metrics.get("forward_advice_level") or "none").lower()
    forward_score = FORWARD_LEVEL_SCORE.get(forward_level, 0)

    if gas_count > 0:
        return (
            "gas_attention",
            f"gas exceed types={metrics.get('gas_exceed_types') or gas_count}",
            max(gas_count, 1),
        )
    if grs >= 0.55 and rai >= 0.55 and grci >= 0.55:
        return (
            "coupled_attention",
            f"GRS={grs:.2f}, RAI={rai:.2f}, GRCI={grci:.2f}",
            grci,
        )
    if rai >= 0.60 and grci < 0.55:
        return (
            "response_anomaly",
            f"RAI={rai:.2f}, GRCI={grci:.2f}",
            rai,
        )
    if grs >= 0.60 or high_risk_count > 0 or forward_score >= 2:
        return (
            "geology_attention",
            f"GRS={grs:.2f}, high_risk_segments={high_risk_count}, forward={forward_level}",
            max(grs, forward_score / 3.0),
        )
    if grs < 0.35 and rai < 0.35 and grci < 0.35 and gas_count == 0:
        stability = 1.0 - max(grs, rai, grci)
        return (
            "normal",
            f"GRS={grs:.2f}, RAI={rai:.2f}, GRCI={grci:.2f}",
            stability,
        )

    # Fallback: choose the strongest signal.
    if grci >= max(grs, rai):
        return ("coupled_attention", f"fallback by GRCI={grci:.2f}", grci)
    if rai >= grs:
        return ("response_anomaly", f"fallback by RAI={rai:.2f}", rai)
    return ("geology_attention", f"fallback by GRS={grs:.2f}", grs)


def pick_balanced_cases(candidate_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Pick a balanced subset of candidates across target case types."""
    target_order = [
        "normal",
        "geology_attention",
        "response_anomaly",
        "coupled_attention",
        "gas_attention",
    ]
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in target_order}
    for row in candidate_rows:
        grouped.setdefault(str(row.get("case_type")), []).append(row)
    for values in grouped.values():
        values.sort(key=lambda item: float(item.get("selection_score") or 0), reverse=True)

    selected: list[dict[str, Any]] = []
    seen_dates: set[str] = set()

    # First pass: at most one per type.
    for case_type in target_order:
        for row in grouped.get(case_type, []):
            if row["date"] in seen_dates:
                continue
            selected.append(row)
            seen_dates.add(row["date"])
            break

    # Second pass: fill remaining slots by score.
    remaining = []
    for rows in grouped.values():
        for row in rows:
            if row["date"] in seen_dates:
                continue
            remaining.append(row)
    remaining.sort(key=lambda item: float(item.get("selection_score") or 0), reverse=True)
    for row in remaining:
        if len(selected) >= limit:
            break
        selected.append(row)
        seen_dates.add(row["date"])

    selected = sorted(selected[:limit], key=lambda item: item["date"])
    for index, row in enumerate(selected, start=1):
        row["case_id"] = f"C{index:02d}"
    return selected


def safe_float(value: Any) -> float | None:
    """Convert a cell value to float when possible."""
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate manual evaluation rows into method-level metrics."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["method"], []).append(row)
    output: list[dict[str, Any]] = []
    for method, items in grouped.items():
        ics_values = []
        fcs_values = []
        ts_values = []
        rdr_values = []
        eor_values = []
        for item in items:
            ics_parts = [
                safe_float(item.get("ICS_operation")),
                safe_float(item.get("ICS_geology")),
                safe_float(item.get("ICS_gas")),
                safe_float(item.get("ICS_forward")),
            ]
            valid_ics = [part for part in ics_parts if part is not None]
            if valid_ics:
                ics_values.append(sum(valid_ics) / (2.0 * len(valid_ics)))
            factual_errors = safe_float(item.get("factual_errors_count"))
            key_facts = safe_float(item.get("key_facts_count"))
            unsupported_claims = safe_float(item.get("unsupported_claims_count"))
            key_claims = safe_float(item.get("key_claims_count"))
            if factual_errors is not None and key_facts and key_facts > 0:
                fcs_values.append(1.0 - factual_errors / key_facts)
            if unsupported_claims is not None and key_claims and key_claims > 0:
                ts_values.append(1.0 - unsupported_claims / key_claims)
            rdr = safe_float(item.get("RDR_score"))
            eor = safe_float(item.get("EOR_score"))
            if rdr is not None:
                rdr_values.append(rdr)
            if eor is not None:
                eor_values.append(eor)
        output.append(
            {
                "method": method,
                "ICS_mean": round(sum(ics_values) / len(ics_values), 4) if ics_values else "",
                "FCS_mean": round(sum(fcs_values) / len(fcs_values), 4) if fcs_values else "",
                "TS_mean": round(sum(ts_values) / len(ts_values), 4) if ts_values else "",
                "RDR_mean": round(sum(rdr_values) / len(rdr_values), 4) if rdr_values else "",
                "EOR_mean": round(sum(eor_values) / len(eor_values), 4) if eor_values else "",
                "n_rows": len(items),
            }
        )
    return output


def extract_claim_candidates(report_text: str) -> list[str]:
    """Split report text into lightweight claim candidates for traceability review."""
    normalized = re.sub(r"\s+", " ", report_text).strip()
    if not normalized:
        return []
    parts = re.split(r"[。！？；;\n]+", normalized)
    claims = []
    for part in parts:
        cleaned = part.strip("  \t-")
        if len(cleaned) >= 8:
            claims.append(cleaned)
    return claims
