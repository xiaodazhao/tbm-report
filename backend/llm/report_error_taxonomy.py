from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


ERROR_TYPES = [
    "E1_UNSUPPORTED_CLAIM",
    "E2_FORECAST_AS_FACT",
    "E3_GRCI_AS_PROBABILITY",
    "E4_FORWARD_AS_EXCAVATED_REVIEW",
    "E5_BACKGROUND_AS_DAILY_RESPONSE",
    "E6_GAS_FIELD_MISUSE",
    "E7_UNSUPPORTED_RECOMMENDATION",
    "E8_MISSING_REQUIRED_SECTION",
    "E9_SOURCE_ROLE_CONFUSION",
    "E10_NUMERIC_VALUE_UNGROUNDED",
    "E11_HEADING_FALSE_POSITIVE",
    "E12_METHOD_BOUNDARY_STATEMENT",
    "E13_STOP_REASON_OVERINTERPRETATION",
    "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE",
]

SUPPORT_TYPES = [
    "statistical_support",
    "daily_review_support",
    "forward_attention_support",
    "local_background_support",
    "observed_support",
    "forecast_support",
    "policy_support",
    "none",
]

SOURCE_ROLES = [
    "daily_review_evidence",
    "forward_attention_evidence",
    "local_background_evidence",
    "excluded_by_distance",
    "excluded_by_time",
    "unknown",
]


def classify_violation(violation: dict[str, Any]) -> str:
    """Map a quality violation to the method-level error taxonomy."""
    explicit = _text(violation.get("error_type"))
    if explicit in ERROR_TYPES:
        return explicit

    type_ = _text(violation.get("type"))
    phrase = _text(violation.get("phrase"))
    message = _text(violation.get("message"))
    combined = f"{type_} {phrase} {message}"

    if type_ == "missing_section":
        return "E8_MISSING_REQUIRED_SECTION"
    if type_ == "grci_misuse" or "GRCI" in combined and ("概率" in combined or "灾害概率" in combined or "风险概率" in combined):
        return "E3_GRCI_AS_PROBABILITY"
    if type_ == "forward_as_current_fact" or "前方" in combined and ("已发生" in combined or "当前事实" in combined):
        return "E2_FORECAST_AS_FACT"
    if type_ == "gas_semantics":
        return "E6_GAS_FIELD_MISUSE"
    if type_ in {"recommendation_overreach", "hazard_overreach"}:
        return "E7_UNSUPPORTED_RECOMMENDATION"
    if type_ == "stop_semantics" or "停机=异常原因" in combined or "stop_ratio" in combined and "异常原因" in combined:
        return "E13_STOP_REASON_OVERINTERPRETATION"
    if type_ == "aligned_scope_as_actual_advance":
        return "E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE"
    if type_ in {"current_face_misuse", "spatial_semantics"}:
        return "E9_SOURCE_ROLE_CONFUSION"
    if type_ == "forbidden_phrase":
        return "E1_UNSUPPORTED_CLAIM"
    return "E1_UNSUPPORTED_CLAIM"


