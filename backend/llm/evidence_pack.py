from __future__ import annotations

from typing import Any

from schemas.pipeline import ConstructionStateCell
from schemas.twin import DailyConstructionTwin, TwinCellView


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
    top_k_review_cells: int = 10,
    top_k_forward_cells: int = 8,
    top_k_background_cells: int = 8,
) -> dict[str, Any]:
    """Build the sole evidence pack used for report prompting and trace."""
    excavated_review_cells = _select_excavated_review_cells(construction_state_cells, high_grci_cells)[:top_k_review_cells]
    forward_attention_cells = _select_forward_attention_cells(construction_state_cells)[:top_k_forward_cells]
    background_context_cells = _select_background_context_cells(
        construction_state_cells,
        excluded_ids={
            *(cell.cell_id for cell in excavated_review_cells),
            *(cell.cell_id for cell in forward_attention_cells),
        },
    )[:top_k_background_cells]
    selected_cells = _merge_cells(
        excavated_review_cells,
        forward_attention_cells,
        background_context_cells,
    )
    selected_ids = {cell.cell_id for cell in selected_cells}
    for cell in construction_state_cells:
        cell.used_in_evidence_pack = cell.cell_id in selected_ids

    excavated_pack_cells = _pack_cells_with_selection(excavated_review_cells, "daily_review")
    forward_pack_cells = _pack_cells_with_selection(forward_attention_cells, "forward_attention")
    background_pack_cells = _pack_cells_with_selection(background_context_cells, "local_background")
    key_cells = _merge_pack_cells(excavated_pack_cells, forward_pack_cells, background_pack_cells)
    scope = dict(scope_summary or {})
    scope.setdefault("date", date)
    scope.setdefault("current_chainage", current_chainage)
    scope.setdefault("cell_length_m", 10)
    scope.setdefault("cell_count", len(construction_state_cells))
    daily_plc_range = {
        "start_chainage": scope.get("daily_chainage_min"),
        "end_chainage": scope.get("daily_chainage_max"),
        "daily_advance_m": scope.get("daily_advance_m"),
        "meaning": "PLC measured daily advance range; use this for actual daily advance statements.",
    }
    scope["daily_plc_range"] = daily_plc_range
    scope["daily_chainage_raw"] = daily_plc_range
    if isinstance(scope.get("daily_excavated_scope"), dict):
        scope["daily_excavated_scope"] = {
            **scope["daily_excavated_scope"],
            "meaning": "10m-cell aligned excavated review scope; not the actual PLC advance distance.",
        }
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
        "selection_config": {
            "top_k_review_cells": top_k_review_cells,
            "top_k_forward_cells": top_k_forward_cells,
            "top_k_background_cells": top_k_background_cells,
            "selection_methods": {
                "daily_review": "0.40*GRCI + 0.25*RAI + 0.25*GRS + 0.10*trace_completeness with available terms renormalized",
                "forward_attention": "0.45*GRS + 0.25*forward_distance_weight + 0.20*evidence_confidence + 0.10*trace_completeness with available terms renormalized; GRCI is not used",
                "local_background": "0.50*GRS + 0.25*evidence_confidence + 0.25*trace_completeness with available terms renormalized",
            },
        },
        "warnings": warnings or [],
    }


