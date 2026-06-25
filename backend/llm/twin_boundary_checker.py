from __future__ import annotations

import re
from typing import Any


BOUNDARY_RULES: dict[str, dict[str, Any]] = {
    "grci_probability_misuse": {
        "severity": "error",
        "patterns": [
            r"GRCI.{0,24}(灾害概率|风险概率|发生概率|灾害发生概率|hazard probability|disaster probability|risk probability)",
            r"(灾害概率|风险概率|发生概率|灾害发生概率|hazard probability|disaster probability|risk probability).{0,24}GRCI",
            r"GRCI.{0,24}(预测|predicts?).{0,24}(灾害|hazard|disaster).{0,24}(概率|probability)",
            r"GRCI.{0,24}predicts?.{0,24}probability.{0,12}(hazard|disaster|risk)",
            r"GRCI.{0,24}(indicates?|represents?).{0,24}(disaster|risk|hazard).{0,12}probability",
        ],
    },
    "forward_fact_misuse": {
        "severity": "error",
        "patterns": [
            r"(前方|当前掌子面前方).{0,24}(已发生|已经发生|已揭示|已揭露|现场揭露|存在异常|发生异常)",
            r"PLC.{0,16}(证明|表明|说明).{0,16}(前方|当前掌子面前方).{0,24}(异常|不良地质|风险|灾害)",
            r"(已掘|已开挖).{0,12}PLC.{0,16}(证明|表明|说明).{0,16}(前方|当前掌子面前方)",
            r"forward_attention.{0,16}(证明|表明|说明).{0,16}(前方|风险|异常)",
            r"forward attention.{0,24}(proves?|indicates?).{0,24}(front|forward).{0,24}(condition|risk|abnormal|geology)",
            r"PLC.{0,24}proves?.{0,24}forward.{0,24}(abnormal|risk|geology|ground)",
            r"excavated PLC data.{0,24}proves?.{0,24}forward.{0,24}(risk|condition|geology)",
        ],
    },
    "plc_proxy_misuse": {
        "severity": "error",
        "patterns": [
            r"cutterhead_power_proxy.{0,20}(真实功率|实际功率|物理功率|true physical power|real power|actual power)",
            r"刀盘.{0,12}proxy.{0,20}(真实功率|实际功率|物理功率)",
            r"thrust_per_penetration.{0,20}(严格比能|真实比能|specific energy)",
            r"torque_per_penetration.{0,20}(真实比能|严格比能|specific energy|geological hazard|geological risk)",
            r"PLC enhanced metrics.{0,24}(证明|prove|proves).{0,24}(地质风险|geological risk|geological hazard)",
            r"单位贯入.{0,16}(扭矩|推力).{0,16}(证明|表明|说明).{0,20}(地质灾害|地质风险|灾害)",
        ],
    },
    "stop_causality_misuse": {
        "severity": "error",
        "patterns": [
            r"stop_ratio.{0,20}(说明|证明|表明).{0,20}(设备异常|设备故障|施工异常原因|异常原因|非计划停机)",
            r"停机比例.{0,20}(高)?(说明|证明|表明).{0,20}(设备异常|设备故障|异常原因|非计划停机)",
            r"stop[_ ]?ratio.{0,24}proves?.{0,24}(equipment failure|abnormal cause|unplanned shutdown)",
            r"high stop ratio.{0,24}(indicates?|proves?).{0,24}(abnormal cause|equipment failure)",
        ],
    },
    "local_background_scope_misuse": {
        "severity": "error",
        "patterns": [
            r"local_background.{0,20}(证明|表明|说明).{0,20}(当日异常|当前异常|前方风险|前方异常)",
            r"(背景证据|局部背景证据).{0,20}(证明|表明|说明).{0,20}(当前掌子面异常|当日异常|前方已经发生异常|前方异常)",
            r"local background.{0,24}proves?.{0,24}(today'?s abnormal condition|forward condition|forward risk)",
            r"background evidence.{0,24}proves?.{0,24}(forward condition|today'?s abnormal condition)",
        ],
    },
}

