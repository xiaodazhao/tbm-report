from __future__ import annotations

from copy import deepcopy
from typing import Any

LLM_SUMMARY_SCHEMA_VERSION = "tbm_llm_summary_v4"
NO_TEXT = "暂无"


def _non_empty(*values: Any) -> Any:
    """Return the first non-empty value."""
    for value in values:
        if value not in (None, "", {}, []):
            return value
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    """Return a dict fallback."""
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Return a list fallback."""
    return deepcopy(value) if isinstance(value, list) else []


def _safe_text(value: Any, default: str = NO_TEXT) -> str:
    """Return compact text while refusing raw structured objects."""
    if value is None:
        return default
    if isinstance(value, dict):
        preferred = _non_empty(
            value.get("text"),
            value.get("summary_text"),
            value.get("advice_text"),
            value.get("forward_advice_text"),
            value.get("comparison_text"),
            value.get("message"),
        )
        if preferred is None:
            return default
        return _safe_text(preferred, default=default)
    if isinstance(value, (list, tuple, set)):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return "；".join(cleaned) if cleaned else default
    text = str(value).strip()
    return text or default


def build_response_anomaly_summary(
    coupling_summary: dict[str, Any] | None,
    high_attention_segments: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build a segment-level response anomaly view separate from cluster states."""
    coupling_summary = coupling_summary if isinstance(coupling_summary, dict) else {}
    high_attention_segments = high_attention_segments if isinstance(high_attention_segments, list) else []
    primary = high_attention_segments[0] if high_attention_segments else {}

    rai = float(primary.get("RAI", primary.get("response_anomaly_index", 0)) or 0)
    anomaly_type = primary.get("anomaly_type")
    segment_name = (
        primary.get("segment")
        or primary.get("segment_name")
        or primary.get("chainage_range_dk")
        or primary.get("chainage_range")
    )

    has_response_anomaly = bool(primary) and (
        rai > 0
        or anomaly_type
        or primary.get("stop_anomaly")
        or primary.get("efficiency_anomaly")
        or primary.get("param_anomaly")
    )

    anomaly_flags = []
    if primary.get("stop_anomaly"):
        anomaly_flags.append("停机异常")
    if primary.get("efficiency_anomaly"):
        anomaly_flags.append("效率异常")
    if primary.get("param_anomaly"):
        anomaly_flags.append("参数异常")
    if anomaly_type:
        anomaly_flags.append(str(anomaly_type))

    if has_response_anomaly and segment_name:
        summary_text = (
            f"已开挖区段中的主要响应异常关注段为 {segment_name}，"
            f"RAI={rai:.2f}，"
            f"异常表现为{_safe_text(anomaly_flags)}。"
        )
    else:
        summary_text = "当前未形成明确的区段级施工响应异常摘要。"

    return {
        "state_space": "response_anomaly",
        "level": "segment_window",
        "has_response_anomaly": has_response_anomaly,
        "high_attention_segment_count": len(high_attention_segments),
        "primary_segment": deepcopy(primary),
        "primary_segment_name": segment_name,
        "RAI": rai,
        "anomaly_type": anomaly_type,
        "anomaly_flags": anomaly_flags,
        "summary_text": summary_text,
        "coupling_summary_text": coupling_summary.get("summary_text"),
    }


