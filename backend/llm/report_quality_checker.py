from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from contracts.data_dictionary import STRONG_HAZARD_TERMS, collect_supported_tags_from_item
from llm.report_claim_extractor import extract_report_claims
from llm.report_error_taxonomy import annotate_quality_result, is_method_boundary_text
from llm.report_grounding_checker import check_claim_grounding
from llm.report_policy import (
    DEFAULT_FORBIDDEN_TERMS,
    DEFAULT_MINIMUM_OK_SCORE,
    DEFAULT_SCORE_WEIGHTS,
    DEFAULT_SECTION_REQUIREMENTS,
    FORWARD_FACT_RE,
    FORWARD_LOW_RISK_RE,
    GAS_CERTAIN_RE,
    GAS_CONCENTRATION_RE,
    GAS_GENERIC_MISUSE_RE,
    METADATA_PREFIXES,
    PURE_LABELS,
    is_gas_negated_concentration_context as policy_is_gas_negated_concentration_context,
    is_grci_negated_probability_context as policy_is_grci_negated_probability_context,
    iter_grci_misuse_phrases as policy_iter_grci_misuse_phrases,
    load_report_policy,
    normalize_space as policy_normalize_space,
    split_sentences as policy_split_sentences,
)
from schemas.twin_state_schema import get_context_dict, get_context_list


SCHEMA_VERSION = "report_quality_v2"



# ============================================================
# Basic helpers
# ============================================================

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


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _load_policy() -> dict[str, Any]:
    return load_report_policy(
        Path(__file__).resolve().parents[1] / "configs" / "quality_checker_policy.json"
    )


def _normalize_space(text: str) -> str:
    return policy_normalize_space(text)


def _split_sentences(text: str) -> list[str]:
    return policy_split_sentences(text)


def _window_around(text: str, start: int, end: int, radius: int = 120) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right]


# ============================================================
# GRCI / gas semantic helpers
# ============================================================

def _is_grci_negated_probability_context(text: str) -> bool:
    return policy_is_grci_negated_probability_context(text)


def _iter_grci_misuse_phrases(text: str) -> list[str]:
    return policy_iter_grci_misuse_phrases(text)

def _is_allowed_forbidden_probability_phrase(
    *,
    phrase: str,
    sentence: str,
) -> bool:
    """
    对 forbidden_terms 中的“灾害概率 / 风险概率”做白名单处理。

    只有当它们出现在 GRCI 的否定解释语境中时才允许：
      GRCI 不是灾害概率
      GRCI 不等同于风险概率
    """
    phrase = _safe_text(phrase)
    sentence = _safe_text(sentence)
    if phrase not in {"灾害概率", "风险概率"}:
        return False
    if phrase not in sentence:
        return False
    return _is_grci_negated_probability_context(sentence)


def _is_gas_negated_concentration_context(text: str) -> bool:
    return policy_is_gas_negated_concentration_context(text)


def _is_stop_boundary_statement(text: str) -> bool:
    compact = _safe_text(text)
    return bool(
        ("停机" in compact or "stop_ratio" in compact or "计划停机" in compact)
        and any(
            phrase in compact
            for phrase in [
                "未区分计划停机",
                "非计划停机",
                "仅作为施工响应关注信号",
                "不直接作为异常原因",
                "不能直接作为异常原因",
            ]
        )
    )


def _is_stop_causal_overreach(text: str) -> bool:
    compact = _safe_text(text)
    if is_method_boundary_text(compact) or _is_stop_boundary_statement(compact):
        return False
    if (
        ("停机" in compact or "stop_ratio" in compact)
        and (
            re.search(r"(停机|stop_ratio).{0,18}(导致|造成|说明|表明|证明|作为|是).{0,18}(异常|故障|原因)", compact)
            or re.search(r"(异常|故障).{0,18}(原因|由来|来源).{0,18}(停机|stop_ratio)", compact)
            or "直接作为异常原因" in compact
        )
    ):
        return True
    if not ("停机" in compact or "stop_ratio" in compact):
        return False
    return bool(
        re.search(r"(停机|stop_ratio).{0,18}(导致|造成|说明|表明|证明).{0,18}(异常|故障|原因)", compact)
        or re.search(r"(异常|故障).{0,18}(原因|由来|来源).{0,18}(停机|stop_ratio)", compact)
        or re.search(r"停机.{0,8}(就是|即为|属于).{0,8}异常", compact)
    )


