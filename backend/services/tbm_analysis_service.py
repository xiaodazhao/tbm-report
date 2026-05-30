from typing import Any

import pandas as pd

from analysis.dataprocess import (
    annotate_routine_ring_building_stops, annotate_operation_mode, load_and_process, segments_to_text, compute_stats, stats_to_text,
    build_operation_context,
)
from analysis.excavation_state import (
    detect_excavation_state, excavation_state_segments, explain_excavation_states,
    excavation_state_to_text, excavation_state_efficiency, excavation_state_stats,
    excavation_state_stats_to_text, build_cluster_context
)
from analysis.gas_analysis import compute_gas_stats, gas_stats_to_text, build_gas_context
from analysis.plc_cell_response import build_cell_response_df, summarize_cell_response
from analysis.plc_quality_checker import check_plc_quality
from analysis.forward_risk_advisor import (
    generate_forward_risk_summary,
    forward_risk_to_text,
)
from analysis.geology_response_coupling import run_coupling_analysis
from config import BACKEND_DIR, EVIDENCE_DB_PATH, RESULT_DIR
from geology.geology_fusion_backend import attach_geology_labels, load_evidence_db
from geology.geology_summary import (
    summarize_geology_record_level,
    summarize_geology_segment_level,
    geology_summary_to_text,
    build_face_geo_text,
)
from geology.segment_analysis import (
    run_segment_analysis,
    build_typical_segments_table,
)
from llm.summary_contract import (
    LLM_SUMMARY_SCHEMA_VERSION,
    build_response_anomaly_summary,
)
from llm.prompt_evidence_pack import build_prompt_evidence_pack
from services.digital_twin_state import build_digital_twin_state
from services.cst_update_service import build_or_update_cst
from services.run_metadata_service import build_run_metadata
from services.twin_state_builder import build_twin_state
from utils.chainage_utils import format_chainage_dk
from utils.serialization import serialize_for_json

from geology_v2.pipeline import run_geology_v2_context, geology_v2_prompt_block


RUN_METADATA_CONFIG_PATHS = [
    str(BACKEND_DIR / "configs" / "tbm_report_config.json"),
    str(BACKEND_DIR / "configs" / "prompt_policy.json"),
    str(BACKEND_DIR / "configs" / "quality_checker_policy.json"),
]

def semantic_efficiency_to_text(eff_df: pd.DataFrame) -> str:
    """
    语义聚合后的施工状态效率表 -> 文本
    """
    if eff_df is None or eff_df.empty:
        return "数据量不足，无法计算施工状态效率统计。"

    lines = ["不同施工状态语义下的效率统计如下："]

    for _, row in eff_df.iterrows():
        label = row.get("label_text", "未知状态")
        parts = [f"{label}："]

        if "平均推进速度" in row and pd.notna(row["平均推进速度"]):
            parts.append(f"平均推进速度 {row['平均推进速度']:.2f}")

        if "平均推力" in row and pd.notna(row["平均推力"]):
            parts.append(f"平均推力 {row['平均推力']:.2f}")

        if "平均刀盘扭矩" in row and pd.notna(row["平均刀盘扭矩"]):
            parts.append(f"平均刀盘扭矩 {row['平均刀盘扭矩']:.2f}")

        if "平均刀盘实际转速" in row and pd.notna(row["平均刀盘实际转速"]):
            parts.append(f"平均刀盘实际转速 {row['平均刀盘实际转速']:.2f}")

        lines.append("，".join(parts) + "。")

    return "\n".join(lines)


# =========================
# 自适应状态识别参数
# =========================
STATE_FEATURES = ("推力", "刀盘扭矩", "刀盘实际转速", "推进速度")


def estimate_valid_samples(
    df: pd.DataFrame,
    feature_cols=STATE_FEATURES
) -> int:
    """Estimate valid samples."""
    valid_mask = pd.Series(True, index=df.index)

    if "is_working" in df.columns:
        valid_mask &= df["is_working"].fillna(False).astype(bool)
    elif "operation_mode" in df.columns:
        valid_mask &= df["operation_mode"].astype(str).eq("work")
    elif "掘进状态" in df.columns:
        valid_mask &= (pd.to_numeric(df["掘进状态"], errors="coerce").fillna(0) != 0)
    else:
        temp_mask = pd.Series(False, index=df.index)
        if "推力" in df.columns:
            temp_mask |= (pd.to_numeric(df["推力"], errors="coerce").fillna(0).abs() > 1e-8)
        if "推进速度" in df.columns:
            temp_mask |= (pd.to_numeric(df["推进速度"], errors="coerce").fillna(0).abs() > 1e-8)
        valid_mask &= temp_mask

    for col in feature_cols:
        if col in df.columns:
            valid_mask &= pd.to_numeric(df[col], errors="coerce").notna()

    return int(valid_mask.sum())


def choose_state_params(n_valid: int):
    """Choose state params."""
    if n_valid < 5:
        return {
            "do_cluster": False,
            "n_states": 0,
            "min_duration_sec": 0
        }
    elif n_valid < 10:
        return {
            "do_cluster": True,
            "n_states": 2,
            "min_duration_sec": 0
        }
    elif n_valid < 30:
        return {
            "do_cluster": True,
            "n_states": 3,
            "min_duration_sec": 20
        }
    else:
        return {
            "do_cluster": True,
            "n_states": 4,
            "min_duration_sec": 60
        }


def risk_probability_to_text(df_geo):
    """
    Backward-compatible name for a geo-attention profile text.

    This is not a probability model. It ranks chainage points by existing
    multi-source geology evidence support and produces prompt-safe wording.
    """
    try:
        if df_geo is None or df_geo.empty:
            return "未进行沿线地质关注剖面分析。"

        df = df_geo.copy()
        if "chainage" not in df.columns:
            return "缺少里程信息，无法进行沿线地质关注剖面分析。"

        df["chainage"] = pd.to_numeric(df["chainage"], errors="coerce")
        df = df.dropna(subset=["chainage"]).copy()
        if df.empty:
            return "缺少有效里程数据，无法进行沿线地质关注剖面分析。"

        score = pd.Series(0.0, index=df.index)
        for col, weight in [
            ("active_report_source_count", 1.0),
            ("active_source_count", 1.0),
            ("matched_evidence_record_count", 0.4),
            ("evidence_count", 0.4),
            ("evidence_support_weight_sum", 1.0),
            ("weighted_evidence_strength", 1.0),
            ("geo_attention_hint_score", 1.0),
            ("risk_score", 1.0),
        ]:
            if col in df.columns:
                score += pd.to_numeric(df[col], errors="coerce").fillna(0) * weight

        df["geo_attention_profile_score"] = score
        top = (
            df.sort_values("geo_attention_profile_score", ascending=False)
              .drop_duplicates(subset=["chainage"])
              .head(5)
        )

        if top.empty or float(top["geo_attention_profile_score"].fillna(0).max()) <= 0:
            return "基于现有多源地质信息，当前未识别出表现特别突出的地质关注里程点，整体关注程度相对平稳。"

        lines = ["基于多源地质信息，对沿线里程点进行了地质关注度排序。结果提示："]
        for _, row in top.iterrows():
            ch = row["chainage"]
            active_cnt = int(pd.to_numeric(row.get("active_report_source_count", row.get("active_source_count", 0)), errors="coerce") or 0)
            evidence_cnt = int(pd.to_numeric(row.get("matched_evidence_record_count", row.get("evidence_count", 0)), errors="coerce") or 0)
            hazard = str(row.get("geo_hazard_summary", row.get("hazard", ""))).strip()
            text_line = f"里程约 {format_chainage_dk(ch)} 附近表现出相对较高地质关注特征"
            if active_cnt > 0:
                text_line += f"，报告-来源组合命中数为 {active_cnt}"
            if evidence_cnt > 0:
                text_line += f"，证据记录数为 {evidence_cnt}"
            if hazard and hazard.lower() != "nan":
                text_line += f"，主要关注表现为{hazard}"
            text_line += "。"
            lines.append(text_line)

        lines.append(
            "上述结果反映的是多源信息综合关注程度，不代表实际灾害已发生，相关结论需结合现场监测、掌子面揭示及施工响应进一步核查。"
        )
        return "\n".join(lines)
    except Exception as e:
        print("[Geo Attention Profile Text Error]", e)
        return "沿线地质关注剖面分析不可用。"


