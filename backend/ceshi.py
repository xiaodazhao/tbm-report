# ceshi.py
# 放在 backend/ceshi.py 运行

import json
from pathlib import Path

import pandas as pd

from config import EVIDENCE_DB_PATH

from geology_v2.evidence_normalizer import (
    normalize_evidence_df,
    summarize_normalized_evidence,
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

def print_title(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

from geology_v2.report_context_builder import (
    build_geology_v2_report_context,
    report_context_to_prompt_text,
)

from geology_v2.report_renderer import (
    render_geology_v2_report_context,
    render_prompt_block_from_context,
)
def safe_json_dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main():
    # =========================================================
    # 0. 输出目录
    # =========================================================
    out_dir = Path("outputs/geology_v2_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================
    # 1. 读取旧 evidence_df
    # =========================================================
    print_title("1. 读取 evidence_df")

    evidence_df = pd.read_csv(EVIDENCE_DB_PATH)

    print("EVIDENCE_DB_PATH =", EVIDENCE_DB_PATH)
    print("evidence_df shape =", evidence_df.shape)
    print("evidence_df columns =", list(evidence_df.columns))

    # =========================================================
    # 2. 第二阶段：normalize_evidence_df
    # =========================================================
    print_title("2. 标准化 evidence_df -> normalized_df")

    normalized_df = normalize_evidence_df(evidence_df)

    print("normalized_df shape =", normalized_df.shape)
    print(normalized_df.head())

    normalized_summary = summarize_normalized_evidence(normalized_df)
    print("normalized summary:")
    print(normalized_summary)

    normalized_df.to_csv(
        out_dir / "normalized_evidence_df.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(normalized_summary, out_dir / "normalized_summary.json")

    # 查看 HSP anomaly_point
    print_title("2.1 检查 HSP anomaly_point")

    anomaly_points = normalized_df[
        normalized_df["spatial_type"].eq("anomaly_point")
    ].copy()

    print("anomaly_point count =", len(anomaly_points))

    if not anomaly_points.empty:
        print(
            anomaly_points[
                [
                    "evidence_id",
                    "source_type_norm",
                    "spatial_type",
                    "center_chainage",
                    "hazard_tags",
                ]
            ].head(20).to_string()
        )

    # =========================================================
    # 3. 第三阶段：build_chainage_cells
    # =========================================================
    print_title("3. 构建 10m chainage cells")

    extra_min = normalized_df["start_chainage"].dropna().min()
    extra_max = normalized_df["end_chainage"].dropna().max()

    cells_df = build_chainage_cells(
        df_plc=pd.DataFrame(),
        cell_length=10.0,
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

    print("cell_evidence_df head:")
    print(cell_evidence_df.head(20).to_string())

    cell_evidence_df.to_csv(
        out_dir / "cell_evidence_df.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(cell_evidence_summary, out_dir / "cell_evidence_summary.json")

    # =========================================================
    # 5. 检查某个里程附近的投影
    # =========================================================
    print_title("5. 检查 1013224m 附近投影")

    target_chainage = 1013224.0

    near_cells = cells_df[
        (cells_df["cell_center"] >= target_chainage - 20)
        & (cells_df["cell_center"] <= target_chainage + 20)
    ].copy()

    near_projection = cell_evidence_df[
        cell_evidence_df["cell_id"].isin(near_cells["cell_id"])
    ].sort_values(
        ["cell_id", "effective_weight"],
        ascending=[True, False],
    )

    print("near_cells:")
    print(near_cells.to_string())

    print("near_projection head 80:")
    if not near_projection.empty:
        print(
            near_projection[
                [
                    "cell_id",
                    "evidence_id",
                    "source_type_norm",
                    "spatial_type",
                    "distance_m",
                    "spatial_weight",
                    "effective_weight",
                ]
            ].head(80).to_string()
        )
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

    geo_states_summary = summarize_geo_states(geo_states_df)
    print("geo states summary:")
    print(geo_states_summary)

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
        "confidence_score",
        "uncertainty_level",
        "conflict_level",
        "GRS_geo_base",
    ]
    show_cols = [c for c in show_cols if c in geo_states_df.columns]
    print(geo_states_df[show_cols].head(40).to_string())

    geo_states_df.to_csv(
        out_dir / "geo_states_df.csv",
        index=False,
        encoding="utf-8-sig",
    )
    safe_json_dump(geo_states_summary, out_dir / "geo_states_summary.json")

    # =========================================================
    # 7. 检查 1013224m 附近融合结果
    # =========================================================
    print_title("7. 检查 1013224m 附近 geo_states")

    near_states = geo_states_df[
        (geo_states_df["cell_center"] >= target_chainage - 30)
        & (geo_states_df["cell_center"] <= target_chainage + 30)
    ].copy()

    near_state_cols = [
        "cell_id",
        "cell_center",
        "has_geology_evidence",
        "fused_grade",
        "grade_distribution",
        "hazard_scores",
        "main_hazards",
        "source_type_count",
        "evidence_count",
        "confidence_score",
        "uncertainty_level",
        "conflict_level",
        "conflict_reasons",
        "GRS_geo_base",
        "supporting_evidence_ids",
    ]
    near_state_cols = [c for c in near_state_cols if c in near_states.columns]

    print(near_states[near_state_cols].to_string())

    near_states.to_csv(
        out_dir / "near_geo_states_1013224.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # =========================================================
    # 8. 第五阶段：build_forward_profile
    # =========================================================
    print_title("8. 构建 forward_profile")

    current_chainage = 1013220.0

    forward_profile = build_forward_profile(
        geo_states_df=geo_states_df,
        current_chainage=current_chainage,
        lookahead_m=30.0,
        step_m=10.0,
        advance_direction=1,
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

    checks["normalized_not_empty"] = not normalized_df.empty
    checks["has_face_sketch"] = "face_sketch" in set(normalized_df["source_type_norm"])
    checks["has_TSP"] = "TSP" in set(normalized_df["source_type_norm"])
    checks["has_HSP"] = "HSP" in set(normalized_df["source_type_norm"])
    checks["has_anomaly_point"] = bool(
        (normalized_df["spatial_type"] == "anomaly_point").any()
    )

    checks["cells_not_empty"] = not cells_df.empty
    checks["cell_evidence_not_empty"] = not cell_evidence_df.empty
    checks["geo_states_not_empty"] = not geo_states_df.empty

    checks["geo_states_has_GRS_geo_base"] = "GRS_geo_base" in geo_states_df.columns
    checks["geo_states_has_supporting_ids"] = "supporting_evidence_ids" in geo_states_df.columns

    checks["forward_profile_has_3_ranges"] = len(forward_profile.get("profile", [])) == 3
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
        chainage_min=1013200.0,
        chainage_max=1013260.0,
        top_k=5,
    )

    forward_text = forward_profile_to_text(forward_profile)

    prompt_block = build_geology_v2_prompt_block(
        geo_states_df=geo_states_df,
        forward_profile=forward_profile,
        include_geo_states_brief=True,
        include_forward_profile=True,
        chainage_min=1013200.0,
        chainage_max=1013260.0,
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

    # 说明：
    # 这里先构造一个 mock_response_df，只用于测试 coupling_adapter 是否跑通。
    # 后面接真实 PLC 或已有 RAI 时，把这里替换成真实 response_df 即可。
    mock_response_df = geo_states_df[
        [
            "cell_id",
            "cell_start",
            "cell_end",
            "cell_center",
        ]
    ].copy()

    mock_response_df["RAI"] = 0.0
    mock_response_df["response_support_count"] = 1
    mock_response_df["response_metrics"] = [{} for _ in range(len(mock_response_df))]

    # 模拟当前 1013220～1013250m 前方 30m 施工响应偏高。
    mask = (
        (mock_response_df["cell_center"] >= 1013220.0)
        & (mock_response_df["cell_center"] < 1013250.0)
    )

    # 给三个 cell 一个测试用 RAI。
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
        chainage_min=1013200.0,
        chainage_max=1013260.0,
        top_k=5,
    )

    print("=== coupled summary ===")
    print(coupled_summary)

    print("\n=== coupled_df near target ===")
    near_coupled = coupled_df[
        (coupled_df["cell_center"] >= 1013200.0)
        & (coupled_df["cell_center"] <= 1013260.0)
    ].copy()

    print(
        near_coupled[
            [
                "cell_id",
                "cell_center",
                "GRS_geo_base",
                "RAI",
                "GRCI",
                "coupling_level",
                "coupling_type",
                "coupling_explanation",
            ]
        ].to_string()
    )

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
            "text": "测试阶段使用当前里程附近地质融合结果作为掌子面上下文占位，正式接入时应替换为掌子面素描解析结果。"
        },
        current_chainage=current_chainage,
        chainage_min=1013200.0,
        chainage_max=1013260.0,
        metadata={
            "date": "test",
            "source": "ceshi.py",
            "note": "第八阶段 report_context 测试",
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
    print(json.dumps(report_context.get("data_summary", {}), ensure_ascii=False, indent=2, default=str))

    print("\n=== rendered_report_text ===")
    print(rendered_report_text)

    print("\n=== prompt_text_from_context preview ===")
    print(prompt_text_from_context[:2000])

    # 保存结果
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

    # 简单检查
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
    # 11. 完成
    # =========================================================
    print_title("测试完成")
    print("输出目录:", out_dir.resolve())


if __name__ == "__main__":
    main()