def _is_forward_role_confusion(text: str) -> bool:
    compact = _safe_text(text)
    if is_method_boundary_text(compact):
        return False
    return bool(("前方" in compact or "forward_attention" in compact) and re.search(r"(已开挖|已掘|已发生|施工异常|响应异常)", compact))


def _is_background_role_confusion(text: str) -> bool:
    compact = _safe_text(text)
    if is_method_boundary_text(compact):
        return False
    return bool(("背景" in compact or "local_background" in compact) and re.search(r"(当日|今日).{0,12}(施工响应|响应异常|GRCI|RAI)", compact))


# ============================================================
# Evidence helpers
# ============================================================

def _collect_allowed_hazards(
    twin_state: dict[str, Any],
    geology_context: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> set[str]:
    allowed: set[str] = set()

    current_window_summary = _as_dict(geology_context.get("current_window_summary"))
    for item in _as_list(current_window_summary.get("main_hazards")):
        if _safe_text(item):
            allowed.add(_safe_text(item))

    for cell in get_context_list(
        "key_cells",
        twin_state=twin_state,
        geology_context=geology_context,
        prompt_evidence_pack=prompt_evidence_pack,
    ):
        if isinstance(cell, dict):
            allowed.update(collect_supported_tags_from_item(cell))

    for segment in get_context_list(
        "forward_segments",
        twin_state=twin_state,
        geology_context=geology_context,
        prompt_evidence_pack=prompt_evidence_pack,
    ):
        if isinstance(segment, dict):
            allowed.update(collect_supported_tags_from_item(segment))

    return allowed


def _get_current_face_context(geology_context: dict[str, Any]) -> dict[str, Any]:
    return get_context_dict("current_face", geology_context=geology_context)


def _has_direct_face_observation(geology_context: dict[str, Any]) -> bool:
    current_face = _get_current_face_context(geology_context)
    return bool(current_face.get("has_direct_face_observation"))


def _has_low_coverage_forward_segments(
    twin_state: dict[str, Any],
    geology_context: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> bool:
    segments = get_context_list(
        "forward_segments",
        twin_state=twin_state,
        geology_context=geology_context,
        prompt_evidence_pack=prompt_evidence_pack,
    )

    for segment in segments:
        segment_dict = _as_dict(segment)
        evidence_count = int(segment_dict.get("evidence_count") or 0)
        confidence = _safe_float(segment_dict.get("confidence"), default=None)
        uncertainty = _safe_text(segment_dict.get("uncertainty_level")).lower()

        if evidence_count <= 1:
            return True
        if confidence is None or confidence < 0.45:
            return True
        if uncertainty in {"high", "unknown", "高", "未知"}:
            return True

    return False


def _get_gas_summaries(
    twin_state: dict[str, Any],
    prompt_evidence_pack: dict[str, Any],
) -> list[dict[str, Any]]:
    summaries = get_context_list(
        "gas_summaries",
        twin_state=twin_state,
        prompt_evidence_pack=prompt_evidence_pack,
    )
    return [item for item in summaries if isinstance(item, dict)]


# ============================================================
# Claim filtering
# ============================================================

def _claim_text(claim: Any) -> str:
    if isinstance(claim, dict):
        return _safe_text(claim.get("claim_text") or claim.get("text") or claim.get("sentence"))
    return _safe_text(claim)


def _is_non_technical_claim_text(text: str) -> bool:
    """
    过滤不应进入 grounding 分母的非技术主张。

    这些内容不是结构化证据 claim：
    - Markdown 标题
    - 报告编号、编制日期、编制单位、报告对象
    - “主要结论：”这种纯标签
    - “本报告基于...”这种模板导语
    """
    raw = _safe_text(text)
    if not raw:
        return True

    compact = raw.strip().strip("*").strip()
    normalized_title = re.sub(r"^\s*(#+\s*)?\d+[\.\、]\s*", "", compact).strip()
    normalized_title = re.sub(r"（.*?）", "", normalized_title).strip()
    if normalized_title in {
        "综合结论摘要",
        "总体施工运行概况",
        "今日施工运行概况",
        "基础工况统计分析",
        "PLC 工况统计分析",
        "聚类施工状态与效率分析",
        "当前掌子面描述",
        "已开挖区段地质与响应异常复核",
        "气体监测分析",
        "前方关注提示",
        "当前掌子面前方关注提示",
        "结论与建议",
    }:
        return True
    if compact.startswith("该结果只描述当日 PLC 参数状态分组"):
        return True
    if compact.startswith("当前掌子面描述只作为空间定位"):
        return True
    if compact.startswith("报告不得把 GRCI"):
        return True
    if "这些 cell 使用 GRS_geo_base" in compact and "不进入已开挖区段 GRCI 复核单元" in compact:
        return True
        # 报告元信息 / 声明 / 编制信息，不进入 grounding 分母
    if compact.startswith("报告编制"):
        return True
    if compact.startswith("声明：") or compact.startswith("声明:"):
        return True

    # 说明句：如果只是解释指标语义、不是新增工程事实，不进入 grounding 分母
    if compact.startswith("说明：") or compact.startswith("说明:"):
        if any(
            phrase in compact
            for phrase in [
                "不等同于灾害发生概率",
                "不表示灾害发生概率",
                "不等同于灾害预测",
                "不等同于真实地质状态",
                "聚类状态为施工参数聚类结果",
                "基于多源地质证据融合得到",
                "表示地质证据融合关注程度",
            ]
        ):
            return True

    # 建议章节小标题，不是 claim
    if re.match(r"^\d+[\.、]\s*\*\*[^：:]{2,30}[：:]?$", compact):
        return True

    # 建议类引导标题，不是 claim
    if compact in {
        "1. **施工监测与复核：",
        "2. **支护与排水准备：",
        "3. **气体监测管理：",
        "4. **参数联动观察：",
        "5. **证据补充与核查：",
    }:
        return True
    claim_like_prefixes = (
        "分析模式",
        "当前里程",
        "报告日期",
        "报告编号",
        "编制日期",
        "编制单位",
        "报告对象",
    )
    for prefix in claim_like_prefixes:
        if compact.startswith(prefix + "：") or compact.startswith(prefix + ":"):
            return True

    # 表格分隔线
    if re.match(r"^\|?[-:| ]+$", compact):
        return True

    # 表头行不作为 claim
    if "|" in compact:
        header_words = [
            "类型",
            "状态",
            "分段",
            "里程",
            "关注等级",
            "主要地质关注",
            "主要施工关注",
            "融合置信度",
            "不确定性",
            "气体类型",
            "平均值",
            "最大值",
            "阈值",
            "超阈值次数",
            "样本数",
            "占比",
        ]
        if sum(1 for word in header_words if word in compact) >= 2:
            return True

    # unknown 表格行通常会拉低 grounding 分母；真正的 forward/gas/operation claim 应由 extractor 分类后保留。
    if "|" in compact and compact.count("|") >= 3:
        return True

    # 引导句，不是独立技术主张。
    if compact.endswith("其中：") or compact.endswith("如下：") or compact.endswith("包括："):
        return True

    # Markdown 标题：# / ## / ### ...
    if re.match(r"^\s{0,3}#{1,6}\s+", compact):
        return True

    # 章节编号标题：1. xxx / 一、xxx / （一）xxx
    if re.match(r"^(\d+[\.\、]|[一二三四五六七八九十]+[、.．]|（[一二三四五六七八九十]+）)\s*[\u4e00-\u9fffA-Za-z0-9（）()：: -]{2,40}$", compact):
        # 如果是纯章节标题，没有明显数据或判断词，则跳过。
        if not re.search(r"(=|\d+\.\d+|占比|推力|扭矩|速度|RAI|GRS|GRCI|CH4|H2S|NO2|CO|m|分钟|异常|关注|提示|超限)", compact):
            return True

    # 报告元信息
    for prefix in METADATA_PREFIXES:
        if compact.startswith(prefix + "：") or compact.startswith(prefix + ":"):
            return True

    # 纯标签
    label = compact.rstrip("：:")
    if label in PURE_LABELS:
        return True

    # 过短、且没有技术含义
    if len(compact) <= 6 and not re.search(r"(RAI|GRS|GRCI|CH4|H2S|NO2|CO|\d)", compact):
        return True

    # 模板导语，不作为证据 claim 进入分母
    if compact.startswith("本报告基于") and "进行综合分析" in compact:
        return True

    return False


def _filter_quality_claims(claims: list[Any]) -> tuple[list[Any], int]:
    filtered: list[Any] = []
    excluded_count = 0

    for claim in claims:
        text = _claim_text(claim)
        if _is_non_technical_claim_text(text):
            excluded_count += 1
            continue
        filtered.append(claim)

    return filtered, excluded_count


# ============================================================
# Violation / score helpers
# ============================================================

def _add_violation(
    violations: list[dict[str, Any]],
    *,
    type_: str,
    severity: str,
    message: str,
    suggestion: str,
    phrase: str | None = None,
    claim_id: str | None = None,
) -> None:
    violations.append(
        {
            "type": type_,
            "severity": severity,
            "phrase": phrase,
            "message": message,
            "suggestion": suggestion,
            "claim_id": claim_id,
        }
    )


def _score_from_violations(
    violations: list[dict[str, Any]],
    *,
    missing_section_count: int,
    grounding_rate: float,
    policy: dict[str, Any],
) -> int:
    weights = _as_dict(policy.get("score_weights"))
    forbidden_error = int(weights.get("forbidden_error", DEFAULT_SCORE_WEIGHTS["forbidden_error"]))
    warning_penalty = int(weights.get("warning", DEFAULT_SCORE_WEIGHTS["warning"]))
    missing_section_penalty = int(weights.get("missing_section", DEFAULT_SCORE_WEIGHTS["missing_section"]))
    low_grounding_penalty = int(weights.get("low_grounding_rate", DEFAULT_SCORE_WEIGHTS["low_grounding_rate"]))

    score = 100

    for item in violations:
        if item.get("severity") == "error":
            score -= max(forbidden_error, 12)
        else:
            score -= max(warning_penalty, 3)

    score -= missing_section_count * max(missing_section_penalty, 1)

    if grounding_rate < 0.6:
        score -= 20
    elif grounding_rate < 0.8:
        score -= max(low_grounding_penalty, 10)

    return max(0, score)


def _filter_grounding_violations(
    grounding: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    对 grounding checker 返回的 violations 做二次过滤。
    主要用于过滤 GRCI 否定语境误报。
    """
    claim_results = _as_list(grounding.get("claim_results"))
    claim_text_by_id: dict[str, str] = {}

    for claim in claim_results:
        claim_dict = _as_dict(claim)
        claim_id = _safe_text(claim_dict.get("claim_id"))
        if claim_id:
            claim_text_by_id[claim_id] = _safe_text(claim_dict.get("claim_text"))

    filtered: list[dict[str, Any]] = []

    for item in _as_list(grounding.get("violations")):
        if not isinstance(item, dict):
            continue

        violation_type = _safe_text(item.get("type"))
        claim_id = _safe_text(item.get("claim_id"))
        phrase = _safe_text(item.get("phrase"))
        claim_text = claim_text_by_id.get(claim_id, "")
        context = claim_text or phrase

        if violation_type == "grci_misuse" and _is_grci_negated_probability_context(context):
            continue

        filtered.append(item)

    return filtered


# ============================================================
# Main checker
# ============================================================

def check_report_quality(
    report_text: str,
    llm_summary: dict | None = None,
    geology_context: dict | None = None,
    twin_state: dict | None = None,
    prompt_evidence_pack: dict | None = None,
    include_claim_results: bool = False,
) -> dict:
    """Run non-blocking report quality checks with claim grounding."""
    try:
        policy = _load_policy()
        text = _safe_text(report_text)

        summary = _as_dict(llm_summary)
        geology_context = _as_dict(geology_context) or _as_dict(summary.get("geology_v2_context"))
        twin_state = _as_dict(twin_state) or _as_dict(summary.get("twin_state"))
        prompt_evidence_pack = _as_dict(prompt_evidence_pack) or _as_dict(summary.get("prompt_evidence_pack"))

        forbidden_terms = _as_list(policy.get("forbidden_terms")) or DEFAULT_FORBIDDEN_TERMS
        strong_hazard_terms = _as_list(policy.get("strong_hazard_terms")) or STRONG_HAZARD_TERMS
        section_titles = _as_list(policy.get("section_requirements")) or DEFAULT_SECTION_REQUIREMENTS
        minimum_ok_score = int(policy.get("minimum_ok_score", DEFAULT_MINIMUM_OK_SCORE))

        violations: list[dict[str, Any]] = []
        warnings: list[str] = []
        sentences = _split_sentences(text)

        # ------------------------------------------------------------
        # 1. Forbidden terms
        # ------------------------------------------------------------
        for phrase in forbidden_terms:
            phrase_text = _safe_text(phrase)
            if not phrase_text:
                continue

            unsafe_found = False

            for sentence in sentences:
                if phrase_text not in sentence:
                    continue

                if _is_allowed_forbidden_probability_phrase(
                    phrase=phrase_text,
                    sentence=sentence,
                ):
                    continue

                unsafe_found = True
                break

            if unsafe_found:
                severity = "warning" if phrase_text == "防爆措施" else "error"
                _add_violation(
                    violations,
                    type_="forbidden_phrase",
                    severity=severity,
                    phrase=phrase_text,
                    message=f"报告中出现禁用或高风险表述：{phrase_text}",
                    suggestion="改为“关注提示”“证据融合关注程度”或“按现场规程复核”。",
                )

        # ------------------------------------------------------------
        # 2. Strong hazard overreach
        # ------------------------------------------------------------
        allowed_hazards = _collect_allowed_hazards(twin_state, geology_context, prompt_evidence_pack)
        for term in strong_hazard_terms:
            hazard = _safe_text(term)
            if hazard and hazard in text and hazard not in allowed_hazards:
                _add_violation(
                    violations,
                    type_="hazard_overreach",
                    severity="warning",
                    phrase=hazard,
                    message=f"报告出现了证据包中未明确支持的强灾害词：{hazard}",
                    suggestion="删除该词，或改为证据中实际出现的关注表述。",
                )

        # ------------------------------------------------------------
        # 3. Spatial semantics
        # ------------------------------------------------------------
        if "当前掌子面揭示" in text and not _has_direct_face_observation(geology_context):
            _add_violation(
                violations,
                type_="spatial_semantics",
                severity="error",
                phrase="当前掌子面揭示",
                message="报告使用了“当前掌子面揭示”，但缺少直接掌子面观测依据。",
                suggestion="改为“当前里程附近已有地质证据提示”或“最近现场素描点记录显示”。",
            )


        for sentence in sentences:
            forward_fact_match = FORWARD_FACT_RE.search(sentence)
            if not forward_fact_match:
                continue

            _add_violation(
                violations,
                type_="forward_as_current_fact",
                severity="warning",
                phrase=forward_fact_match.group(0),
                message="报告可能把前方提示写成了当前事实。",
                suggestion="改为“前方窗口内提示”或“前方范围内需关注”。",
            )
            break
        # ------------------------------------------------------------
        # 4. GRCI misuse
        # ------------------------------------------------------------
        for phrase in _iter_grci_misuse_phrases(text):
            _add_violation(
                violations,
                type_="grci_misuse",
                severity="error",
                phrase=phrase,
                message="GRCI 被表述为概率或预测语义。",
                suggestion="改为“地质-施工响应耦合关注度，是复盘解释指标”。",
            )

        # ------------------------------------------------------------
        # 5. Forward low-risk misuse
        # ------------------------------------------------------------
        low_risk_match = FORWARD_LOW_RISK_RE.search(text)
        if low_risk_match and _has_low_coverage_forward_segments(
            twin_state,
            geology_context,
            prompt_evidence_pack,
        ):
            _add_violation(
                violations,
                type_="forward_low_risk_misuse",
                severity="warning",
                phrase=low_risk_match.group(0),
                message="前方窗口存在低覆盖或高不确定性分段，不宜直接写成低风险或无风险。",
                suggestion="改为“当前融合关注较低，但不能据此判断为低风险”。",
            )

        # ------------------------------------------------------------
        # 6. Gas semantics
        # ------------------------------------------------------------
        for sentence in sentences:
            generic_match = GAS_GENERIC_MISUSE_RE.search(sentence)
            if generic_match and not _is_gas_negated_concentration_context(sentence):
                _add_violation(
                    violations,
                    type_="gas_semantics",
                    severity="error",
                    phrase=generic_match.group(0),
                    message="报告可能将 alarm_flag、疑似报警量或 unknown 字段直接写成浓度超限。",
                    suggestion="改为“报警标志/疑似报警量/字段语义需复核”，不要直接解释为浓度超限。",
                )

        for gas_item in _get_gas_summaries(twin_state, prompt_evidence_pack):
            gas_name = _safe_text(gas_item.get("gas"))
            field_type_guess = _safe_text(gas_item.get("field_type_guess")).lower()

            if not gas_name or gas_name not in text:
                continue

            related_sentences = [s for s in sentences if gas_name in s]

            for sentence in related_sentences:
                if _is_gas_negated_concentration_context(sentence):
                    continue

                if field_type_guess == "alarm_flag" and GAS_CONCENTRATION_RE.search(sentence):
                    _add_violation(
                        violations,
                        type_="gas_semantics",
                        severity="warning",
                        phrase=gas_name,
                        message=f"{gas_name} 疑似 alarm_flag，报告不应写成浓度超限。",
                        suggestion="改为报警记录、监测告警或需复核表述。",
                    )

                if field_type_guess == "unknown" and GAS_CERTAIN_RE.search(sentence):
                    _add_violation(
                        violations,
                        type_="gas_semantics",
                        severity="warning",
                        phrase=gas_name,
                        message=f"{gas_name} 字段语义未知，报告不应写成确定超限。",
                        suggestion="改为需结合现场气体制度复核。",
                    )

        # ------------------------------------------------------------
        # 6.5 Stop-ratio semantics
        # ------------------------------------------------------------
        for sentence in sentences:
            if _is_stop_causal_overreach(sentence):
                _add_violation(
                    violations,
                    type_="stop_semantics",
                    severity="warning",
                    phrase="停机=异常原因",
                    message="报告可能把 stop_ratio 或停机直接写成异常原因，但当前 PLC 字段未区分计划停机与非计划停机。",
                    suggestion="改为“stop_ratio 仅作为施工响应关注信号，不直接作为异常原因”。",
                )
                break

        for sentence in sentences:
            if _is_forward_role_confusion(sentence):
                _add_violation(
                    violations,
                    type_="role_consistency",
                    severity="warning",
                    phrase="forward_attention_as_daily_review",
                    message="报告可能把 forward_attention cell 写成已开挖事实或已发生施工异常。",
                    suggestion="改为前方关注提示，不使用已发生或已开挖复核语义。",
                )
                violations[-1]["error_type"] = "E4_FORWARD_AS_EXCAVATED_REVIEW"
                break

        for sentence in sentences:
            if _is_background_role_confusion(sentence):
                _add_violation(
                    violations,
                    type_="role_consistency",
                    severity="warning",
                    phrase="local_background_as_daily_response",
                    message="报告可能把 local_background cell 写成当日施工响应异常。",
                    suggestion="local_background 只能作为背景说明，不能支撑当日响应异常判断。",
                )
                violations[-1]["error_type"] = "E5_BACKGROUND_AS_DAILY_RESPONSE"
                break

        if "excluded_by_distance" in text:
            _add_violation(
                violations,
                type_="source_role_confusion",
                severity="warning",
                phrase="excluded_by_distance",
                message="报告引用了 excluded_by_distance evidence 作为正文支撑。",
                suggestion="excluded_by_distance evidence 只能进入审计排除清单，不能作为日报主证据链支撑。",
            )
            violations[-1]["error_type"] = "E9_SOURCE_ROLE_CONFUSION"

        # ------------------------------------------------------------
        # 7. Section completeness
        # ------------------------------------------------------------
        missing_sections = [
            title
            for title in section_titles
            if _safe_text(title) and _safe_text(title) not in text
        ]

        if missing_sections:
            warnings.append(f"报告缺少章节标题：{', '.join(missing_sections)}")
            for title in missing_sections:
                _add_violation(
                    violations,
                    type_="missing_section",
                    severity="warning",
                    phrase=title,
                    message=f"报告未包含建议章节：{title}",
                    suggestion="补齐标准章节结构。",
                )

        # ------------------------------------------------------------
        # 8. Claim grounding
        # ------------------------------------------------------------
        raw_claims = extract_report_claims(text)
        raw_claim_count = len(_as_list(raw_claims))
        claims, excluded_claim_count = _filter_quality_claims(_as_list(raw_claims))

        grounding = check_claim_grounding(
            claims,
            twin_state=twin_state,
            geology_context=geology_context,
            prompt_evidence_pack=prompt_evidence_pack,
        )

        for item in _filter_grounding_violations(grounding):
            violations.append(item)

        grounding_rate = float(grounding.get("grounding_rate") or 0.0)
        unsupported_claim_count = int(grounding.get("unsupported_claim_count") or 0)

        if unsupported_claim_count > 0:
            warnings.append(f"存在 {unsupported_claim_count} 条主张未获得结构化证据支撑。")

        # ------------------------------------------------------------
        # 9. Score and response
        # ------------------------------------------------------------
        score = _score_from_violations(
            violations,
            missing_section_count=len(missing_sections),
            grounding_rate=grounding_rate,
            policy=policy,
        )

        error_count = sum(1 for item in violations if item.get("severity") == "error")
        warning_count = sum(1 for item in violations if item.get("severity") == "warning")
        ok = error_count == 0 and score >= minimum_ok_score

        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": ok,
            "score": score,
            "quality_score": score,
            "claim_count": int(grounding.get("claim_count") or 0),
            "grounded_claim_count": int(grounding.get("grounded_claim_count") or 0),
            "unsupported_claim_count": unsupported_claim_count,
            "grounding_rate": grounding_rate,
            "violations": violations,
            "warnings": warnings + _as_list(grounding.get("warnings")),
            "stats": {
                "forbidden_phrase_count": sum(
                    1 for item in violations if item.get("type") == "forbidden_phrase"
                ),
                "strong_hazard_count": sum(
                    1 for item in violations if item.get("type") == "hazard_overreach"
                ),
                "raw_claim_count": raw_claim_count,
                "excluded_non_technical_claim_count": excluded_claim_count,
                "claim_count": int(grounding.get("claim_count") or 0),
                "grounded_claim_count": int(grounding.get("grounded_claim_count") or 0),
                "unsupported_claim_count": unsupported_claim_count,
                "grounding_rate": grounding_rate,
                "section_count": len(section_titles),
                "missing_section_count": len(missing_sections),
                "error_count": error_count,
                "warning_count": warning_count,
            },
            "grounding_summary": {
                "raw_claim_count": raw_claim_count,
                "excluded_non_technical_claim_count": excluded_claim_count,
                "claim_count": int(grounding.get("claim_count") or 0),
                "grounded_claim_count": int(grounding.get("grounded_claim_count") or 0),
                "grounding_rate": grounding_rate,
                "unsupported_claim_count": unsupported_claim_count,
            },
            "claim_results": _as_list(grounding.get("claim_results")) if include_claim_results else None,
        }
        return annotate_quality_result(result)

    except Exception as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "score": 0,
            "quality_score": 0,
            "claim_count": 0,
            "grounded_claim_count": 0,
            "unsupported_claim_count": 0,
            "grounding_rate": 0.0,
            "violations": [],
            "warnings": [f"report quality checker failed: {exc}"],
            "stats": {
                "forbidden_phrase_count": 0,
                "strong_hazard_count": 0,
                "raw_claim_count": 0,
                "excluded_non_technical_claim_count": 0,
                "claim_count": 0,
                "grounded_claim_count": 0,
                "unsupported_claim_count": 0,
                "grounding_rate": 0.0,
                "section_count": 0,
                "missing_section_count": 0,
                "error_count": 0,
                "warning_count": 0,
            },
            "grounding_summary": {
                "raw_claim_count": 0,
                "excluded_non_technical_claim_count": 0,
                "claim_count": 0,
                "grounded_claim_count": 0,
                "grounding_rate": 0.0,
                "unsupported_claim_count": 0,
            },
            "claim_results": [] if include_claim_results else None,
        }
        return annotate_quality_result(result)
