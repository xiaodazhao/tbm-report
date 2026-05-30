"""PLC field contract helpers for TBM analysis modules."""

from __future__ import annotations

from typing import Any


PLC_CONTRACT_VERSION = "plc_contract_v1"

TIME_COLUMNS = [
    "运行时间-time",
    "timestamp",
    "time",
    "datetime",
    "date_time",
]

CHAINAGE_COLUMNS = [
    "chainage",
    "当前里程",
    "导向盾首里程",
    "开累进尺",
    "里程",
]

STATE_COLUMNS = [
    "掘进状态",
    "施工状态",
    "state",
    "excavation_state",
]

MOTION_COLUMNS = {
    "advance_speed": ["推进速度", "advance_speed", "speed", "actual_speed"],
    "set_advance_speed": ["推进给定速度", "给定速度", "target_speed", "set_speed"],
    "thrust": ["推力", "总推力", "thrust", "total_thrust"],
    "torque": ["刀盘扭矩", "扭矩", "cutter_torque", "torque"],
    "rpm": ["刀盘实际转速", "刀盘转速", "转速", "cutter_rpm", "rpm"],
    "penetration": ["贯入度", "penetration"],
}

GAS_COLUMNS = {
    "CH4": ["CH4检测", "CH4", "甲烷"],
    "CO2": ["CO2检测", "CO2"],
    "H2S": ["H2S检测", "H2S"],
    "SO2": ["SO2检测", "SO2"],
    "NO2": ["NO2检测", "NO2"],
    "NO": ["NO检测", "NO"],
}

PLC_UNIT_ASSUMPTIONS = {
    "推进速度": "mm/min 或项目配置单位，需结合原始数据字典确认。",
    "推力": "kN 或项目配置单位。",
    "刀盘扭矩": "kN·m 或项目配置单位。",
    "刀盘实际转速": "rpm 或百分比，需结合字段说明确认。",
    "CH4检测": "% 或报警量，需由数据质量检查识别。",
}

_FIELD_GROUPS = {
    "time": TIME_COLUMNS,
    "chainage": CHAINAGE_COLUMNS,
    "state": STATE_COLUMNS,
    **MOTION_COLUMNS,
    **GAS_COLUMNS,
}


def find_first_existing(df: Any, candidates: list[str]) -> str | None:
    """Return the first matching column from a list of aliases."""
    columns = [str(col) for col in getattr(df, "columns", [])]
    lower_map = {col.strip().lower(): col for col in columns}

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower_map:
            return lower_map[key]

    for candidate in candidates:
        key = candidate.strip().lower()
        for column in columns:
            if key and key in column.strip().lower():
                return column
    return None


def resolve_plc_columns(df: Any) -> dict[str, Any]:
    """Resolve canonical PLC field groups from a DataFrame-like object."""
    return {
        "time_col": find_first_existing(df, TIME_COLUMNS),
        "chainage_col": find_first_existing(df, CHAINAGE_COLUMNS),
        "state_col": find_first_existing(df, STATE_COLUMNS),
        "motion_cols": {
            name: find_first_existing(df, aliases)
            for name, aliases in MOTION_COLUMNS.items()
        },
        "gas_cols": {
            name: find_first_existing(df, aliases)
            for name, aliases in GAS_COLUMNS.items()
        },
        "plc_contract_version": PLC_CONTRACT_VERSION,
    }


def get_canonical_plc_field(name: str) -> str:
    """Return the canonical PLC field key for a raw field alias."""
    if not name:
        return name
    for canonical_name, aliases in _FIELD_GROUPS.items():
        if name == canonical_name or name in aliases:
            return canonical_name
    return name


def explain_plc_field(name: str) -> dict[str, Any]:
    """Explain a PLC field alias, its canonical key, and known unit notes."""
    canonical_name = get_canonical_plc_field(name)
    aliases = list(_FIELD_GROUPS.get(canonical_name, []))
    unit_note = PLC_UNIT_ASSUMPTIONS.get(name)
    if unit_note is None:
        for alias in aliases:
            unit_note = PLC_UNIT_ASSUMPTIONS.get(alias)
            if unit_note:
                break
    return {
        "requested_name": name,
        "canonical_name": canonical_name,
        "aliases": aliases,
        "unit_assumption": unit_note,
        "plc_contract_version": PLC_CONTRACT_VERSION,
    }


def list_required_plc_fields() -> dict[str, Any]:
    """List the canonical PLC field groups used by downstream analysis modules."""
    return {
        "time": list(TIME_COLUMNS),
        "chainage": list(CHAINAGE_COLUMNS),
        "state": list(STATE_COLUMNS),
        "motion": {key: list(value) for key, value in MOTION_COLUMNS.items()},
        "gas": {key: list(value) for key, value in GAS_COLUMNS.items()},
        "plc_contract_version": PLC_CONTRACT_VERSION,
    }