def build_evidence_pack_from_twin(
    *,
    twin: DailyConstructionTwin,
    operation_summary: dict[str, Any] | None = None,
    cluster_summary: dict[str, Any] | None = None,
    gas_summary: dict[str, Any] | None = None,
    forward_profile: dict[str, Any] | None = None,
    high_grci_cells: list[dict[str, Any]] | None = None,
    excluded_evidence_summary: dict[str, Any] | None = None,
    priority_cells: dict[str, list[dict[str, Any]]] | None = None,
    quality_evidence: dict[str, Any] | None = None,
    top_k_review_cells: int = 10,
    top_k_forward_cells: int = 8,
    top_k_background_cells: int = 8,
) -> dict[str, Any]:
    """Build the report Evidence Pack from the DailyConstructionTwin contract."""
    scope = twin.scope.model_dump()
    scope.setdefault("date", twin.date)
    scope.setdefault("current_chainage", scope.get("current_chainage") or scope.get("face_chainage"))
    scope.setdefault("cell_length_m", scope.get("cell_length_m") or 10)
    scope.setdefault("cell_count", len(twin.cells))

    excavated_cells = [_twin_cell_for_pack(cell, "daily_review") for cell in twin.daily_review_cells[:top_k_review_cells]]
    forward_cells = [
        _twin_cell_for_forward_pack(cell, "forward_attention")
        for cell in twin.forward_attention_cells[:top_k_forward_cells]
    ]
    background_cells = [
        _twin_cell_for_pack(cell, "local_background")
        for cell in twin.local_background_cells[:top_k_background_cells]
    ]
    key_cells = _merge_pack_cells(excavated_cells, forward_cells, background_cells)
    priority_cells = priority_cells or {}
    governance = twin.governance.model_dump()

    pack = {
        "schema_version": "twin_evidence_pack_v1",
        "evidence_pack_source": "daily_construction_twin",
        "report_scope": scope,
        "scope_summary": scope,
        "operation_evidence": operation_summary or twin.summaries.operation_summary,
        "cluster_evidence": cluster_summary or (twin.summaries.response_summary or {}).get("cluster_summary", {}),
        "gas_evidence": gas_summary or twin.summaries.gas_summary,
        "geology_evidence": {
            "key_cells": key_cells,
            "selected_cells": key_cells,
            "excavated_review_cells": excavated_cells,
            "forward_attention_cells": forward_cells,
            "background_context_cells": background_cells,
        },
        "daily_review_evidence": {
            "daily_review_cells": excavated_cells,
            "review_cells": excavated_cells,
            "high_priority_cells": priority_cells.get("high_priority_cells", []),
            "medium_priority_cells": priority_cells.get("medium_priority_cells", []),
            "low_priority_cells": priority_cells.get("low_priority_cells", []),
            "note": "Daily review cells are excavated review cells. GRCI is available only when PLC response and geology evidence are both present.",
        },
        "excavated_review_evidence": {
            "high_grci_cells": high_grci_cells or twin.high_grci_cells,
            "review_cells": excavated_cells,
            "note": "GRCI is a review-priority/co-attention index for excavated review cells, not a disaster probability.",
        },
        "forward_evidence": {
            **(forward_profile if isinstance(forward_profile, dict) else twin.summaries.forward_summary),
            "forward_attention_cells": forward_cells,
            "note": "Forward evidence is an attention/indication profile and does not use GRCI.",
        },
        "forward_attention_evidence": {
            "forward_profile": forward_profile if isinstance(forward_profile, dict) else twin.summaries.forward_summary,
            "forward_attention_cells": forward_cells,
            "note": "Forward attention cells are not excavated review cells and must not be described as occurred facts.",
        },
        "background_context_evidence": {
            "background_context_cells": background_cells,
            "note": "Background cells provide local geological context only.",
        },
        "local_background_evidence": {
            "local_background_cells": background_cells,
            "background_context_cells": background_cells,
            "note": "Local background cells do not enter daily GRCI review.",
        },
        "excluded_evidence_summary": excluded_evidence_summary or {},
        "coupling_evidence": {
            "high_grci_cells": high_grci_cells or twin.high_grci_cells,
            "legacy_high_grci_cells": high_grci_cells or twin.high_grci_cells,
            "review_cells": priority_cells.get("review_cells", high_grci_cells or twin.high_grci_cells),
            "high_priority_cells": priority_cells.get("high_priority_cells", []),
            "medium_priority_cells": priority_cells.get("medium_priority_cells", []),
            "low_priority_cells": priority_cells.get("low_priority_cells", []),
            "review_priority_cells": high_grci_cells or twin.high_grci_cells,
            "note": "high_grci_cells are daily_review cells only. GRCI is not forward risk.",
        },
        "quality_evidence": quality_evidence or {},
        "source_trace": _collect_twin_source_trace(twin.cells),
        "evidence_governance": governance,
        "source_role_boundaries": governance.get("role_rules", {}),
        "metric_boundaries": governance.get("metric_boundaries", {}),
        "allowed_claims": governance.get("allowed_claims", []),
        "forbidden_claims": governance.get("forbidden_claims", []),
        "generation_constraints": GENERATION_CONSTRAINTS
        + list(governance.get("forbidden_claims", []))
        + [
            "Evidence Pack comes from DailyConstructionTwin; do not infer beyond cell role and trace state.",
            "forward_attention cells use GRS/source_trace only and must not be ranked by GRCI.",
        ],
        "selection_config": {
            "top_k_review_cells": top_k_review_cells,
            "top_k_forward_cells": top_k_forward_cells,
            "top_k_background_cells": top_k_background_cells,
            "source": "DailyConstructionTwin role-separated cell views",
        },
        "warnings": twin.warnings,
    }
    return pack


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