def classify_claim_result(claim: dict[str, Any]) -> str | None:
    """Return an error type for unsupported claims or policy/boundary statements."""
    if _bool(claim.get("grounded")):
        if _text(claim.get("trace_support_type")) == "policy_support" and is_method_boundary_text(_claim_text(claim)):
            return "E12_METHOD_BOUNDARY_STATEMENT"
        return None

    claim_type = _text(claim.get("claim_type")) or "unknown"
    text = _claim_text(claim)

    if is_method_boundary_text(text):
        return "E12_METHOD_BOUNDARY_STATEMENT"
    if _looks_like_heading(text):
        return "E11_HEADING_FALSE_POSITIVE"
    if "GRCI" in text and ("概率" in text or "灾害概率" in text or "风险概率" in text):
        return "E3_GRCI_AS_PROBABILITY"
    if ("前方" in text or "forward" in text.lower()) and ("已开挖" in text or "已发生" in text or "施工异常" in text):
        return "E4_FORWARD_AS_EXCAVATED_REVIEW"
    if ("背景" in text or "local_background" in text) and ("当日" in text or "施工响应异常" in text):
        return "E5_BACKGROUND_AS_DAILY_RESPONSE"
    if "excluded_by_distance" in text:
        return "E9_SOURCE_ROLE_CONFUSION"
    if ("停机" in text or "stop_ratio" in text) and "异常原因" in text:
        return "E13_STOP_REASON_OVERINTERPRETATION"
    if any(ch.isdigit() for ch in text) and claim_type == "unknown":
        return "E10_NUMERIC_VALUE_UNGROUNDED"
    if claim_type == "recommendation":
        return "E7_UNSUPPORTED_RECOMMENDATION"
    if claim_type == "gas":
        return "E6_GAS_FIELD_MISUSE"
    return "E1_UNSUPPORTED_CLAIM"


def annotate_quality_result(quality: dict[str, Any]) -> dict[str, Any]:
    """Add taxonomy summaries to a quality checker result."""
    violations = [dict(item) for item in _list(quality.get("violations")) if isinstance(item, dict)]
    claim_results = [dict(item) for item in _list(quality.get("claim_results")) if isinstance(item, dict)]

    violation_groups: dict[str, list[dict[str, Any]]] = {key: [] for key in ERROR_TYPES}
    counts = Counter({key: 0 for key in ERROR_TYPES})

    for item in violations:
        error_type = classify_violation(item)
        item["error_type"] = error_type
        counts[error_type] += 1
        violation_groups[error_type].append(item)

    unsupported_by_claim_type: Counter[str] = Counter()
    for item in claim_results:
        error_type = classify_claim_result(item)
        if error_type:
            item["error_type"] = error_type
            if _bool(item.get("grounded")) and error_type == "E12_METHOD_BOUNDARY_STATEMENT":
                counts[error_type] += 1
        if not _bool(item.get("grounded")):
            counts[error_type or "E1_UNSUPPORTED_CLAIM"] += 1
            unsupported_by_claim_type[_text(item.get("claim_type")) or "unknown"] += 1

    quality["violations"] = violations
    quality["claim_results"] = claim_results if quality.get("claim_results") is not None else None
    quality["error_type_counts"] = dict(counts)
    quality["violations_by_error_type"] = violation_groups
    quality["unsupported_by_claim_type"] = dict(unsupported_by_claim_type)
    return quality


def build_trace_distributions(trace: dict[str, Any]) -> dict[str, Any]:
    """Build support and source distributions for report trace output."""
    claims = [item for item in _list(trace.get("traced_claims")) if isinstance(item, dict)]

    support_counts = Counter({key: 0 for key in SUPPORT_TYPES})
    claim_type_counts: Counter[str] = Counter()
    source_role_counts = Counter({key: 0 for key in SOURCE_ROLES})
    source_type_counts: Counter[str] = Counter()
    unsupported_by_claim_type: Counter[str] = Counter()

    for claim in claims:
        claim_type = _text(claim.get("claim_type")) or "unknown"
        claim_type_counts[claim_type] += 1
        if not _bool(claim.get("grounded")):
            unsupported_by_claim_type[claim_type] += 1

        support_type = normalize_support_type(claim.get("trace_support_type") or claim.get("support_type"))
        support_counts[support_type] += 1

        traces = [item for item in _list(claim.get("source_trace")) if isinstance(item, dict)]
        if not traces:
            source_role_counts["unknown"] += 1
            continue
        for trace in traces:
            source_role_counts[normalize_source_role(trace.get("evidence_report_role") or trace.get("evidence_role"))] += 1
            source_type_counts[_text(trace.get("source_type")) or "unknown"] += 1

    return {
        "support_type_distribution": dict(support_counts),
        "claim_type_distribution": dict(claim_type_counts),
        "source_role_distribution": dict(source_role_counts),
        "source_type_distribution": dict(source_type_counts),
        "unsupported_by_claim_type": dict(unsupported_by_claim_type),
    }


