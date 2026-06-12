from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

import pandas as pd

from agent.common import fail, ok
from services.twin_query_service import get_twin_events
from services.history_memory_service import (
    build_history_comparison,
    build_history_record,
    load_history_records,
)
from utils.io_utils import get_all_csv_paths, load_csv_by_date, load_latest_csv
from utils.serialization import serialize_for_json


class TBMTools:
    """Structured tool layer over the existing TBM analysis pipeline."""

    def __init__(
        self,
        analyze_tbm_data: Callable[[pd.DataFrame], dict[str, Any]],
        build_risk_profile: Callable[[pd.DataFrame], dict[str, Any]],
        build_speed_profile: Callable[[pd.DataFrame], list[dict[str, Any]]],
    ):
        """Internal helper for init."""
        self.analyze_tbm_data = analyze_tbm_data
        self.build_risk_profile = build_risk_profile
        self.build_speed_profile = build_speed_profile
        self._analysis_cache: dict[str, dict[str, Any]] = {}

    def clear_cache(self) -> None:
        """Clear cache."""
        self._analysis_cache.clear()

    def _run_analysis(self, df: pd.DataFrame, context: dict[str, Any]) -> dict[str, Any]:
        """Run analysis with CST context while tolerating one-arg test doubles."""
        try:
            return self.analyze_tbm_data(df, context=context)
        except TypeError as exc:
            if "context" not in str(exc):
                raise
            return self.analyze_tbm_data(df)

    def list_dates(self) -> dict[str, Any]:
        """Handle list dates."""
        dates = []
        for path in get_all_csv_paths():
            try:
                raw = path.name.replace("tbm_data_", "").replace(".csv", "")
                dates.append(datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d"))
            except Exception:
                continue
        dates.sort(reverse=True)
        return ok(
            {"dates": dates},
            "Found available TBM dates.",
            tool="list_dates",
            count=len(dates),
        )

    def load_day(self, date: Optional[str] = None) -> dict[str, Any]:
        """Load day."""
        try:
            path, df = load_csv_by_date(date) if date else load_latest_csv()
            loaded_date = date or self._date_from_path(path.name)
            return ok(
                {
                    "date": loaded_date,
                    "path": str(path),
                    "rows": int(len(df)),
                    "columns": list(df.columns),
                },
                "Loaded TBM day data.",
                tool="load_day",
            )
        except Exception as exc:
            return fail(str(exc), tool="load_day", date=date)

    def analyze_day(self, date: Optional[str] = None) -> dict[str, Any]:
        """Analyze day."""
        try:
            path, df = load_csv_by_date(date) if date else load_latest_csv()
            loaded_date = date or self._date_from_path(path.name)
            result = self._run_analysis(
                df,
                {
                    "date": loaded_date,
                    "analysis_mode": "daily",
                    "source_path": str(path),
                    "source_name": path.name,
                    "persist_cst": True,
                },
            )
            return ok(
                self._summarize_analysis(loaded_date, path, df, result),
                "Analyzed TBM day data.",
                tool="analyze_day",
                date=loaded_date,
            )
        except Exception as exc:
            return fail(str(exc), tool="analyze_day", date=date)

    def analyze_operation(self, date: Optional[str] = None) -> dict[str, Any]:
        """Analyze operation."""
        analysis = self._analysis_or_error(date, "analyze_operation")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        stats = result.get("stats", {})
        state_stats = result.get("state_stats", {})
        state_labels = result.get("state_labels", {})
        return ok(
            {
                "date": analysis["data"]["date"],
                "stats": serialize_for_json(stats),
                "state_stats": serialize_for_json(state_stats),
                "state_labels": serialize_for_json(state_labels),
                "valid_samples": result.get("llm_summary", {}).get(
                    "éˆå¤‹æ™¥é˜èˆµâ‚¬ä½¹ç‰±éˆî„æšŸ",
                    0,
                ),
            },
            "Analyzed operation states.",
            tool="analyze_operation",
        )

    def analyze_gas(self, date: Optional[str] = None) -> dict[str, Any]:
        """Analyze gas."""
        analysis = self._analysis_or_error(date, "analyze_gas")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        gas_stats = result.get("gas_stats", {})
        exceed_types = []
        for gas, stat in gas_stats.get("all", {}).items():
            if isinstance(stat, dict) and stat.get("exceed_event_count", 0) > 0:
                exceed_types.append(gas)

        return ok(
            {
                "date": analysis["data"]["date"],
                "gas_stats": serialize_for_json(gas_stats),
                "exceed_types": exceed_types,
            },
            "Analyzed gas safety statistics.",
            tool="analyze_gas",
        )

    def analyze_geology(self, date: Optional[str] = None) -> dict[str, Any]:
        """Analyze geology."""
        analysis = self._analysis_or_error(date, "analyze_geology")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        segment_df = result.get("segment_df", pd.DataFrame())
        typical_df = result.get("typical_segments_df", pd.DataFrame())
        return ok(
            {
                "date": analysis["data"]["date"],
                "record_summary": serialize_for_json(result.get("geo_summary_record", {})),
                "segment_summary": serialize_for_json(result.get("geo_summary_segment", {})),
                "coupling_summary": serialize_for_json(result.get("coupling_summary", {})),
                "coupling_validation": serialize_for_json(result.get("coupling_validation", {})),
                "coupling_output_paths": serialize_for_json(result.get("coupling_output_paths", {})),
                "high_attention_segments": serialize_for_json(
                    result.get("high_attention_segments", [])
                ),
                "top_segments": serialize_for_json(
                    typical_df.head(10).to_dict(orient="records")
                    if not typical_df.empty
                    else []
                ),
                "segment_count": int(len(segment_df)),
            },
            "Analyzed geology and coupling risk.",
            tool="analyze_geology",
        )

    def analyze_forward_risk(self, date: Optional[str] = None) -> dict[str, Any]:
        """Analyze forward risk."""
        analysis = self._analysis_or_error(date, "analyze_forward_risk")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        forward_summary = result.get("forward_risk_summary", {}) or {}
        return ok(
            {
                "date": analysis["data"]["date"],
                "forward_risk": serialize_for_json(forward_summary),
                "forward_attention": serialize_for_json(forward_summary),
                "forward_attention_level": forward_summary.get("forward_advice_level", forward_summary.get("advice_level")),
                "high_attention_count": forward_summary.get("forward_high_source_risk_evidence_count", forward_summary.get("high_risk_count", 0)),
                "high_source_risk_evidence_count": forward_summary.get("forward_high_source_risk_evidence_count", forward_summary.get("high_risk_count", 0)),
                "forward_risk_text": result.get("forward_risk_text", ""),
                "semantics_note": "这里的关注等级表示证据融合关注程度，不等同于灾害发生概率。",
            },
            "Analyzed forward attention hints.",
            tool="analyze_forward_risk",
        )

    def get_digital_twin_state(self, date: Optional[str] = None) -> dict[str, Any]:
        """Get digital twin state."""
        analysis = self._analysis_or_error(date, "get_digital_twin_state")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        cst_state = result.get("cst_state", {}) or {}
        twin_state = result.get("twin_state", {}) or cst_state
        return ok(
            {
                "date": analysis["data"]["date"],
                "digital_twin_state": serialize_for_json(result.get("digital_twin_state", {})),
                "twin_state": serialize_for_json(twin_state),
                "events": serialize_for_json(cst_state.get("events", []) if isinstance(cst_state, dict) else []),
                "diff_from_previous": serialize_for_json(cst_state.get("diff_from_previous", {}) if isinstance(cst_state, dict) else {}),
                "summary": {
                    "event_count": len(cst_state.get("events", []) or []) if isinstance(cst_state, dict) else 0,
                    "confidence": (cst_state.get("provenance_state", {}) or {}).get("state_confidence") if isinstance(cst_state, dict) else None,
                    "face_chainage": (cst_state.get("spatial_reference", {}) or {}).get("face_chainage") if isinstance(cst_state, dict) else None,
                    "forward_level": (cst_state.get("forward_state", {}) or {}).get("forward_advice_level") if isinstance(cst_state, dict) else None,
                },
                "twin_state_summary": {
                    "ok": bool((twin_state or {}).get("ok")) if isinstance(twin_state, dict) else False,
                    "warning_count": len((twin_state or {}).get("warnings", []) or []) if isinstance(twin_state, dict) else 0,
                },
                "report_quality_summary": serialize_for_json(result.get("report_quality", {})),
            },
            "Built digital twin state.",
            tool="get_digital_twin_state",
        )

    def compare_history(self, date: Optional[str] = None, limit: int = 10) -> dict[str, Any]:
        """Compare history."""
        analysis = self._analysis_or_error(date, "compare_history")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        current_date = analysis["data"]["date"]
        current_record = build_history_record(current_date, result)
        history_records = load_history_records(limit=limit, before_date=current_date)
        comparison = build_history_comparison(current_record, history_records)
        return ok(
            {
                "date": current_date,
                "current_record": serialize_for_json(current_record),
                "history_comparison": serialize_for_json(comparison),
            },
            "Compared current day with history memory.",
            tool="compare_history",
            history_count=len(history_records),
        )

    def risk_profile(self, date: Optional[str] = None) -> dict[str, Any]:
        """Handle risk profile."""
        analysis = self._analysis_or_error(date, "risk_profile")
        if not analysis["success"]:
            return analysis

        result = analysis["metadata"]["raw_result"]
        df_geo = result.get("df_geo", pd.DataFrame())
        return ok(
            {
                "date": analysis["data"]["date"],
                "risk_profile": self.build_risk_profile(df_geo),
                "speed_profile": self.build_speed_profile(df_geo),
            },
            "Built risk and speed profiles.",
            tool="risk_profile",
        )

    def _analysis_or_error(self, date: Optional[str], tool_name: str) -> dict[str, Any]:
        """Internal helper for analysis or error."""
        try:
            path, df = load_csv_by_date(date) if date else load_latest_csv()
            loaded_date = date or self._date_from_path(path.name)
            cache_key = loaded_date or str(path)
            cached = self._analysis_cache.get(cache_key)
            if cached is None:
                result = self._run_analysis(
                    df,
                    {
                        "date": loaded_date,
                        "analysis_mode": "daily",
                        "source_path": str(path),
                        "source_name": path.name,
                        "persist_cst": True,
                    },
                )
                data = self._summarize_analysis(loaded_date, path, df, result)
                cached = {"result": result, "data": data}
                self._analysis_cache[cache_key] = cached
            result = cached["result"]
            data = cached["data"]
            return ok(
                data,
                "Analysis ready.",
                tool=tool_name,
                date=loaded_date,
                raw_result=result,
            )
        except Exception as exc:
            return fail(str(exc), tool=tool_name, date=date)

    @staticmethod
    def _date_from_path(name: str) -> Optional[str]:
        """Internal helper for date from path."""
        try:
            raw = name.replace("tbm_data_", "").replace(".csv", "")
            return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            return None

    @staticmethod
    def _summarize_analysis(
        date: Optional[str],
        path: Any,
        df: pd.DataFrame,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Summarize analysis."""
        stats = result.get("stats", {})
        twin = result.get("digital_twin_state", {})
        geo = result.get("geo_summary_segment", {})
        coupling = result.get("coupling_summary", {})
        forward = result.get("forward_risk_summary", {})
        return serialize_for_json(
            {
                "date": date,
                "path": str(path),
                "rows": int(len(df)),
                "operation": {
                    "work_total_min": stats.get("work_total_min", 0),
                    "stop_total_min": stats.get("stop_total_min", 0),
                    "transition_total_min": stats.get("transition_total_min", 0),
                    "abnormal_total_min": stats.get("abnormal_total_min", 0),
                    "work_count": stats.get("work_count", 0),
                    "stop_count": stats.get("stop_count", 0),
                    "abnormal_count": stats.get("abnormal_count", 0),
                },
                "geology": {
                    "has_geology": geo.get("has_geology", False),
                    "high_geo_attention_segment_count": geo.get("high_geo_attention_segment_count", geo.get("high_risk_segment_count", 0)),
                    "multi_report_source_segment_count": geo.get("multi_report_source_segment_count", geo.get("multi_source_segment_count", 0)),
                    "high_attention_count": geo.get("high_geo_attention_segment_count", geo.get("high_risk_segment_count", 0)),
                },
                "forward_risk": {
                    "has_forward_risk": forward.get("has_forward_risk", False),
                    "forward_advice_level": forward.get("forward_advice_level", forward.get("advice_level")),
                    "forward_high_source_risk_evidence_count": forward.get("forward_high_source_risk_evidence_count", forward.get("high_risk_count", 0)),
                    "forward_main_hazard_tags": forward.get("forward_main_hazard_tags", forward.get("main_hazards", [])),
                },
                "forward_attention": {
                    "has_forward_attention": forward.get("has_forward_risk", False),
                    "forward_attention_level": forward.get("forward_advice_level", forward.get("advice_level")),
                    "high_attention_count": forward.get("forward_high_source_risk_evidence_count", forward.get("high_risk_count", 0)),
                    "forward_main_hazard_tags": forward.get("forward_main_hazard_tags", forward.get("main_hazards", [])),
                    "semantics_note": "关注等级表示证据融合关注程度，不等同于灾害发生概率。",
                },
                "coupling": {
                    "has_coupling": coupling.get("has_coupling", False),
                    "summary_text": coupling.get("summary_text"),
                    "level_counts": coupling.get("level_counts", {}),
                },
                "digital_twin_state": twin,
                "twin_state": result.get("twin_state", result.get("cst_state", {})),
                "twin_event_count": len((result.get("cst_state", {}) or {}).get("events", []) or []),
                "twin_state_summary": {
                    "ok": bool((result.get("twin_state", {}) or {}).get("ok")) if isinstance(result.get("twin_state", {}), dict) else False,
                    "warning_count": len(((result.get("twin_state", {}) or {}).get("warnings", []) or [])) if isinstance(result.get("twin_state", {}), dict) else 0,
                },
                "report_quality_summary": result.get("report_quality", {}),
            }
        )