def _pack_cells_with_selection(cells: list[ConstructionStateCell], role: str) -> list[dict[str, Any]]:
    scored = []
    for cell in cells:
        score, method, reason = _selection_score(cell, role)
        payload = _cell_for_forward_pack(cell) if role == "forward_attention" else _cell_for_pack(cell)
        payload.update(
            {
                "selection_score": score,
                "selection_method": method,
                "selection_reason": reason,
                "selected_by_score": True,
            }
        )
        scored.append(payload)
    scored.sort(key=lambda item: item.get("selection_score") or 0.0, reverse=True)
    for index, item in enumerate(scored, start=1):
        item["selection_rank"] = index
    return scored


def _twin_cell_for_pack(cell: TwinCellView, role: str) -> dict[str, Any]:
    response = cell.response_state or {}
    geology = cell.geology_state or {}
    coupling = cell.coupling_state or {}
    position = cell.position_state or {}
    trace = cell.trace_state or {}
    payload = {
        "cell_id": cell.cell_id,
        "cell_start": cell.mileage_start,
        "cell_end": cell.mileage_end,
        "cell_center": _center(cell),
        "cell_role": cell.cell_role,
        "evidence_role": role,
        "distance_to_face_m": cell.distance_to_face_m,
        "is_excavated_today": position.get("is_excavated_today"),
        "is_current_face_cell": position.get("is_current_face_cell"),
        "is_forward_cell": position.get("is_forward_cell"),
        "RAI": response.get("RAI"),
        "RAI_formula_text": response.get("RAI_formula_text"),
        "speed_mean": response.get("speed_mean"),
        "thrust_mean": response.get("thrust_mean"),
        "torque_mean": response.get("torque_mean"),
        "GRS_geo_base": geology.get("GRS_geo_base"),
        "GRS_available": geology.get("GRS_available"),
        "GRS_unavailable_reason": geology.get("GRS_unavailable_reason"),
        "fused_grade": geology.get("fused_grade"),
        "main_hazards": geology.get("main_hazards"),
        "hazard_scores": geology.get("hazard_scores"),
        "confidence_score": geology.get("confidence_score"),
        "supporting_evidence_ids": geology.get("supporting_evidence_ids"),
        "source_trace": geology.get("source_trace") or trace.get("source_trace"),
        "GRCI": coupling.get("GRCI"),
        "GRCI_available": coupling.get("GRCI_available"),
        "GRCI_source": coupling.get("GRCI_source"),
        "GRCI_unavailable_reason": coupling.get("GRCI_unavailable_reason"),
        "coupling_level": coupling.get("coupling_level"),
        "coupling_explanation": coupling.get("coupling_explanation"),
        "trace_refs": trace.get("trace_refs"),
        "trace_completeness": trace.get("trace_completeness"),
    }
    if role == "daily_review":
        metrics = _twin_plc_enhanced_metrics_for_pack(cell)
        if metrics:
            payload["plc_enhanced_metrics"] = metrics
    score, method, reason = _twin_selection_score(cell, role)
    payload.update(
        {
            "selection_score": score,
            "selection_method": method,
            "selection_reason": reason,
            "selected_by_score": True,
        }
    )
    return payload


def _twin_cell_for_forward_pack(cell: TwinCellView, role: str) -> dict[str, Any]:
    payload = _twin_cell_for_pack(cell, role)
    _strip_forward_plc_response_fields(payload)
    payload["GRCI"] = None
    payload["GRCI_available"] = False
    payload["GRCI_source"] = "not_applicable_forward_attention"
    payload["GRCI_unavailable_reason"] = "forward_attention_uses_grs_not_grci"
    payload["boundary"] = "Forward attention cells use GRS/source_trace only, not GRCI or PLC response evidence."
    return payload


