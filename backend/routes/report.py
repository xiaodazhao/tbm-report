from __future__ import annotations

from fastapi import FastAPI

from pipeline.daily_report_pipeline import run_daily_report_pipeline
from schemas.api import DailyReportRequest
from utils.io_utils import get_all_csv_paths


def register_report_routes(app: FastAPI) -> None:
    """Register the slim daily-report API surface."""

    @app.get("/api/tbm/health")
    def health() -> dict:
        return {
            "ok": True,
            "service": "tbm-daily-report-backend",
            "pipeline": "run_daily_report_pipeline",
        }

    @app.get("/api/tbm/dates")
    def list_dates() -> dict:
        dates = []
        for path in get_all_csv_paths():
            raw = path.name.replace("tbm_data_", "").replace(".csv", "")
            if len(raw) == 8:
                dates.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
        dates.sort(reverse=True)
        return {"dates": dates}

    @app.post("/api/tbm/report")
    def build_report(request: DailyReportRequest) -> dict:
        result = run_daily_report_pipeline(
            request.date,
            use_llm=request.use_llm,
            generation_mode=request.generation_mode,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            mock_llm=request.mock_llm,
            enable_revision=request.enable_revision,
            enable_planner=request.enable_planner,
            planner_provider=request.planner_provider,
            planner_model=request.planner_model,
        )
        return {
            "date": result.date,
            "report_text": result.report_text,
            "quality_summary": result.quality_summary,
            "trace_summary": result.trace_summary,
            "forward_profile": result.forward_profile,
            "high_grci_cells": result.high_grci_cells,
            "generation_mode": result.generation_mode,
            "llm_summary": (result.llm_generation or {}).get("summary", {}),
            "warnings": result.warnings,
        }

    @app.post("/api/tbm/report/debug")
    def build_report_debug(request: DailyReportRequest) -> dict:
        result = run_daily_report_pipeline(
            request.date,
            use_llm=request.use_llm,
            generation_mode=request.generation_mode,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            mock_llm=request.mock_llm,
            enable_revision=request.enable_revision,
            enable_planner=request.enable_planner,
            planner_provider=request.planner_provider,
            planner_model=request.planner_model,
        )
        return {
            "date": result.date,
            "operation_summary": result.operation_summary,
            "cluster_summary": result.cluster_summary,
            "gas_summary": result.gas_summary,
            "normalized_evidence_summary": result.normalized_evidence_summary,
            "construction_state_cells": [
                cell.model_dump() for cell in result.construction_state_cells
            ],
            "prompt_evidence_pack": result.prompt_evidence_pack,
            "prompt_text": result.prompt_text,
            "report_text": result.report_text,
            "quality": result.quality,
            "quality_summary": result.quality_summary,
            "trace": result.trace,
            "trace_summary": result.trace_summary,
            "forward_profile": result.forward_profile,
            "high_grci_cells": result.high_grci_cells,
            "generation_mode": result.generation_mode,
            "llm_generation": result.llm_generation,
            "warnings": result.warnings,
        }
