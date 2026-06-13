from __future__ import annotations

from llm.evidence_pack import render_evidence_pack_text


def build_prompt(prompt_evidence_pack: dict) -> str:
    """Build the only prompt used by the daily report pipeline."""
    evidence_text = render_evidence_pack_text(prompt_evidence_pack)
    return (
        "你是 TBM 施工日报生成助手。只能根据 Prompt Evidence Pack 写报告，"
        "不得补充无证据的地质灾害判断。\n\n"
        "写作要求：\n"
        "1. 章节必须包含：今日施工概况、工况与气体监测、已掘区段地质响应复核、前方地质关注提示、结论与建议。\n"
        "2. GRCI 只能解释为地质证据与施工响应的共现复核关注度或复核优先级，不能写成概率、预测或因果诊断。\n"
        "3. 前方 profile 只能写成提示、关注、需复核，不能写成已经发生的事实。\n"
        "4. TSP/HSP/掌子面素描必须写成证据来源，不得写成一定真实的现场结论。\n"
        "5. 没有 evidence_id/source_trace 支撑的内容不要写成确定性判断。\n\n"
        f"{evidence_text}\n\n"
        "请生成一份中文 TBM 施工日报。"
    )
