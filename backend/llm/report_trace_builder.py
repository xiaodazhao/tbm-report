from __future__ import annotations

import re
from typing import Any

from llm.report_claim_extractor import extract_report_claims
from llm.report_claim_types import normalize_claim_type
from llm.report_grounding_checker import check_claim_grounding
from llm.report_policy import METADATA_PREFIXES, PURE_LABELS


TRACE_SCHEMA_VERSION = "report_trace_v1"
TRACE_SUMMARY_SCHEMA_VERSION = "report_trace_summary_v1"


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


def _claim_text(claim: Any) -> str:
    if isinstance(claim, dict):
        return _safe_text(
            claim.get("claim_text")
            or claim.get("text")
            or claim.get("sentence")
        )
    return _safe_text(claim)


def _claim_type(claim: Any) -> str:
    if isinstance(claim, dict):
        return normalize_claim_type(claim.get("claim_type") or claim.get("type"))
    return ""


def _looks_like_markdown_heading(text: str) -> bool:
    return bool(re.match(r"^\s{0,3}#{1,6}\s+", text))


def _looks_like_section_title(text: str) -> bool:
    compact = _safe_text(text).strip("*").strip()
    if not compact:
        return True

    if re.match(
        r"^(\d+[\.\、]|[一二三四五六七八九十]+[、.．]|（[一二三四五六七八九十]+）)\s*[\u4e00-\u9fffA-Za-z0-9（）()：: -]{2,50}$",
        compact,
    ):
        # 含技术指标、数值或判断词时不按纯标题过滤。
        if not re.search(
            r"(=|\d+\.\d+|占比|推力|扭矩|速度|RAI|GRS|GRCI|CH4|H2S|NO2|CO|m|min|分钟|异常|关注|提示|超限|围岩|地质|掘进)",
            compact,
        ):
            return True

    return False


def _looks_like_table_separator(text: str) -> bool:
    compact = _safe_text(text).replace(" ", "")
    if not compact:
        return True
    return bool(re.match(r"^\|?[-:|]+$", compact))


def _looks_like_table_header(text: str) -> bool:
    compact = _safe_text(text)
    if "|" not in compact:
        return False

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
    return sum(1 for word in header_words if word in compact) >= 2


def _looks_like_unknown_table_row(claim: Any) -> bool:
    text = _claim_text(claim)
    claim_type = _claim_type(claim)

    if "|" not in text:
        return False

    # 已被 extractor 识别为 operation/gas/forward/coupling 的表格行可以保留；
    # unknown 表格行多数是格式噪声或当前 checker 不能稳定归因的展示行。
    if claim_type and claim_type != "unknown":
        return False

    if _looks_like_table_separator(text) or _looks_like_table_header(text):
        return True

    # unknown 表格数据行也先不进入 trace 分母，避免 trace_coverage 被格式行拉低。
    if text.count("|") >= 3:
        return True

    return False


def _is_non_trace_claim(claim: Any) -> bool:
    text = _claim_text(claim)
    claim_type = _claim_type(claim)

    if not text:
        return True

    compact = text.strip().strip("*").strip()

    if _looks_like_markdown_heading(compact):
        return True

    if _looks_like_section_title(compact):
        return True

    for prefix in METADATA_PREFIXES:
        if compact.startswith(prefix + "：") or compact.startswith(prefix + ":"):
            return True

    label = compact.rstrip("：:")
    if label in PURE_LABELS:
        return True

    if _looks_like_unknown_table_row(claim):
        return True

    # “当日 TBM 总运行时长...其中：”是引导句，不是独立 claim。
    if compact.endswith("其中：") or compact.endswith("如下：") or compact.endswith("包括："):
        return True

    # 过短且没有技术指标，不进 trace。
    if len(compact) <= 8 and not re.search(r"(RAI|GRS|GRCI|CH4|H2S|NO2|CO|\d)", compact):
        return True

    # 保留已分类 claim。
    if claim_type and claim_type != "unknown":
        return False

    # unknown 但含明显技术实体/指标的可以保留，让 grounding checker 判断。
    if re.search(
        r"(围岩|地质|掌子面|素描|裂隙|掉块|出水|反射异常|掘进|停机|推力|扭矩|速度|RAI|GRS|GRCI|CH4|H2S|NO2|CO|超限|阈值|cell|区段|里程|DK)",
        compact,
    ):
        return False

    return True


def _filter_claims_for_trace(claims: list[Any], max_claims: int) -> tuple[list[dict], int]:
    filtered: list[dict] = []
    excluded_count = 0

    for item in claims:
        if not isinstance(item, dict):
            excluded_count += 1
            continue

        if _is_non_trace_claim(item):
            excluded_count += 1
            continue

        filtered.append(item)

        if max_claims > 0 and len(filtered) >= max_claims:
            break

    return filtered, excluded_count


def _infer_trace_support_type(item: dict[str, Any], traces: list[dict[str, Any]]) -> str:
    """Infer a semantic trace support type when grounding output is older."""
    explicit = _safe_text(item.get("trace_support_type"))
    if explicit:
        return explicit

    support_type = _safe_text(item.get("support_type"))
    if support_type in {"operation_context", "cluster_context", "gas_context"}:
        return "statistical_support"
    if support_type == "coupling_context":
        return "coupling_review_support"
    if support_type == "forward_segment":
        return "forward_attention_support"
    if support_type == "recommendation_policy":
        return "policy_support"

    roles = {
        _safe_text(trace.get("evidence_role")).lower()
        for trace in traces
        if isinstance(trace, dict)
    }
    source_types = {
        _safe_text(trace.get("source_type")).lower()
        for trace in traces
        if isinstance(trace, dict)
    }
    if "observed" in roles or source_types.intersection({"face_sketch", "sketch"}):
        return "observed_support"
    if "prediction" in roles or source_types.intersection({"tsp", "hsp"}):
        return "forecast_support"
    if "interpreted" in roles:
        return "interpreted_support"
    if support_type == "key_cell":
        return "cell_evidence_support"
    return support_type or "none"


