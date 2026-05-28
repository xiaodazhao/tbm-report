from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    tools: tuple[str, ...]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    agent: str
    description: str
    method_name: str
    needs_date: bool = True


AGENT_SPECS: dict[str, AgentSpec] = {
    "DataAgent": AgentSpec(
        name="DataAgent",
        description="Find dates, load TBM CSV data, and expose available fields.",
        tools=("list_dates", "load_day", "analyze_day"),
    ),
    "OperationAgent": AgentSpec(
        name="OperationAgent",
        description="Analyze TBM operation states, work/stop balance, and efficiency.",
        tools=("analyze_operation",),
    ),
    "SafetyAgent": AgentSpec(
        name="SafetyAgent",
        description="Analyze gas statistics and exceedance events.",
        tools=("analyze_gas",),
    ),
    "GeologyAgent": AgentSpec(
        name="GeologyAgent",
        description="Analyze geology fusion, segment risk, coupling, and forward risk.",
        tools=("analyze_geology", "analyze_forward_risk", "risk_profile"),
    ),
    "TwinAgent": AgentSpec(
        name="TwinAgent",
        description="Build the compact digital-twin state snapshot.",
        tools=("get_digital_twin_state",),
    ),
    "MemoryAgent": AgentSpec(
        name="MemoryAgent",
        description="Compare current analysis with history memory.",
        tools=("compare_history",),
    ),
}


TOOL_SPECS: dict[str, ToolSpec] = {
    "list_dates": ToolSpec(
        name="list_dates",
        agent="DataAgent",
        description="List available TBM data dates.",
        method_name="list_dates",
        needs_date=False,
    ),
    "load_day": ToolSpec(
        name="load_day",
        agent="DataAgent",
        description="Load one day of TBM CSV data and return basic metadata.",
        method_name="load_day",
    ),
    "analyze_day": ToolSpec(
        name="analyze_day",
        agent="DataAgent",
        description="Run the complete daily TBM analysis and return a compact summary.",
        method_name="analyze_day",
    ),
    "analyze_operation": ToolSpec(
        name="analyze_operation",
        agent="OperationAgent",
        description="Analyze work, stop, transition, abnormal states, and clustered operation states.",
        method_name="analyze_operation",
    ),
    "analyze_gas": ToolSpec(
        name="analyze_gas",
        agent="SafetyAgent",
        description="Analyze gas statistics and exceedance events.",
        method_name="analyze_gas",
    ),
    "analyze_geology": ToolSpec(
        name="analyze_geology",
        agent="GeologyAgent",
        description="Analyze geology fusion, segment risk, and risk-response coupling.",
        method_name="analyze_geology",
    ),
    "analyze_forward_risk": ToolSpec(
        name="analyze_forward_risk",
        agent="GeologyAgent",
        description="Analyze look-ahead geological risk from the current chainage.",
        method_name="analyze_forward_risk",
    ),
    "risk_profile": ToolSpec(
        name="risk_profile",
        agent="GeologyAgent",
        description="Build risk and speed profiles along chainage.",
        method_name="risk_profile",
    ),
    "get_digital_twin_state": ToolSpec(
        name="get_digital_twin_state",
        agent="TwinAgent",
        description="Build a compact digital-twin state snapshot.",
        method_name="get_digital_twin_state",
    ),
    "compare_history": ToolSpec(
        name="compare_history",
        agent="MemoryAgent",
        description="Compare the selected date with saved history memory records.",
        method_name="compare_history",
    ),
}


def describe_capabilities() -> dict:
    """Describe capabilities."""
    return {
        "agents": [
            {
                "name": spec.name,
                "description": spec.description,
                "tools": list(spec.tools),
            }
            for spec in AGENT_SPECS.values()
        ],
        "tools": [
            {
                "name": spec.name,
                "agent": spec.agent,
                "description": spec.description,
                "needs_date": spec.needs_date,
            }
            for spec in TOOL_SPECS.values()
        ],
    }


def tool_agent_name(tool_name: str) -> Optional[str]:
    """Handle tool agent name."""
    spec = TOOL_SPECS.get(tool_name)
    return spec.agent if spec else None


def resolve_tool(tools_obj: object, tool_name: str) -> Optional[Callable]:
    """Resolve tool."""
    spec = TOOL_SPECS.get(tool_name)
    if spec is None:
        return None
    return getattr(tools_obj, spec.method_name, None)