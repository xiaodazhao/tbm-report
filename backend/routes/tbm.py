from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, FastAPI

from agent.supervisor_agent import TBMSupervisorAgent
from llm.summary_contract import normalize_llm_summary
from llm.llm_api import call_llm
from llm.prompt_builder import build_prompt
from llm.prompt_builder_timewindow import build_prompt_timewindow
from schemas.api import AgentRequest, DailyReportRequest, EvidenceImportRequest, TimeWindowRequest
from schemas.responses import (
    AgentSessionPayload,
    ApiEnvelope,
    DatesPayload,
    DigitalTwinPayload,
    EvidenceImportPayload,
    GeologyPayload,
    HistoryMemoryPayload,
    ReportPayload,
    RiskProfilePayload,
    StatePayload,
    SummaryPayload,
)
from services.analysis_cache_service import get_or_compute_file_cache
from services.evidence_import_service import import_evidence_files
from services.twin_query_service import (
    compare_twin_snapshots,
    explain_twin_event,
    get_twin_events,
    query_twin_by_chainage,
)
from services.history_memory_service import (
    build_history_comparison,
    build_history_record,
    load_history_records,
    save_history_record,
)
from services.sqlite_storage_service import load_agent_messages, load_agent_session
from utils.api_response import api_error, api_success
from utils.io_utils import get_all_csv_paths, get_csv_path_by_date, get_latest_csv_path, load_csv, load_csv_by_date
from utils.serialization import serialize_for_json
from utils.time_window_utils import load_df_by_time


DAILY_ANALYSIS_CACHE_NAMESPACE = "tbm_daily_analysis"
# Backward compatibility for summaries persisted before the UTF-8 cleanup.
LEGACY_VALID_SAMPLE_KEYS = ["有效状态样本数", "鏈夋晥鐘舵€佹牱鏈暟"]
LEGACY_STATE_CONFIG_KEYS = ["状态识别配置", "鐘舵€佽瘑鍒厤缃�"]
DEBUG_PREFIX = "[TBM DEBUG]"


def _date_from_csv_path(path: Path) -> str | None:
    """Internal helper for date from csv path."""
    raw = path.name.replace("tbm_data_", "").replace(".csv", "")
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _build_analysis_meta(path: Path, cache_hit: bool, resolved_date: str | None) -> dict:
    """Build analysis meta."""
    return {
        "cache_hit": cache_hit,
        "resolved_date": resolved_date,
        "source_file": path.name,
        "source_path": str(path),
    }


def _collect_warnings(result: dict | None, extra_warnings: list[str] | None = None) -> list[str]:
    """Collect warnings."""
    warnings = list((result or {}).get("warnings", []))
    if extra_warnings:
        warnings.extend(extra_warnings)
    return warnings


def _summary_value(summary: dict | None, keys: list[str], default: Any):
    """Internal helper for summary value."""
    if not isinstance(summary, dict):
        return default
    for key in keys:
        if key in summary and summary[key] is not None:
            return summary[key]
    return default


def _stringify_dict_keys(value: Any) -> Any:
    """Internal helper for stringify dict keys."""
    if isinstance(value, dict):
        return {str(key): _stringify_dict_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_dict_keys(item) for item in value]
    return value


def _debug_log(event: str, **fields: Any) -> None:
    """Internal helper for debug log."""
    ordered = []
    for key, value in fields.items():
        if value is None:
            continue
        ordered.append(f"{key}={value}")
    suffix = f" | {'; '.join(ordered)}" if ordered else ""
    print(f"{DEBUG_PREFIX} {event}{suffix}")


def _debug_start(feature: str, **fields: Any) -> float:
    """Internal helper for debug start."""
    started = perf_counter()
    _debug_log(f"{feature}.start", **fields)
    return started


def _debug_success(feature: str, started: float, **fields: Any) -> None:
    """Internal helper for debug success."""
    duration_ms = round((perf_counter() - started) * 1000, 1)
    _debug_log(f"{feature}.success", duration_ms=duration_ms, **fields)


def _debug_failure(feature: str, started: float, exc: Exception, **fields: Any) -> None:
    """Internal helper for debug failure."""
    duration_ms = round((perf_counter() - started) * 1000, 1)
    _debug_log(f"{feature}.failure", duration_ms=duration_ms, error=str(exc), **fields)