def build_report_trace(
    report_text: str,
    claims: list[dict] | None = None,
    grounding_result: dict | None = None,
    twin_state: dict | None = None,
    geology_context: dict | None = None,
    prompt_evidence_pack: dict | None = None,
    max_claims: int = 120,
    max_trace_per_claim: int = 3,
) -> dict:
    """Build compact claim-to-evidence trace for one generated report."""
    try:
        raw_claim_list = [item for item in _as_list(claims) if isinstance(item, dict)]
        if not raw_claim_list:
            raw_claim_list = extract_report_claims(report_text)

        claim_list, excluded_non_trace_claim_count = _filter_claims_for_trace(
            raw_claim_list,
            max_claims=max(max_claims, 0),
        )

        grounding = _as_dict(grounding_result)

        # 如果外部传入 grounding_result，就优先复用，保证 QualityChecker 和 TraceBuilder 口径一致。
        # 如果没有传入，则用过滤后的 claim_list 重新 grounding。
        if not grounding:
            grounding = check_claim_grounding(
                claim_list,
                twin_state=twin_state,
                geology_context=geology_context,
                prompt_evidence_pack=prompt_evidence_pack,
            )

        traced_claims: list[dict[str, Any]] = []
        grounding_claims = _as_list(grounding.get("claim_results"))

        if max_claims > 0:
            grounding_claims = grounding_claims[:max_claims]

        for item in grounding_claims:
            if not isinstance(item, dict):
                continue

            # 再过滤一次，兼容外部传入的 grounding_result 没有经过 trace filter 的情况。
            if _is_non_trace_claim(item):
                excluded_non_trace_claim_count += 1
                continue

            traces = []
            for trace in _as_list(item.get("source_trace"))[: max(max_trace_per_claim, 0)]:
                if not isinstance(trace, dict):
                    continue

                excerpt = _safe_text(trace.get("raw_text_excerpt"))
                if len(excerpt) > 200:
                    excerpt = excerpt[:197].rstrip() + "..."

                traces.append(
                    {
                        "evidence_id": _safe_text(trace.get("evidence_id")) or None,
                        "report_id": _safe_text(trace.get("report_id")) or None,
                        "source_type": _safe_text(trace.get("source_type")) or None,
                        "evidence_role": _safe_text(trace.get("evidence_role")) or None,
                        "raw_text_excerpt": excerpt or None,
                    }
                )

            traced_claims.append(
                {
                    "claim_id": _safe_text(item.get("claim_id")) or None,
                    "claim_text": _safe_text(item.get("claim_text")),
                    "claim_type": _safe_text(item.get("claim_type")),
                    "grounded": bool(item.get("grounded")),
                    "support_type": _safe_text(item.get("support_type")) or None,
                    "trace_support_type": _infer_trace_support_type(item, traces),
                    "supporting_evidence_ids": _as_list(item.get("supporting_evidence_ids")),
                    "source_trace": traces,
                    "support_note": "; ".join(
                        _safe_text(message)
                        for message in _as_list(item.get("messages"))
                        if _safe_text(message)
                    ),
                }
            )

        grounded_count = sum(1 for item in traced_claims if item.get("grounded"))
        claim_count = len(traced_claims)
        unsupported_count = claim_count - grounded_count
        coverage = round(grounded_count / claim_count, 4) if claim_count else 0.0

        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_available": claim_count > 0,
            "raw_claim_count": len(raw_claim_list),
            "excluded_non_trace_claim_count": excluded_non_trace_claim_count,
            "claim_trace_count": claim_count,
            "grounded_claim_count": grounded_count,
            "unsupported_claim_count": unsupported_count,
            "trace_coverage": coverage,
            "traced_claims": traced_claims,
            "warnings": _as_list(grounding.get("warnings")),
        }

    except Exception as exc:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_available": False,
            "raw_claim_count": 0,
            "excluded_non_trace_claim_count": 0,
            "claim_trace_count": 0,
            "grounded_claim_count": 0,
            "unsupported_claim_count": 0,
            "trace_coverage": 0.0,
            "traced_claims": [],
            "warnings": [f"report trace builder failed: {exc}"],
        }


def summarize_report_trace(trace: dict | None) -> dict:
    """Summarize report trace."""
    trace = _as_dict(trace)
    return {
        "schema_version": TRACE_SUMMARY_SCHEMA_VERSION,
        "trace_available": bool(trace.get("trace_available")),
        "raw_claim_count": int(trace.get("raw_claim_count") or 0),
        "excluded_non_trace_claim_count": int(trace.get("excluded_non_trace_claim_count") or 0),
        "claim_trace_count": int(trace.get("claim_trace_count") or 0),
        "grounded_claim_count": int(trace.get("grounded_claim_count") or 0),
        "unsupported_claim_count": int(trace.get("unsupported_claim_count") or 0),
        "trace_coverage": float(trace.get("trace_coverage") or 0.0),
        "warnings": _as_list(trace.get("warnings")),
    }
