# ceshi.py
# 放在 backend/ceshi.py 运行

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import EVIDENCE_DB_PATH

from geology_v2.evidence_normalizer import (
    normalize_evidence_df,
    filter_available_evidence,
    summarize_normalized_evidence,
)

from geology_v2.pipeline import (
    run_geology_v2_context,
    print_pipeline_debug_summary,
    geology_v2_prompt_block,
)

from geology_v2.evidence_dedup import (
    deduplicate_hsp_anomaly_points,
    summarize_hsp_anomaly_point_dedup,
)

from geology_v2.cell_builder import build_chainage_cells

from geology_v2.evidence_projector import (
    project_evidence_to_cells,
    summarize_cell_evidence,
)

from geology_v2.fusion_engine import (
    fuse_geo_states,
    summarize_geo_states,
)

from geology_v2.forward_profile import (
    build_forward_profile,
    summarize_forward_profile,
)

from geology_v2.text_builder import (
    forward_profile_to_text,
    geo_states_to_brief_text,
    build_geology_v2_prompt_block,
)

from geology_v2.coupling_adapter import (
    couple_geo_response,
    summarize_coupled_df,
    coupled_df_to_text,
)

from geology_v2.report_context_builder import (
    build_geology_v2_report_context,
    report_context_to_prompt_text,
)

from geology_v2.report_renderer import (
    render_geology_v2_report_context,
    render_prompt_block_from_context,
)

from geology_v2.explainability import (
    explain_geo_state,
    explain_geo_state_text,
)


# =========================================================
# 测试参数
# =========================================================
CURRENT_CHAINAGE = 1013220.0
TARGET_CHAINAGE = 1013224.0
CHAINAGE_MIN = 1013200.0
CHAINAGE_MAX = 1013260.0
CELL_LENGTH_M = 10.0
LOOKAHEAD_M = 30.0
STEP_M = 10.0
ADVANCE_DIRECTION = 1

# online 模式会过滤未来 evidence，避免掌子面素描等未来信息泄漏。
# 如果你只是想复现旧的完整回顾结果，可以临时改成 "retrospective"。
EVIDENCE_FILTER_MODE = "online"
ANALYSIS_DATE = None


# =========================================================
# 工具函数
# =========================================================

