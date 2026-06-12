from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolOutput(BaseModel):
    """Common output shape for agent tools."""

    success: bool
    data: Optional[Any] = None
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def _dump(output: ToolOutput) -> dict[str, Any]:
    """Internal helper for dump."""
    if hasattr(output, "model_dump"):
        return output.model_dump()
    return output.dict()


def ok(data: Any = None, message: str = "", **metadata: Any) -> dict[str, Any]:
    """Handle ok."""
    return _dump(ToolOutput(
        success=True,
        data=data,
        message=message,
        metadata=metadata,
    ))


def fail(message: str, **metadata: Any) -> dict[str, Any]:
    """Handle fail."""
    return _dump(ToolOutput(
        success=False,
        data=None,
        message=message,
        metadata=metadata,
    ))