def _strip_forward_plc_response_fields(payload: dict[str, Any]) -> None:
    """Remove excavated PLC response fields from forward Evidence Pack cells."""
    for key in [
        "RAI",
        "RAI_formula_text",
        "speed_mean",
        "thrust_mean",
        "torque_mean",
        "rpm_mean",
        "plc_enhanced_metrics",
        "working_sample_count",
        "working_ratio",
        "insufficient_working_samples",
        "working_speed_cv",
        "working_thrust_cv",
        "working_torque_cv",
        "penetration_mean",
        "cutterhead_power_proxy",
        "thrust_per_penetration",
        "torque_per_penetration",
    ]:
        payload.pop(key, None)


def _twin_selection_score(cell: TwinCellView, role: str) -> tuple[float | None, str, str]:
    response = cell.response_state or {}
    geology = cell.geology_state or {}
    coupling = cell.coupling_state or {}
    forward = cell.forward_state or {}
    trace = cell.trace_state or {}
    if role == "daily_review":
        terms = [
            ("GRCI", 0.40, coupling.get("GRCI") if coupling.get("GRCI_available") else None),
            ("RAI", 0.25, response.get("RAI")),
            ("GRS", 0.25, geology.get("GRS_geo_base") if geology.get("GRS_available") else None),
            ("trace_completeness", 0.10, trace.get("trace_completeness")),
        ]
        method = "daily_review_twin_selection_score_v1"
    elif role == "forward_attention":
        terms = [
            ("GRS", 0.45, geology.get("GRS_geo_base") if geology.get("GRS_available") else None),
            ("forward_distance_weight", 0.25, forward.get("forward_distance_weight")),
            ("trace_completeness", 0.30, trace.get("trace_completeness")),
        ]
        method = "forward_attention_twin_selection_score_v1_no_grci"
    else:
        terms = [
            ("GRS", 0.50, geology.get("GRS_geo_base") if geology.get("GRS_available") else None),
            ("trace_completeness", 0.50, trace.get("trace_completeness")),
        ]
        method = "local_background_twin_selection_score_v1"
    available = [(name, weight, _bounded(value)) for name, weight, value in terms if value is not None]
    if not available:
        return None, method, "no_available_selection_terms"
    total_weight = sum(weight for _, weight, _ in available) or 1.0
    score = sum((weight / total_weight) * value for _, weight, value in available)
    reason = ", ".join(f"{name}={value:.3f}" for name, _, value in available)
    return round(float(score), 4), method, reason


def _twin_plc_enhanced_metrics_for_pack(cell: TwinCellView) -> dict[str, Any]:
    response = cell.response_state or {}
    keys = [
        "working_sample_count",
        "working_ratio",
        "working_speed_cv",
        "working_thrust_cv",
        "working_torque_cv",
        "penetration_mean",
        "cutterhead_power_proxy",
        "thrust_per_penetration",
        "torque_per_penetration",
        "insufficient_working_samples",
    ]
    out = {key: response.get(key) for key in keys if response.get(key) is not None}
    if out:
        out["interpretation_boundary"] = (
            "PLC enhanced metrics are excavated daily-review response evidence only; "
            "proxy fields are not strict physical quantities or geological-risk proof."
        )
    return out


def _collect_twin_source_trace(cells: list[TwinCellView]) -> list[dict[str, Any]]:
    seen = set()
    traces = []
    for cell in cells:
        for trace in (cell.trace_state or {}).get("source_trace", []) or []:
            key = trace.get("evidence_id") or str(trace)
            if key in seen:
                continue
            seen.add(key)
            traces.append(trace)
    return traces


def _center(cell: TwinCellView) -> float | None:
    try:
        if cell.mileage_start is None or cell.mileage_end is None:
            return None
        return (float(cell.mileage_start) + float(cell.mileage_end)) / 2.0
    except Exception:
        return None


