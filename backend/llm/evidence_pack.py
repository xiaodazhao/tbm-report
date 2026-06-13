from __future__ import annotations

from typing import Any

from schemas.pipeline import ConstructionStateCell


GENERATION_CONSTRAINTS = [
    "不得把 GRCI 表述为灾害发生概率，只能写作地质-施工响应耦合关注度。",
    "前方 profile 只能表述为提示、关注或需复核，不能写成已经发生的现场事实。",
    "TSP/HSP/掌子面素描是证据来源，不得写成一定真实的结论。",
    "没有 source_trace 或 PLC 指标支持的内容不得作为确定性结论写入日报。",
    "既有超前预报不得被表述为现场揭露事实，除非 Evidence Pack 明确提供现场揭露证据。",
    "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 只能写作施工响应关注信号，不得直接写成异常原因。",
]


def build_prompt_evidence_pack(
    *,
    date: str,
    current_chainage: float | None,
    operation_summary: dict[str, Any],
    cluster_summary: dict[str, Any],
    gas_summary: dict[str, Any],
    construction_state_cells: list[ConstructionStateCell],
    forward_profile: dict[str, Any],
    high_grci_cells: list[dict[str, Any]],
    scope_summary: dict[str, Any] | None = None,
    excluded_evidence_summary: dict[str, Any] | None = None,
    priority_cells: dict[str, list[dict[str, Any]]] | None = None,
    quality_evidence: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the sole evidence pack used for report prompting and trace."""
    excavated_review_cells = _select_excavated_review_cells(construction_state_cells, high_grci_cells)
    forward_attention_cells = _select_forward_attention_cells(construction_state_cells)
    background_context_cells = _select_background_context_cells(
        construction_state_cells,
        excluded_ids={
            *(cell.cell_id for cell in excavated_review_cells),
            *(cell.cell_id for cell in forward_attention_cells),
        },
    )
    selected_cells = _merge_cells(
        excavated_review_cells,
        forward_attention_cells,
        background_context_cells,
    )
    selected_ids = {cell.cell_id for cell in selected_cells}
    for cell in construction_state_cells:
        cell.used_in_evidence_pack = cell.cell_id in selected_ids

    key_cells = [_cell_for_pack(cell) for cell in selected_cells]
    excavated_pack_cells = [_cell_for_pack(cell) for cell in excavated_review_cells]
    forward_pack_cells = [_cell_for_forward_pack(cell) for cell in forward_attention_cells]
    background_pack_cells = [_cell_for_pack(cell) for cell in background_context_cells]
    scope = dict(scope_summary or {})
    scope.setdefault("date", date)
    scope.setdefault("current_chainage", current_chainage)
    scope.setdefault("cell_length_m", 10)
    scope.setdefault("cell_count", len(construction_state_cells))
    priority_cells = priority_cells or {}
    return {
        "schema_version": "prompt_evidence_pack_v1",
        "report_scope": scope,
        "scope_summary": scope,
        "operation_evidence": operation_summary,
        "cluster_evidence": cluster_summary,
        "gas_evidence": gas_summary,
        "geology_evidence": {
            "key_cells": key_cells,
            "selected_cells": key_cells,
            "excavated_review_cells": excavated_pack_cells,
            "forward_attention_cells": forward_pack_cells,
            "background_context_cells": background_pack_cells,
        },
        "daily_review_evidence": {
            "daily_review_cells": excavated_pack_cells,
            "review_cells": excavated_pack_cells,
            "high_priority_cells": priority_cells.get("high_priority_cells", []),
            "medium_priority_cells": priority_cells.get("medium_priority_cells", []),
            "low_priority_cells": priority_cells.get("low_priority_cells", []),
            "note": "Daily review cells are inside the report daily excavated scope and may use GRCI when PLC response and geology evidence are both available.",
        },
        "excavated_review_evidence": {
            "high_grci_cells": high_grci_cells,
            "review_cells": excavated_pack_cells,
            "note": "These cells are excavated-today review cells. GRCI is a review-priority/co-attention index, not a disaster probability or causal proof.",
        },
        "forward_evidence": {
            **(forward_profile if isinstance(forward_profile, dict) else {"profile": forward_profile}),
            "forward_attention_cells": forward_pack_cells,
            "note": "Forward evidence is an attention/indication profile and does not use GRCI.",
        },
        "forward_attention_evidence": {
            "forward_profile": forward_profile if isinstance(forward_profile, dict) else {"profile": forward_profile},
            "forward_attention_cells": forward_pack_cells,
            "note": "Forward attention cells are not excavated review cells and must not be described as occurred facts.",
        },
        "background_context_evidence": {
            "background_context_cells": background_pack_cells,
            "note": "Background cells provide geological context only; they are not today's high GRCI review cells.",
        },
        "local_background_evidence": {
            "local_background_cells": background_pack_cells,
            "background_context_cells": background_pack_cells,
            "note": "Local background cells provide geological context only; they are not today's GRCI review cells.",
        },
        "excluded_evidence_summary": excluded_evidence_summary or {},
        "coupling_evidence": {
            "high_grci_cells": high_grci_cells,
            "legacy_high_grci_cells": high_grci_cells,
            "review_cells": priority_cells.get("review_cells", high_grci_cells),
            "high_priority_cells": priority_cells.get("high_priority_cells", []),
            "medium_priority_cells": priority_cells.get("medium_priority_cells", []),
            "low_priority_cells": priority_cells.get("low_priority_cells", []),
            "review_priority_cells": high_grci_cells,
            "note": "high_grci_cells is retained as a legacy top-review-cells field. Strict high priority means GRCI >= 0.75.",
        },
        "quality_evidence": quality_evidence or {},
        "source_trace": _collect_source_trace(selected_cells),
        "generation_constraints": GENERATION_CONSTRAINTS,
        "warnings": warnings or [],
    }


def render_evidence_pack_text(pack: dict[str, Any]) -> str:
    """Render a compact, deterministic prompt section from the Evidence Pack."""
    scope = pack.get("report_scope", {})
    operation = (pack.get("operation_evidence") or {}).get("operation_mode_summary", {})
    gas = (pack.get("gas_evidence") or {}).get("exceed_summary", {})
    cluster = pack.get("cluster_evidence") or {}
    geology_evidence = pack.get("geology_evidence") or {}
    selected_cells = geology_evidence.get("key_cells") or geology_evidence.get("selected_cells", [])
    excavated_review = pack.get("excavated_review_evidence") or {}
    high_grci = excavated_review.get("high_grci_cells") or (pack.get("coupling_evidence") or {}).get("high_grci_cells", [])
    forward = pack.get("forward_evidence") or {}
    background = pack.get("background_context_evidence") or {}

    lines = [
        "# Prompt Evidence Pack",
        f"date: {scope.get('date')}",
        f"current_chainage: {scope.get('current_chainage')}",
        "",
        "## Operation Evidence",
        (
            f"dominant_mode={operation.get('dominant_mode_cn') or operation.get('dominant_mode')}; "
            f"work_total_min={operation.get('work_total_min')}; "
            f"stop_total_min={operation.get('stop_total_min')}; "
            f"abnormal_total_min={operation.get('abnormal_total_min')}"
        ),
        "",
        "## Cluster Evidence",
        f"has_cluster={cluster.get('has_cluster')}; n_states={cluster.get('n_states')}",
        "",
        "## Gas Evidence",
        (
            f"has_exceedance={gas.get('has_exceedance')}; "
            f"exceed_gases={gas.get('exceed_gases')}; "
            f"exceed_event_count_total={gas.get('exceed_event_count_total')}"
        ),
        "",
        "## Excavated Review Evidence",
    ]
    if high_grci:
        for cell in high_grci[:8]:
            lines.append(
                f"- {cell.get('cell_id')} GRS={cell.get('GRS_geo_base')} RAI={cell.get('RAI')} "
                f"GRCI={cell.get('GRCI')} review_level={cell.get('coupling_level')} hazards={cell.get('main_hazards')} "
                f"evidence={cell.get('supporting_evidence_ids')}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Forward Attention Evidence"])
    forward_cells = forward.get("forward_attention_cells") if isinstance(forward, dict) else []
    for cell in (forward_cells or [])[:8]:
        lines.append(
            f"- {cell.get('cell_id')} center={cell.get('cell_center')} GRS={cell.get('GRS_geo_base')} "
            f"hazards={cell.get('main_hazards')} forward={cell.get('is_forward_cell')} "
            "GRCI=not_applicable"
        )

    lines.extend(["", "## Forward Profile"])
    profile = forward.get("profile") if isinstance(forward, dict) else None
    if profile:
        for item in profile[:5]:
            lines.append(f"- {item}")
    else:
        lines.append(str(forward)[:1200])

    lines.extend(["", "## Background Context Cells"])
    for cell in (background.get("background_context_cells") or [])[:8]:
        lines.append(
            f"- {cell.get('cell_id')} center={cell.get('cell_center')} GRS={cell.get('GRS_geo_base')} "
            f"hazards={cell.get('main_hazards')} background_only=True"
        )

    lines.extend(["", "## Compatibility Key Cells"])
    for cell in selected_cells[:12]:
        lines.append(
            f"- {cell.get('cell_id')} center={cell.get('cell_center')} GRS={cell.get('GRS_geo_base')} "
            f"RAI={cell.get('RAI')} GRCI={cell.get('GRCI')} hazards={cell.get('main_hazards')} "
            f"forward={cell.get('is_forward_cell')} excavated_today={cell.get('is_excavated_today')}"
        )

    lines.extend(["", "## Generation Constraints"])
    for item in pack.get("generation_constraints", []):
        lines.append(f"- {item}")

    return "\n".join(lines)


def build_template_report(pack: dict[str, Any]) -> str:
    """Generate a no-LLM fallback report that still exercises quality/trace."""
    scope = pack.get("report_scope", {})
    operation = (pack.get("operation_evidence") or {}).get("operation_mode_summary", {})
    cluster = pack.get("cluster_evidence") or {}
    gas = (pack.get("gas_evidence") or {}).get("exceed_summary", {})
    high_grci = (
        (pack.get("excavated_review_evidence") or {}).get("high_grci_cells")
        or (pack.get("coupling_evidence") or {}).get("high_grci_cells", [])
    )
    forward = pack.get("forward_evidence") or {}
    forward_cells = forward.get("forward_attention_cells", []) if isinstance(forward, dict) else []
    profile = forward.get("profile", []) if isinstance(forward, dict) else []
    date = scope.get("date")

    lines = [
        f"# TBM 施工日报（{date}）",
        "",
        "## 1. 综合结论摘要",
        (
            f"本日报基于 {date} 的 PLC 日运行数据、online 可用地质证据、"
            f"cell 级 GRS/RAI/GRCI 和 source_trace 生成。"
        ),
        f"本日已形成 {len(high_grci)} 个可用的已开挖区段 GRCI 复核优先 cell；GRCI 仅用于已开挖区段复核排序。",
        f"前方关注提示来自 forward_profile，共 {len(profile)} 个前方窗口，仅用于提示和复核。",
        "",
        "## 2. 总体施工运行概况（今日施工运行概况）",
        (
            f"PLC 工况统计显示，主导工况为 {operation.get('dominant_mode_cn') or operation.get('dominant_mode') or '未识别'}；"
            f"稳定掘进约 {_num(operation.get('work_total_min')):.1f} 分钟，"
            f"停机约 {_num(operation.get('stop_total_min')):.1f} 分钟，"
            f"过渡约 {_num(operation.get('transition_total_min')):.1f} 分钟。"
        ),
        "",
        "## 3. 基础工况统计分析（PLC 工况统计分析）",
        (
            f"PLC 统计记录中，稳定掘进段数量为 {operation.get('work_count', 0)}，"
            f"停机段数量为 {operation.get('stop_count', 0)}，"
            f"异常段数量为 {operation.get('abnormal_count', 0)}。"
        ),
        "",
        "## 4. 聚类施工状态与效率分析",
        "该结果只描述当日 PLC 参数状态分组。",
        "",
        "## 5. 当前掌子面描述",
        "当前掌子面描述只作为空间定位；如无当日可用掌子面素描，不把前方证据写成已揭露事实。",
        "",
        "## 6. 已开挖区段地质与响应异常复核",
    ]
    if high_grci:
        for cell in high_grci[:5]:
            lines.append(
                f"- {cell.get('cell_id')}：GRCI复核优先级为 {cell.get('coupling_level')}，"
                f"GRCI值约 {_format_score(cell.get('GRCI'))}；"
                f"主要地质关注标签为 {_join_items(cell.get('main_hazards'))}。"
                "该 cell 同时具备 GRS、RAI 和当日 PLC response，GRCI 只表示地质证据与施工响应的共现复核关注度。"
            )
    else:
        lines.append("Evidence Pack 中未形成可用的已开挖区段 review_cells。")

    lines.extend(
        [
            "",
            "## 7. 气体监测分析",
            (
                f"气体监测结构化结果显示，has_exceedance={gas.get('has_exceedance', False)}；"
                f"涉及气体为 {_join_items(gas.get('exceed_gases'))}。"
            ),
            "",
            "## 8. 前方关注提示（当前掌子面前方地质关注提示）",
            _forward_text(forward),
            f"forward_attention_cells 数量为 {len(forward_cells)}；这些 cell 使用 GRS_geo_base、main_hazards 和 source_trace，不进入已开挖区段 GRCI 复核单元。",
            "",
            "## 9. 结论与建议",
            "建议围绕 Evidence Pack 中的 review_cells 做已开挖区段复核，围绕 forward_profile 做前方关注提示复核。",
            "报告不得把 GRCI 写成确定性灾害判断，也不得把前方提示或 TSP/HSP 证据写成已发生事实。",
        ]
    )
    return "\n".join(lines)


def _select_pack_cells(cells: list[ConstructionStateCell]) -> list[ConstructionStateCell]:
    ranked = sorted(
        cells,
        key=lambda cell: (
            cell.GRCI or 0.0,
            cell.GRS_geo_base or 0.0,
            cell.RAI or 0.0,
        ),
        reverse=True,
    )
    forward = [cell for cell in cells if cell.is_forward_cell]
    excavated = [cell for cell in cells if cell.is_excavated_today]
    selected = ranked[:10] + forward[:6] + excavated[:6]
    out: list[ConstructionStateCell] = []
    seen = set()
    for cell in selected:
        if cell.cell_id in seen:
            continue
        out.append(cell)
        seen.add(cell.cell_id)
    return out


def _select_excavated_review_cells(
    cells: list[ConstructionStateCell],
    high_grci_cells: list[dict[str, Any]],
) -> list[ConstructionStateCell]:
    high_ids = [str(cell.get("cell_id")) for cell in high_grci_cells if isinstance(cell, dict)]
    by_id = {cell.cell_id: cell for cell in cells}
    out = [by_id[cell_id] for cell_id in high_ids if cell_id in by_id]
    if out:
        return out
    return sorted(
        [
            cell for cell in cells
            if _is_daily_review_cell(cell)
            and cell.GRCI_available
            and cell.GRCI is not None
            and cell.is_excavated_today
            and not cell.is_forward_cell
        ],
        key=lambda cell: cell.GRCI or 0.0,
        reverse=True,
    )[:10]


def _select_background_context_cells(
    cells: list[ConstructionStateCell],
    *,
    excluded_ids: set[str],
    limit: int = 8,
) -> list[ConstructionStateCell]:
    candidates = [
        cell for cell in cells
        if cell.cell_id not in excluded_ids
        and _is_local_background_cell(cell)
        and cell.has_geology_evidence
    ]
    return sorted(
        candidates,
        key=lambda cell: (
            cell.GRS_geo_base or 0.0,
            len(cell.supporting_evidence_ids),
            cell.cell_center or 0.0,
        ),
        reverse=True,
    )[: max(limit, 0)]


def _merge_cells(*groups: list[ConstructionStateCell]) -> list[ConstructionStateCell]:
    out: list[ConstructionStateCell] = []
    seen: set[str] = set()
    for group in groups:
        for cell in group:
            if cell.cell_id in seen:
                continue
            out.append(cell)
            seen.add(cell.cell_id)
    return out


def _select_forward_attention_cells(cells: list[ConstructionStateCell]) -> list[ConstructionStateCell]:
    ranked = sorted(
        [cell for cell in cells if _is_forward_attention_cell(cell)],
        key=lambda cell: (
            cell.GRS_geo_base or 0.0,
            len(cell.supporting_evidence_ids),
            cell.cell_center or 0.0,
        ),
        reverse=True,
    )
    return ranked[:8]


def _is_daily_review_cell(cell: ConstructionStateCell) -> bool:
    return cell.cell_role == "daily_review" or (
        cell.cell_role == "outside_report_scope"
        and cell.is_excavated_today
        and not cell.is_forward_cell
    )


def _is_forward_attention_cell(cell: ConstructionStateCell) -> bool:
    return cell.cell_role == "forward_attention" or (
        cell.cell_role == "outside_report_scope"
        and cell.is_forward_cell
    )


def _is_local_background_cell(cell: ConstructionStateCell) -> bool:
    return cell.cell_role == "local_background"


def _cell_for_pack(cell: ConstructionStateCell) -> dict[str, Any]:
    return cell.model_dump(
        include={
            "cell_id",
            "cell_start",
            "cell_end",
            "cell_center",
            "operation_state",
            "speed_mean",
            "thrust_mean",
            "torque_mean",
            "stop_duration_min",
            "abnormal_score",
            "RAI",
            "stop_ratio",
            "abnormal_ratio",
            "speed_drop_score",
            "torque_volatility_score",
            "speed_volatility_score",
            "stop_component",
            "abnormal_component",
            "speed_drop_component",
            "torque_component",
            "speed_volatility_component",
            "dominant_component",
            "RAI_formula_text",
            "stop_reason_available",
            "planned_stop_distinguishable",
            "stop_interpretation_warning",
            "fused_grade",
            "main_hazards",
            "hazard_scores",
            "confidence_score",
            "uncertainty_level",
            "conflict_level",
            "GRS_geo_base",
            "grade_score_component",
            "hazard_component",
            "confidence_component",
            "GRS_formula_text",
            "GRS_component_method",
            "GRS_available",
            "GRS_unavailable_reason",
            "GRCI",
            "GRCI_available",
            "GRCI_source",
            "GRCI_unavailable_reason",
            "grs_term",
            "rai_term",
            "interaction_term",
            "GRCI_formula_text",
            "coupling_level",
            "coupling_explanation",
            "has_plc_response",
            "has_geology_evidence",
            "supporting_evidence_ids",
            "source_trace",
            "is_excavated_today",
            "is_current_face_cell",
            "is_forward_cell",
            "cell_role",
            "trace_refs",
        }
    )


def _cell_for_forward_pack(cell: ConstructionStateCell) -> dict[str, Any]:
    return cell.model_dump(
        include={
            "cell_id",
            "cell_start",
            "cell_end",
            "cell_center",
            "fused_grade",
            "main_hazards",
            "hazard_scores",
            "confidence_score",
            "uncertainty_level",
            "conflict_level",
            "GRS_geo_base",
            "grade_score_component",
            "hazard_component",
            "confidence_component",
            "GRS_formula_text",
            "GRS_component_method",
            "GRS_available",
            "GRS_unavailable_reason",
            "supporting_evidence_ids",
            "source_trace",
            "is_current_face_cell",
            "is_forward_cell",
            "cell_role",
            "trace_refs",
        }
    )


def _collect_source_trace(cells: list[ConstructionStateCell]) -> list[dict[str, Any]]:
    seen = set()
    traces = []
    for cell in cells:
        for trace in cell.source_trace:
            key = trace.get("evidence_id") or str(trace)
            if key in seen:
                continue
            seen.add(key)
            traces.append(trace)
    return traces


def _forward_text(forward: dict[str, Any]) -> str:
    if not isinstance(forward, dict) or not forward:
        return "未形成可用的前方地质关注 profile。"
    profile = forward.get("profile")
    if profile:
        return f"当前 forward_profile 共 {len(profile)} 个窗口，语义为前方关注提示，不是已发生事实。"
    return "已形成前方关注提示，需结合现场复核。"


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _format_score(value: Any) -> str:
    return f"{_num(value):.2f}".replace(".", "点")


def _join_items(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value if str(item)]
    elif value in (None, ""):
        items = []
    else:
        items = [str(value)]
    return "、".join(items) if items else "无"
