from __future__ import annotations

import pytest

from llm.twin_boundary_checker import check_twin_boundary_violations


@pytest.mark.parametrize(
    ("text", "violation_type"),
    [
        ("GRCI 表示灾害概率", "grci_probability_misuse"),
        ("该单元 GRCI 为 0.8，说明灾害概率较高", "grci_probability_misuse"),
        ("GRCI indicates disaster probability", "grci_probability_misuse"),
        ("GRCI predicts the probability of hazard occurrence", "grci_probability_misuse"),
        ("前方已发生异常", "forward_fact_misuse"),
        ("前方已经揭示破碎带", "forward_fact_misuse"),
        ("PLC 证明前方异常", "forward_fact_misuse"),
        ("已掘 PLC 表明前方存在不良地质", "forward_fact_misuse"),
        ("forward_attention 证明前方风险", "forward_fact_misuse"),
        ("forward attention proves the front ground condition", "forward_fact_misuse"),
        ("PLC proves forward abnormal geology", "forward_fact_misuse"),
        ("cutterhead_power_proxy 是真实功率", "plc_proxy_misuse"),
        ("PLC enhanced metrics 证明地质风险", "plc_proxy_misuse"),
        ("cutterhead_power_proxy is true physical power", "plc_proxy_misuse"),
        ("torque_per_penetration proves geological hazard", "plc_proxy_misuse"),
        ("stop_ratio 说明设备异常", "stop_causality_misuse"),
        ("停机比例高说明发生设备故障", "stop_causality_misuse"),
        ("stop_ratio proves equipment failure", "stop_causality_misuse"),
        ("high stop ratio indicates abnormal cause", "stop_causality_misuse"),
        ("local_background 证明当日异常", "local_background_scope_misuse"),
        ("背景证据证明当前掌子面异常", "local_background_scope_misuse"),
        ("local background proves today's abnormal condition", "local_background_scope_misuse"),
        ("background evidence proves the forward condition", "local_background_scope_misuse"),
    ],
)
def test_twin_boundary_checker_detects_chinese_and_english_violations(text: str, violation_type: str):
    result = check_twin_boundary_violations(text)

    assert result["has_violation"] is True
    assert result["violation_count"] >= 1
    assert violation_type in {item["type"] for item in result["violations"]}
    first = result["violations"][0]
    assert first["severity"] == "error"
    assert first["matched_text"]


@pytest.mark.parametrize(
    "text",
    [
        "GRCI 不是灾害概率。",
        "RAI 不是风险概率。",
        "forward_attention 仅表示前方关注提示，不表示已发生事实。",
        "不把前方证据写成已揭露事实。",
        "不能将前方提示写成已发生事实。",
        "前方证据不能证明已揭露地质事实。",
        "不能把 PLC 写成证明前方异常。",
        "PLC enhanced metrics 仅作为已掘区段施工响应证据，不单独构成地质风险判断。",
        "cutterhead_power_proxy 不是真实物理功率。",
        "thrust_per_penetration 仅作为负载-贯入关系 proxy。",
        "stop_ratio 只能作为施工运行中断关注信号，不能直接解释为异常原因。",
        "local_background 仅作为背景解释，不作为当日结论。",
        "GRCI is not a disaster probability.",
        "GRCI 为地质-施工响应耦合关注度，非灾害发生概率。",
        "forward attention only indicates attention and does not indicate an occurred fact.",
        "Forward evidence should not be written as an occurred fact.",
        "PLC evidence cannot prove forward abnormal geology.",
        "stop_ratio only serves as an operation interruption signal.",
        "前方关注证据需结合后续现场揭露进行复核。",
        "前方关注证据，需结合现场揭露进行核查。",
    ],
)
def test_twin_boundary_checker_does_not_flag_safe_boundary_statements(text: str):
    result = check_twin_boundary_violations(text)

    assert result["has_violation"] is False
    assert result["violation_count"] == 0
    assert result["violations"] == []


@pytest.mark.parametrize(
    "text",
    [
        "该提示基于前方地质证据，属于关注与提示性质，非已发生现场事实。",
        "该提示基于前方地质预报证据，为关注性提示，非已发生事实。",
    ],
)
def test_twin_boundary_checker_allows_forward_fact_negation(text: str):
    result = check_twin_boundary_violations(text)

    assert result["has_violation"] is False
    assert result["violation_count"] == 0
