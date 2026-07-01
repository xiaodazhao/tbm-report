from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "report_policy_v1"

DEFAULT_FORBIDDEN_TERMS = [
    "灾害概率",
    "风险概率",
    "必然发生",
    "已证实灾害",
    "确定发生塌方",
    "防爆措施",
]

DEFAULT_SECTION_REQUIREMENTS = [
    "综合摘要",
    "总体概况",
    "工况统计",
    "聚类状态与效率分析",
    "掌子面与地质揭示",
    "已掘区段地质-施工响应复核",
    "气体监测",
    "前方地质关注提示",
    "结论与施工建议",
]

DEFAULT_SCORE_WEIGHTS = {
    "forbidden_error": 15,
    "warning": 5,
    "missing_section": 3,
    "unsupported_claim": 8,
    "low_grounding_rate": 10,
}

DEFAULT_MINIMUM_OK_SCORE = 80

METADATA_PREFIXES = (
    "报告编号",
    "编制日期",
    "编制单位",
    "报告对象",
    "报告日期",
    "报告名称",
    "报告主题",
    "编制人",
    "审核人",
    "项目名称",
    "隧道名称",
    "分析模式",
    "当前里程",
)

PURE_LABELS = (
    "主要结论",
    "总体建议",
    "综合建议",
    "结论",
    "建议",
    "说明",
    "备注",
)

GRCI_MISUSE_RE = re.compile(
    r"("
    r"GRCI.{0,80}(概率|预测概率|灾害概率|风险概率|发生概率|灾害发生|必然发生|预测灾害|预测风险)"
    r"|"
    r"(?:概率|预测概率|灾害概率|风险概率|发生概率|灾害发生|必然发生|预测灾害|预测风险).{0,80}GRCI"
    r")"
)

GRCI_NEGATED_PROBABILITY_RE = re.compile(
    r"("
    r"GRCI.{0,160}"
    r"(不等同于|不是|并非|不代表|不能解释为|不应解释为|不可解释为|不宜解释为|不能视为|不得视为|不作为|不用于|不是用于)"
    r".{0,100}"
    r"(预测概率|灾害概率|风险概率|发生概率|概率|灾害预测|风险预测|预测结论|预测指标|预测模型|预测结果)"
    r"|"
    r"(不应|不能|不可|不得|不宜|不等同于|不是|并非).{0,80}GRCI.{0,80}"
    r"(解释为|视为|作为|等同于|用于).{0,80}"
    r"(预测概率|灾害概率|风险概率|发生概率|概率|灾害预测|风险预测|预测结论|预测指标|预测模型|预测结果)"
    r"|"
    r"(预测概率|灾害概率|风险概率|发生概率|概率|灾害预测|风险预测|预测结论|预测指标|预测模型|预测结果).{0,100}"
    r"(不等同于|不是|并非|不代表|不能解释为|不应解释为|不可解释为|不宜解释为|不能视为|不得视为)"
    r".{0,160}GRCI"
    r")"
)

FORWARD_FACT_RE = re.compile(
    r"("
    r"(前方|预测|预报).{0,30}(揭示|证实|已证实|证明).{0,30}(当前掌子面|当前里程|已发生|发生)"
    r"|"
    r"(当前掌子面前方|掌子面前方).{0,24}(已发生|确定发生|必然发生)"
    r")"
)

FORWARD_LOW_RISK_RE = re.compile(r"(前方低风险|无风险|无异常)")

GAS_CONCENTRATION_RE = re.compile(r"(浓度超限|浓度超过|浓度偏高|达到超限|超阈值|超限事件)")
GAS_CERTAIN_RE = re.compile(r"(确定超限|明确超限|已经超限|证实超限)")
GAS_GENERIC_MISUSE_RE = re.compile(
    r"(alarm_flag|报警标志|告警标志|疑似报警量|字段语义未知|unknown).{0,40}"
    r"(浓度超限|浓度超过|浓度偏高|达到超限|确定超限|明确超限|已经超限|证实超限)"
)
GAS_NEGATED_CONCENTRATION_RE = re.compile(
    r"(不宜|不应|不能|不可|不得|不直接|不宜直接|不能直接|不应直接).{0,40}"
    r"(按|作为|解释为|视为|判定为)?.{0,40}"
    r"(浓度|超限|超标|浓度值)"
)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_report_policy(policy_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(policy_path) if policy_path else Path(__file__).resolve().parents[1] / "configs" / "quality_checker_policy.json"
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def normalize_space(text: Any) -> str:
    raw = _safe_text(text)
    raw = raw.replace("\u3000", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    return raw.strip()


def split_sentences(text: Any) -> list[str]:
    raw = _safe_text(text)
    if not raw:
        return []

    parts: list[str] = []

    def should_split(line: str, index: int) -> bool:
        ch = line[index]
        if ch in "。！？；;!?":
            return True
        if ch != ".":
            return False

        prev_ch = line[index - 1] if index > 0 else ""
        next_ch = line[index + 1] if index + 1 < len(line) else ""

        # Do not split decimals, dates, mileage-like values, or list markers.
        if prev_ch.isdigit():
            return False
        if next_ch.isdigit():
            return False
        return True

    for line in re.split(r"[\r\n]+", raw):
        line = line.strip()
        if not line:
            continue

        start = 0
        for index, _ in enumerate(line):
            if not should_split(line, index):
                continue
            piece = line[start:index + 1].strip()
            if piece:
                parts.append(piece)
            start = index + 1

        tail = line[start:].strip()
        if tail:
            parts.append(tail)

    return parts


def is_grci_negated_probability_context(text: Any) -> bool:
    candidate = normalize_space(text)
    if "GRCI" not in candidate:
        return False
    return bool(GRCI_NEGATED_PROBABILITY_RE.search(candidate))


def iter_grci_misuse_phrases(text: Any) -> list[str]:
    phrases: list[str] = []
    for sentence in split_sentences(text):
        if "GRCI" not in sentence:
            continue
        if is_grci_negated_probability_context(sentence):
            continue
        for match in GRCI_MISUSE_RE.finditer(sentence):
            phrase = _safe_text(match.group(0))
            if phrase:
                phrases.append(phrase)
    return phrases


def is_gas_negated_concentration_context(text: Any) -> bool:
    candidate = normalize_space(text)
    return bool(GAS_NEGATED_CONCENTRATION_RE.search(candidate))