# ============================================================
# _run_geology_analysis：地质融合与地质-施工耦合分析主流程
#
# 输入：
#   df：单日 TBM 原始运行数据
#
# 主流程：
#   1. 读取 evidence_db.csv 地质证据库
#   2. 根据里程把 TSP/HSP/素描/钻孔等证据贴到 PLC 数据上，生成 df_geo
#   3. 生成记录级地质摘要 geo_summary_record
#   4. 生成区段级地质摘要 geo_summary_segment
#   5. 提取典型高关注区段 typical_segments_df
#   6. 根据当前掌子面位置生成前方风险提示 forward_risk_summary
#   7. 计算地质-施工响应耦合指标 GRS、RAI、GRCI
#   8. 返回 geology_result，供 analyze_tbm_data 统一组装 result
#
# 输出：
#   geology_result：包含 df_geo、geo_text、forward_risk_text、
#   coupling_summary、high_attention_segments 等地质相关结果
# ============================================================

# ============================================================
# geology_v2 接入辅助函数
# ============================================================
def _infer_current_chainage_for_geology_v2(df: pd.DataFrame) -> float | None:
    # 从 PLC/df_geo 中推断当前掌子面里程。
    # 优先使用 chainage 最后一条有效记录，保持与原有 _run_geology_analysis 逻辑一致。
    if df is None or df.empty or "chainage" not in df.columns:
        return None

    values = pd.to_numeric(df["chainage"], errors="coerce").dropna()
    if values.empty:
        return None

    return float(values.iloc[-1])


def _run_geology_v2_context_safe(
    *,
    df_geo: pd.DataFrame,
    evidence_df: pd.DataFrame,
    current_chainage: float | None,
    context: dict | None = None,
) -> dict:
    # 安全运行 geology_v2 pipeline。
    # online 模式会进行 evidence availability filter，避免未来超前预报/解释结论泄漏。
    # 这里不替代旧的 GRS/RAI/GRCI 主链路，只补充 geology_v2 上下文。
    # 失败时返回 ok=False，不抛出到主报告流程。
    if run_geology_v2_context is None:
        return {
            "ok": False,
            "warnings": ["geology_v2.pipeline 未能导入，跳过 geology_v2 接入。"],
            "texts": {},
            "data_summary": {},
        }

    if current_chainage is None:
        return {
            "ok": False,
            "warnings": ["缺少 current_chainage，跳过 geology_v2 接入。"],
            "texts": {},
            "data_summary": {},
        }

    ctx = context or {}
    analysis_date = (
        ctx.get("analysis_date")
        or ctx.get("date")
        or ctx.get("report_date")
        or None
    )

    try:
        return run_geology_v2_context(
            df_plc=df_geo,
            evidence_df=evidence_df,
            current_chainage=current_chainage,
            analysis_date=analysis_date,
            mode=ctx.get("geology_v2_mode", "online"),
            advance_direction=ctx.get("advance_direction", 1),
            lookahead_m=float(ctx.get("geology_v2_lookahead_m", 30.0)),
            cell_length=float(ctx.get("geology_v2_cell_length_m", 10.0)),
            review_back_m=float(ctx.get("geology_v2_review_back_m", 20.0)),
            review_forward_m=float(ctx.get("geology_v2_review_forward_m", 40.0)),
            build_report=True,
            base_context={
                "analysis_mode": ctx.get("analysis_mode"),
                "source_name": ctx.get("source_name"),
                "source_path": ctx.get("source_path"),
            },
        )
    except Exception as exc:
        return {
            "ok": False,
            "warnings": [f"geology_v2 pipeline 运行失败：{exc}"],
            "texts": {},
            "data_summary": {},
        }


def _apply_geology_v2_to_llm_summary(
    llm_summary: dict,
    geology_result: dict,
) -> dict:
    # 将 geology_v2 文本接入 LLM summary 的 prompt_text_inputs。
    # 原 prompt_builder 已经读取 excavated_segment_text 和 forward_risk_text，
    # 这里只替换这两个面向报告的文本入口。
    if not isinstance(llm_summary, dict):
        return llm_summary

    v2_result = geology_result.get("geology_v2_result") or {}
    if not isinstance(v2_result, dict) or not v2_result.get("ok"):
        return llm_summary

    texts = geology_result.get("geology_v2_texts") or {}
    if not isinstance(texts, dict):
        texts = {}

    prompt_text_inputs = llm_summary.setdefault("prompt_text_inputs", {})

    geo_brief_text = str(texts.get("geo_brief_text") or "").strip()
    forward_text = str(texts.get("forward_text") or "").strip()
    prompt_block = str(geology_result.get("geology_v2_prompt_block") or texts.get("prompt_block") or "").strip()
    rendered_text = str(geology_result.get("geology_v2_rendered_text") or "").strip()

    # 已开挖区段摘要：优先采用 geology_v2 的严格 cell 融合摘要。
    if geo_brief_text:
        prompt_text_inputs["excavated_segment_text"] = geo_brief_text

    # 前方风险提示：优先采用 geology_v2 的 forward_profile 文本。
    # 该文本明确说明“关注等级不等于灾害概率”，适合直接进报告。
    if forward_text:
        prompt_text_inputs["forward_risk_text"] = forward_text
        llm_summary["forward_risk_text"] = forward_text

    # 保留完整块，方便后续前端/调试读取；当前 prompt_builder 不强制展示该字段。
    if prompt_block:
        prompt_text_inputs["geology_v2_prompt_block"] = prompt_block
        llm_summary["geology_v2_prompt_block"] = prompt_block

    if rendered_text:
        llm_summary["geology_v2_rendered_text"] = rendered_text

    llm_summary["geology_v2_data_summary"] = serialize_for_json(
        geology_result.get("geology_v2_data_summary", {})
    )
    llm_summary["geology_v2_context"] = serialize_for_json(
        geology_result.get("geology_v2_context", {})
    )

    return llm_summary


