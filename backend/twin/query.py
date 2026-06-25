from __future__ import annotations

from typing import Any

from schemas.twin import DailyConstructionTwin, TwinCellView


def get_cells_by_role(twin: DailyConstructionTwin, role: str) -> list[TwinCellView]:
    """Return twin cells by evidence role without mutating the twin."""
    return [cell for cell in twin.cells if cell.cell_role == role]


def get_daily_review_cells(twin: DailyConstructionTwin) -> list[TwinCellView]:
    """Return excavated review cells."""
    return list(twin.daily_review_cells)


def get_forward_attention_cells(twin: DailyConstructionTwin) -> list[TwinCellView]:
    """Return forward attention cells. GRCI is not applicable for these cells."""
    return list(twin.forward_attention_cells)


def get_local_background_cells(twin: DailyConstructionTwin) -> list[TwinCellView]:
    """Return local background cells."""
    return list(twin.local_background_cells)


def get_high_grci_cells(twin: DailyConstructionTwin) -> list[dict[str, Any]]:
    """Return daily-review high GRCI cells only."""
    return [
        cell for cell in twin.high_grci_cells
        if cell.get("cell_role") in {None, "daily_review"} and not cell.get("is_forward_cell")
    ]


def find_cell(twin: DailyConstructionTwin, cell_id: str) -> TwinCellView | None:
    """Find a cell in the daily construction twin by id."""
    for cell in twin.cells:
        if cell.cell_id == cell_id:
            return cell
    return None


def summarize_twin(twin: DailyConstructionTwin) -> dict[str, Any]:
    """Build a compact summary for debug/API/export usage."""
    return {
        "date": twin.date,
        "cell_count": len(twin.cells),
        "daily_review_cell_count": len(twin.daily_review_cells),
        "forward_attention_cell_count": len(twin.forward_attention_cells),
        "local_background_cell_count": len(twin.local_background_cells),
        "high_grci_cell_count": len(twin.high_grci_cells),
        "scope": twin.scope.model_dump(),
        "summaries": twin.summaries.model_dump(),
        "warnings": twin.warnings,
    }