def print_title(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def safe_json_dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def print_before_after_summary(before: dict, after: dict):
    print("=== 修改前后关键指标对比 ===")

    keys = [
        "GRS_geo_base_mean",
        "high_attention_cell_count",
        "main_hazard_counts",
        "conflict_level_counts",
    ]

    for key in keys:
        print(f"{key}:")
        print("  before:", before.get(key))
        print("  after :", after.get(key))


def print_existing_columns(
    df: pd.DataFrame,
    cols: list[str],
    title: str,
    max_rows: int = 20,
):
    print_title(title)

    if df is None or df.empty:
        print("DataFrame 为空。")
        return

    show_cols = [c for c in cols if c in df.columns]

    if not show_cols:
        print("没有可展示的目标列。候选列 =", cols)
        print("当前列 =", list(df.columns))
        return

    print(df[show_cols].head(max_rows).to_string())


def main():
    # =========================================================
    # 0. 输出目录
    # =========================================================
    out_dir = Path("outputs/geology_v2_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    current_chainage = CURRENT_CHAINAGE
    target_chainage = TARGET_CHAINAGE

    # =========================================================
    # 1. 读取旧 evidence_df
    # =========================================================
    print_title("1. 读取 evidence_df")

    evidence_df = pd.read_csv(EVIDENCE_DB_PATH)

    print("EVIDENCE_DB_PATH =", EVIDENCE_DB_PATH)
    print("evidence_df shape =", evidence_df.shape)
    print("evidence_df columns =", list(evidence_df.columns))
    print("current_chainage =", current_chainage)
    print("evidence filter mode =", EVIDENCE_FILTER_MODE)

    # =========================================================
    # 1.5. 临时测试 pipeline 模块
    # =========================================================
    print_title("1.5. 临时测试 pipeline 模块")

    try:
        pipeline_result = run_geology_v2_context(
            df_plc=None,
            evidence_df=evidence_df,
            current_chainage=current_chainage,
            analysis_date=ANALYSIS_DATE,
            mode=EVIDENCE_FILTER_MODE,
            advance_direction=ADVANCE_DIRECTION,
            lookahead_m=LOOKAHEAD_M,
            cell_length=CELL_LENGTH_M,
            review_back_m=20,
            review_forward_m=40,
            build_report=True,
        )

        print_pipeline_debug_summary(pipeline_result)

        print("\n=== pipeline prompt_block ===")
        print(geology_v2_prompt_block(pipeline_result))

        print("\n=== pipeline rendered_report_text ===")
        print(pipeline_result.get("rendered_report_text", ""))

    except Exception:
        print("pipeline 临时测试失败，但不影响后续原 ceshi.py 分步测试。异常如下：")
        traceback.print_exc()

    # =========================================================
    # 2. 第二阶段：normalize_evidence_df + 可用性过滤
    # =========================================================
    print_title("2. 标准化 evidence_df -> normalized_df，并过滤未来证据")

    normalized_df_all = normalize_evidence_df(evidence_df)

    print("normalized_df_all shape =", normalized_df_all.shape)
    print(normalized_df_all.head())

    normalized_summary_all = summarize_normalized_evidence(normalized_df_all)
    print("normalized summary before availability filter:")
    print(normalized_summary_all)

    normalized_df_all.to_csv(
        out_dir / "normalized_evidence_df_before_available_filter.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(
        normalized_summary_all,
        out_dir / "normalized_summary_before_available_filter.json",
    )

    normalized_df = filter_available_evidence(
        normalized_df=normalized_df_all,
        current_chainage=current_chainage,
        analysis_date=ANALYSIS_DATE,
        mode=EVIDENCE_FILTER_MODE,
        advance_direction=ADVANCE_DIRECTION,
        chainage_tolerance_m=1.0,
    )

    availability_filter_info = normalized_df.attrs.get("availability_filter", {})
    print("availability filter attrs:")
    print(availability_filter_info)

    print(
        "excluded_unavailable_prediction_count =",
        availability_filter_info.get("excluded_unavailable_prediction_count"),
    )

    print(
        "excluded_missing_face_chainage_count =",
        availability_filter_info.get("excluded_missing_face_chainage_count"),
    )

    print("normalized_df after availability filter shape =", normalized_df.shape)
    print(normalized_df.head())

    normalized_summary_before_dedup = summarize_normalized_evidence(normalized_df)
    print("normalized summary after availability filter, before HSP anomaly_point dedup:")
    print(normalized_summary_before_dedup)

    safe_json_dump(
        normalized_summary_before_dedup,
        out_dir / "normalized_summary_after_available_filter_before_hsp_dedup.json",
    )

    normalized_df_before_hsp_dedup = normalized_df.copy()
    normalized_df_before_hsp_dedup.to_csv(
        out_dir / "normalized_evidence_df_before_hsp_anomaly_point_dedup.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # =========================================================
    # 2.x HSP anomaly_point 边界重复去重
    # 必须放在 availability filter 之后、project_evidence_to_cells 之前
    # =========================================================
    print_title("2.x HSP anomaly_point 边界重复去重")

    hsp_anomaly_before = normalized_df[
        normalized_df.get("source_type_norm", pd.Series(dtype=str)).astype(str).eq("HSP")
        & normalized_df.get("spatial_type", pd.Series(dtype=str)).astype(str).eq("anomaly_point")
    ].copy()

    print("HSP anomaly_point count before dedup =", len(hsp_anomaly_before))

    if not hsp_anomaly_before.empty:
        before_cols = [
            "evidence_id",
            "report_id",
            "source_type_norm",
            "spatial_type",
            "face_chainage",
            "center_chainage",
            "collapse_flag",
            "collapse_state",
            "hazard_tags",
        ]
        before_cols = [c for c in before_cols if c in hsp_anomaly_before.columns]
        print("HSP anomaly_point before dedup:")
        print(
            hsp_anomaly_before[before_cols]
            .sort_values(["center_chainage", "evidence_id"], ascending=[True, True])
            .to_string()
        )

    normalized_df = deduplicate_hsp_anomaly_points(
        normalized_df=normalized_df,
        chainage_tol_m=0.5,
        face_tol_m=1.0,
    )

    hsp_dedup_info = summarize_hsp_anomaly_point_dedup(normalized_df)

    print("HSP anomaly_point dedup attrs:")
    print(json.dumps(hsp_dedup_info, ensure_ascii=False, indent=2, default=str))

    hsp_anomaly_after = normalized_df[
        normalized_df.get("source_type_norm", pd.Series(dtype=str)).astype(str).eq("HSP")
        & normalized_df.get("spatial_type", pd.Series(dtype=str)).astype(str).eq("anomaly_point")
    ].copy()

    print("HSP anomaly_point count after dedup =", len(hsp_anomaly_after))
    print(
        "HSP anomaly_point count reduced =",
        len(hsp_anomaly_before) - len(hsp_anomaly_after),
    )

    if not hsp_anomaly_after.empty:
        after_cols = [
            "evidence_id",
            "report_id",
            "source_type_norm",
            "spatial_type",
            "face_chainage",
            "center_chainage",
            "collapse_flag",
            "collapse_state",
            "hazard_tags",
            "duplicate_count",
            "duplicate_evidence_ids",
            "dedup_note",
        ]
        after_cols = [c for c in after_cols if c in hsp_anomaly_after.columns]
        print("HSP anomaly_point after dedup:")
        print(
            hsp_anomaly_after[after_cols]
            .sort_values(["center_chainage", "evidence_id"], ascending=[True, True])
            .to_string()
        )

    # 专门检查 DK1013+224 和 DK1013+265
    for check_chainage in [1013224.0, 1013265.0]:
        center_series = pd.to_numeric(
            hsp_anomaly_after.get("center_chainage", pd.Series(dtype=float)),
            errors="coerce",
        )
        part = hsp_anomaly_after[
            center_series.sub(check_chainage).abs() <= 0.5
        ].copy()

        print(f"\nHSP anomaly_point near {check_chainage}: count =", len(part))
        if not part.empty:
            cols = [
                "evidence_id",
                "center_chainage",
                "face_chainage",
                "duplicate_count",
                "duplicate_evidence_ids",
                "dedup_note",
                "hazard_tags",
            ]
            cols = [c for c in cols if c in part.columns]
            print(part[cols].to_string())

    safe_json_dump(
        hsp_dedup_info,
        out_dir / "hsp_anomaly_point_dedup_info.json",
    )

    normalized_df.to_csv(
        out_dir / "normalized_evidence_df_after_hsp_anomaly_point_dedup.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print("normalized_df after HSP anomaly_point dedup shape =", normalized_df.shape)
    print(normalized_df.head())

    normalized_summary = summarize_normalized_evidence(normalized_df)
    print("normalized summary after availability filter and HSP anomaly_point dedup:")
    print(normalized_summary)

    normalized_df.to_csv(
        out_dir / "normalized_evidence_df.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(normalized_summary, out_dir / "normalized_summary.json")
    safe_json_dump(
        availability_filter_info,
        out_dir / "availability_filter_info.json",
    )

    # 查看三态字段和 tag 分层字段
    print_existing_columns(
        normalized_df,
        cols=[
            "evidence_id",
            "source_type_norm",
            "evidence_role",
            "spatial_type",
            "center_chainage",
            "face_chainage",
            "water_flag",
            "water_state",
            "collapse_flag",
            "collapse_state",
            "deformation_flag",
            "deformation_state",
            "hazard_tags",
            "attribute_tags",
            "method_tags",
            "unknown_hazard_tags",
        ],
        title="2.0 检查三态字段与 tag 分层字段",
        max_rows=30,
    )

    # 查看 HSP anomaly_point
    print_title("2.1 检查 HSP anomaly_point")

    if normalized_df.empty or "spatial_type" not in normalized_df.columns:
        anomaly_points = pd.DataFrame()
    else:
        anomaly_points = normalized_df[
            normalized_df["spatial_type"].eq("anomaly_point")
        ].copy()

    print("anomaly_point count =", len(anomaly_points))

    if not anomaly_points.empty:
        anomaly_cols = [
            "evidence_id",
            "source_type_norm",
            "spatial_type",
            "face_chainage",
            "center_chainage",
            "collapse_flag",
            "collapse_state",
            "hazard_tags",
            "duplicate_count",
            "duplicate_evidence_ids",
            "dedup_note",
        ]
        anomaly_cols = [c for c in anomaly_cols if c in anomaly_points.columns]
        print(anomaly_points[anomaly_cols].head(20).to_string())

    # =========================================================
    # 3. 第三阶段：build_chainage_cells
    # =========================================================
    print_title("3. 构建 10m chainage cells")

    if "start_chainage" in normalized_df.columns:
        extra_min = normalized_df["start_chainage"].dropna().min()
    else:
        extra_min = None

    if "end_chainage" in normalized_df.columns:
        extra_max = normalized_df["end_chainage"].dropna().max()
    else:
        extra_max = None

    cells_df = build_chainage_cells(
        df_plc=pd.DataFrame(),
        cell_length=CELL_LENGTH_M,
        extra_min=extra_min,
        extra_max=extra_max,
    )

    print("extra_min =", extra_min)
    print("extra_max =", extra_max)
    print("cells_df shape =", cells_df.shape)
    print(cells_df.head())
    print(cells_df.tail())
    print("cell_count =", len(cells_df))

    cells_df.to_csv(
        out_dir / "cells_df.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # =========================================================
    # 4. 第三阶段：project_evidence_to_cells
    # =========================================================
    print_title("4. 证据投影到 cell")

    cell_evidence_df = project_evidence_to_cells(
        cells_df=cells_df,
        normalized_evidence_df=normalized_df,
    )

    print("cell_evidence_df shape =", cell_evidence_df.shape)

    cell_evidence_summary = summarize_cell_evidence(cell_evidence_df)
    print("cell evidence summary:")
    print(cell_evidence_summary)

    print("effective_weight_max should be <= 1.0:")
    print(cell_evidence_summary.get("effective_weight_max"))

    print("cell_evidence_df head:")
    if not cell_evidence_df.empty:
        print(cell_evidence_df.head(20).to_string())
    else:
        print("cell_evidence_df 为空。")

    cell_evidence_df.to_csv(
        out_dir / "cell_evidence_df.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(cell_evidence_summary, out_dir / "cell_evidence_summary.json")

    # =========================================================
    # 5. 检查某个里程附近的投影
    # =========================================================
    print_title(f"5. 检查 {target_chainage:.1f}m 附近投影")

    if not cells_df.empty:
        near_cells = cells_df[
            (cells_df["cell_center"] >= target_chainage - 20)
            & (cells_df["cell_center"] <= target_chainage + 20)
        ].copy()
    else:
        near_cells = pd.DataFrame()

    if not cell_evidence_df.empty and not near_cells.empty:
        near_projection = cell_evidence_df[
            cell_evidence_df["cell_id"].isin(near_cells["cell_id"])
        ].sort_values(
            ["cell_id", "effective_weight"],
            ascending=[True, False],
        )
    else:
        near_projection = pd.DataFrame()

    print("near_cells:")
    if not near_cells.empty:
        print(near_cells.to_string())
    else:
        print("附近没有 cell。")

    print("near_projection head 80:")
    if not near_projection.empty:
        near_projection_show = near_projection.copy()

        dedup_cols = [
            "evidence_id",
            "face_chainage",
            "center_chainage",
            "duplicate_count",
            "duplicate_evidence_ids",
            "dedup_note",
        ]
        dedup_cols = [c for c in dedup_cols if c in normalized_df.columns]

        if "evidence_id" in near_projection_show.columns and dedup_cols:
            ev_dedup = normalized_df[dedup_cols].drop_duplicates(
                subset=["evidence_id"],
                keep="first",
            )
            near_projection_show = near_projection_show.merge(
                ev_dedup,
                on="evidence_id",
                how="left",
            )

        show_projection_cols = [
            "cell_id",
            "evidence_id",
            "source_type_norm",
            "spatial_type",
            "face_chainage",
            "center_chainage",
            "distance_m",
            "spatial_weight",
            "effective_weight",
            "duplicate_count",
            "duplicate_evidence_ids",
            "dedup_note",
        ]
        show_projection_cols = [
            c for c in show_projection_cols if c in near_projection_show.columns
        ]

        print(near_projection_show[show_projection_cols].head(80).to_string())
    else:
        print("附近没有投影证据。")

    near_projection.to_csv(
        out_dir / "near_projection_1013224.csv",
        index=False,
        encoding="utf-8-sig",
    )


    # =========================================================
    # 6. 第四阶段：fuse_geo_states
    # =========================================================
    print_title("6. 融合 cell 地质状态 geo_states_df")

    geo_states_df = fuse_geo_states(
        cells_df=cells_df,
        cell_evidence_df=cell_evidence_df,
        normalized_evidence_df=normalized_df,
    )

    print("geo_states_df shape =", geo_states_df.shape)
    print("geo_states_df columns =", list(geo_states_df.columns))

    geo_states_summary = summarize_geo_states(geo_states_df)
    print("geo states summary:")
    print(geo_states_summary)

    baseline_geo_states_summary = {
        "high_attention_cell_count": 393,
        "GRS_geo_base_mean": 0.6948853252836316,
        "main_hazard_counts": {
            "掉块": 416,
            "围岩破碎": 393,
            "裂隙发育": 314,
            "软硬不均": 249,
            "明显反射异常": 238,
            "出水": 166,
            "裂隙密集": 135,
            "稳定性较差": 131,
            "围岩极破碎": 121,
            "突涌水": 22,
            "反射异常": 13,
        },
        "conflict_level_counts": {
            "low": 188,
            "medium": 183,
            "none": 74,
        },
    }

    print_before_after_summary(
        before=baseline_geo_states_summary,
        after=geo_states_summary,
    )

    print("geo_states_df head:")
    show_cols = [
        "cell_id",
        "cell_start",
        "cell_end",
        "has_geology_evidence",
        "fused_grade",
        "main_hazards",
        "water_score",
        "collapse_score",
        "deformation_score",
        "confidence_score",
        "uncertainty_level",
        "conflict_level",
        "GRS_geo_base",
        "grade_score_component",
        "hazard_component",
        "confidence_component",
        "GRS_component_method",
    ]
    show_cols = [c for c in show_cols if c in geo_states_df.columns]

    if show_cols and not geo_states_df.empty:
        print(geo_states_df[show_cols].head(40).to_string())
    else:
        print("geo_states_df 为空或无可展示列。")

    print_existing_columns(
        geo_states_df,
        cols=[
            "cell_id",
            "GRS_geo_base",
            "grade_score_component",
            "hazard_component",
            "confidence_component",
            "GRS_formula_text",
            "GRS_component_method",
        ],
        title="6.1 检查 GRS_geo_base 真实组件字段",
        max_rows=30,
    )

    geo_states_df.to_csv(
        out_dir / "geo_states_df.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(geo_states_summary, out_dir / "geo_states_summary.json")

    # =========================================================
    # 7. 检查 1013224m 附近融合结果
    # =========================================================
    print_title(f"7. 检查 {target_chainage:.1f}m 附近 geo_states")

    if not geo_states_df.empty:
        near_states = geo_states_df[
            (geo_states_df["cell_center"] >= target_chainage - 30)
            & (geo_states_df["cell_center"] <= target_chainage + 30)
        ].copy()
    else:
        near_states = pd.DataFrame()

    near_state_cols = [
        "cell_id",
        "cell_center",
        "has_geology_evidence",
        "fused_grade",
        "grade_distribution",
        "hazard_scores",
        "main_hazards",
        "water_score",
        "collapse_score",
        "deformation_score",
        "source_type_count",
        "evidence_count",
        "confidence_score",
        "uncertainty_level",
        "conflict_level",
        "conflict_reasons",
        "GRS_geo_base",
        "grade_score_component",
        "hazard_component",
        "confidence_component",
        "GRS_formula_text",
        "GRS_component_method",
        "supporting_evidence_ids",
    ]
    near_state_cols = [c for c in near_state_cols if c in near_states.columns]

    if near_state_cols and not near_states.empty:
        print(near_states[near_state_cols].to_string())
    else:
        print("附近没有 geo_states。")

    near_states.to_csv(
        out_dir / "near_geo_states_1013224.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # =========================================================
    # 8. 第五阶段：build_forward_profile
    # =========================================================
    print_title("8. 构建 forward_profile")

    forward_profile = build_forward_profile(
        geo_states_df=geo_states_df,
        current_chainage=current_chainage,
        lookahead_m=LOOKAHEAD_M,
        step_m=STEP_M,
        advance_direction=ADVANCE_DIRECTION,
    )

    forward_summary = summarize_forward_profile(forward_profile)

    print("current_chainage =", current_chainage)
    print("forward profile summary:")
    print(forward_summary)

    print("forward profile detail:")
    for item in forward_profile.get("profile", []):
        print("-" * 80)
        print(json.dumps(item, ensure_ascii=False, indent=2, default=str))

    safe_json_dump(forward_profile, out_dir / "forward_profile.json")
    safe_json_dump(forward_summary, out_dir / "forward_profile_summary.json")

    # =========================================================
    # 9. 简单断言检查
    # =========================================================
    print_title("9. 简单检查")

    checks = {}

    checks["normalized_all_not_empty"] = not normalized_df_all.empty
    checks["normalized_available_not_empty"] = not normalized_df.empty
    checks["availability_filter_info"] = availability_filter_info
    checks["hsp_anomaly_point_dedup_info"] = hsp_dedup_info

    checks["has_face_sketch"] = "face_sketch" in set(
        normalized_df.get("source_type_norm", pd.Series(dtype=str))
    )
    checks["has_TSP"] = "TSP" in set(
        normalized_df.get("source_type_norm", pd.Series(dtype=str))
    )
    checks["has_HSP"] = "HSP" in set(
        normalized_df.get("source_type_norm", pd.Series(dtype=str))
    )
    checks["has_anomaly_point"] = bool(
        (
            normalized_df.get("spatial_type", pd.Series(dtype=str))
            == "anomaly_point"
        ).any()
    )

    checks["has_water_state_col"] = "water_state" in normalized_df.columns
    checks["has_collapse_state_col"] = "collapse_state" in normalized_df.columns
    checks["has_deformation_state_col"] = "deformation_state" in normalized_df.columns
    checks["has_attribute_tags_col"] = "attribute_tags" in normalized_df.columns
    checks["has_method_tags_col"] = "method_tags" in normalized_df.columns
    checks["has_unknown_hazard_tags_col"] = "unknown_hazard_tags" in normalized_df.columns

    checks["has_duplicate_count_col"] = "duplicate_count" in normalized_df.columns
    checks["has_duplicate_evidence_ids_col"] = "duplicate_evidence_ids" in normalized_df.columns
    checks["has_dedup_note_col"] = "dedup_note" in normalized_df.columns

    checks["cells_not_empty"] = not cells_df.empty
    checks["cell_evidence_not_empty"] = not cell_evidence_df.empty
    checks["cell_evidence_effective_weight_max_le_1"] = (
        float(cell_evidence_summary.get("effective_weight_max", 0.0)) <= 1.000001
    )
    checks["geo_states_not_empty"] = not geo_states_df.empty

    checks["geo_states_has_GRS_geo_base"] = "GRS_geo_base" in geo_states_df.columns
    checks["geo_states_has_supporting_ids"] = (
        "supporting_evidence_ids" in geo_states_df.columns
    )

    checks["geo_states_has_grade_score_component"] = (
        "grade_score_component" in geo_states_df.columns
    )
    checks["geo_states_has_hazard_component"] = (
        "hazard_component" in geo_states_df.columns
    )
    checks["geo_states_has_confidence_component"] = (
        "confidence_component" in geo_states_df.columns
    )
    checks["geo_states_has_GRS_formula_text"] = (
        "GRS_formula_text" in geo_states_df.columns
    )
    checks["geo_states_has_GRS_component_method"] = (
        "GRS_component_method" in geo_states_df.columns
    )

    checks["forward_profile_has_3_ranges"] = (
        len(forward_profile.get("profile", [])) == 3
    )
    checks["forward_profile_range_labels"] = [
        item.get("range_label") for item in forward_profile.get("profile", [])
    ]

    for key, value in checks.items():
        print(f"{key}: {value}")

    safe_json_dump(checks, out_dir / "checks.json")

    # =========================================================
    # 10. 第六阶段：构建 geology_v2 文本
    # =========================================================
    print_title("10. 第六阶段：构建 geology_v2 文本")

    geo_brief_text = geo_states_to_brief_text(
        geo_states_df=geo_states_df,
        chainage_min=CHAINAGE_MIN,
        chainage_max=CHAINAGE_MAX,
        top_k=5,
    )

    forward_text = forward_profile_to_text(forward_profile)

    prompt_block = build_geology_v2_prompt_block(
        geo_states_df=geo_states_df,
        forward_profile=forward_profile,
        include_geo_states_brief=True,
        include_forward_profile=True,
        chainage_min=CHAINAGE_MIN,
        chainage_max=CHAINAGE_MAX,
    )

    print("=== geo_brief_text ===")
    print(geo_brief_text)

    print("\n=== forward_text ===")
    print(forward_text)

    print("\n=== prompt_block ===")
    print(prompt_block)

    (out_dir / "geo_brief_text.txt").write_text(
        geo_brief_text,
        encoding="utf-8",
    )

    (out_dir / "forward_text.txt").write_text(
        forward_text,
        encoding="utf-8",
    )

    (out_dir / "geology_v2_prompt_block.txt").write_text(
        prompt_block,
        encoding="utf-8",
    )

    # =========================================================
    # 11. 第七阶段：地质-施工响应耦合 GRCI
    # =========================================================
    print_title("11. 第七阶段：地质-施工响应耦合 GRCI")

    if not geo_states_df.empty:
        mock_response_df = geo_states_df[
            [
                "cell_id",
                "cell_start",
                "cell_end",
                "cell_center",
            ]
        ].copy()
    else:
        mock_response_df = pd.DataFrame(
            columns=["cell_id", "cell_start", "cell_end", "cell_center"]
        )

    mock_response_df["RAI"] = 0.0
    mock_response_df["response_support_count"] = 1
    mock_response_df["response_metrics"] = [
        {} for _ in range(len(mock_response_df))
    ]

    if not mock_response_df.empty:
        mask = (
            (mock_response_df["cell_center"] >= current_chainage)
            & (mock_response_df["cell_center"] < current_chainage + LOOKAHEAD_M)
        )

        target_cells = mock_response_df[mask].sort_values("cell_center").index.tolist()
        test_rai_values = [0.75, 0.65, 0.55]

        for idx, rai in zip(target_cells, test_rai_values):
            mock_response_df.at[idx, "RAI"] = rai
            mock_response_df.at[idx, "response_metrics"] = {
                "mock": True,
                "note": "测试用 RAI，后续应替换为真实施工响应异常指数",
            }

    coupled_df = couple_geo_response(
        geo_states_df=geo_states_df,
        response_df=mock_response_df,
        cells_df=cells_df,
    )

    coupled_summary = summarize_coupled_df(coupled_df)

    coupling_text = coupled_df_to_text(
        coupled_df=coupled_df,
        chainage_min=CHAINAGE_MIN,
        chainage_max=CHAINAGE_MAX,
        top_k=5,
    )

    print("=== coupled summary ===")
    print(coupled_summary)

    print("\n=== coupled_df near target ===")
    if not coupled_df.empty:
        near_coupled = coupled_df[
            (coupled_df["cell_center"] >= CHAINAGE_MIN)
            & (coupled_df["cell_center"] <= CHAINAGE_MAX)
        ].copy()
    else:
        near_coupled = pd.DataFrame()

    coupled_show_cols = [
        "cell_id",
        "cell_center",
        "GRS_geo_base",
        "RAI",
        "GRCI",
        "coupling_level",
        "coupling_type",
        "coupling_explanation",
    ]
    coupled_show_cols = [c for c in coupled_show_cols if c in near_coupled.columns]

    if not near_coupled.empty and coupled_show_cols:
        print(near_coupled[coupled_show_cols].to_string())
    else:
        print("near_coupled 为空。")

    print("\n=== coupling_text ===")
    print(coupling_text)

    coupled_df.to_csv(
        out_dir / "coupled_df.csv",
        index=False,
        encoding="utf-8-sig",
    )

    safe_json_dump(coupled_summary, out_dir / "coupled_summary.json")

    (out_dir / "coupling_text.txt").write_text(
        coupling_text,
        encoding="utf-8",
    )

    # =========================================================
    # 12. 第八阶段：统一 report_context 与 report_renderer
    # =========================================================
    print_title("12. 第八阶段：统一 report_context 与 report_renderer")

    report_context = build_geology_v2_report_context(
        geo_states_df=geo_states_df,
        forward_profile=forward_profile,
        coupled_df=coupled_df,
        operation_context={
            "text": "测试阶段暂未接入真实基础工况上下文。"
        },
        gas_context={
            "text": "测试阶段暂未接入真实气体监测上下文。"
        },
        face_context={
            "has_face_evidence": True,
            "text": (
                "测试阶段使用当前里程附近地质融合结果作为掌子面上下文占位，"
                "正式接入时应替换为掌子面素描解析结果。"
            ),
        },
        current_chainage=current_chainage,
        chainage_min=CHAINAGE_MIN,
        chainage_max=CHAINAGE_MAX,
        metadata={
            "date": "test",
            "source": "ceshi.py",
            "note": "第八阶段 report_context 测试",
            "evidence_filter_mode": EVIDENCE_FILTER_MODE,
            "availability_filter_info": availability_filter_info,
            "hsp_anomaly_point_dedup_info": hsp_dedup_info,
        },
        include_data_preview=True,
    )

    rendered_report_text = render_geology_v2_report_context(
        report_context,
        include_operation=True,
        include_gas=True,
    )

    prompt_text_from_context = report_context_to_prompt_text(report_context)
    prompt_text_from_renderer = render_prompt_block_from_context(report_context)

    print("=== report_context keys ===")
    print(list(report_context.keys()))

    print("\n=== report_context texts keys ===")
    print(list(report_context.get("texts", {}).keys()))

    print("\n=== report_context data_summary ===")
    print(
        json.dumps(
            report_context.get("data_summary", {}),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    print("\n=== rendered_report_text ===")
    print(rendered_report_text)

    print("\n=== prompt_text_from_context preview ===")
    print(prompt_text_from_context[:2000])

    safe_json_dump(report_context, out_dir / "geology_v2_report_context.json")

    (out_dir / "geology_v2_rendered_report.txt").write_text(
        rendered_report_text,
        encoding="utf-8",
    )

    (out_dir / "geology_v2_context_prompt.txt").write_text(
        prompt_text_from_context,
        encoding="utf-8",
    )

    (out_dir / "geology_v2_renderer_prompt.txt").write_text(
        prompt_text_from_renderer,
        encoding="utf-8",
    )

    print("\n=== report_context checks ===")
    context_checks = {
        "context_ok": report_context.get("ok") is True,
        "has_texts": bool(report_context.get("texts")),
        "has_prompt_block": bool(report_context.get("texts", {}).get("prompt_block")),
        "has_sections": bool(report_context.get("sections")),
        "has_forward_section": "forward_profile" in report_context.get("sections", {}),
        "has_coupling_section": "coupling" in report_context.get("sections", {}),
        "rendered_report_not_empty": bool(rendered_report_text.strip()),
        "prompt_text_consistent": prompt_text_from_context == prompt_text_from_renderer,
    }

    for key, value in context_checks.items():
        print(f"{key}: {value}")

    safe_json_dump(context_checks, out_dir / "report_context_checks.json")

    # =========================================================
    # 12.1 单 cell 可解释性检查
    # =========================================================
    print_title("12.1 explain_geo_state 单 cell 可解释性检查")

    explanation = explain_geo_state(
        cell_id="cell_1013220_1013230",
        geo_states_df=geo_states_df,
        cell_evidence_df=cell_evidence_df,
        normalized_df=normalized_df,
        top_n_evidence=12,
    )

    explanation_text = explain_geo_state_text(explanation)

    print(explanation_text)

    safe_json_dump(
        explanation,
        out_dir / "explain_geo_state_cell_1013220_1013230.json",
    )

    (out_dir / "explain_geo_state_cell_1013220_1013230.txt").write_text(
        explanation_text,
        encoding="utf-8",
    )

    print("\n=== explain GRS component source check ===")
    grs_exp = explanation.get("grs_explanation", {}) if isinstance(explanation, dict) else {}
    print("component_source =", grs_exp.get("component_source"))
    print("GRS_component_method =", grs_exp.get("GRS_component_method"))
    print("GRS_formula_text =", grs_exp.get("GRS_formula_text"))
    print("residual_to_actual =", grs_exp.get("residual_to_actual"))

    # =========================================================
    # 13. 完成
    # =========================================================
    print_title("测试完成")
    print("输出目录:", out_dir.resolve())


# =========================================================
# 程序入口：将所有终端输出保存到 txt
# =========================================================

if __name__ == "__main__":
    """
    将 ceshi.py 的全部终端输出保存到 txt 文件。

    默认模式：
    - 终端不再刷大量内容；
    - 只提示日志文件路径；
    - 所有 print 输出、报错 traceback 都写入 txt。

    如果你想同时在终端显示和写入 txt：
    - 把 WRITE_ONLY_TO_TXT = True 改成 False。
    """

    WRITE_ONLY_TO_TXT = True

    out_dir = Path("outputs/geology_v2_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    time_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = out_dir / f"ceshi_terminal_output_{time_tag}.txt"

    class Tee:
        def __init__(self, *files):
            self.files = files

        def write(self, data):
            for f in self.files:
                f.write(data)
                f.flush()

        def flush(self):
            for f in self.files:
                f.flush()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    print(f"[ceshi.py] 终端输出将保存到: {log_path.resolve()}")

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            if WRITE_ONLY_TO_TXT:
                sys.stdout = log_file
                sys.stderr = log_file
            else:
                sys.stdout = Tee(old_stdout, log_file)
                sys.stderr = Tee(old_stderr, log_file)

            print("=" * 80)
            print("ceshi.py 运行日志")
            print("开始时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            print("日志文件:", log_path.resolve())
            print("=" * 80)

            try:
                main()
                print("\n" + "=" * 80)
                print("ceshi.py 运行完成")
                print("结束时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                print("=" * 80)

            except Exception:
                print("\n" + "=" * 80)
                print("ceshi.py 运行失败，异常信息如下：")
                print("=" * 80)
                traceback.print_exc()
                raise

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    print(f"[ceshi.py] 运行结束，完整输出已保存到: {log_path.resolve()}")