def _run_geology_analysis(df: pd.DataFrame, context: dict | None = None) -> dict:
    # Run geology analysis with legacy geology chain + optional geology_v2 context.
    try:
        evidence_df = load_evidence_db(EVIDENCE_DB_PATH)

        # 1. 旧链路：按里程将地质证据融合到 TBM 运行数据上
        df_geo = attach_geology_labels(df, evidence_df)
        df_geo = annotate_routine_ring_building_stops(df_geo)

        current_chainage = _infer_current_chainage_for_geology_v2(df_geo)

        # 2. 旧链路：已开挖区段分析 + GRS/RAI/GRCI 耦合分析
        segment_df = run_segment_analysis(df_geo, segment_length=10)
        coupling_analysis_result = run_coupling_analysis(
            df_geo=df_geo,
            segment_length=10,
            base_segment_df=segment_df,
            output_dir=RESULT_DIR / "geology_response_coupling",
            top_k=10,
        )

        segment_df = coupling_analysis_result["segment_df"]
        coupling_summary = coupling_analysis_result["summary"]
        coupling_validation = coupling_analysis_result.get("validation", {})
        coupling_output_paths = coupling_analysis_result.get("output_paths", {})
        high_attention_segments = coupling_analysis_result.get("high_attention_segments", [])
        top_grci_segments = coupling_analysis_result.get("top_grci_segments", high_attention_segments)
        top_grs_segments = coupling_analysis_result.get("top_grs_segments", [])
        top_rai_segments = coupling_analysis_result.get("top_rai_segments", [])
        weak_label_validation = coupling_analysis_result.get("weak_label_validation", coupling_validation)

        # 3. 旧链路：记录级/区段级摘要、典型区段、前方风险提示
        geo_summary_record = summarize_geology_record_level(df_geo)
        geo_summary_segment = summarize_geology_segment_level(segment_df)
        typical_segments_df = build_typical_segments_table(segment_df, top_n=20)

        forward_risk_summary = generate_forward_risk_summary(
            df_plc=df_geo,
            evidence_df=evidence_df,
            lookahead_m=30,
        )

        geology_result = {
            "df_geo": df_geo,
            "segment_df": segment_df,
            "typical_segments_df": typical_segments_df,
            "geo_summary_record": geo_summary_record,
            "geo_summary_segment": geo_summary_segment,
            "geo_text": geology_summary_to_text(geo_summary_segment),
            "face_geo_text": build_face_geo_text(
                evidence_df,
                current_chainage=current_chainage,
            ),
            "forward_risk_summary": forward_risk_summary,
            "forward_risk_text": forward_risk_to_text(forward_risk_summary),
            "coupling_summary": coupling_summary,
            "coupling_validation": coupling_validation,
            "coupling_output_paths": coupling_output_paths,
            "high_attention_segments": high_attention_segments,
            "top_grci_segments": top_grci_segments,
            "top_grs_segments": top_grs_segments,
            "top_rai_segments": top_rai_segments,
            "weak_label_validation": weak_label_validation,
            "warnings": [],
        }

        # 4. 新链路：geology_v2 并行上下文
        geology_v2_result = _run_geology_v2_context_safe(
            df_geo=df_geo,
            evidence_df=evidence_df,
            current_chainage=current_chainage,
            context=context,
        )

        geology_v2_texts = geology_v2_result.get("texts") or {}
        if not isinstance(geology_v2_texts, dict):
            geology_v2_texts = {}

        geology_v2_prompt = ""
        if geology_v2_result.get("ok"):
            if geology_v2_prompt_block is not None:
                try:
                    geology_v2_prompt = geology_v2_prompt_block(geology_v2_result)
                except Exception:
                    geology_v2_prompt = str(geology_v2_texts.get("prompt_block") or "")
            else:
                geology_v2_prompt = str(geology_v2_texts.get("prompt_block") or "")

            # 面向报告的文本入口优先使用 v2。
            # 注意：不覆盖 coupling_summary，避免 v2 无响应数据时把旧 GRCI 结果冲掉。
            if geology_v2_texts.get("geo_brief_text"):
                geology_result["geo_text"] = str(geology_v2_texts["geo_brief_text"])
            if geology_v2_texts.get("forward_text"):
                geology_result["forward_risk_text"] = str(geology_v2_texts["forward_text"])
        else:
            geology_result["warnings"].extend(geology_v2_result.get("warnings", []))

        geology_result.update(
            {
                "geology_v2_result": geology_v2_result,
                "geology_v2_context": geology_v2_result.get("report_context", {}),
                "geology_v2_prompt_block": geology_v2_prompt,
                "geology_v2_rendered_text": geology_v2_result.get("rendered_report_text", ""),
                "geology_v2_data_summary": geology_v2_result.get("data_summary", {}),
                "geology_v2_texts": geology_v2_texts,
                "geology_v2_forward_profile": geology_v2_result.get("forward_profile", {}),
                "geology_v2_warnings": geology_v2_result.get("warnings", []),
                "geology_v2_geo_states_df": geology_v2_result.get("geo_states_df", pd.DataFrame()),
                "geology_v2_cell_evidence_df": geology_v2_result.get("cell_evidence_df", pd.DataFrame()),
                "geology_v2_normalized_df": geology_v2_result.get("normalized_df", pd.DataFrame()),
            }
        )

        return geology_result

    except Exception as exc:
        print(f"[Geology Error] {exc}")
        return {
            "df_geo": df.copy(),
            "segment_df": pd.DataFrame(),
            "typical_segments_df": pd.DataFrame(),
            "geo_summary_record": {"has_geology": False, "summary_text": "地质融合分析不可用。"},
            "geo_summary_segment": {"has_geology": False, "summary_text": "地质融合分析不可用。"},
            "geo_text": "地质融合分析不可用。",
            "face_geo_text": "掌子面地质摘要不可用。",
            "forward_risk_summary": {"has_forward_risk": False},
            "forward_risk_text": "前方风险提示不可用。",
            "coupling_summary": {
                "has_coupling": False,
                "level_counts": {},
                "top_segments": [],
                "summary_text": "区段风险-施工响应耦合分析不可用。",
            },
            "coupling_validation": {},
            "coupling_output_paths": {},
            "high_attention_segments": [],
            "top_grci_segments": [],
            "top_grs_segments": [],
            "top_rai_segments": [],
            "weak_label_validation": {},
            "geology_v2_result": {"ok": False, "warnings": [f"主地质流程失败，未运行 geology_v2：{exc}"]},
            "geology_v2_context": {},
            "geology_v2_prompt_block": "",
            "geology_v2_rendered_text": "",
            "geology_v2_data_summary": {},
            "geology_v2_texts": {},
            "geology_v2_forward_profile": {},
            "geology_v2_warnings": [f"主地质流程失败，未运行 geology_v2：{exc}"],
            "geology_v2_geo_states_df": pd.DataFrame(),
            "geology_v2_cell_evidence_df": pd.DataFrame(),
            "geology_v2_normalized_df": pd.DataFrame(),
            "warnings": [f"地质融合分析已降级：{exc}"],
        }


def _run_operation_analysis(df_geo: pd.DataFrame) -> dict:
    """Run operation analysis."""
    df_operation = annotate_operation_mode(df_geo)
    df_operation = annotate_routine_ring_building_stops(df_operation)
    segments = load_and_process(df_operation)
    stats = compute_stats(segments)
    return {
        "df_operation": df_operation,
        "segments": segments,
        "seg_text": segments_to_text(segments),
        "stats": stats,
        "stats_text": stats_to_text(stats),
    }