def _merge_pack_cells(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen = set()
    for group in groups:
        for cell in group:
            cell_id = cell.get("cell_id")
            if cell_id in seen:
                continue
            out.append(cell)
            seen.add(cell_id)
    return out


def _selection_score(cell: ConstructionStateCell, role: str) -> tuple[float | None, str, str]:
    if role == "daily_review":
        terms = [
            ("GRCI", 0.40, cell.GRCI if cell.GRCI_available else None),
            ("RAI", 0.25, cell.RAI),
            ("GRS", 0.25, cell.GRS_geo_base if cell.GRS_available else None),
            ("trace_completeness", 0.10, cell.trace_completeness),
        ]
        method = "daily_review_selection_score_v1"
    elif role == "forward_attention":
        terms = [
            ("GRS", 0.45, cell.GRS_geo_base if cell.GRS_available else None),
            ("forward_distance_weight", 0.25, cell.forward_distance_weight),
            ("evidence_confidence", 0.20, cell.evidence_confidence),
            ("trace_completeness", 0.10, cell.trace_completeness),
        ]
        method = "forward_attention_selection_score_v1_no_grci"
    else:
        terms = [
            ("GRS", 0.50, cell.GRS_geo_base if cell.GRS_available else None),
            ("evidence_confidence", 0.25, cell.evidence_confidence),
            ("trace_completeness", 0.25, cell.trace_completeness),
        ]
        method = "local_background_selection_score_v1"
    available = [(name, weight, _bounded(value)) for name, weight, value in terms if value is not None]
    if not available:
        return None, method, "no_available_selection_terms"
    total_weight = sum(weight for _, weight, _ in available) or 1.0
    score = sum((weight / total_weight) * value for _, weight, value in available)
    reason = ", ".join(f"{name}={value:.3f}" for name, _, value in available)
    return round(float(score), 4), method, reason


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
    payload = cell.model_dump(
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
            "evidence_overlap_length",
            "evidence_overlap_ratio",
            "max_overlap_ratio",
            "mean_overlap_ratio",
            "total_overlap_length",
            "evidence_count",
            "evidence_ids",
            "source_type_distribution",
            "evidence_confidence",
            "evidence_confidence_method",
            "trace_completeness",
            "trace_completeness_method",
            "manual_review_status",
            "source_reliability",
            "source_reliability_method",
            "source_trace",
            "is_excavated_today",
            "is_current_face_cell",
            "is_forward_cell",
            "distance_to_face_m",
            "forward_distance_band",
            "forward_distance_weight",
            "cell_role",
            "trace_refs",
        }
    )
    enhanced = _plc_enhanced_metrics_for_pack(cell)
    if enhanced:
        payload["plc_enhanced_metrics"] = enhanced
    return payload


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
            "evidence_overlap_length",
            "evidence_overlap_ratio",
            "max_overlap_ratio",
            "mean_overlap_ratio",
            "total_overlap_length",
            "evidence_count",
            "evidence_ids",
            "source_type_distribution",
            "evidence_confidence",
            "evidence_confidence_method",
            "trace_completeness",
            "trace_completeness_method",
            "manual_review_status",
            "source_reliability",
            "source_reliability_method",
            "source_trace",
            "is_current_face_cell",
            "is_forward_cell",
            "distance_to_face_m",
            "forward_distance_band",
            "forward_distance_weight",
            "cell_role",
            "trace_refs",
        }
    )


def _plc_enhanced_metrics_for_pack(cell: ConstructionStateCell) -> dict[str, Any]:
    metrics = cell.plc_metrics if isinstance(cell.plc_metrics, dict) else {}
    keys = [
        "working_sample_count",
        "working_ratio",
        "working_speed_cv",
        "working_torque_cv",
        "penetration_mean",
        "thrust_per_penetration",
        "torque_per_penetration",
        "insufficient_working_samples",
    ]
    out = {key: metrics.get(key) for key in keys if key in metrics and metrics.get(key) is not None}
    if not out:
        return {}
    out["interpretation_boundary"] = (
        "该单元 PLC 增强指标仅作为已掘区段施工响应证据，不单独构成地质风险判断，"
        "也不表示当前掌子面前方地质事实。"
    )
    return out


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


def _bounded(value: Any) -> float:
    return max(0.0, min(1.0, _num(value)))


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
