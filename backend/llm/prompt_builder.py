from __future__ import annotations

from llm.summary_contract import build_prompt_payload


def build_prompt(
    seg_text: str,
    stats_text: str,
    state_text: str,
    eff_text: str,
    state_stats_text: str,
    gas_text: str,
    geo_text: str,
    face_geo_text: str,
    llm_summary: dict,
    risk_prob_text: str,
) -> str:
    """Build the daily TBM report prompt."""
    payload = build_prompt_payload(
        llm_summary,
        fallbacks={
            "seg_text": seg_text,
            "stats_text": stats_text,
            "state_text": state_text,
            "eff_text": eff_text,
            "state_stats_text": state_stats_text,
            "gas_text": gas_text,
            "geo_text": geo_text,
            "face_geo_text": face_geo_text,
            "risk_prob_text": risk_prob_text,
        },
    )
    texts = payload["texts"]
    summary_block = payload["summary_block"]

    return f"""
你现在要撰写一份正式的《TBM 综合施工工况分析报告》。

角色定位：你是一名 TBM 施工分析工程师，面向项目管理、施工技术和安全管理人员输出正式工程报告。

写作原则：
1. 直接输出报告正文，不要写聊天式开场白。
2. 只能依据给定信息写作，不要虚构数字、现场现象或结论。
3. 必须严格区分三类空间语义：
当前掌子面描述：只写当前掌子面或最近邻掌子面的现场揭示/素描信息。
已开挖区段摘要：只写已经掘进完成区段的回顾性地质与施工响应复核。
前方风险提示：只写掌子面前方窗口内的风险提示，不要与当前掌子面混写。
4. 必须严格区分三类状态语义：
operation_mode：工作、停机、过渡、异常扭矩等基础工况状态。
cluster_state：基于施工参数聚类得到的施工状态。
response_anomaly：区段级响应异常与 RAI/GRCI 相关关注。
5. GRS 表示地质关注度，RAI 表示施工响应异常度，GRCI 表示地质-施工耦合关注证据，不能写成已被证实的灾害概率。
6. 若掌子面直接揭示资料不足，必须明确写出“当前掌子面直接揭示资料不足”，不能用前方预报或已开挖区段摘要替代。
7. 风险表述应使用“提示、关注、显示、建议核查、需谨慎解释”等审慎措辞。
8. 不要输出程序字段名，不要把结构化对象解释成原始 JSON。

建议章节：
1. 综合结论摘要
2. 总体施工运行概况
3. 基础工况统计分析
4. 聚类施工状态与效率分析
5. 当前掌子面描述
6. 已开挖区段地质与响应异常复核
7. 气体监测分析
8. 前方风险提示
9. 结论与建议

结构化 CST 摘要：
{summary_block}

基础工况分段：
{texts["operation_segments_text"]}

基础工况统计：
{texts["operation_stats_text"]}

聚类施工状态：
{texts["cluster_state_text"]}

聚类状态效率：
{texts["cluster_efficiency_text"]}

聚类状态统计：
{texts["cluster_state_stats_text"]}

当前掌子面描述：
{texts["face_description_text"]}

已开挖区段摘要：
{texts["excavated_segment_text"]}

补充区段风险剖面：
{texts["risk_profile_text"]}

区段响应异常摘要：
{texts["response_anomaly_text"]}

区段耦合分析：
{texts["coupling_text"]}

数字孪生快照：
{texts["digital_twin_text"]}

历史对比：
{texts["history_comparison_text"]}

气体分析：
{texts["gas_text"]}

前方风险提示：
{texts["forward_risk_text"]}
""".strip()