def _run_state_analysis(df_geo: pd.DataFrame) -> dict:
    """Run state analysis."""
    n_valid = estimate_valid_samples(df_geo, STATE_FEATURES)
    state_cfg = choose_state_params(n_valid)

    result = {
        "df_state": df_geo.copy(),
        "state_labels": {},
        "state_segments": {},
        "state_text": "当日有效工作样本过少，未进行隐含施工状态识别。",
        "eff_df": pd.DataFrame(),
        "eff_text": "当日有效工作样本过少，无法计算施工状态效率统计。",
        "state_stats": {},
        "state_stats_text": "当日有效工作样本过少，无施工状态统计结果。",
        "n_valid": n_valid,
        "state_cfg": state_cfg,
        "warnings": [],
    }

    if not state_cfg["do_cluster"]:
        return result

    try:
        df_state, _ = detect_excavation_state(
            df_geo.copy(),
            features=STATE_FEATURES,
            n_states=state_cfg["n_states"],
        )
        state_labels = explain_excavation_states(df_state)
        state_segments = excavation_state_segments(
            df_state,
            min_duration_sec=state_cfg["min_duration_sec"],
        )
        state_text = excavation_state_to_text(state_segments, state_labels)
        raw_eff_df = excavation_state_efficiency(df_state)

        if not raw_eff_df.empty:
            eff_df = raw_eff_df.reset_index().rename(columns={"state_id": "label"})
            eff_df["label_text"] = eff_df["label"].map(state_labels).fillna("未知状态")

            agg_dict = {}
            for col in ["平均推进速度", "平均推力", "平均刀盘扭矩", "平均刀盘实际转速", "平均推进给定速度"]:
                if col in eff_df.columns:
                    agg_dict[col] = "mean"

            if agg_dict:
                eff_df = eff_df.groupby("label_text", as_index=False).agg(agg_dict)
            else:
                eff_df = pd.DataFrame()
        else:
            eff_df = pd.DataFrame()

        result.update({
            "df_state": df_state,
            "state_labels": state_labels,
            "state_segments": state_segments,
            "state_text": state_text,
            "eff_df": eff_df,
            "eff_text": semantic_efficiency_to_text(eff_df),
            "state_stats": excavation_state_stats(df_state, state_segments),
        })
        result["state_stats_text"] = excavation_state_stats_to_text(
            result["state_stats"],
            state_labels,
        )
        return result
    except Exception as exc:
        print(f"[State Error] {exc}")
        result.update({
            "state_text": "施工状态分析不可用。",
            "eff_text": "施工效率分析不可用。",
            "state_stats_text": "施工状态统计不可用。",
            "warnings": [f"施工状态分析已降级：{exc}"],
        })
        return result


def _run_gas_analysis(df_geo: pd.DataFrame, df_state: pd.DataFrame) -> dict:
    """Run gas analysis."""
    try:
        gas_stats = compute_gas_stats(df_geo, df_state=df_state)
        return {
            "gas_stats": gas_stats,
            "gas_text": gas_stats_to_text(gas_stats),
            "warnings": [],
        }
    except Exception as exc:
        print(f"[Gas Error] {exc}")
        return {
            "gas_stats": {},
            "gas_text": "无气体监测数据。",
            "warnings": [f"气体分析已降级：{exc}"],
        }


def _build_operation_mode_summary(stats: dict) -> dict:
    """Build the rule-based operation-mode summary."""
    return {
        "state_space": "operation_mode",
        "level": "record_window",
        "stats": serialize_for_json(stats),
    }


def _build_cluster_state_summary(
    *,
    state_labels: dict,
    state_stats: dict,
    eff_df: pd.DataFrame,
    n_valid: int,
    state_cfg: dict,
) -> dict:
    """Build the unsupervised cluster-state summary."""
    efficiency_table = (
        eff_df.to_dict(orient="records")
        if isinstance(eff_df, pd.DataFrame) and not eff_df.empty
        else []
    )
    return {
        "state_space": "cluster_state",
        "level": "record_window",
        "labels": serialize_for_json(state_labels),
        "stats": serialize_for_json(state_stats),
        "efficiency_table": serialize_for_json(efficiency_table),
        "valid_samples": int(n_valid),
        "config": serialize_for_json(state_cfg),
    }


def _build_gas_summary(gas_stats: dict, gas_text: str) -> dict:
    """Build the gas summary object."""
    return {
        "stats": serialize_for_json(gas_stats),
        "text": gas_text,
    }


def _build_face_description(face_geo_text: str, digital_twin_state: dict) -> dict:
    """Build the current-face description object."""
    position_state = digital_twin_state.get("position_state", {}) if isinstance(digital_twin_state, dict) else {}
    return {
        "level": "current_face",
        "text": face_geo_text,
        "face_chainage": position_state.get("current_chainage"),
        "face_chainage_dk": position_state.get("current_chainage_dk"),
    }


def _build_excavated_segment_summary(
    *,
    geo_summary_segment: dict,
    geo_text: str,
    typical_segments_df: pd.DataFrame,
) -> dict:
    """Build the excavated-segment summary separate from face and forward views."""
    typical_segments = (
        typical_segments_df.to_dict(orient="records")
        if isinstance(typical_segments_df, pd.DataFrame) and not typical_segments_df.empty
        else []
    )
    return {
        "level": "excavated_segment",
        "summary": serialize_for_json(geo_summary_segment),
        "typical_segments": serialize_for_json(typical_segments),
        "text": geo_text,
    }


def _build_prompt_text_inputs(
    *,
    seg_text: str,
    stats_text: str,
    state_text: str,
    eff_text: str,
    state_stats_text: str,
    gas_text: str,
    geo_text: str,
    face_geo_text: str,
    forward_risk_text: str,
    risk_prob_text: str,
    coupling_summary: dict,
    response_anomaly_summary: dict,
    digital_twin_state: dict,
) -> dict:
    """Build prompt-only text fields so structured objects never enter prompts directly."""
    position_state = digital_twin_state.get("position_state", {}) if isinstance(digital_twin_state, dict) else {}
    if position_state:
        digital_twin_text = (
            f"当前掌子面里程 {position_state.get('current_chainage_dk', '暂无')}，"
            f"本次推进 {position_state.get('advance_length', 0)} m。"
        )
    else:
        digital_twin_text = "暂无数字孪生文字摘要。"

    return {
        "operation_segments_text": seg_text,
        "operation_stats_text": stats_text,
        "cluster_state_text": state_text,
        "cluster_efficiency_text": eff_text,
        "cluster_state_stats_text": state_stats_text,
        "gas_text": gas_text,
        "face_description_text": face_geo_text,
        "excavated_segment_text": geo_text,
        "forward_risk_text": forward_risk_text,
        "risk_profile_text": risk_prob_text,
        "response_anomaly_text": response_anomaly_summary.get("summary_text", "暂无"),
        "coupling_text": coupling_summary.get("summary_text", "暂无"),
        "digital_twin_text": digital_twin_text,
        "history_comparison_text": "暂无历史对比信息。",
    }