SAFE_BOUNDARY_PATTERNS = [
    r"GRCI.{0,16}(不是|不表示|不等同于|不得写成|不能写成).{0,16}(灾害概率|风险概率|概率)",
    r"(不得|不能|不应).{0,12}(把)?GRCI.{0,16}(写成|表述为|解释为).{0,16}(灾害概率|风险概率|概率)",
    r"RAI.{0,16}(不是|不表示|不等同于).{0,16}(风险概率|灾害概率|概率)",
    r"前方关注提示.{0,24}(不表示|不是|不等同于).{0,24}(已发生|事实)",
    r"forward_attention.{0,24}(仅表示|只表示).{0,24}(前方关注|关注提示)",
    r"forward_attention.{0,24}(不表示|不等同于).{0,24}(已发生|事实)",
    r"PLC enhanced metrics.{0,24}(仅作为|只作为).{0,24}(施工响应证据|已掘区段)",
    r"PLC enhanced metrics.{0,24}(不单独|不能|不得).{0,24}(地质风险|风险判断)",
    r"cutterhead_power_proxy.{0,16}(不是|不表示|不等同于).{0,20}(真实物理功率|真实功率|物理功率|actual power|true physical power)",
    r"thrust_per_penetration.{0,24}(仅作为|只作为).{0,24}proxy",
    r"stop_ratio.{0,24}(仅作为|只作为|只能作为).{0,24}(关注信号|中断关注信号)",
    r"stop_ratio.{0,24}(不能|不得|不应).{0,24}(直接解释|解释为|证明).{0,24}(异常原因|设备异常|非计划停机)",
    r"local_background.{0,24}(仅作为|只作为).{0,24}(背景|解释)",
    r"local_background.{0,24}(不作为|不能作为|不得作为).{0,24}(当日结论|结论)",
    r"GRCI.{0,24}(is not|does not mean|must not be written as).{0,24}(disaster probability|risk probability|probability)",
    r"forward attention.{0,24}(only indicates|does not indicate|does not mean).{0,24}(attention|occurred fact|fact)",
    r"stop[_ ]?ratio.{0,24}(only serves|does not directly prove|must not be interpreted).{0,24}(signal|abnormal cause|unplanned shutdown)",
]


def check_twin_boundary_violations(
    report_text: str,
    *,
    evidence_pack: dict[str, Any] | None = None,
    twin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check whether report text violates twin/evidence governance boundaries."""
    text = report_text or ""
    violations: list[dict[str, Any]] = []
    for violation_type, rule in BOUNDARY_RULES.items():
        for pattern in rule["patterns"]:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                context = text[max(0, match.start() - 32): min(len(text), match.end() + 32)]
                if _is_safe_boundary_statement(context):
                    continue
                violations.append(
                    {
                        "type": violation_type,
                        "violation_type": violation_type,
                        "severity": rule.get("severity", "error"),
                        "matched_text": match.group(0),
                        "pattern": pattern,
                        "span": [match.start(), match.end()],
                    }
                )

    pack_governance = (evidence_pack or {}).get("evidence_governance") or {}
    twin_governance = (twin or {}).get("governance") or {}
    return {
        "ok": not violations,
        "has_violation": bool(violations),
        "violation_count": len(violations),
        "violations": violations,
        "checked_boundaries": list(BOUNDARY_RULES.keys()),
        "governance_source": {
            "evidence_pack_has_governance": bool(pack_governance),
            "twin_has_governance": bool(twin_governance),
        },
    }


def _is_safe_boundary_statement(text: str) -> bool:
    """Return True for explicit policy/boundary statements, not violations."""
    return any(re.search(pattern, text or "", flags=re.IGNORECASE) for pattern in SAFE_BOUNDARY_PATTERNS)
