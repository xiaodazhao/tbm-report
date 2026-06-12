from datetime import datetime

from services.sqlite_storage_service import (
    load_history_records_from_db,
    save_history_record_to_db,
)
from utils.chainage_utils import format_chainage_dk


def _safe_float(value, default=0.0):
    """Safely convert a value to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_round(value, ndigits=3):
    """Safely round a numeric value."""
    return round(_safe_float(value), ndigits)


def _json_safe(value):
    """Internal helper for json safe."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def _gas_exceed_types(gas_stats):
    """Internal helper for gas exceed types."""
    gas_all = gas_stats.get("all", {}) if isinstance(gas_stats, dict) else {}
    out = []
    for gas, stat in gas_all.items():
        if isinstance(stat, dict) and stat.get("exceed_event_count", 0) > 0:
            out.append(str(gas))
    return out


def _latest_top_segment(coupling_summary):
    """Internal helper for latest top segment."""
    top_segments = coupling_summary.get("top_segments", []) if isinstance(coupling_summary, dict) else []
    if not top_segments:
        return {}
    return top_segments[0] if isinstance(top_segments[0], dict) else {}


def build_history_record(date, analysis_result):
    """Build history record."""
    cst = analysis_result.get("cst_state", {}) if isinstance(analysis_result, dict) else {}
    stats = analysis_result.get("stats", {})
    state_stats = analysis_result.get("state_stats", {})
    gas_stats = analysis_result.get("gas_stats", {})
    geo_summary = analysis_result.get("geo_summary_segment", {})
    forward_risk = analysis_result.get("forward_risk_summary", {})
    coupling = analysis_result.get("coupling_summary", {})
    twin = analysis_result.get("digital_twin_state", {})

    total_min = (
        _safe_float(stats.get("stop_total_min"))
        + _safe_float(stats.get("transition_total_min"))
        + _safe_float(stats.get("work_total_min"))
        + _safe_float(stats.get("abnormal_total_min"))
    )
    work_total = _safe_float(stats.get("work_total_min"))
    stop_total = _safe_float(stats.get("stop_total_min"))
    position_state = twin.get("position_state", {}) if isinstance(twin, dict) else {}
    coupling_state = twin.get("coupling_state", {}) if isinstance(twin, dict) else {}
    top_segment = _latest_top_segment(coupling)

    if isinstance(cst, dict) and cst:
        cst_spatial = cst.get("spatial_state", {})
        cst_operation = cst.get("operation_state", {})
        cst_attention = cst.get("attention_state", {})
        cst_response = cst.get("response_state", {})
        cst_geo = cst.get("geological_state", {})
        current_chainage = cst_spatial.get("face_chainage", position_state.get("current_chainage"))
        advance_length = cst_spatial.get("advance_length", position_state.get("advance_length"))
        work_total = _safe_float(cst_operation.get("working_duration_min"), work_total)
        stop_total = _safe_float(cst_operation.get("stoppage_duration_min"), stop_total)
        grs_value = _safe_round(cst_attention.get("GRS", 0))
        rai_value = _safe_round(cst_response.get("RAI", 0))
        grci_value = _safe_round(cst_attention.get("GRCI", 0))
        geology_hazards = cst_geo.get("hazards", [])
    else:
        current_chainage = position_state.get("current_chainage")
        advance_length = position_state.get("advance_length")
        grs_value = _safe_round(top_segment.get("GRS", 0))
        rai_value = _safe_round(top_segment.get("RAI", 0))
        grci_value = _safe_round(top_segment.get("GRCI", 0))
        geology_hazards = []

    return _json_safe({
        "date": date,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "position": {
            "current_chainage": current_chainage,
            "current_chainage_dk": position_state.get("current_chainage_dk")
            or format_chainage_dk(current_chainage),
            "start_chainage_dk": position_state.get("start_chainage_dk"),
            "end_chainage_dk": position_state.get("end_chainage_dk"),
            "advance_length": _safe_round(advance_length, 2),
        },
        "operation": {
            "total_min": _safe_round(total_min, 1),
            "work_total_min": _safe_round(work_total, 1),
            "stop_total_min": _safe_round(stop_total, 1),
            "work_ratio": _safe_round(work_total / total_min if total_min else 0),
            "stop_ratio": _safe_round(stop_total / total_min if total_min else 0),
            "work_count": int(stats.get("work_count", 0)),
            "stop_count": int(stats.get("stop_count", 0)),
            "abnormal_count": int(stats.get("abnormal_count", 0)),
            "state_switch_count": int(state_stats.get("状态切换次数", 0))
            if isinstance(state_stats, dict) else 0,
        },
        "geology": {
            "has_geology": bool(geo_summary.get("has_geology", False))
            if isinstance(geo_summary, dict) else False,
            "high_risk_segment_count": int(geo_summary.get("high_risk_segment_count", 0))
            if isinstance(geo_summary, dict) else 0,
            "multi_source_segment_count": int(geo_summary.get("multi_source_segment_count", 0))
            if isinstance(geo_summary, dict) else 0,
        },
        "forward_risk": {
            "has_forward_risk": bool(forward_risk.get("has_forward_risk", False))
            if isinstance(forward_risk, dict) else False,
            "lookahead_m": _safe_round(forward_risk.get("lookahead_m"), 1)
            if isinstance(forward_risk, dict) else 0,
            "high_risk_count": int(forward_risk.get("high_risk_count", 0))
            if isinstance(forward_risk, dict) else 0,
            "multi_source_count": int(forward_risk.get("multi_source_count", 0))
            if isinstance(forward_risk, dict) else 0,
            "main_hazards": forward_risk.get("main_hazards", [])
            if isinstance(forward_risk, dict) else [],
        },
        "coupling": {
            "has_coupling": bool(coupling.get("has_coupling", False))
            if isinstance(coupling, dict) else False,
            "dominant_level": coupling_state.get("dominant_level"),
            "max_index": grci_value,
            "mean_index": _safe_round(coupling.get("mean_index", grci_value)),
            "level_counts": coupling.get("level_counts", {}) if isinstance(coupling, dict) else {},
            "top_segment": top_segment.get("segment"),
            "top_segment_index": grci_value,
            "GRS": grs_value,
            "RAI": rai_value,
            "GRCI": grci_value,
        },
        "safety": {
            "gas_exceed_types": _gas_exceed_types(gas_stats),
        },
        "geological_attention": {
            "hazards": geology_hazards,
        },
    })