def _build_llm_summary(
    *,
    seg_text: str,
    stats: dict,
    stats_text: str,
    state_labels: dict,
    state_text: str,
    state_stats: dict,
    state_stats_text: str,
    eff_df: pd.DataFrame,
    eff_text: str,
    gas_stats: dict,
    gas_text: str,
    geo_summary_record: dict,
    geo_summary_segment: dict,
    geo_text: str,
    face_geo_text: str,
    typical_segments_df: pd.DataFrame,
    forward_risk_summary: dict,
    forward_risk_text: str,
    risk_prob_text: str,
    n_valid: int,
    state_cfg: dict,
    coupling_summary: dict,
    coupling_validation: dict,
    high_attention_segments: list,
    digital_twin_state: dict,
    cst_state: dict | None = None,
) -> dict:
    """Build llm summary."""
    response_anomaly_summary = build_response_anomaly_summary(
        coupling_summary=coupling_summary,
        high_attention_segments=high_attention_segments,
    )
    summary = {
        "schema_version": LLM_SUMMARY_SCHEMA_VERSION,
        "operation_mode_summary": _build_operation_mode_summary(stats),
        "cluster_state_summary": _build_cluster_state_summary(
            state_labels=state_labels,
            state_stats=state_stats,
            eff_df=eff_df,
            n_valid=n_valid,
            state_cfg=state_cfg,
        ),
        "gas_summary": _build_gas_summary(gas_stats, gas_text),
        "geology_summary_record": serialize_for_json(geo_summary_record),
        "geology_summary_segment": serialize_for_json(geo_summary_segment),
        "excavated_segment_summary": _build_excavated_segment_summary(
            geo_summary_segment=geo_summary_segment,
            geo_text=geo_text,
            typical_segments_df=typical_segments_df,
        ),
        "face_description": _build_face_description(face_geo_text, digital_twin_state),
        "forward_risk_summary": serialize_for_json(forward_risk_summary),
        "forward_risk_text": forward_risk_text,
        "response_anomaly_summary": response_anomaly_summary,
        "coupling_summary": serialize_for_json(coupling_summary),
        "coupling_validation": serialize_for_json(coupling_validation),
        "high_attention_segments": serialize_for_json(high_attention_segments),
        "top_grci_segments": serialize_for_json(coupling_summary.get("top_grci_segments", high_attention_segments) if isinstance(coupling_summary, dict) else high_attention_segments),
        "top_grs_segments": serialize_for_json(coupling_summary.get("top_grs_segments", []) if isinstance(coupling_summary, dict) else []),
        "top_rai_segments": serialize_for_json(coupling_summary.get("top_rai_segments", []) if isinstance(coupling_summary, dict) else []),
        "weak_label_validation": serialize_for_json(coupling_summary.get("weak_label_validation", coupling_validation) if isinstance(coupling_summary, dict) else coupling_validation),
        "digital_twin_state": serialize_for_json(digital_twin_state),
        "cst_state": serialize_for_json(cst_state or {}),
        "prompt_text_inputs": _build_prompt_text_inputs(
            seg_text=seg_text,
            stats_text=stats_text,
            state_text=state_text,
            eff_text=eff_text,
            state_stats_text=state_stats_text,
            gas_text=gas_text,
            geo_text=geo_text,
            face_geo_text=face_geo_text,
            forward_risk_text=forward_risk_text,
            risk_prob_text=risk_prob_text,
            coupling_summary=coupling_summary,
            response_anomaly_summary=response_anomaly_summary,
            digital_twin_state=digital_twin_state,
        ),
        "基础工况统计": stats,
        "施工状态标签": state_labels,
        "施工状态统计": state_stats,
        "施工状态效率表": eff_df.to_dict(orient="records") if not eff_df.empty else [],
        "气体统计": gas_stats,
        "地质摘要_记录级": geo_summary_record,
        "地质摘要_区段级": geo_summary_segment,
        "典型地质区段": typical_segments_df.to_dict(orient="records") if not typical_segments_df.empty else [],
        "前方风险提示摘要": forward_risk_summary,
        "前方风险提示文本": forward_risk_text,
        "有效状态样本数": n_valid,
        "状态识别配置": state_cfg,
        "区段风险-施工响应耦合分析": coupling_summary,
        "耦合分析弱标签验证": coupling_validation,
        "耦合分析高关注区段": high_attention_segments,
        "耦合分析GRCI高关注区段": coupling_summary.get("top_grci_segments", high_attention_segments) if isinstance(coupling_summary, dict) else high_attention_segments,
        "耦合分析RAI高响应区段": coupling_summary.get("top_rai_segments", []) if isinstance(coupling_summary, dict) else [],
        "数字孪生状态": digital_twin_state,
    }
    if cst_state:
        summary["Construction State Twin"] = cst_state
        summary["CST"] = cst_state
    return summary


def _build_prompt_evidence_pack_summary(pack: dict[str, Any] | None) -> dict[str, Any]:
    """Build a small debug-safe summary for PromptEvidencePack."""
    pack = pack if isinstance(pack, dict) else {}
    operation = pack.get("operation_evidence", {}) if isinstance(pack.get("operation_evidence"), dict) else {}
    geology = pack.get("geology_evidence", {}) if isinstance(pack.get("geology_evidence"), dict) else {}
    forward = pack.get("forward_evidence", {}) if isinstance(pack.get("forward_evidence"), dict) else {}
    return {
        "schema_version": pack.get("schema_version"),
        "ok": bool(pack.get("ok", False)),
        "has_operation_evidence": bool(
            operation.get("dominant_mode")
            or operation.get("dominant_mode_cn")
            or operation.get("key_segments")
        ),
        "has_geology_evidence": bool(
            geology.get("current_window_summary")
            or geology.get("key_cells")
        ),
        "has_forward_evidence": bool(forward.get("segments")),
        "source_trace_count": len(pack.get("source_trace", []) or []),
        "warning_count": len(pack.get("warnings", []) or []),
    }


def _build_pending_report_quality_summary() -> dict[str, Any]:
    """Build a placeholder report quality object before report text exists."""
    return {
        "schema_version": "report_quality_v2",
        "ok": False,
        "score": 0,
        "violations": [],
        "warnings": ["report_text 尚未生成，analyze_tbm_data 仅返回待检查占位对象。"],
        "stats": {
            "claim_count": 0,
            "grounded_claim_count": 0,
            "unsupported_claim_count": 0,
            "grounding_rate": 0.0,
            "section_count": 0,
            "missing_section_count": 0,
        },
        "grounding_summary": {
            "claim_count": 0,
            "grounded_claim_count": 0,
            "grounding_rate": 0.0,
            "unsupported_claim_count": 0,
        },
        "claim_results": None,
    }


def _build_pending_report_trace_summary() -> dict[str, Any]:
    """Build a placeholder report trace summary before report text exists."""
    return {
        "schema_version": "report_trace_summary_v1",
        "trace_available": False,
        "claim_trace_count": 0,
        "grounded_claim_count": 0,
        "unsupported_claim_count": 0,
        "trace_coverage": 0.0,
        "warnings": ["report_text 尚未生成，analyze_tbm_data 仅返回待溯源占位摘要。"],
    }