def normalize_support_type(value: Any) -> str:
    text = _text(value)
    mapping = {
        "operation_context": "statistical_support",
        "cluster_context": "statistical_support",
        "gas_context": "statistical_support",
        "coupling_context": "daily_review_support",
        "coupling_review_support": "daily_review_support",
        "cell_evidence_support": "daily_review_support",
        "key_cell": "daily_review_support",
        "forward_segment": "forward_attention_support",
        "forward_attention_support": "forward_attention_support",
        "background_context": "local_background_support",
        "local_background_support": "local_background_support",
        "observed_support": "observed_support",
        "forecast_support": "forecast_support",
        "recommendation_policy": "policy_support",
        "policy_support": "policy_support",
        "statistical_support": "statistical_support",
        "none": "none",
    }
    return mapping.get(text, "none" if not text else text)


def normalize_source_role(value: Any) -> str:
    text = _text(value)
    if text in SOURCE_ROLES:
        return text
    if text == "prediction":
        return "forward_attention_evidence"
    if text == "observed":
        return "daily_review_evidence"
    if text == "background":
        return "local_background_evidence"
    return "unknown"


def _looks_like_heading(text: str) -> bool:
    stripped = text.strip().strip("#").strip("*").strip()
    return bool(stripped) and len(stripped) <= 40 and not any(ch.isdigit() for ch in stripped)


def is_method_boundary_text(text: str) -> bool:
    compact = _text(text)
    if not compact:
        return False

    boundary_phrases = [
        "不把前方证据写成已揭露事实",
        "不能写成已揭露事实",
        "不将前方预报写成已发生事实",
        "如无当日可用掌子面素描",
        "当前 PLC 字段未区分计划停机与非计划停机",
        "当前PLC字段未区分计划停机与非计划停机",
        "stop_ratio 仅作为施工响应关注信号",
        "stop_ratio仅作为施工响应关注信号",
        "stop_ratio 只能写作施工响应关注信号",
        "stop_ratio只能写作施工响应关注信号",
        "GRCI 不表示灾害概率",
        "GRCI不表示灾害概率",
        "GRCI 不表示风险概率",
        "GRCI不表示风险概率",
        "GRCI 不是灾害概率",
        "GRCI不是灾害概率",
        "GRCI 不等同于风险概率",
        "GRCI不等同于风险概率",
        "前方关注提示不等同于已发生异常",
        "语义为前方关注提示",
        "不是已发生事实",
        "围绕 forward_profile 做前方关注提示复核",
        "不得把前方提示或 TSP/HSP 证据写成已发生事实",
        "不得把前方提示或TSP/HSP证据写成已发生事实",
        "不得把前方提示",
        "不把前方提示写成已发生事实",
        "不写成已发生事实",
        "不直接作为异常原因",
        "仅作为施工响应关注信号",
        # Compatibility with older mojibake fixtures in tests.
        "涓嶆槸鐏惧姒傜巼",
        "涓嶇瓑鍚層簬鐏惧姒傜巼",
        "涓嶇洿鎺ヤ綔涓哄紓甯稿師鍥",
        "浠呬綔涓烘柦宸搷搴斿叧娉ㄤ俊鍙",
        "鏈尯鍒嗚鍒掑仠鏈",
        "涓嶅啓鎴愬凡鍙戠敓浜嬪疄",
    ]
    return any(phrase in compact for phrase in boundary_phrases)


def _is_boundary_text(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "不是灾害概率",
            "不等同于灾害概率",
            "不直接作为异常原因",
            "仅作为施工响应关注信号",
            "未区分计划停机",
            "不写成已发生事实",
        ]
    )


def _claim_text(claim: dict[str, Any]) -> str:
    return _text(claim.get("claim_text") or claim.get("text") or claim.get("sentence"))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _bool(value: Any) -> bool:
    return bool(value)
