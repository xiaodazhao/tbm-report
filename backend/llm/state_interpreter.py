from __future__ import annotations

from typing import Any

from schemas.twin import DailyConstructionTwin, TwinCellView


def build_cell_interpretation_prompt(cell: TwinCellView, *, task: str = "cell_explanation") -> str:
    """Build a deterministic prompt for optional cell-level interpretation."""
    return "\n".join(
        [
            "# Cell State Interpretation",
            f"task: {task}",
            f"cell_id: {cell.cell_id}",
            f"role: {cell.cell_role}",
            f"mileage: {cell.mileage_start} ~ {cell.mileage_end}",
            f"RAI: {cell.response_state.get('RAI')}",
            f"GRS_geo_base: {cell.geology_state.get('GRS_geo_base')}",
            f"GRCI: {cell.coupling_state.get('GRCI')}",
            f"GRCI_available: {cell.coupling_state.get('GRCI_available')}",
            f"main_hazards: {cell.geology_state.get('main_hazards')}",
            "boundary: GRCI only supports excavated daily_review review; forward cells use GRS/source trace only.",
        ]
    )


def interpret_cell_state(cell: TwinCellView) -> dict[str, Any]:
    """Return a template-only explanation for a single twin cell."""
    role = cell.cell_role
    hazards = cell.geology_state.get("main_hazards") or []
    explanation = (
        f"{cell.cell_id} 为 {role} 单元，里程 {cell.mileage_start}~{cell.mileage_end}。"
        f"RAI={cell.response_state.get('RAI')}，GRS={cell.geology_state.get('GRS_geo_base')}，"
        f"GRCI={cell.coupling_state.get('GRCI')}。"
    )
    if role == "forward_attention":
        explanation += "该单元属于当前掌子面前方关注范围，不使用 GRCI。"
    if hazards:
        explanation += f"主要地质关注标签包括：{'、'.join(str(item) for item in hazards[:5])}。"
    return {
        "cell_id": cell.cell_id,
        "cell_role": role,
        "prompt": build_cell_interpretation_prompt(cell),
        "interpretation": explanation,
        "boundary_notes": [
            "GRCI 不是灾害概率。",
            "PLC proxy 指标不是严格物理量。",
            "forward_attention 只表示前方关注提示。",
        ],
    }


def interpret_high_attention_cells(twin: DailyConstructionTwin, limit: int = 5) -> list[dict[str, Any]]:
    """Return template explanations for high GRCI review cells."""
    ids = [item.get("cell_id") for item in twin.high_grci_cells[:limit]]
    by_id = {cell.cell_id: cell for cell in twin.cells}
    return [interpret_cell_state(by_id[cell_id]) for cell_id in ids if cell_id in by_id]


def interpret_daily_twin_summary(twin: DailyConstructionTwin) -> dict[str, Any]:
    """Return a template-only summary of the daily construction twin."""
    return {
        "date": twin.date,
        "summary_text": (
            f"{twin.date} 构建 {len(twin.cells)} 个施工状态单元，其中 "
            f"daily_review={len(twin.daily_review_cells)}，"
            f"forward_attention={len(twin.forward_attention_cells)}，"
            f"local_background={len(twin.local_background_cells)}。"
        ),
        "high_grci_cell_count": len(twin.high_grci_cells),
        "warnings": twin.warnings,
    }