# ============================================================
# analyze_tbm_data 是后端核心分析总入口
#
# 输入：
#   df：单日 TBM 原始运行数据
#   context：日期、数据源、分析模式等上下文信息
#
# 主流程：
#   1. 地质融合：把 TSP/HSP/素描/钻孔等证据按里程贴到 PLC 数据上
#   2. 基础工况分析：识别停机、过渡、稳定掘进、异常扭矩
#   3. 聚类施工状态：在有效掘进样本中识别高负载/低速/稳定等状态模式
#   4. 气体分析：统计全天、掘进期、停机期及状态级气体变化
#   5. 风险与耦合分析：形成 GRS、RAI、GRCI 等区段级关注指标
#   6. 数字孪生状态：生成当前施工状态快照和 CST 结构
#   7. LLM 摘要：组装报告生成所需的结构化摘要和文本输入
#
# 输出：
#   result：一个大字典，供 /summary、/state、/geology、/report 等接口复用
# ============================================================ 
# df：一天的 TBM 运行数据
# context：接口传进来的日期、分析模式、文件名等
def analyze_tbm_data(df: pd.DataFrame, context: dict | None = None):
    """Analyze tbm data."""
    context = context or {}
    run_metadata = build_run_metadata(
        context=context,
        source_path=context.get("source_path"),
        evidence_db_path=str(EVIDENCE_DB_PATH),
        config_paths=RUN_METADATA_CONFIG_PATHS,
        llm_model=context.get("llm_model"),
    )
    plc_quality_report = check_plc_quality(df, date=context.get("date"))
    # 1. 地质融合：把 evidence_db 和 PLC 里程对齐
    geology_result = _run_geology_analysis(df, context=context)
    # 2. 基础工况：判断停机、过渡、稳定掘进、异常扭矩
    operation_result = _run_operation_analysis(geology_result["df_geo"])
    # 3. 聚类状态：用推力、扭矩、转速、推进速度做 KMeans
    state_result = _run_state_analysis(operation_result["df_operation"])
    # 4. 气体分析：统计 CO2/H2S/SO2/NO2/NO/CH4
    gas_result = _run_gas_analysis(operation_result["df_operation"], state_result["df_state"])

    operation_context = {
        "ok": False,
        "warnings": ["operation_context 未生成。"],
    }
    cluster_context = {
        "ok": False,
        "warnings": ["cluster_context 未生成。"],
    }
    gas_context = {
        "ok": False,
        "warnings": ["gas_context 未生成。"],
    }
    cell_response_summary = {
        "ok": False,
        "warnings": ["cell_response_summary 未生成。"],
    }
    cell_response_df = pd.DataFrame()

    try:
        operation_context = build_operation_context(
            operation_result.get("df_operation", geology_result["df_geo"]),
            segments=operation_result.get("segments"),
            stats=operation_result.get("stats"),
            quality_report=plc_quality_report,
        )
    except Exception as exc:
        operation_context = {"ok": False, "warnings": [f"operation_context 构建失败：{exc}"]}

    try:
        cluster_context = build_cluster_context(
            state_result.get("df_state"),
            segments=state_result.get("state_segments"),
            state_labels=state_result.get("state_labels"),
            eff_df=state_result.get("eff_df"),
            state_stats=state_result.get("state_stats"),
        )
    except Exception as exc:
        cluster_context = {"ok": False, "warnings": [f"cluster_context 构建失败：{exc}"]}

    try:
        gas_context = build_gas_context(
            gas_result.get("gas_stats", {}),
            quality_report=plc_quality_report,
        )
    except Exception as exc:
        gas_context = {"ok": False, "warnings": [f"gas_context 构建失败：{exc}"]}

    try:
        cell_response_df = build_cell_response_df(
            operation_result.get("df_operation", geology_result["df_geo"]),
            cell_length=10.0,
        )
        cell_response_summary = summarize_cell_response(cell_response_df)
    except Exception as exc:
        cell_response_summary = {"ok": False, "warnings": [f"cell_response_summary 构建失败：{exc}"]}

    warnings = [
        *plc_quality_report.get("warnings", []),
        *geology_result.get("warnings", []),
        *state_result.get("warnings", []),
        *gas_result.get("warnings", []),
        *(operation_context.get("warnings", []) if isinstance(operation_context, dict) else []),
        *(cluster_context.get("warnings", []) if isinstance(cluster_context, dict) else []),
        *(gas_context.get("warnings", []) if isinstance(gas_context, dict) else []),
        *(cell_response_summary.get("warnings", []) if isinstance(cell_response_summary, dict) else []),
    ]

    risk_prob_text = risk_probability_to_text(geology_result["df_geo"])
    digital_twin_state = build_digital_twin_state(
        df_geo=geology_result["df_geo"],
        stats=operation_result["stats"],
        state_stats=state_result["state_stats"],
        gas_stats=gas_result["gas_stats"],
        geo_summary_segment=geology_result["geo_summary_segment"],
        forward_risk_summary=geology_result["forward_risk_summary"],
        coupling_summary=geology_result["coupling_summary"],
    )
    cst_state = build_or_update_cst(
        {
            "stats": operation_result["stats"],
            "state_stats": state_result["state_stats"],
            "gas_stats": gas_result["gas_stats"],
            "geo_summary_record": geology_result["geo_summary_record"],
            "geo_summary_segment": geology_result["geo_summary_segment"],
            "forward_risk_summary": geology_result["forward_risk_summary"],
            "coupling_summary": geology_result["coupling_summary"],
            "digital_twin_state": digital_twin_state,
            "llm_summary": {},
            "face_geo_text": geology_result["face_geo_text"],
            "high_attention_segments": geology_result["high_attention_segments"],
            "top_grci_segments": geology_result.get("top_grci_segments", geology_result["high_attention_segments"]),
            "top_grs_segments": geology_result.get("top_grs_segments", []),
            "top_rai_segments": geology_result.get("top_rai_segments", []),
            "warnings": warnings,
        },
        case_id=context.get("case_id"),
        context=context,
        persist=bool(context.get("persist_cst", False)),
    )
    
    # 5. 汇总成给 LLM 用的结构化 summary
    llm_summary = _build_llm_summary(
        seg_text=operation_result["seg_text"],
        stats=operation_result["stats"],
        stats_text=operation_result["stats_text"],
        state_labels=state_result["state_labels"],
        state_text=state_result["state_text"],
        state_stats=state_result["state_stats"],
        state_stats_text=state_result["state_stats_text"],
        eff_df=state_result["eff_df"],
        eff_text=state_result["eff_text"],
        gas_stats=gas_result["gas_stats"],
        gas_text=gas_result["gas_text"],
        geo_summary_record=geology_result["geo_summary_record"],
        geo_summary_segment=geology_result["geo_summary_segment"],
        geo_text=geology_result["geo_text"],
        face_geo_text=geology_result["face_geo_text"],
        typical_segments_df=geology_result["typical_segments_df"],
        forward_risk_summary=geology_result["forward_risk_summary"],
        forward_risk_text=geology_result["forward_risk_text"],
        risk_prob_text=risk_prob_text,
        n_valid=state_result["n_valid"],
        state_cfg=state_result["state_cfg"],
        coupling_summary=geology_result["coupling_summary"],
        coupling_validation=geology_result["coupling_validation"],
        high_attention_segments=geology_result["high_attention_segments"],
        digital_twin_state=digital_twin_state,
        cst_state=cst_state,
    )
    llm_summary = _apply_geology_v2_to_llm_summary(llm_summary, geology_result)
    llm_summary["plc_quality_report"] = serialize_for_json(plc_quality_report)
    llm_summary["operation_context"] = serialize_for_json(operation_context)
    llm_summary["cluster_context"] = serialize_for_json(cluster_context)
    llm_summary["gas_context"] = serialize_for_json(gas_context)
    llm_summary["cell_response_summary"] = serialize_for_json(cell_response_summary)
    llm_summary["run_metadata"] = serialize_for_json(run_metadata)

    twin_state = {
        "schema_version": "twin_state_v1",
        "ok": False,
        "warnings": ["twin_state 未生成。"],
    }
    history_context = context.get("history_context") if isinstance(context.get("history_context"), dict) else {}
    try:
        twin_state = build_twin_state(
            date=context.get("date") or run_metadata.get("analysis_date"),
            context=context,
            operation_context=operation_context,
            cluster_context=cluster_context,
            gas_context=gas_context,
            geology_context=geology_result.get("geology_v2_context", {}),
            coupling_summary=geology_result["coupling_summary"],
            forward_context=geology_result.get("geology_v2_forward_profile") or geology_result["forward_risk_summary"],
            plc_quality_report=plc_quality_report,
            cell_response_summary=cell_response_summary,
            run_metadata=run_metadata,
            history_context=history_context,
        )
    except Exception as exc:
        twin_state = {
            "schema_version": "twin_state_v1",
            "ok": False,
            "warnings": [f"twin_state 构建失败：{exc}"],
        }

    llm_summary["twin_state"] = serialize_for_json(twin_state)

    try:
        prompt_evidence_pack = build_prompt_evidence_pack(
            twin_state=twin_state,
            llm_summary=llm_summary,
        )
    except Exception as exc:
        prompt_evidence_pack = {
            "schema_version": "prompt_evidence_pack_v1",
            "ok": False,
            "warnings": [f"prompt_evidence_pack 构建失败：{exc}"],
        }
    llm_summary["prompt_evidence_pack"] = serialize_for_json(prompt_evidence_pack)

    # Keep structural Twin/CST state independent from LLM summary/prompt text.
    # Only a lightweight reference is kept to avoid recursive references and semantic drift.
    if isinstance(cst_state, dict):
        cst_state["llm_summary_ref"] = {
            "schema_version": llm_summary.get("schema_version"),
            "prompt_text_input_keys": sorted((llm_summary.get("prompt_text_inputs") or {}).keys()),
        }

    return {
    "segments": operation_result["segments"],  # 基础工况分段结果：停机、过渡、工作、异常等连续时间段
    "seg_text": operation_result["seg_text"],  # 基础工况分段的文本描述，主要给 LLM 报告使用
    "stats": operation_result["stats"],  # 基础工况统计结果，例如工作时长、停机时长、异常段数量等
    "stats_text": operation_result["stats_text"],  # 基础工况统计的文本描述，主要给 LLM 报告使用
    "operation_mode_summary": _build_operation_mode_summary(operation_result["stats"]),  # 基础工况结构化摘要，用于统一描述 operation_mode 层面的状态
    "plc_quality_report": serialize_for_json(plc_quality_report),  # 单日 PLC 数据质量报告，包括时间/里程/缺失率/气体字段诊断
    "operation_context": serialize_for_json(operation_context),  # PLC 基础工况结构化上下文，保留关键工况段和位置摘要
    "df_geo": geology_result["df_geo"],  # 融合地质信息后的 TBM 数据表，在原始 PLC 数据基础上增加地质风险、围岩、灾害标签等字段
    "df_state": state_result["df_state"],  # 融合施工状态后的数据表，在 df_geo 基础上增加 state_id 等聚类状态字段
    "state_labels": state_result["state_labels"],  # 聚类施工状态的语义标签，例如高负载低速、稳定推进、低负载快速推进等
    "state_segments": state_result["state_segments"],  # 聚类施工状态的连续时间分段结果
    "state_text": state_result["state_text"],  # 聚类施工状态分段的文本描述，主要给 LLM 报告使用
    "eff_df": state_result["eff_df"],  # 不同聚类施工状态下的效率统计表，例如平均推进速度、平均推力、平均扭矩等
    "eff_text": state_result["eff_text"],  # 施工状态效率统计的文本描述，主要给 LLM 报告使用
    "state_stats": state_result["state_stats"],  # 聚类施工状态的总体统计，例如累计时长、占比、最大连续段、切换次数等
    "state_stats_text": state_result["state_stats_text"],  # 聚类施工状态总体统计的文本描述，主要给 LLM 报告使用
    "cluster_state_summary": _build_cluster_state_summary(  # 聚类施工状态的结构化摘要，用于统一描述 cluster_state 层面的状态
        state_labels=state_result["state_labels"],
        state_stats=state_result["state_stats"],
        eff_df=state_result["eff_df"],
        n_valid=state_result["n_valid"],
        state_cfg=state_result["state_cfg"],
    ),
    "cluster_context": serialize_for_json(cluster_context),  # 聚类施工状态结构化上下文，补充状态占比、稳定性和效率特征
    "gas_stats": gas_result["gas_stats"],  # 气体监测结构化统计结果，包括全天、掘进期、停机期及状态级气体统计
    "gas_text": gas_result["gas_text"],  # 气体监测分析文本，主要给 LLM 报告使用
    "gas_context": serialize_for_json(gas_context),  # 气体结构化上下文，区分 concentration / alarm_flag / unknown
    "geo_summary_record": geology_result["geo_summary_record"],  # 记录级地质摘要，通常对应每条 PLC 记录附近的地质融合信息
    "geo_summary_segment": geology_result["geo_summary_segment"],  # 区段级地质摘要，按里程区段汇总后的地质风险、围岩、灾害关注信息
    "geo_summary": geology_result["geo_summary_segment"],  # 地质摘要的兼容字段，实际等同于 geo_summary_segment
    "geo_text": geology_result["geo_text"],  # 已开挖区段地质摘要文本，主要给 LLM 报告使用
    "face_description": _build_face_description(geology_result["face_geo_text"], digital_twin_state),  # 当前掌子面描述的结构化对象，强调当前掌子面直接揭示信息
    "excavated_segment_summary": _build_excavated_segment_summary(  # 已开挖区段地质与响应复核摘要，用于和前方风险区分
        geo_summary_segment=geology_result["geo_summary_segment"],
        geo_text=geology_result["geo_text"],
        typical_segments_df=geology_result["typical_segments_df"],
    ),
    "segment_df": geology_result["segment_df"],  # 区段级分析结果表，通常包含地质关注、施工响应、耦合指标等字段
    "typical_segments_df": geology_result["typical_segments_df"],  # 典型地质区段表，用于提取代表性高关注区段
    "forward_risk_summary": geology_result["forward_risk_summary"],  # 掌子面前方窗口内的风险提示结构化摘要
    "forward_risk_text": geology_result["forward_risk_text"],  # 掌子面前方风险提示文本，主要给 LLM 报告使用
    "coupling_summary": geology_result["coupling_summary"],  # 地质-施工响应耦合分析摘要，包含 GRS、RAI、GRCI 等指标总体结果
    "coupling_validation": geology_result["coupling_validation"],  # 耦合分析的弱标签验证结果，用于评估高关注区段与施工异常代理标签的一致性
    "coupling_output_paths": geology_result["coupling_output_paths"],  # 耦合分析输出文件路径，例如区段 CSV、摘要 JSON、高关注区段 JSON 等
    "high_attention_segments": geology_result["high_attention_segments"],  # 高关注区段列表，通常指 GRCI 排名前列的区段
    "top_grci_segments": geology_result.get("top_grci_segments", geology_result["high_attention_segments"]),  # 按 GRCI 排序的高耦合关注区段，缺省时使用 high_attention_segments
    "top_grs_segments": geology_result.get("top_grs_segments", []),  # 按 GRS 排序的高地质关注区段
    "top_rai_segments": geology_result.get("top_rai_segments", []),  # 按 RAI 排序的高施工响应异常区段
    "weak_label_validation": geology_result.get("weak_label_validation", geology_result["coupling_validation"]),  # 弱标签验证结果的兼容字段，优先使用 weak_label_validation
    "response_anomaly_summary": build_response_anomaly_summary(  # 区段级施工响应异常摘要，用于和 operation_mode、cluster_state 区分
        coupling_summary=geology_result["coupling_summary"],
        high_attention_segments=geology_result["high_attention_segments"],
    ),
    "cell_response_summary": serialize_for_json(cell_response_summary),  # 按 10m cell 聚合的 PLC 响应摘要，不默认暴露完整 DataFrame
    "digital_twin_state": digital_twin_state,  # 数字孪生状态快照，描述当前 TBM 施工、地质、风险、气体等综合状态
    "cst_state": cst_state,  # Construction State Twin 结构化状态对象，比 digital_twin_state 更适合做状态更新和历史对比
    "twin_state": serialize_for_json(twin_state),  # 阶段 3 正式 TwinState，对 operation/cluster/gas/geology/coupling/forward/quality 做统一收口
    "run_metadata": run_metadata,  # 本次分析的轻量可复现元信息，包括源文件/hash/配置版本等
    "llm_summary": llm_summary,  # 给 LLM 报告生成使用的统一结构化摘要
    "prompt_evidence_pack_summary": serialize_for_json(
        _build_prompt_evidence_pack_summary(prompt_evidence_pack)
    ),  # PromptEvidencePack 的轻量摘要，默认不暴露完整 pack
    "report_quality": serialize_for_json(_build_pending_report_quality_summary()),  # 阶段 4 报告可信检查占位对象，真实内容在 report 生成后补齐
    "report_trace_summary": serialize_for_json(_build_pending_report_trace_summary()),  # 阶段 4 报告主张溯源摘要占位对象，真实内容在 report 生成后补齐
    "face_geo_text": geology_result["face_geo_text"],  # 当前掌子面地质描述文本，主要给 LLM 报告使用
    "risk_prob_text": risk_prob_text,  # 补充风险剖面文本，注意这里不是严格概率，应理解为风险/关注度描述
    "geology_v2_context": geology_result.get("geology_v2_context", {}),  # geology_v2 统一报告上下文
    "geology_v2_prompt_block": geology_result.get("geology_v2_prompt_block", ""),  # geology_v2 给 LLM 的完整地质块
    "geology_v2_rendered_text": geology_result.get("geology_v2_rendered_text", ""),  # geology_v2 渲染后的地质报告文本
    "geology_v2_data_summary": geology_result.get("geology_v2_data_summary", {}),  # geology_v2 诊断摘要
    "geology_v2_texts": geology_result.get("geology_v2_texts", {}),  # geology_v2 各类文本
    "geology_v2_forward_profile": geology_result.get("geology_v2_forward_profile", {}),  # geology_v2 前方分段剖面
    "geology_v2_warnings": geology_result.get("geology_v2_warnings", []),  # geology_v2 警告
    "warnings": warnings,  # 分析过程中的警告信息，例如字段缺失、地质证据不足、耦合分析不可用等
}