def normalize_llm_summary(llm_summary: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize current and legacy llm_summary payloads into one stable schema."""
    summary = llm_summary if isinstance(llm_summary, dict) else {}

    operation_summary = _as_dict(
        _non_empty(
            summary.get("operation_mode_summary"),
            summary.get("operation_summary"),
            summary.get("基础工况统计"),
        )
    )
    if operation_summary and "state_space" not in operation_summary:
        operation_summary = {
            "state_space": "operation_mode",
            "level": "record_window",
            "stats": deepcopy(operation_summary.get("stats", operation_summary)),
        }

    cluster_summary = _as_dict(
        _non_empty(
            summary.get("cluster_state_summary"),
            summary.get("state_summary"),
        )
    )
    if not cluster_summary:
        cluster_summary = {
            "state_space": "cluster_state",
            "level": "record_window",
            "labels": _as_dict(_non_empty(summary.get("施工状态标签"), summary.get("state_labels"))),
            "stats": _as_dict(_non_empty(summary.get("施工状态统计"), summary.get("state_stats"))),
            "efficiency_table": _as_list(_non_empty(summary.get("施工状态效率表"), summary.get("efficiency_table"))),
            "valid_samples": _non_empty(summary.get("valid_samples"), summary.get("有效状态样本数"), 0) or 0,
            "config": _as_dict(_non_empty(summary.get("cluster_config"), summary.get("状态识别配置"))),
        }

    gas_summary = _as_dict(_non_empty(summary.get("gas_summary"), summary.get("气体统计")))
    if gas_summary and "stats" not in gas_summary:
        gas_summary = {
            "stats": deepcopy(gas_summary),
            "text": _safe_text(summary.get("gas_text"), default=NO_TEXT),
        }

    geology_record = _as_dict(_non_empty(summary.get("geology_summary_record"), summary.get("地质摘要_记录级")))
    geology_segment = _as_dict(_non_empty(summary.get("geology_summary_segment"), summary.get("地质摘要_区段级")))
    excavated_segment_summary = _as_dict(_non_empty(summary.get("excavated_segment_summary")))
    if not excavated_segment_summary:
        excavated_segment_summary = {
            "level": "excavated_segment",
            "summary": deepcopy(geology_segment),
            "typical_segments": _as_list(_non_empty(summary.get("typical_segments"), summary.get("典型地质区段"))),
            "text": _safe_text(
                _non_empty(
                    summary.get("excavated_segment_text"),
                    summary.get("geo_text"),
                    geology_segment.get("summary_text"),
                ),
                default=NO_TEXT,
            ),
        }

    face_description = _as_dict(_non_empty(summary.get("face_description")))
    if not face_description:
        face_description = {
            "level": "current_face",
            "text": _safe_text(summary.get("face_geo_text"), default=NO_TEXT),
        }

    forward_risk_summary = _as_dict(
        _non_empty(
            summary.get("forward_risk_summary"),
            summary.get("前方风险提示摘要"),
        )
    )
    forward_risk_text = _safe_text(
        _non_empty(
            summary.get("forward_risk_text"),
            summary.get("前方风险提示文本"),
            forward_risk_summary.get("forward_advice_text"),
            forward_risk_summary.get("advice_text"),
        ),
        default=NO_TEXT,
    )

    coupling_summary = _as_dict(
        _non_empty(
            summary.get("coupling_summary"),
            summary.get("区段风险-施工响应耦合分析"),
            summary.get("区段地质-施工耦合分析"),
        )
    )
    response_anomaly_summary = _as_dict(
        _non_empty(summary.get("response_anomaly_summary"))
    )
    if not response_anomaly_summary:
        response_anomaly_summary = build_response_anomaly_summary(
            coupling_summary,
            _as_list(
                _non_empty(
                    summary.get("top_rai_segments"),
                    coupling_summary.get("top_rai_segments"),
                    summary.get("high_attention_segments"),
                    coupling_summary.get("high_attention_segments"),
                    coupling_summary.get("top_segments"),
                )
            ),
        )

    digital_twin_state = _as_dict(
        _non_empty(
            summary.get("digital_twin_state"),
            summary.get("数字孪生状态"),
        )
    )
    cst_state = _as_dict(_non_empty(summary.get("cst_state"), summary.get("CST"), summary.get("Construction State Twin")))
    explicit_twin_state = _as_dict(_non_empty(summary.get("twin_state")))
    prompt_evidence_pack = _as_dict(_non_empty(summary.get("prompt_evidence_pack")))
    history_comparison = _as_dict(
        _non_empty(
            summary.get("history_comparison"),
            summary.get("施工历史记忆对比"),
        )
    )

    prompt_text_inputs = _as_dict(summary.get("prompt_text_inputs"))
    prompt_text_inputs.setdefault(
        "excavated_segment_text",
        _safe_text(excavated_segment_summary.get("text"), default=NO_TEXT),
    )
    prompt_text_inputs.setdefault(
        "face_description_text",
        _safe_text(face_description.get("text"), default=NO_TEXT),
    )
    prompt_text_inputs.setdefault("forward_risk_text", forward_risk_text)
    prompt_text_inputs.setdefault(
        "response_anomaly_text",
        _safe_text(response_anomaly_summary.get("summary_text"), default=NO_TEXT),
    )
    prompt_text_inputs.setdefault(
        "coupling_text",
        _safe_text(coupling_summary.get("summary_text"), default=NO_TEXT),
    )
    prompt_text_inputs.setdefault(
        "history_comparison_text",
        _safe_text(history_comparison.get("comparison_text"), default=NO_TEXT),
    )
    if cst_state:
        try:
            from services.cst_update_service import summarize_cst_for_prompt

            twin_text = summarize_cst_for_prompt(cst_state)
        except Exception:
            twin_text = _safe_text(summary.get("digital_twin_text"), default=NO_TEXT)
    else:
        twin_text = _safe_text(summary.get("digital_twin_text"), default=NO_TEXT)
    prompt_text_inputs.setdefault("digital_twin_text", twin_text)

    plc_quality_report = _as_dict(summary.get("plc_quality_report"))
    operation_context = _as_dict(summary.get("operation_context"))
    cluster_context = _as_dict(summary.get("cluster_context"))
    gas_context = _as_dict(summary.get("gas_context"))
    cell_response_summary = _as_dict(summary.get("cell_response_summary"))

    return {
        "schema_version": summary.get("schema_version") or LLM_SUMMARY_SCHEMA_VERSION,
        "operation_mode_summary": operation_summary or {
            "state_space": "operation_mode",
            "level": "record_window",
            "stats": {},
        },
        "cluster_state_summary": cluster_summary,
        "gas_summary": gas_summary,
        "geology_summary_record": geology_record,
        "geology_summary_segment": geology_segment,
        "excavated_segment_summary": excavated_segment_summary,
        "face_description": face_description,
        "forward_risk_summary": forward_risk_summary,
        "forward_risk_text": forward_risk_text,
        "response_anomaly_summary": response_anomaly_summary,
        "coupling_summary": coupling_summary,
        "top_grci_segments": _as_list(_non_empty(summary.get("top_grci_segments"), coupling_summary.get("top_grci_segments"), coupling_summary.get("high_attention_segments"), coupling_summary.get("top_segments"))),
        "top_grs_segments": _as_list(_non_empty(summary.get("top_grs_segments"), coupling_summary.get("top_grs_segments"))),
        "top_rai_segments": _as_list(_non_empty(summary.get("top_rai_segments"), coupling_summary.get("top_rai_segments"))),
        "weak_label_validation": _as_dict(_non_empty(summary.get("weak_label_validation"), coupling_summary.get("weak_label_validation"), summary.get("coupling_validation"))),
        "digital_twin_state": digital_twin_state,
        "cst_state": cst_state,
        "twin_state": explicit_twin_state or cst_state or digital_twin_state,
        "prompt_evidence_pack": prompt_evidence_pack,
        "history_comparison": history_comparison,
        "plc_quality_report": plc_quality_report,
        "operation_context": operation_context,
        "cluster_context": cluster_context,
        "gas_context": gas_context,
        "cell_response_summary": cell_response_summary,
        "prompt_text_inputs": prompt_text_inputs,
    }


def build_prompt_payload(
    llm_summary: dict[str, Any] | None,
    *,
    fallbacks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build prompt-safe text inputs from structured llm_summary plus explicit fallbacks."""
    normalized = normalize_llm_summary(llm_summary)
    fallbacks = fallbacks if isinstance(fallbacks, dict) else {}
    prompt_text_inputs = deepcopy(normalized.get("prompt_text_inputs", {}))

    text_map = {
        "operation_segments_text": _safe_text(
            _non_empty(prompt_text_inputs.get("operation_segments_text"), fallbacks.get("seg_text"))
        ),
        "operation_stats_text": _safe_text(
            _non_empty(prompt_text_inputs.get("operation_stats_text"), fallbacks.get("stats_text"))
        ),
        "cluster_state_text": _safe_text(
            _non_empty(prompt_text_inputs.get("cluster_state_text"), fallbacks.get("state_text"))
        ),
        "cluster_efficiency_text": _safe_text(
            _non_empty(prompt_text_inputs.get("cluster_efficiency_text"), fallbacks.get("eff_text"))
        ),
        "cluster_state_stats_text": _safe_text(
            _non_empty(prompt_text_inputs.get("cluster_state_stats_text"), fallbacks.get("state_stats_text"))
        ),
        "gas_text": _safe_text(
            _non_empty(prompt_text_inputs.get("gas_text"), fallbacks.get("gas_text"))
        ),
        "face_description_text": _safe_text(
            _non_empty(prompt_text_inputs.get("face_description_text"), fallbacks.get("face_geo_text"))
        ),
        "excavated_segment_text": _safe_text(
            _non_empty(prompt_text_inputs.get("excavated_segment_text"), fallbacks.get("geo_text"))
        ),
        "forward_risk_text": _safe_text(
            _non_empty(prompt_text_inputs.get("forward_risk_text"), fallbacks.get("forward_risk_text"))
        ),
        "response_anomaly_text": _safe_text(prompt_text_inputs.get("response_anomaly_text")),
        "coupling_text": _safe_text(prompt_text_inputs.get("coupling_text")),
        "digital_twin_text": _safe_text(
            _non_empty(prompt_text_inputs.get("digital_twin_text"), fallbacks.get("digital_twin_text"))
        ),
        "history_comparison_text": _safe_text(prompt_text_inputs.get("history_comparison_text")),
        "risk_profile_text": _safe_text(
            _non_empty(prompt_text_inputs.get("risk_profile_text"), fallbacks.get("risk_prob_text"))
        ),
    }

    cst_state = normalized.get("cst_state", {})
    if isinstance(cst_state, dict) and cst_state:
        from services.cst_update_service import summarize_cst_for_prompt

        summary_block = summarize_cst_for_prompt(cst_state)
    else:
        operation_stats = _as_dict(normalized.get("operation_mode_summary", {}).get("stats"))
        geology_summary = _as_dict(normalized.get("geology_summary_segment"))
        forward_summary = _as_dict(normalized.get("forward_risk_summary"))
        response_summary = _as_dict(normalized.get("response_anomaly_summary"))
        summary_block = "\n".join(
            [
                f"- 运行工况：工作 {operation_stats.get('work_total_min', 0)} min，停机 {operation_stats.get('stop_total_min', 0)} min，异常 {operation_stats.get('abnormal_count', 0)} 段。",
                f"- 已开挖区段：高地质关注区段 {geology_summary.get('high_geo_attention_segment_count', geology_summary.get('high_risk_segment_count', 0))} 个，多报告-来源支持区段 {geology_summary.get('multi_report_source_segment_count', geology_summary.get('multi_source_segment_count', 0))} 个。",
                f"- 前方提示：等级 {forward_summary.get('forward_advice_level', forward_summary.get('advice_level', '暂无'))}，证据记录 {forward_summary.get('forward_evidence_count', forward_summary.get('forward_segment_count', 0))} 条，主要关注 {_safe_text(forward_summary.get('forward_main_hazard_tags', forward_summary.get('main_hazards')))}。",
                f"- 响应异常：{_safe_text(response_summary.get('summary_text'))}",
            ]
        )

    operation_context = _as_dict(normalized.get("operation_context"))
    cluster_context = _as_dict(normalized.get("cluster_context"))
    gas_context = _as_dict(normalized.get("gas_context"))
    plc_quality_report = _as_dict(normalized.get("plc_quality_report"))
    cell_response_summary = _as_dict(normalized.get("cell_response_summary"))
    twin_state = _as_dict(normalized.get("twin_state"))
    prompt_evidence_pack = _as_dict(normalized.get("prompt_evidence_pack"))
    plc_lines = []
    if twin_state:
        plc_lines.append("- 已提供 TwinState，结构化状态应优先于自然语言兜底文本。")
    if prompt_evidence_pack:
        plc_lines.append("- 已提供 PromptEvidencePack，prompt 生成应优先使用结构化证据包。")
    if plc_quality_report:
        plc_lines.append(
            f"- PLC 数据质量：样本数={plc_quality_report.get('row_count', 0)}，"
            f"数据质量告警数={len(plc_quality_report.get('warnings', []) or [])}。"
        )
    if operation_context:
        op_summary = _as_dict(operation_context.get("operation_mode_summary"))
        plc_lines.append(
            f"- 基础工况：主导工况={op_summary.get('dominant_mode_cn') or op_summary.get('dominant_mode') or '暂无'}，"
            f"工作={op_summary.get('work_total_min', 0)} min，停机={op_summary.get('stop_total_min', 0)} min。"
        )
    if cluster_context:
        cluster_quality = _as_dict(cluster_context.get("cluster_quality"))
        plc_lines.append(
            f"- 聚类状态：状态数={cluster_context.get('n_states', 0)}，"
            f"有效样本={cluster_quality.get('valid_sample_count', 0)}，"
            f"稳定性={'是' if cluster_quality.get('is_stable_enough') else '否'}。"
        )
    if gas_context:
        exceed_summary = _as_dict(gas_context.get("exceed_summary"))
        plc_lines.append(
            f"- 气体状态：超阈值字段数={len(exceed_summary.get('exceed_gases', []) or [])}，"
            f"超阈值事件总数={exceed_summary.get('exceed_event_count_total', 0)}。"
        )
    if cell_response_summary:
        plc_lines.append(
            f"- Cell 响应摘要：高响应 cell 数={cell_response_summary.get('high_response_cell_count', 0)}。"
        )
    if plc_lines:
        summary_block = summary_block + "\n" + "\n".join(plc_lines)

    return {
        "normalized_summary": normalized,
        "summary_block": summary_block,
        "texts": text_map,
    }