def _run_analysis_with_context(
    analyze_tbm_data: Any,
    df: pd.DataFrame,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Call analysis with CST context and tolerate legacy one-arg stubs."""
    try:
        return analyze_tbm_data(df, context=context)
    except TypeError as exc:
        if "context" not in str(exc):
            raise
        return analyze_tbm_data(df)


def _build_summary_payload(result: dict) -> dict:
    """Build summary payload."""
    stats = result["stats"]
    geo_summary = result.get("geo_summary_segment", {})
    return {
        "stop_count": stats.get("stop_count", 0),
        "transition_count": stats.get("transition_count", 0),
        "work_count": stats.get("work_count", 0),
        "abnormal_count": stats.get("abnormal_count", 0),
        "stop_total_min": round(stats.get("stop_total_min", 0), 1),
        "transition_total_min": round(stats.get("transition_total_min", 0), 1),
        "work_total_min": round(stats.get("work_total_min", 0), 1),
        "abnormal_total_min": round(stats.get("abnormal_total_min", 0), 1),
        "geology_has": geo_summary.get("has_geology", False),
        "geology_high_risk_segment_count": geo_summary.get("high_risk_segment_count", 0),
        "geology_multi_source_segment_count": geo_summary.get("multi_source_segment_count", 0),
    }


def _build_state_payload(result: dict) -> dict:
    """Build state payload."""
    state_segments = result.get("state_segments") or {}
    state_labels = result.get("state_labels") or {}
    llm_summary = normalize_llm_summary(result.get("llm_summary") or {})
    cluster_summary = llm_summary.get("cluster_state_summary", {})
    segments = []
    for state, pairs in state_segments.items():
        try:
            state_label = int(state)
        except (TypeError, ValueError):
            continue
        label_text = state_labels.get(state_label, f"施工状态 {state_label}")
        for start_time, end_time in pairs:
            segments.append({
                "label": state_label,
                "label_text": label_text,
                "start": start_time.strftime("%H:%M:%S"),
                "end": end_time.strftime("%H:%M:%S"),
                "duration": (end_time - start_time).total_seconds(),
            })

    efficiency = []
    eff_df = result.get("eff_df")
    if isinstance(eff_df, pd.DataFrame) and not eff_df.empty:
        efficiency = eff_df.to_dict(orient="records")
    elif isinstance(eff_df, list):
        efficiency = eff_df

    return {
        "segments": serialize_for_json(segments),
        "efficiency": serialize_for_json(efficiency),
        "state_labels": serialize_for_json(_stringify_dict_keys(state_labels)),
        "state_stats": serialize_for_json(_stringify_dict_keys(result.get("state_stats", {}))),
        "valid_samples": int(cluster_summary.get("valid_samples", 0) or 0),
        "state_config": serialize_for_json(cluster_summary.get("config", {})),
    }


def _build_geology_payload(result: dict) -> dict:
    """Build geology endpoint payload.

    注意：
    - 保留旧 geology 字段；
    - 额外返回 geology_v2 字段；
    - 即使 result 中 geology_v2 为空，也要返回对应 key，方便前端/测试判断。
    """
    segment_df = result.get("segment_df", pd.DataFrame())
    typical_df = result.get("typical_segments_df", pd.DataFrame())

    def _df_to_records(df):
        try:
            if df is not None and hasattr(df, "empty") and not df.empty:
                return df.to_dict(orient="records")
        except Exception:
            pass
        return []

    payload = {
        # 旧版地质摘要
        "record_summary": serialize_for_json(result.get("geo_summary_record", {})),
        "segment_summary": serialize_for_json(result.get("geo_summary_segment", {})),
        "segment_table": serialize_for_json(_df_to_records(segment_df)),
        "typical_segments": serialize_for_json(_df_to_records(typical_df)),

        # 旧版 GRS / RAI / GRCI 耦合分析
        "coupling_summary": serialize_for_json(result.get("coupling_summary", {})),
        "coupling_validation": serialize_for_json(result.get("coupling_validation", {})),
        "weak_label_validation": serialize_for_json(result.get("weak_label_validation", {})),
        "coupling_output_paths": serialize_for_json(result.get("coupling_output_paths", {})),
        "high_attention_segments": serialize_for_json(result.get("high_attention_segments", [])),
        "top_grci_segments": serialize_for_json(result.get("top_grci_segments", [])),
        "top_grs_segments": serialize_for_json(result.get("top_grs_segments", [])),
        "top_rai_segments": serialize_for_json(result.get("top_rai_segments", [])),

        # 旧版前方风险 / 掌子面 / 数字孪生状态
        "forward_risk_summary": serialize_for_json(result.get("forward_risk_summary", {})),
        "face_description": serialize_for_json(result.get("face_description", {})),
        "digital_twin_state": serialize_for_json(result.get("digital_twin_state", {})),
        "cst_state": serialize_for_json(result.get("cst_state", {})),

        # geology_v2：严格证据过滤 + cell 融合 + forward_profile + report_context
        "geology_v2_context": serialize_for_json(result.get("geology_v2_context", {})),
        "geology_v2_prompt_block": result.get("geology_v2_prompt_block", ""),
        "geology_v2_rendered_text": result.get("geology_v2_rendered_text", ""),
        "geology_v2_data_summary": serialize_for_json(result.get("geology_v2_data_summary", {})),
        "geology_v2_texts": serialize_for_json(result.get("geology_v2_texts", {})),
        "geology_v2_forward_profile": serialize_for_json(result.get("geology_v2_forward_profile", {})),
        "geology_v2_warnings": serialize_for_json(result.get("geology_v2_warnings", [])),
    }

    return payload


def _build_history_payload(current_date: str, result: dict, limit: int) -> dict:
    """Build history payload."""
    current_record = build_history_record(current_date, result)
    history_records = load_history_records(limit=limit, before_date=current_date)
    history_comparison = build_history_comparison(current_record, history_records)
    return {
        "date": current_date,
        "current_record": serialize_for_json(current_record),
        "history_comparison": serialize_for_json(history_comparison),
    }

# 这里定义 /api/tbm 下的所有接口
def register_tbm_routes(
    app: FastAPI,
    analyze_tbm_data,
    build_risk_profile,
    build_speed_profile,
):
    """Handle register tbm routes."""
    router = APIRouter(prefix="/api/tbm", tags=["tbm"])
    tbm_supervisor_agent = TBMSupervisorAgent(
        analyze_tbm_data=analyze_tbm_data,
        build_risk_profile=build_risk_profile,
        build_speed_profile=build_speed_profile,
    )

    def _resolve_daily_path(date: Optional[str] = None) -> Path:
        """Resolve daily path."""
        return get_csv_path_by_date(date) if date else get_latest_csv_path()
    
    # 根据日期找到 CSV，读取数据，调用 analyze_tbm_data，返回统一分析结果 result
    def _get_daily_analysis(date: Optional[str] = None) -> tuple[Path, dict, list[str], dict, str | None]:
        """Get daily analysis."""
        path = _resolve_daily_path(date)
        resolved_date = date or _date_from_csv_path(path)
        result, cache_hit = get_or_compute_file_cache(
            DAILY_ANALYSIS_CACHE_NAMESPACE,
            path,
            lambda: _run_analysis_with_context(
                analyze_tbm_data,
                load_csv(path),
                {
                    "date": resolved_date,
                    "analysis_mode": "daily",
                    "source_path": str(path),
                    "source_name": path.name,
                    "persist_cst": True,
                },
            ),
        )
        meta = _build_analysis_meta(path, cache_hit, resolved_date)
        return path, result, _collect_warnings(result), meta, resolved_date

    def _internal_error(prefix: str, exc: Exception, *, status_code: int = 500, meta: dict | None = None):
        """Internal helper for internal error."""
        print(f"[{prefix}] {exc}")
        return api_error(
            f"{prefix}：{exc}",
            status_code=status_code,
            meta=meta,
            error_code="INTERNAL_ERROR",
        )

    @router.get("/dates", response_model=ApiEnvelope[DatesPayload])
    def get_available_dates():
        """Get available dates."""
        started = _debug_start("dates")
        try:
            dates = []
            for file_path in get_all_csv_paths():
                parsed = _date_from_csv_path(file_path)
                if parsed:
                    dates.append(parsed)
            dates.sort(reverse=True)
            _debug_success("dates", started, count=len(dates), latest=dates[0] if dates else None)
            return api_success({"dates": dates})
        except Exception as exc:
            _debug_failure("dates", started, exc)
            return _internal_error("日期列表加载失败", exc)

    @router.post("/agent_v2")
    def run_tbm_supervisor_agent(req: AgentRequest):
        """Run tbm supervisor agent."""
        started = _debug_start(
            "agent_v2",
            date=req.date,
            session_id=req.session_id,
            use_llm=req.use_llm,
            verbose=req.verbose,
            query=req.query[:80],
        )
        result = tbm_supervisor_agent.run(
            query=req.query,
            date=req.date,
            session_id=req.session_id,
            history_limit=req.history_limit,
            use_llm=req.use_llm,
            verbose=req.verbose,
        )
        if result.get("success"):
            data = result.get("data") or {}
            _debug_success(
                "agent_v2",
                started,
                routed_agents=",".join(data.get("routed_agents", [])),
                session_id=data.get("session_id"),
                resolved_date=data.get("date"),
            )
        else:
            _debug_log(
                "agent_v2.failure",
                duration_ms=round((perf_counter() - started) * 1000, 1),
                error=result.get("message"),
                session_id=req.session_id,
            )
        return result

    @router.get("/agent_v2/capabilities")
    def tbm_supervisor_agent_capabilities():
        """Handle tbm supervisor agent capabilities."""
        started = _debug_start("agent_v2.capabilities")
        payload = tbm_supervisor_agent.capabilities()
        _debug_success(
            "agent_v2.capabilities",
            started,
            agent_count=len(payload.get("agents", [])),
        )
        return payload

    @router.get("/agent_v2/session", response_model=ApiEnvelope[AgentSessionPayload])
    def tbm_supervisor_agent_session(session_id: str, limit: int = 30):
        """Handle tbm supervisor agent session."""
        started = _debug_start("agent_v2.session", session_id=session_id, limit=limit)
        try:
            session = load_agent_session(session_id)
            if not session:
                _debug_success("agent_v2.session", started, session_id=session_id, message_count=0)
                return api_success(
                    {
                        "session_id": session_id,
                        "title": None,
                        "created_at": None,
                        "updated_at": None,
                        "messages": [],
                    }
                )

            payload = {
                "session_id": session_id,
                "title": session.get("title"),
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
                "messages": load_agent_messages(session_id, limit=limit),
            }
            _debug_success(
                "agent_v2.session",
                started,
                session_id=session_id,
                message_count=len(payload["messages"]),
            )
            return api_success(payload)
        except Exception as exc:
            _debug_failure("agent_v2.session", started, exc, session_id=session_id, limit=limit)
            return _internal_error("问答会话加载失败", exc, meta={"session_id": session_id, "limit": limit})

    @router.post("/evidence/import", response_model=ApiEnvelope[EvidenceImportPayload])
    def import_evidence_api(req: EvidenceImportRequest):
        """Handle import evidence api."""
        started = _debug_start(
            "evidence.import",
            path_count=len(req.paths),
            source_type=req.source_type,
            dry_run=req.dry_run,
            replace_existing=req.replace_existing,
            recursive=req.recursive,
        )
        try:
            result = import_evidence_files(
                paths=req.paths,
                source_type=req.source_type,
                dry_run=req.dry_run,
                replace_existing=req.replace_existing,
                recursive=req.recursive,
            )
            warnings = [item.get("error", "") for item in result.get("errors", []) if item.get("error")]
            _debug_success(
                "evidence.import",
                started,
                parsed_record_count=result.get("parsed_record_count"),
                inserted_count=result.get("inserted_count"),
                replaced_count=result.get("replaced_count"),
                error_count=len(result.get("errors", [])),
            )
            return api_success(result, warnings=warnings)
        except FileNotFoundError as exc:
            _debug_failure("evidence.import", started, exc)
            return api_error(str(exc), status_code=404, error_code="IMPORT_PATH_NOT_FOUND")
        except Exception as exc:
            _debug_failure("evidence.import", started, exc)
            return _internal_error("证据库导入失败", exc)

    @router.post("/report", response_model=ApiEnvelope[ReportPayload])
    def generate_daily_report(req: DailyReportRequest):
        """Generate daily report."""
        started = _debug_start("report.daily", date=req.date)
        try:
            _, result, warnings, meta, _ = _get_daily_analysis(req.date)
            current_record = build_history_record(req.date, result)
            history_records = load_history_records(limit=10, before_date=req.date)
            history_comparison = build_history_comparison(current_record, history_records)
            save_history_record(current_record)

            llm_summary = deepcopy(result["llm_summary"])
            llm_summary["history_comparison"] = history_comparison
            llm_summary.setdefault("prompt_text_inputs", {})
            llm_summary["prompt_text_inputs"]["history_comparison_text"] = (
                history_comparison.get("comparison_text") or "暂无历史对比信息。"
            )
            llm_summary["施工历史记忆对比"] = history_comparison

            prompt = build_prompt(
                seg_text=result["seg_text"],
                stats_text=result["stats_text"],
                state_text=result["state_text"],
                eff_text=result["eff_text"],
                state_stats_text=result["state_stats_text"],
                gas_text=result["gas_text"],
                geo_text=result["geo_text"],
                face_geo_text=result["face_geo_text"],
                llm_summary=llm_summary,
                risk_prob_text=result["risk_prob_text"],
            )

            report = call_llm(prompt)
            _debug_success(
                "report.daily",
                started,
                date=req.date,
                warning_count=len(warnings),
                cache_hit=meta.get("cache_hit"),
            )
            return api_success({"report": report}, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("report.daily", started, exc, date=req.date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("report.daily", started, exc, date=req.date)
            return _internal_error("日报生成失败", exc, meta={"requested_date": req.date})

    @router.get("/summary", response_model=ApiEnvelope[SummaryPayload])
    def tbm_summary(date: Optional[str] = None):
        """Handle tbm summary."""
        started = _debug_start("summary", date=date)
        try:
            _, result, warnings, meta, _ = _get_daily_analysis(date)
            payload = _build_summary_payload(result)
            _debug_success(
                "summary",
                started,
                date=meta.get("resolved_date"),
                cache_hit=meta.get("cache_hit"),
                work_total_min=payload.get("work_total_min"),
                stop_total_min=payload.get("stop_total_min"),
            )
            return api_success(payload, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("summary", started, exc, date=date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("summary", started, exc, date=date)
            return _internal_error("概览数据加载失败", exc, meta={"requested_date": date})

    @router.get("/state", response_model=ApiEnvelope[StatePayload])
    def state_api(date: Optional[str] = None):
        """Handle state api."""
        started = _debug_start("state", date=date)
        try:
            _, result, warnings, meta, _ = _get_daily_analysis(date)
            payload = _build_state_payload(result)
            _debug_success(
                "state",
                started,
                date=meta.get("resolved_date"),
                cache_hit=meta.get("cache_hit"),
                segment_count=len(payload.get("segments", [])),
                valid_samples=payload.get("valid_samples"),
            )
            return api_success(payload, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("state", started, exc, date=date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("state", started, exc, date=date)
            return _internal_error("施工状态数据加载失败", exc, meta={"requested_date": date})

    @router.get("/gas", response_model=ApiEnvelope[dict[str, Any]])
    def gas_api(date: Optional[str] = None):
        """Handle gas api."""
        started = _debug_start("gas", date=date)
        try:
            _, result, warnings, meta, _ = _get_daily_analysis(date)
            gas_stats = result["gas_stats"]
            _debug_success(
                "gas",
                started,
                date=meta.get("resolved_date"),
                cache_hit=meta.get("cache_hit"),
                gas_types=len((gas_stats.get("all") or {})) if isinstance(gas_stats, dict) else None,
            )
            return api_success(gas_stats, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("gas", started, exc, date=date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("gas", started, exc, date=date)
            return _internal_error("气体监测数据加载失败", exc, meta={"requested_date": date})

    @router.get("/geology", response_model=ApiEnvelope[GeologyPayload])
    def geology_api(date: Optional[str] = None):
        """Handle geology api."""
        started = _debug_start("geology", date=date)
        try:
            _, result, warnings, meta, _ = _get_daily_analysis(date)
            payload = _build_geology_payload(result)
            segment_summary = payload.get("segment_summary", {})
            _debug_success(
                "geology",
                started,
                date=meta.get("resolved_date"),
                cache_hit=meta.get("cache_hit"),
                has_geology=segment_summary.get("has_geology"),
                high_risk_segment_count=segment_summary.get("high_risk_segment_count"),
            )
            return api_success(payload, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("geology", started, exc, date=date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("geology", started, exc, date=date)
            return _internal_error("地质融合数据加载失败", exc, meta={"requested_date": date})

    @router.get("/digital_twin_state", response_model=ApiEnvelope[DigitalTwinPayload])
    def digital_twin_state_api(date: Optional[str] = None):
        """Handle digital twin state api."""
        started = _debug_start("digital_twin_state", date=date)
        try:
            _, result, warnings, meta, resolved_date = _get_daily_analysis(date)
            cst_state = result.get("cst_state", {}) or {}
            payload = {
                "date": resolved_date,
                "digital_twin_state": serialize_for_json(result.get("digital_twin_state", {})),
                "cst_state": serialize_for_json(cst_state),
                "twin_state": serialize_for_json(cst_state),
                "twin_events": serialize_for_json(cst_state.get("events", []) if isinstance(cst_state, dict) else []),
                "twin_diff": serialize_for_json(cst_state.get("diff_from_previous", {}) if isinstance(cst_state, dict) else {}),
                "coupling_summary": serialize_for_json(result.get("coupling_summary", {})),
                "forward_risk_summary": serialize_for_json(result.get("forward_risk_summary", {})),
            }
            _debug_success(
                "digital_twin_state",
                started,
                date=resolved_date,
                cache_hit=meta.get("cache_hit"),
            )
            return api_success(payload, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("digital_twin_state", started, exc, date=date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("digital_twin_state", started, exc, date=date)
            return _internal_error("数字孪生状态加载失败", exc, meta={"requested_date": date})

    @router.get("/twin/events", response_model=ApiEnvelope[dict[str, Any]])
    def twin_events_api(date: Optional[str] = None, event_type: Optional[str] = None, level: Optional[str] = None):
        """Return typed TwinEvents from persisted TwinState snapshots."""
        started = _debug_start("twin_events", date=date, event_type=event_type, level=level)
        try:
            events = get_twin_events(date=date, event_type=event_type, level=level)
            payload = {"date": date, "event_count": len(events), "events": serialize_for_json(events)}
            _debug_success("twin_events", started, date=date, event_count=len(events))
            return api_success(payload)
        except Exception as exc:
            _debug_failure("twin_events", started, exc, date=date)
            return _internal_error("孪生事件查询失败", exc, meta={"requested_date": date})

    @router.get("/twin/segment", response_model=ApiEnvelope[dict[str, Any]])
    def twin_segment_api(date: Optional[str] = None, chainage: float = 0.0):
        """Query TwinEvents and state context around one chainage."""
        started = _debug_start("twin_segment", date=date, chainage=chainage)
        try:
            payload = query_twin_by_chainage(date=date, chainage=chainage)
            _debug_success("twin_segment", started, date=date)
            return api_success(payload)
        except Exception as exc:
            _debug_failure("twin_segment", started, exc, date=date, chainage=chainage)
            return _internal_error("孪生区段查询失败", exc, meta={"requested_date": date, "chainage": chainage})

    @router.get("/twin/event_explain", response_model=ApiEnvelope[dict[str, Any]])
    def twin_event_explain_api(event_id: str, date: Optional[str] = None):
        """Explain one TwinEvent by event_id."""
        started = _debug_start("twin_event_explain", date=date, event_id=event_id)
        try:
            payload = explain_twin_event(date=date, event_id=event_id)
            _debug_success("twin_event_explain", started, date=date, found=payload.get("found"))
            return api_success(payload)
        except Exception as exc:
            _debug_failure("twin_event_explain", started, exc, date=date, event_id=event_id)
            return _internal_error("孪生事件解释失败", exc, meta={"requested_date": date, "event_id": event_id})

    @router.get("/twin/diff", response_model=ApiEnvelope[dict[str, Any]])
    def twin_diff_api(date1: str, date2: str):
        """Compare two persisted TwinState snapshots."""
        started = _debug_start("twin_diff", date1=date1, date2=date2)
        try:
            payload = compare_twin_snapshots(date1=date1, date2=date2)
            _debug_success("twin_diff", started, date1=date1, date2=date2)
            return api_success(payload)
        except Exception as exc:
            _debug_failure("twin_diff", started, exc, date1=date1, date2=date2)
            return _internal_error("孪生状态对比失败", exc, meta={"date1": date1, "date2": date2})

    @router.get("/history_memory", response_model=ApiEnvelope[HistoryMemoryPayload])
    def history_memory_api(date: Optional[str] = None, limit: int = 10):
        """Handle history memory api."""
        started = _debug_start("history_memory", date=date, limit=limit)
        try:
            _, result, warnings, meta, resolved_date = _get_daily_analysis(date)
            current_date = resolved_date or date or datetime.now().strftime("%Y-%m-%d")
            payload = _build_history_payload(current_date, result, limit)
            _debug_success(
                "history_memory",
                started,
                date=current_date,
                cache_hit=meta.get("cache_hit"),
                history_count=payload.get("history_comparison", {}).get("history_count"),
            )
            return api_success(payload, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("history_memory", started, exc, date=date, limit=limit)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("history_memory", started, exc, date=date, limit=limit)
            return _internal_error("历史记忆加载失败", exc, meta={"requested_date": date, "limit": limit})

    @router.post("/report_by_time", response_model=ApiEnvelope[ReportPayload])
    def generate_report_by_time(req: TimeWindowRequest):
        """Generate report by time."""
        start = req.start_time.replace("T", " ")
        end = req.end_time.replace("T", " ")
        date = start.split(" ")[0]
        meta = {
            "date": date,
            "start_time": start,
            "end_time": end,
        }
        started = _debug_start("report.time_window", **meta)

        try:
            _, df_day = load_csv_by_date(date)
            df = load_df_by_time(df_day, start, end)

            if df.empty:
                _debug_log("report.time_window.empty", **meta)
                return api_error(
                    "该时间段无数据。",
                    status_code=404,
                    meta=meta,
                    error_code="EMPTY_TIME_WINDOW",
                )

            result = _run_analysis_with_context(
                analyze_tbm_data,
                df,
                {
                    "date": date,
                    "analysis_mode": "time_window",
                    "time_start": start,
                    "time_end": end,
                    "source_path": str(_resolve_daily_path(date)),
                    "source_name": _resolve_daily_path(date).name,
                    "persist_cst": True,
                },
            )
            prompt = build_prompt_timewindow(
                start_time=start,
                end_time=end,
                seg_text=result["seg_text"],
                stats_text=result["stats_text"],
                state_text=result["state_text"],
                eff_text=result["eff_text"],
                state_stats_text=result["state_stats_text"],
                gas_text=result["gas_text"],
                geo_text=result["geo_text"],
                llm_summary=result["llm_summary"],
            )

            report = call_llm(prompt)
            _debug_success(
                "report.time_window",
                started,
                date=date,
                row_count=len(df),
                warning_count=len(_collect_warnings(result)),
            )
            return api_success(
                {"report": report},
                warnings=_collect_warnings(result),
                meta=meta,
            )
        except FileNotFoundError as exc:
            _debug_failure("report.time_window", started, exc, **meta)
            return api_error(str(exc), status_code=404, meta=meta, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("report.time_window", started, exc, **meta)
            return _internal_error("时间段报告生成失败", exc, meta=meta)

    @router.get("/risk_profile", response_model=ApiEnvelope[RiskProfilePayload])
    def risk_profile_api(date: Optional[str] = None):
        """Handle risk profile api."""
        started = _debug_start("risk_profile", date=date)
        try:
            _, result, warnings, meta, resolved_date = _get_daily_analysis(date)
            payload = {
                "date": resolved_date,
                "risk_profile": build_risk_profile(result["df_geo"]),
                "speed_profile": build_speed_profile(result["df_geo"]),
            }
            _debug_success(
                "risk_profile",
                started,
                date=resolved_date,
                cache_hit=meta.get("cache_hit"),
                speed_profile_count=len(payload["speed_profile"]),
            )
            return api_success(payload, warnings=warnings, meta=meta)
        except FileNotFoundError as exc:
            _debug_failure("risk_profile", started, exc, date=date)
            return api_error(str(exc), status_code=404, error_code="DATA_FILE_NOT_FOUND")
        except Exception as exc:
            _debug_failure("risk_profile", started, exc, date=date)
            return _internal_error("空间风险剖面加载失败", exc, meta={"requested_date": date})

    app.include_router(router)