# =========================
# 空间风险剖面
# =========================
def build_risk_profile(df_geo: pd.DataFrame):
    """Build risk profile."""
    if "chainage" not in df_geo.columns:
        return {
            "profile": [],
            "high_segments": [],
            "has_data": False,
            "message": "缺少 chainage 字段"
        }

    use_cols = [c for c in [
        "chainage",
        "active_report_source_count",
        "active_source_count",
        "matched_evidence_record_count",
        "risk",
        "risk_score",
        "geo_hazard_summary",
        "hazard",
        "geo_coverage_status",
        "coverage",
        "active_source_types",
        "active_sources",
        "geo_fused_grade",
        "fused_grade"
    ] if c in df_geo.columns]

    if not use_cols:
        return {
            "profile": [],
            "high_segments": [],
            "has_data": False,
            "message": "缺少风险剖面所需字段"
        }

    prof_raw = df_geo[use_cols].copy()
    prof_raw["chainage"] = pd.to_numeric(prof_raw["chainage"], errors="coerce")
    prof_raw = prof_raw.dropna(subset=["chainage"]).copy()

    if prof_raw.empty:
        return {
            "profile": [],
            "high_segments": [],
            "has_data": False,
            "message": "当前日期无可用剖面数据"
        }

    source_count_col = "active_report_source_count" if "active_report_source_count" in prof_raw.columns else "active_source_count" if "active_source_count" in prof_raw.columns else None
    if source_count_col:
        prof_raw[source_count_col] = pd.to_numeric(
            prof_raw[source_count_col], errors="coerce"
        ).fillna(0)

    if "risk_score" in prof_raw.columns:
        prof_raw["risk_score"] = pd.to_numeric(
            prof_raw["risk_score"], errors="coerce"
        ).fillna(0)

    for col in ["risk", "geo_hazard_summary", "hazard", "geo_coverage_status", "coverage", "active_source_types", "active_sources", "geo_fused_grade", "fused_grade"]:
        if col in prof_raw.columns:
            prof_raw[col] = prof_raw[col].fillna("")

    agg_dict = {}
    if source_count_col:
        agg_dict[source_count_col] = "max"
    if "risk_score" in prof_raw.columns:
        agg_dict["risk_score"] = "max"
    if "risk" in prof_raw.columns:
        agg_dict["risk"] = "first"
    if "geo_hazard_summary" in prof_raw.columns:
        agg_dict["geo_hazard_summary"] = "first"
    if "hazard" in prof_raw.columns:
        agg_dict["hazard"] = "first"
    if "geo_coverage_status" in prof_raw.columns:
        agg_dict["geo_coverage_status"] = "first"
    if "coverage" in prof_raw.columns:
        agg_dict["coverage"] = "first"
    if "active_source_types" in prof_raw.columns:
        agg_dict["active_source_types"] = "first"
    if "active_sources" in prof_raw.columns:
        agg_dict["active_sources"] = "first"
    if "geo_fused_grade" in prof_raw.columns:
        agg_dict["geo_fused_grade"] = "first"
    if "fused_grade" in prof_raw.columns:
        agg_dict["fused_grade"] = "first"

    prof = (
        prof_raw
        .groupby("chainage", as_index=False)
        .agg(agg_dict)
        .sort_values("chainage")
        .reset_index(drop=True)
    )

    if prof.empty:
        return {
            "profile": [],
            "high_segments": [],
            "has_data": False,
            "message": "当前日期无可用剖面数据"
        }

    if source_count_col and source_count_col != "active_source_count" and source_count_col in prof.columns:
        prof["active_source_count"] = prof[source_count_col]

    if "risk_score" in prof.columns:
        prof["risk_value"] = prof["risk_score"]
    elif "risk" in prof.columns:
        risk_map = {"low": 1, "medium": 2, "high": 3}
        prof["risk_value"] = prof["risk"].map(risk_map).fillna(0)
    else:
        prof["risk_value"] = 0

    ch_min = prof["chainage"].min()
    prof["chainage_rel"] = prof["chainage"] - ch_min

    high_segments = []
    if "active_source_count" in prof.columns:
        high_df = prof[prof["active_source_count"] >= 4].copy()
    else:
        high_df = pd.DataFrame()

    if not high_df.empty:
        high_df["gap"] = high_df["chainage"].diff().fillna(0)
        high_df["group"] = (high_df["gap"] > 2).cumsum()

        for _, g in high_df.groupby("group"):
            hazards = sorted(set(
                str(x) for x in g.get("geo_hazard_summary", g.get("hazard", pd.Series(dtype=str))).dropna().tolist() if str(x).strip()
            ))
            sources = sorted(set(
                str(x) for x in g.get("active_source_types", g.get("active_sources", pd.Series(dtype=str))).dropna().tolist() if str(x).strip()
            ))

            high_segments.append({
                "start_chainage": float(g["chainage"].min()),
                "start_chainage_dk": format_chainage_dk(g["chainage"].min()),
                "end_chainage": float(g["chainage"].max()),
                "end_chainage_dk": format_chainage_dk(g["chainage"].max()),
                "start_rel": float(g["chainage_rel"].min()),
                "end_rel": float(g["chainage_rel"].max()),
                "max_attention": int(g["active_source_count"].max()),
                "hazards": " / ".join(hazards[:3]) if hazards else "",
                "sources": " / ".join(sources[:3]) if sources else "",
            })

    return {
        "has_data": True,
        "profile": serialize_for_json(prof.to_dict(orient="records")),
        "high_segments": serialize_for_json(high_segments),
        "message": "ok"
    }


def build_speed_profile(df_geo: pd.DataFrame):
    """Build speed profile."""
    if "chainage" not in df_geo.columns or "推进速度" not in df_geo.columns:
        return []

    plc = df_geo.copy()
    plc["chainage"] = pd.to_numeric(plc["chainage"], errors="coerce")
    plc["推进速度"] = pd.to_numeric(plc["推进速度"], errors="coerce")
    plc = plc.dropna(subset=["chainage", "推进速度"])

    if plc.empty:
        return []

    if "掘进状态" in plc.columns:
        plc = plc[pd.to_numeric(plc["掘进状态"], errors="coerce").fillna(0) != 0].copy()

    if plc.empty:
        return []

    grp = (
        plc.groupby("chainage", as_index=False)["推进速度"]
        .mean()
        .sort_values("chainage")
        .reset_index(drop=True)
    )

    global_min = pd.to_numeric(df_geo["chainage"], errors="coerce").dropna().min()
    grp["chainage_rel"] = grp["chainage"] - global_min

    return serialize_for_json(grp.to_dict(orient="records"))
