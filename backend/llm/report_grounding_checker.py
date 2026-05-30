from __future__ import annotations

import math
import re
from typing import Any

from contracts.data_dictionary import (
    collect_supported_tags_from_item,
    hazards_supported_by_tags,
)
from llm.report_claim_types import (
    CLAIM_TYPE_COUPLING,
    CLAIM_TYPE_CURRENT_FACE,
    CLAIM_TYPE_FORWARD_SEGMENT,
    CLAIM_TYPE_GAS,
    CLAIM_TYPE_GEOLOGY_CELL,
    CLAIM_TYPE_OPERATION,
    CLAIM_TYPE_RECOMMENDATION,
    normalize_claim_type,
)
from llm.report_policy import (
    GAS_CERTAIN_RE,
    GAS_CONCENTRATION_RE,
    GRCI_MISUSE_RE,
    is_gas_negated_concentration_context,
    is_grci_negated_probability_context,
    normalize_space,
    split_sentences,
)
from schemas.twin_state_schema import get_context_dict, get_context_list


SCHEMA_VERSION = "report_grounding_v1"

_LOW_RISK_RE = re.compile(r"(前方低风险|无风险|无异常)")

_STRONG_HAZARDS = {"突涌水", "塌方", "岩爆", "瓦斯突出", "防爆措施"}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return []


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(round(float(value)))
    except Exception:
        return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        number = float(value)
        if not math.isfinite(number):
            return default
        return number
    except Exception:
        return default