def save_history_record(record):
    """Save history record."""
    return save_history_record_to_db(record)


def load_history_records(limit=10, before_date=None):
    """Load history records."""
    return load_history_records_from_db(limit=limit, before_date=before_date)


def _delta_text(name, current_value, previous_value, unit="", ndigits=1):
    """Internal helper for delta text."""
    current = _safe_float(current_value)
    previous = _safe_float(previous_value)
    delta = current - previous
    if abs(delta) < 10 ** (-ndigits):
        return f"{name}基本持平"
    direction = "升高" if delta > 0 else "降低"
    return f"{name}较上一记录{direction}{abs(delta):.{ndigits}f}{unit}"


def build_history_comparison(current_record, history_records):
    """Build history comparison."""
    if not history_records:
        return {
            "has_history": False,
            "history_count": 0,
            "previous_date": None,
            "comparison_text": "暂无历史分析记忆，当前报告仅进行本次施工状态分析。",
            "recent_records": [],
        }

    previous = history_records[-1]
    current_op = current_record.get("operation", {})
    previous_op = previous.get("operation", {})
    current_forward = current_record.get("forward_risk", {})
    previous_forward = previous.get("forward_risk", {})
    current_coupling = current_record.get("coupling", {})
    previous_coupling = previous.get("coupling", {})

    lines = [
        f"已读取 {len(history_records)} 条历史分析记忆，最近一条为 {previous.get('date', '未知日期')}。",
        _delta_text("有效掘进占比", current_op.get("work_ratio", 0) * 100, previous_op.get("work_ratio", 0) * 100, "个百分点"),
        _delta_text("停机占比", current_op.get("stop_ratio", 0) * 100, previous_op.get("stop_ratio", 0) * 100, "个百分点"),
        _delta_text("状态切换次数", current_op.get("state_switch_count", 0), previous_op.get("state_switch_count", 0), "次", 0),
        _delta_text("前方高风险提示段数量", current_forward.get("high_risk_count", 0), previous_forward.get("high_risk_count", 0), "个", 0),
        _delta_text("平均耦合指数", current_coupling.get("mean_index", 0), previous_coupling.get("mean_index", 0), "", 3),
    ]

    current_hazards = set(current_forward.get("main_hazards", []) or [])
    previous_hazards = set(previous_forward.get("main_hazards", []) or [])
    new_hazards = sorted(current_hazards - previous_hazards)
    if new_hazards:
        lines.append(f"本次新增主要风险类型：{'、'.join(new_hazards)}。")
    elif current_hazards:
        lines.append(f"主要风险类型与上一记录基本一致，仍以{'、'.join(sorted(current_hazards))}为主。")

    return {
        "has_history": True,
        "history_count": len(history_records),
        "previous_date": previous.get("date"),
        "comparison_text": "\n".join(lines),
        "recent_records": history_records,
    }