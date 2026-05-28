from __future__ import annotations

from llm.summary_contract import build_prompt_payload


def build_prompt_timewindow(
    start_time: str,
    end_time: str,
    seg_text: str,
    stats_text: str,
    state_text: str,
    eff_text: str,
    state_stats_text: str,
    gas_text: str,
    geo_text: str,
    llm_summary: dict,
) -> str:
    """Build the time-window TBM report prompt."""
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
        },
    )
    texts = payload["texts"]
    summary_block = payload["summary_block"]

    return f"""
你现在要撰写一份正式的《TBM 施工时间窗工况分析报告》。

分析时间窗：
开始时间：{start_time}
结束时间：{end_time}

写作原则：
1. 只围绕该时间窗写作，不外推到其他日期或未给出的时段。
2. 只能依据给定信息写作，不要虚构结论。
3. 仍然必须严格区分 operation_mode、cluster_state、response_anomaly 三类状态。
4. 仍然必须严格区分 当前掌子面描述、已开挖区段摘要、前方风险提示 三类空间信息。
5. 已开挖区段摘要属于回顾性复核，不要写成“尚未开挖的潜在风险段”。
6. 如果掌子面资料不足，要直接说明，不要用前方预报替代。
7. 风险表述保持审慎，避免写成已经发生灾害。
8. 不要输出程序字段名，不要把结构化对象直接拼成字符串。

建议章节：
1. 时段施工概况
2. 基础工况与施工节奏
3. 聚类施工状态与效率分析
4. 当前掌子面描述
5. 已开挖区段响应异常与耦合复核
6. 气体监测分析
7. 前方风险提示
8. 结论与建议

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

区段响应异常摘要：
{texts["response_anomaly_text"]}

区段耦合分析：
{texts["coupling_text"]}

数字孪生快照：
{texts["digital_twin_text"]}

气体分析：
{texts["gas_text"]}

前方风险提示：
{texts["forward_risk_text"]}
""".strip()