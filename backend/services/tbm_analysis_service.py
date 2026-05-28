import pandas as pd

from analysis.dataprocess import (
    annotate_routine_ring_building_stops, annotate_operation_mode, load_and_process, segments_to_text, compute_stats, stats_to_text
)
from analysis.excavation_state import (
    detect_excavation_state, excavation_state_segments, explain_excavation_states,
    excavation_state_to_text, excavation_state_efficiency, excavation_state_stats,
    excavation_state_stats_to_text
)
from analysis.gas_analysis import compute_gas_stats, gas_stats_to_text
from analysis.forward_risk_advisor import (
    generate_forward_risk_summary,
    forward_risk_to_text,
)
from analysis.geology_response_coupling import run_coupling_analysis
from config import EVIDENCE_DB_PATH, RESULT_DIR
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
from services.digital_twin_state import build_digital_twin_state
from services.cst_update_service import build_or_update_cst
from utils.chainage_utils import format_chainage_dk
from utils.serialization import serialize_for_json

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
# =========================
# 核心分析引擎
# =========================
def _run_geology_analysis(df: pd.DataFrame) -> dict:
    """Run geology analysis."""
    try:
        evidence_df = load_evidence_db(EVIDENCE_DB_PATH)
        df_geo = attach_geology_labels(df, evidence_df)
        df_geo = annotate_routine_ring_building_stops(df_geo)
        current_chainage = None
        if "chainage" in df_geo.columns:
            valid_chainage = pd.to_numeric(df_geo["chainage"], errors="coerce").dropna()
            if not valid_chainage.empty:
                current_chainage = float(valid_chainage.iloc[-1])

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

        geo_summary_record = summarize_geology_record_level(df_geo)
        geo_summary_segment = summarize_geology_segment_level(segment_df)
        typical_segments_df = build_typical_segments_table(segment_df, top_n=20)
        forward_risk_summary = generate_forward_risk_summary(
            df_plc=df_geo,
            evidence_df=evidence_df,
            lookahead_m=30,
        )

        return {
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
            "warnings": [f"地质融合分析已降级：{exc}"],
        }


def _run_operation_analysis(df_geo: pd.DataFrame) -> dict:
    """Run operation analysis."""
    segments = load_and_process(df_geo)
    stats = compute_stats(segments)
    return {
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


def analyze_tbm_data(df: pd.DataFrame, context: dict | None = None):
    """Analyze tbm data."""
    context = context or {}
    geology_result = _run_geology_analysis(df)
    operation_result = _run_operation_analysis(geology_result["df_geo"])
    state_result = _run_state_analysis(geology_result["df_geo"])
    gas_result = _run_gas_analysis(geology_result["df_geo"], state_result["df_state"])

    warnings = [
        *geology_result.get("warnings", []),
        *state_result.get("warnings", []),
        *gas_result.get("warnings", []),
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
    # Keep structural Twin/CST state independent from LLM summary/prompt text.
    # Only a lightweight reference is kept to avoid recursive references and semantic drift.
    if isinstance(cst_state, dict):
        cst_state["llm_summary_ref"] = {
            "schema_version": llm_summary.get("schema_version"),
            "prompt_text_input_keys": sorted((llm_summary.get("prompt_text_inputs") or {}).keys()),
        }

    return {
        "segments": operation_result["segments"],
        "seg_text": operation_result["seg_text"],
        "stats": operation_result["stats"],
        "stats_text": operation_result["stats_text"],
        "operation_mode_summary": _build_operation_mode_summary(operation_result["stats"]),
        "df_geo": geology_result["df_geo"],
        "df_state": state_result["df_state"],
        "state_labels": state_result["state_labels"],
        "state_segments": state_result["state_segments"],
        "state_text": state_result["state_text"],
        "eff_df": state_result["eff_df"],
        "eff_text": state_result["eff_text"],
        "state_stats": state_result["state_stats"],
        "state_stats_text": state_result["state_stats_text"],
        "cluster_state_summary": _build_cluster_state_summary(
            state_labels=state_result["state_labels"],
            state_stats=state_result["state_stats"],
            eff_df=state_result["eff_df"],
            n_valid=state_result["n_valid"],
            state_cfg=state_result["state_cfg"],
        ),
        "gas_stats": gas_result["gas_stats"],
        "gas_text": gas_result["gas_text"],
        "geo_summary_record": geology_result["geo_summary_record"],
        "geo_summary_segment": geology_result["geo_summary_segment"],
        "geo_summary": geology_result["geo_summary_segment"],
        "geo_text": geology_result["geo_text"],
        "face_description": _build_face_description(geology_result["face_geo_text"], digital_twin_state),
        "excavated_segment_summary": _build_excavated_segment_summary(
            geo_summary_segment=geology_result["geo_summary_segment"],
            geo_text=geology_result["geo_text"],
            typical_segments_df=geology_result["typical_segments_df"],
        ),
        "segment_df": geology_result["segment_df"],
        "typical_segments_df": geology_result["typical_segments_df"],
        "forward_risk_summary": geology_result["forward_risk_summary"],
        "forward_risk_text": geology_result["forward_risk_text"],
        "coupling_summary": geology_result["coupling_summary"],
        "coupling_validation": geology_result["coupling_validation"],
        "coupling_output_paths": geology_result["coupling_output_paths"],
        "high_attention_segments": geology_result["high_attention_segments"],
        "top_grci_segments": geology_result.get("top_grci_segments", geology_result["high_attention_segments"]),
        "top_grs_segments": geology_result.get("top_grs_segments", []),
        "top_rai_segments": geology_result.get("top_rai_segments", []),
        "weak_label_validation": geology_result.get("weak_label_validation", geology_result["coupling_validation"]),
        "response_anomaly_summary": build_response_anomaly_summary(
            coupling_summary=geology_result["coupling_summary"],
            high_attention_segments=geology_result["high_attention_segments"],
        ),
        "digital_twin_state": digital_twin_state,
        "cst_state": cst_state,
        "llm_summary": llm_summary,
        "face_geo_text": geology_result["face_geo_text"],
        "risk_prob_text": risk_prob_text,
        "warnings": warnings,
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