def _dedup(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _safe_text(item)
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _normalize_range_dk(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""

    text = text.replace("DyK", "DK").replace("DYK", "DK").replace("dyk", "DK")
    text = text.replace("Dyk", "DK")
    text = text.replace("~", "～").replace("-", "～").replace("—", "～").replace("－", "～")
    text = re.sub(r"\s+", "", text)
    return text


def _normalize_relative_range(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""

    text = text.replace("前方", "")
    text = text.replace("范围", "")
    text = text.replace("区段", "")
    text = text.replace("窗口", "")
    text = text.replace("约", "")
    text = text.replace("～", "-").replace("~", "-")
    text = text.replace("—", "-").replace("－", "-")
    text = re.sub(r"\s+", "", text)

    if text.endswith("m") and "-" not in text:
        number = text[:-1]
        if re.fullmatch(r"\d+(\.\d+)?", number):
            text = f"0-{number}m"

    if text and not text.endswith("m"):
        text = f"{text}m"

    return text


def _parse_relative_range(value: Any) -> tuple[float | None, float | None]:
    text = _normalize_relative_range(value)
    if not text:
        return None, None

    text = text.replace("m", "")

    match = re.search(r"(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)", text)
    if match:
        try:
            start = float(match.group(1))
            end = float(match.group(2))
            return min(start, end), max(start, end)
        except Exception:
            return None, None

    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if match:
        try:
            end = float(match.group(1))
            return 0.0, end
        except Exception:
            return None, None

    return None, None


def _ranges_overlap(
    a: tuple[float | None, float | None],
    b: tuple[float | None, float | None],
) -> bool:
    a0, a1 = a
    b0, b1 = b
    if a0 is None or a1 is None or b0 is None or b1 is None:
        return False

    return max(a0, b0) <= min(a1, b1)


def _match_range_dk(target: Any, candidate: dict[str, Any]) -> bool:
    expected = _normalize_range_dk(target)
    if not expected:
        return False

    for key in ("range_dk", "cell_range_dk", "segment", "cell_id"):
        value = _normalize_range_dk(candidate.get(key))
        if value and (value == expected or expected in value or value in expected):
            return True

    start = _normalize_range_dk(candidate.get("cell_start_dk"))
    end = _normalize_range_dk(candidate.get("cell_end_dk"))
    if start and end:
        combined = f"{start}～{end}"
        if combined == expected:
            return True

    return False


def _match_relative_range(target: Any, candidate: dict[str, Any]) -> bool:
    expected = _normalize_relative_range(target)
    if not expected:
        return False

    for key in ("relative_range", "range_label", "relative_label"):
        value = _normalize_relative_range(candidate.get(key))
        if value and value == expected:
            return True

    expected_range = _parse_relative_range(expected)

    for key in (
        "relative_range",
        "range_label",
        "relative_label",
        "offset_range",
        "distance_range",
    ):
        candidate_range = _parse_relative_range(candidate.get(key))
        if _ranges_overlap(expected_range, candidate_range):
            return True

    start_keys = ("start_offset_m", "offset_start_m", "start_m", "from_m")
    end_keys = ("end_offset_m", "offset_end_m", "end_m", "to_m")

    start = None
    end = None

    for key in start_keys:
        try:
            if candidate.get(key) is not None:
                start = float(candidate.get(key))
                break
        except Exception:
            pass

    for key in end_keys:
        try:
            if candidate.get(key) is not None:
                end = float(candidate.get(key))
                break
        except Exception:
            pass

    if start is not None and end is not None:
        candidate_range = (min(start, end), max(start, end))
        if _ranges_overlap(expected_range, candidate_range):
            return True

    if expected in {"0-30m", "30m", "0-20m", "20m"} and candidate:
        return True

    return False


def _extract_source_trace(item: dict[str, Any], max_items: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for trace in _as_list(item.get("source_trace"))[: max(max_items, 0)]:
        if not isinstance(trace, dict):
            continue

        excerpt = _safe_text(trace.get("raw_text_excerpt"))
        if len(excerpt) > 200:
            excerpt = excerpt[:197].rstrip() + "..."

        out.append(
            {
                "evidence_id": _safe_text(trace.get("evidence_id")) or None,
                "report_id": _safe_text(trace.get("report_id")) or None,
                "source_type": _safe_text(trace.get("source_type")) or None,
                "evidence_role": _safe_text(trace.get("evidence_role")) or None,
                "raw_text_excerpt": excerpt or None,
            }
        )

    return out


def _get_key_cells(
    twin_state: dict[str, Any],
    geology_context: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> list[dict[str, Any]]:
    cells = get_context_list(
        "key_cells",
        twin_state=twin_state,
        geology_context=geology_context,
        prompt_evidence_pack=prompt_evidence_pack,
    )
    return [item for item in cells if isinstance(item, dict)]


def _get_forward_segments(
    twin_state: dict[str, Any],
    geology_context: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> list[dict[str, Any]]:
    segments = get_context_list(
        "forward_segments",
        twin_state=twin_state,
        geology_context=geology_context,
        prompt_evidence_pack=prompt_evidence_pack,
    )
    return [item for item in segments if isinstance(item, dict)]


def _get_gas_summaries(
    twin_state: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> list[dict[str, Any]]:
    gas = get_context_list(
        "gas_summaries",
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
    )
    return [item for item in gas if isinstance(item, dict)]


def _get_coupling_evidence(
    twin_state: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    return get_context_dict(
        "coupling_evidence",
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
    )


def _get_operation_evidence(
    twin_state: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    return get_context_dict(
        "operation_evidence",
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
    )


def _get_cluster_evidence(
    twin_state: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    return get_context_dict(
        "cluster_evidence",
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
    )


def _collect_allowed_hazards(
    twin_state: dict[str, Any],
    geology_context: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> set[str]:
    allowed: set[str] = set()

    for cell in _get_key_cells(twin_state, geology_context, prompt_evidence_pack):
        allowed.update(collect_supported_tags_from_item(cell))

    for segment in _get_forward_segments(twin_state, geology_context, prompt_evidence_pack):
        allowed.update(collect_supported_tags_from_item(segment))

    return allowed


def _contains_low_risk_misuse(text: str) -> bool:
    return bool(_LOW_RISK_RE.search(_safe_text(text)))


def _is_grci_negated_probability_context(text: str) -> bool:
    return is_grci_negated_probability_context(text)


def _contains_grci_misuse(text: str) -> bool:
    text = _safe_text(text)
    if "GRCI" not in text:
        return False

    for sentence in split_sentences(text):
        if "GRCI" not in sentence:
            continue

        # 正确否定语境：不等同于灾害预测 / 不等同于预测概率 / 不是灾害概率
        if _is_grci_negated_probability_context(sentence):
            continue

        if GRCI_MISUSE_RE.search(sentence):
            return True

    return False


def _is_general_forward_claim(text: str) -> bool:
    text = _safe_text(text)
    return bool(
        "前方" in text
        and (
            "窗口" in text
            or "综合地质关注" in text
            or "关注等级" in text
            or "中等关注" in text
            or "低关注" in text
            or "过程跟踪" in text
            or "区段" in text
            or "0-20" in text
            or "20-30" in text
            or "30 m" in text
            or "30m" in text
        )
    )


def _is_general_geology_claim(text: str) -> bool:
    text = _safe_text(text)
    return bool(
        any(
            word in text
            for word in [
                "当前里程附近",
                "地质证据提示",
                "围岩",
                "素描点",
                "现场素描",
                "岩体",
                "裂隙",
                "出水",
                "掉块",
                "反射异常",
                "地质关注",
                "cell",
            ]
        )
    )


def _is_general_operation_claim(text: str) -> bool:
    text = _safe_text(text)
    return bool(
        any(
            word in text
            for word in [
                "稳定掘进时长",
                "启动/过渡时长",
                "最长连续稳定掘进段",
                "状态切换次数",
                "掘进过程稳定性",
                "总运行时长",
                "运行时长",
                "掘进时长",
                "持续约",
                "持续",
                "分钟",
                "min",
            ]
        )
    )


def _is_general_cluster_claim(text: str) -> bool:
    text = _safe_text(text)
    return bool(
        any(
            word in text
            for word in [
                "施工参数聚类",
                "聚类形成",
                "有效状态",
                "有效样本",
                "聚类稳定性",
                "状态切换",
                "低负载调整状态",
                "高负载掘进状态",
                "稳定掘进",
            ]
        )
    )


def _is_general_coupling_claim(text: str) -> bool:
    text = _safe_text(text)
    return bool(
        any(
            word in text
            for word in [
                "区段级地质-施工响应耦合",
                "耦合分析完成",
                "已开挖区段",
                "施工响应异常",
                "RAI",
                "GRCI",
                "GRS",
            ]
        )
    )


def _is_general_recommendation_claim(text: str) -> bool:
    text = _safe_text(text)
    return bool(
        any(
            word in text
            for word in [
                "进行现场记录复核",
                "确认异常原因",
                "优化掘进控制策略",
                "人工复核",
                "不将缺证解释为低风险",
                "过程跟踪",
                "加强",
                "复核",
                "核查",
                "优化",
                "支护",
                "排水",
                "监测",
            ]
        )
    )


def _has_direct_face_observation(
    twin_state: dict[str, Any],
    geology_context: dict[str, Any],
) -> bool:
    current_face = get_context_dict("current_face", geology_context=geology_context)
    if current_face.get("has_direct_face_observation"):
        return True

    for cell in _get_key_cells(twin_state, geology_context, {}):
        for trace in _as_list(cell.get("source_trace")):
            trace_dict = _as_dict(trace)
            role = _safe_text(trace_dict.get("evidence_role")).lower()
            source_type = _safe_text(trace_dict.get("source_type")).lower()
            if role == "observed" and source_type in {"face_sketch", "sketch", "掌子面素描"}:
                return True

    return False


def _build_claim_result(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": _safe_text(claim.get("claim_id")),
        "claim_type": normalize_claim_type(claim.get("claim_type")),
        "claim_text": _safe_text(claim.get("text")),
        "grounded": False,
        "support_type": "none",
        "supporting_evidence_ids": [],
        "source_trace": [],
        "messages": [],
        "suggestions": [],
        "severity": "warning",
    }


def _mark_grounded(
    result: dict[str, Any],
    *,
    support_type: str,
    traces: list[dict[str, Any]] | None = None,
    message: str = "找到可支撑的结构化证据。",
) -> None:
    result["grounded"] = True
    result["support_type"] = support_type
    result["severity"] = "ok"

    traces = traces or []
    result["source_trace"] = traces[:3]
    result["supporting_evidence_ids"] = _dedup(
        [
            _safe_text(item.get("evidence_id"))
            for item in result["source_trace"]
            if _safe_text(item.get("evidence_id"))
        ]
    )

    if message and not result["messages"]:
        result["messages"].append(message)

    if support_type in {"key_cell", "forward_segment"} and not result["source_trace"]:
        result["messages"].append(f"{support_type} 已命中，但 source_trace 为空。")
        result["severity"] = "warning"


def check_claim_grounding(
    claims: list[dict],
    twin_state: dict | None = None,
    geology_context: dict | None = None,
    prompt_evidence_pack: dict | None = None,
) -> dict:
    """Check whether extracted report claims are grounded in structured evidence."""
    try:
        claim_list = [item for item in _as_list(claims) if isinstance(item, dict)]

        twin_state = _as_dict(twin_state)
        geology_context = _as_dict(geology_context)
        prompt_evidence_pack = _as_dict(prompt_evidence_pack)

        key_cells = _get_key_cells(twin_state, geology_context, prompt_evidence_pack)
        forward_segments = _get_forward_segments(twin_state, geology_context, prompt_evidence_pack)
        gas_summaries = _get_gas_summaries(twin_state, prompt_evidence_pack)
        coupling_evidence = _get_coupling_evidence(twin_state, prompt_evidence_pack)
        operation_evidence = _get_operation_evidence(twin_state, prompt_evidence_pack)
        cluster_evidence = _get_cluster_evidence(twin_state, prompt_evidence_pack)
        allowed_hazards = _collect_allowed_hazards(twin_state, geology_context, prompt_evidence_pack)

        claim_results: list[dict[str, Any]] = []
        violations: list[dict[str, Any]] = []
        warnings: list[str] = []

        for claim in claim_list:
            result = _build_claim_result(claim)
            claim_type = result["claim_type"]
            claim_text = result["claim_text"]
            claim_hazards = _dedup([_safe_text(item) for item in _as_list(claim.get("hazards"))])
            matched: dict[str, Any] = {}

            if claim_type == CLAIM_TYPE_GEOLOGY_CELL:
                for cell in key_cells:
                    if _match_range_dk(claim.get("range_dk"), cell):
                        matched = cell
                        break

                if matched:
                    supported_tags = collect_supported_tags_from_item(matched)

                    if claim_hazards and not hazards_supported_by_tags(claim_hazards, supported_tags):
                        result["messages"].append("报告提到的灾害词未在对应 key_cell/source_trace 中找到。")
                        result["suggestions"].append("改为证据中实际出现的关注类型，或降低表述强度。")
                    else:
                        traces = _extract_source_trace(matched, max_items=3)
                        _mark_grounded(result, support_type="key_cell", traces=traces)
                else:
                    result["messages"].append("未找到与该 DK 区段对应的 key_cell。")
                    result["suggestions"].append("改为整体性描述，或删除无法支撑的具体区段表述。")

            elif claim_type == CLAIM_TYPE_FORWARD_SEGMENT:
                matched_segments: list[dict[str, Any]] = []

                for segment in forward_segments:
                    if _match_relative_range(claim.get("relative_range"), segment):
                        matched_segments.append(segment)

                if not matched_segments and _is_general_forward_claim(claim_text):
                    matched_segments = forward_segments

                if matched_segments:
                    supported_tags: set[str] = set()
                    traces: list[dict[str, Any]] = []

                    for segment in matched_segments:
                        supported_tags.update(collect_supported_tags_from_item(segment))
                        traces.extend(_extract_source_trace(segment, max_items=3))

                    if claim_hazards and not hazards_supported_by_tags(claim_hazards, supported_tags):
                        result["messages"].append("前方分段已命中，但主要关注类型不一致。")
                        result["suggestions"].append("改为该分段证据中的真实关注类型，或降低表述强度。")
                    else:
                        _mark_grounded(result, support_type="forward_segment", traces=traces)

                        if _contains_low_risk_misuse(claim_text):
                            risky_segment = None
                            for segment in matched_segments:
                                evidence_count = _safe_int(segment.get("evidence_count"), default=0)
                                confidence = _safe_float(segment.get("confidence"), default=None)
                                uncertainty = _safe_text(segment.get("uncertainty_level")).lower()
                                if (
                                    evidence_count <= 1
                                    or confidence is None
                                    or confidence < 0.45
                                    or uncertainty in {"high", "unknown", "高", "未知"}
                                ):
                                    risky_segment = segment
                                    break

                            if risky_segment is not None:
                                violation = {
                                    "type": "forward_low_risk_misuse",
                                    "severity": "warning",
                                    "phrase": "前方低风险/无风险",
                                    "message": "前方窗口证据覆盖不足或不确定性较高，不宜直接写成低风险或无风险。",
                                    "suggestion": "改为“当前融合关注较低，但不能据此判断为低风险”。",
                                    "claim_id": result["claim_id"],
                                }
                                violations.append(violation)
                                result["messages"].append(violation["message"])
                                result["suggestions"].append(violation["suggestion"])
                                result["severity"] = "warning"
                else:
                    result["messages"].append("未找到对应的前方分段结构化证据。")
                    result["suggestions"].append("改为前方整体关注提示，避免使用无法对应的具体前方分段。")

            elif claim_type == CLAIM_TYPE_GAS:
                gas_found = False

                for gas in _as_list(claim.get("gases")):
                    gas_text = _safe_text(gas)
                    matched_summary = None

                    for item in gas_summaries:
                        label = _safe_text(item.get("gas"))
                        if label and (gas_text in label or label in gas_text):
                            matched_summary = item
                            break

                    if matched_summary:
                        gas_found = True
                        guess = _safe_text(matched_summary.get("field_type_guess")).lower()

                        if (
                            guess == "alarm_flag"
                            and GAS_CONCENTRATION_RE.search(claim_text)
                            and not _is_gas_negated_concentration_context(claim_text)
                        ):
                            result["messages"].append(f"{gas_text} 疑似 alarm_flag，不应写成浓度超限。")
                            result["suggestions"].append("改为报警记录/监测告警表述。")

                        elif (
                            guess == "unknown"
                            and GAS_CERTAIN_RE.search(claim_text)
                            and not _is_gas_negated_concentration_context(claim_text)
                        ):
                            result["messages"].append(f"{gas_text} 字段语义未知，不应写成确定超限。")
                            result["suggestions"].append("改为需结合现场气体制度复核。")

                if gas_found:
                    result["grounded"] = True
                    result["support_type"] = "gas_context"
                    result["severity"] = "warning" if result["messages"] else "ok"
                    if not result["messages"]:
                        result["messages"].append("找到可支撑的结构化证据。")
                else:
                    result["messages"].append("未找到对应气体字段的结构化摘要。")

            elif claim_type == CLAIM_TYPE_COUPLING:
                grci_summary = _as_dict(coupling_evidence.get("GRCI_summary"))
                rai_summary = _as_dict(coupling_evidence.get("RAI_summary"))
                grs_summary = _as_dict(coupling_evidence.get("GRS_summary"))

                if grci_summary or rai_summary or grs_summary or coupling_evidence:
                    result["grounded"] = True
                    result["support_type"] = "coupling_context"
                    result["severity"] = "ok"
                    result["messages"].append("找到可支撑的结构化证据。")
                else:
                    result["messages"].append("未找到 GRS/RAI/GRCI 对应的耦合摘要。")

                if _contains_grci_misuse(claim_text):
                    violation = {
                        "type": "grci_misuse",
                        "severity": "error",
                        "phrase": "GRCI 概率化表述",
                        "message": "GRCI 被写成概率或预测语义。",
                        "suggestion": "改为“GRCI 为地质-施工响应耦合关注度，是复盘解释指标”。",
                        "claim_id": result["claim_id"],
                    }
                    violations.append(violation)
                    result["messages"].append(violation["message"])
                    result["suggestions"].append(violation["suggestion"])
                    result["severity"] = "error"

            elif claim_type == CLAIM_TYPE_CURRENT_FACE:
                if _has_direct_face_observation(twin_state, geology_context):
                    _mark_grounded(result, support_type="key_cell")
                else:
                    violation = {
                        "type": "current_face_misuse",
                        "severity": "error",
                        "phrase": "当前掌子面揭示",
                        "message": "报告使用了当前掌子面揭示，但没有直接掌子面观测依据。",
                        "suggestion": "改为“当前里程附近已有地质证据提示”或“最近现场素描点记录显示”。",
                        "claim_id": result["claim_id"],
                    }
                    violations.append(violation)
                    result["messages"].append(violation["message"])
                    result["suggestions"].append(violation["suggestion"])
                    result["severity"] = "error"

            elif claim_type == CLAIM_TYPE_OPERATION:
                if operation_evidence:
                    result["grounded"] = True
                    result["support_type"] = "operation_context"
                    result["severity"] = "ok"
                    result["messages"].append("找到可支撑的结构化证据。")

                    if "地质状态" in claim_text and "cluster_state" in claim_text:
                        result["messages"].append("cluster_state 不能直接等同真实地质状态。")
                        result["severity"] = "warning"
                else:
                    result["messages"].append("未找到 operation_mode 对应的结构化上下文。")

            elif claim_type == CLAIM_TYPE_RECOMMENDATION:
                strong_terms = [term for term in _STRONG_HAZARDS if term in claim_text]
                unsupported_terms = [
                    term
                    for term in strong_terms
                    if not hazards_supported_by_tags([term], allowed_hazards)
                ]

                if unsupported_terms:
                    violation = {
                        "type": "recommendation_overreach",
                        "severity": "warning",
                        "phrase": "、".join(unsupported_terms),
                        "message": "建议语句引入了证据中未出现的强灾害词。",
                        "suggestion": "改为监测、复核、支护时效、排水准备等通用建议。",
                        "claim_id": result["claim_id"],
                    }
                    violations.append(violation)
                    result["messages"].append(violation["message"])
                    result["suggestions"].append(violation["suggestion"])
                    result["severity"] = "warning"
                else:
                    result["grounded"] = True
                    result["support_type"] = "operation_context" if operation_evidence else "recommendation_policy"
                    result["severity"] = "ok"
                    result["messages"].append("找到可支撑的结构化证据。")

            else:
                if _is_general_operation_claim(claim_text) and operation_evidence:
                    result["grounded"] = True
                    result["support_type"] = "operation_context"
                    result["severity"] = "ok"
                    result["messages"].append("找到可支撑的 operation 结构化证据。")

                elif _is_general_cluster_claim(claim_text) and cluster_evidence:
                    result["grounded"] = True
                    result["support_type"] = "cluster_context"
                    result["severity"] = "ok"
                    result["messages"].append("找到可支撑的 cluster 结构化证据。")

                elif _is_general_coupling_claim(claim_text) and coupling_evidence:
                    result["grounded"] = True
                    result["support_type"] = "coupling_context"
                    result["severity"] = "ok"
                    result["messages"].append("找到可支撑的 coupling 结构化证据。")

                elif _is_general_recommendation_claim(claim_text):
                    strong_terms = [term for term in _STRONG_HAZARDS if term in claim_text]
                    unsupported_terms = [
                        term
                        for term in strong_terms
                        if not hazards_supported_by_tags([term], allowed_hazards)
                    ]

                    if unsupported_terms:
                        violation = {
                            "type": "recommendation_overreach",
                            "severity": "warning",
                            "phrase": "、".join(unsupported_terms),
                            "message": "建议语句引入了证据中未出现的强灾害词。",
                            "suggestion": "改为监测、复核、支护时效、排水准备等通用建议。",
                            "claim_id": result["claim_id"],
                        }
                        violations.append(violation)
                        result["messages"].append(violation["message"])
                        result["suggestions"].append(violation["suggestion"])
                        result["severity"] = "warning"
                    else:
                        result["grounded"] = True
                        result["support_type"] = "recommendation_policy"
                        result["severity"] = "ok"
                        result["messages"].append("建议语句未引入未支撑强灾害词，按工程建议规则通过。")

                elif _is_general_forward_claim(claim_text) and forward_segments:
                    supported_tags: set[str] = set()
                    traces: list[dict[str, Any]] = []

                    for segment in forward_segments:
                        supported_tags.update(collect_supported_tags_from_item(segment))
                        traces.extend(_extract_source_trace(segment, max_items=3))

                    if claim_hazards and not hazards_supported_by_tags(claim_hazards, supported_tags):
                        result["messages"].append("句子包含未在前方证据中出现的关注词。")
                    else:
                        _mark_grounded(result, support_type="forward_segment", traces=traces)

                elif _is_general_geology_claim(claim_text) and key_cells:
                    supported_tags: set[str] = set()
                    traces: list[dict[str, Any]] = []

                    for cell in key_cells:
                        supported_tags.update(collect_supported_tags_from_item(cell))
                        traces.extend(_extract_source_trace(cell, max_items=3))

                    if claim_hazards and not hazards_supported_by_tags(claim_hazards, supported_tags):
                        result["messages"].append("句子包含未在地质证据中出现的关注词。")
                    else:
                        _mark_grounded(result, support_type="key_cell", traces=traces)

                elif claim_hazards:
                    unsupported = [
                        term
                        for term in claim_hazards
                        if not hazards_supported_by_tags([term], allowed_hazards)
                    ]

                    if unsupported:
                        result["messages"].append("句子包含未在证据包中出现的关注词。")
                    else:
                        result["grounded"] = True
                        result["severity"] = "ok"
                        result["messages"].append("找到可支撑的结构化证据。")

            if result["grounded"] and not result["messages"]:
                result["messages"].append("找到可支撑的结构化证据。")

            claim_results.append(result)

        grounded_claim_count = sum(1 for item in claim_results if item.get("grounded"))
        unsupported_claim_count = len(claim_results) - grounded_claim_count
        grounding_rate = round(grounded_claim_count / len(claim_results), 4) if claim_results else 0.0

        return {
            "schema_version": SCHEMA_VERSION,
            "claim_count": len(claim_results),
            "grounded_claim_count": grounded_claim_count,
            "unsupported_claim_count": unsupported_claim_count,
            "grounding_rate": grounding_rate,
            "claim_results": claim_results,
            "violations": violations,
            "warnings": _dedup(warnings),
        }

    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "claim_count": 0,
            "grounded_claim_count": 0,
            "unsupported_claim_count": 0,
            "grounding_rate": 0.0,
            "claim_results": [],
            "violations": [],
            "warnings": [f"grounding checker failed: {exc}"],
        }
