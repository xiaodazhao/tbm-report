# -*- coding: utf-8 -*-
"""
geology_v2/pipeline.py

把 ceshi.py 中已经跑通的 geology_v2 主流程封装为统一入口。

建议放置位置：
    backend/geology_v2/pipeline.py

核心入口：
    run_geology_v2_context(...)

设计原则：
    1. 不改 parser；
    2. 不改 GRS/GRCI 公式；
    3. 不改 report_renderer 文本口径；
    4. 只封装现有 normalize -> availability -> HSP dedup -> cells -> projection
       -> geo_states -> forward_profile -> report_context 链路。
"""

from __future__ import annotations

import inspect
import json
import math
import pkgutil
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


PIPELINE_VERSION = "geology_v2_pipeline_20260529"


# =============================================================================
# 通用工具
# =============================================================================

def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        x = float(value)
        if not math.isfinite(x):
            return default
        return x
    except Exception:
        return default


def _json_clean(value: Any) -> Any:
    """让 diagnostics / summary 更适合 json 输出。DataFrame 不在这里转换。"""
    if isinstance(value, dict):
        return {str(k): _json_clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_clean(v) for v in value]
    if isinstance(value, tuple):
        return [_json_clean(v) for v in value]
    if isinstance(value, set):
        return [_json_clean(v) for v in sorted(value, key=str)]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        x = float(value)
        return None if not math.isfinite(x) else x
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    return value


def _df_shape(df: Any) -> Optional[Tuple[int, int]]:
    if isinstance(df, pd.DataFrame):
        return tuple(df.shape)
    return None


def _value_counts_dict(series: pd.Series, top_n: Optional[int] = None) -> Dict[str, int]:
    vc = series.dropna().astype(str).value_counts()
    if top_n:
        vc = vc.head(top_n)
    return {str(k): int(v) for k, v in vc.to_dict().items()}


def _extract_data_and_attrs(result: Any) -> Tuple[Any, Dict[str, Any]]:
    """
    兼容函数返回：
    - df
    - (df, attrs)
    - {"data": df, "attrs": attrs}
    """
    if isinstance(result, tuple) and len(result) >= 2:
        data = result[0]
        attrs = result[1] if isinstance(result[1], dict) else {}
        return data, attrs
    if isinstance(result, dict):
        for key in ["data", "df", "result", "normalized_df", "cell_evidence_df", "geo_states_df"]:
            if key in result:
                return result[key], result.get("attrs", result.get("metadata", {})) or {}
    return result, {}


def _resolve_function(
    module_names: Sequence[str],
    function_names: Sequence[str],
    required: bool = True,
) -> Optional[Callable[..., Any]]:
    """
    从若干模块/函数名候选中找到第一个可调用函数。

    优先按候选模块查找；如果没找到，再扫描 geology_v2 包下的子模块。
    这样可以避免因为文件名不同导致 pipeline 找不到已有函数。
    """
    errors: List[str] = []

    # 1. 先按显式候选模块查找
    for module_name in module_names:
        try:
            module = import_module(module_name)
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
            continue

        for fn_name in function_names:
            fn = getattr(module, fn_name, None)
            if callable(fn):
                return fn

    # 2. 候选模块没找到时，扫描 geology_v2 包下所有模块
    try:
        pkg = import_module("geology_v2")
        pkg_path = getattr(pkg, "__path__", None)

        if pkg_path is not None:
            for mod_info in pkgutil.walk_packages(pkg_path, prefix="geology_v2."):
                module_name = mod_info.name
                lowered = module_name.lower()

                # 跳过测试、临时、缓存模块，避免不必要副作用
                if any(skip in lowered for skip in ["test", "tests", "ceshi", "temp", "__pycache__"]):
                    continue

                try:
                    module = import_module(module_name)
                except Exception as exc:
                    errors.append(f"{module_name}: {exc}")
                    continue

                for fn_name in function_names:
                    fn = getattr(module, fn_name, None)
                    if callable(fn):
                        return fn

    except Exception as exc:
        errors.append(f"scan geology_v2 failed: {exc}")

    if required:
        raise RuntimeError(
            "找不到所需函数。\n"
            f"模块候选：{list(module_names)}\n"
            f"函数候选：{list(function_names)}\n"
            f"导入错误：{errors}"
        )

    return None



def _call_with_supported_kwargs(fn: Callable[..., Any], **kwargs) -> Any:
    """根据函数签名，只传入它支持的关键字参数。"""
    sig = inspect.signature(fn)
    params = sig.parameters
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if has_var_kw:
        return fn(**kwargs)
    supported = {k: v for k, v in kwargs.items() if k in params}
    return fn(**supported)


# =============================================================================
# 里程 / cell 工具
# =============================================================================

def _ensure_chainage_column(df_plc: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df_plc is None or len(df_plc) == 0:
        return df_plc

    out = df_plc.copy()
    if "chainage" in out.columns:
        out["chainage"] = pd.to_numeric(out["chainage"], errors="coerce")
        return out

    for col in ["里程", "桩号", "当前里程", "chainage_m", "mileage", "里程数值"]:
        if col in out.columns:
            out["chainage"] = pd.to_numeric(out[col], errors="coerce")
            return out

    return out


def _infer_current_chainage(
    df_plc: Optional[pd.DataFrame],
    current_chainage: Optional[float],
) -> Optional[float]:
    if current_chainage is not None:
        return float(current_chainage)

    df = _ensure_chainage_column(df_plc)
    if df is None or "chainage" not in df.columns:
        return None

    s = pd.to_numeric(df["chainage"], errors="coerce").dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _chainage_values_from_evidence(df: pd.DataFrame) -> List[float]:
    values: List[float] = []
    if df is None or df.empty:
        return values

    for col in [
        "start_chainage",
        "end_chainage",
        "center_chainage",
        "face_chainage",
        "start_num",
        "end_num",
        "face_num",
    ]:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna().tolist()
            values.extend([float(v) for v in vals if math.isfinite(float(v))])
    return values


def _fallback_build_chainage_cells(
    start_chainage: float,
    end_chainage: float,
    cell_length: float = 10.0,
) -> pd.DataFrame:
    """项目内没有 cell builder 时的兜底实现。"""
    if start_chainage > end_chainage:
        start_chainage, end_chainage = end_chainage, start_chainage

    cell_length = float(cell_length or 10.0)
    start = math.floor(float(start_chainage) / cell_length) * cell_length
    end = math.ceil(float(end_chainage) / cell_length) * cell_length

    rows = []
    x = start
    while x < end + 1e-9:
        cell_start = float(x)
        cell_end = float(x + cell_length)
        rows.append(
            {
                "cell_id": f"cell_{int(round(cell_start))}_{int(round(cell_end))}",
                "cell_start": cell_start,
                "cell_end": cell_end,
                "cell_center": (cell_start + cell_end) / 2.0,
                "cell_length": cell_length,
            }
        )
        x += cell_length
    return pd.DataFrame(rows)


def _build_cells_auto(
    normalized_df: pd.DataFrame,
    current_chainage: Optional[float],
    cell_length: float = 10.0,
    extra_min: Optional[float] = None,
    extra_max: Optional[float] = None,
) -> pd.DataFrame:
    values = _chainage_values_from_evidence(normalized_df)
    if current_chainage is not None:
        values.append(float(current_chainage))
    if extra_min is not None:
        values.append(float(extra_min))
    if extra_max is not None:
        values.append(float(extra_max))

    if not values:
        raise ValueError("无法构建 chainage cells：没有可用里程。")

    start = min(values)
    end = max(values)

    fn = _resolve_function(
        [
            "geology_v2.chainage_cells",
            "geology_v2.cells",
            "geology_v2.cell_builder",
            "geology_v2.grid",
        ],
        [
            "build_chainage_cells",
            "build_cells",
            "build_10m_chainage_cells",
            "build_chainage_grid",
        ],
        required=False,
    )

    if fn is None:
        return _fallback_build_chainage_cells(start, end, cell_length=cell_length)

    result = _call_with_supported_kwargs(
        fn,
        df_plc=pd.DataFrame(),
        start_chainage=start,
        end_chainage=end,
        min_chainage=start,
        max_chainage=end,
        chainage_min=start,
        chainage_max=end,
        cell_length=cell_length,
        cell_length_m=cell_length,
        segment_length=cell_length,
        extra_min=start,
        extra_max=end,
    )
    cells_df, _ = _extract_data_and_attrs(result)
    return cells_df


def _focus_by_cell_center(
    df: Optional[pd.DataFrame],
    current_chainage: Optional[float],
    review_back_m: float = 20.0,
    review_forward_m: float = 40.0,
) -> Optional[pd.DataFrame]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    if current_chainage is None or "cell_center" not in df.columns:
        return df

    center = pd.to_numeric(df["cell_center"], errors="coerce")
    lo = float(current_chainage) - float(review_back_m)
    hi = float(current_chainage) + float(review_forward_m)
    out = df[(center >= lo) & (center <= hi)].copy()
    return out if not out.empty else df


# =============================================================================
# summaries
# =============================================================================

def summarize_normalized_evidence(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "evidence_count": 0,
            "source_type_counts": {},
            "spatial_type_counts": {},
            "role_counts": {},
            "anomaly_point_count": 0,
            "parse_warning_count": 0,
        }

    parse_warning_count = 0
    if "parse_warnings" in df.columns:
        for value in df["parse_warnings"].tolist():
            if isinstance(value, list):
                parse_warning_count += int(len(value) > 0)
            elif isinstance(value, str):
                parse_warning_count += int(value.strip() not in {"", "[]", "nan", "None"})

    anomaly_count = 0
    if "spatial_type" in df.columns:
        anomaly_count = int((df["spatial_type"].astype(str) == "anomaly_point").sum())

    return {
        "evidence_count": int(len(df)),
        "source_type_counts": _value_counts_dict(df["source_type_norm"]) if "source_type_norm" in df.columns else {},
        "spatial_type_counts": _value_counts_dict(df["spatial_type"]) if "spatial_type" in df.columns else {},
        "role_counts": _value_counts_dict(df["evidence_role"]) if "evidence_role" in df.columns else {},
        "anomaly_point_count": anomaly_count,
        "parse_warning_count": int(parse_warning_count),
    }


def summarize_geo_states(geo_states_df: pd.DataFrame) -> Dict[str, Any]:
    if geo_states_df is None or geo_states_df.empty:
        return {
            "cell_count": 0,
            "evidence_cell_count": 0,
            "high_attention_cell_count": 0,
        }

    out: Dict[str, Any] = {
        "cell_count": int(len(geo_states_df)),
    }

    if "has_geology_evidence" in geo_states_df.columns:
        out["evidence_cell_count"] = int(geo_states_df["has_geology_evidence"].astype(bool).sum())
    else:
        out["evidence_cell_count"] = int(len(geo_states_df))

    if "GRS_geo_base" in geo_states_df.columns:
        grs = pd.to_numeric(geo_states_df["GRS_geo_base"], errors="coerce").fillna(0)
        out["high_attention_cell_count"] = int((grs >= 0.70).sum())
        out["GRS_geo_base_max"] = float(grs.max())
        out["GRS_geo_base_mean"] = float(grs.mean())
    else:
        out["high_attention_cell_count"] = 0

    if "fused_grade" in geo_states_df.columns:
        out["grade_counts"] = _value_counts_dict(geo_states_df["fused_grade"])

    if "main_hazards" in geo_states_df.columns:
        counter: Dict[str, int] = {}
        for value in geo_states_df["main_hazards"].tolist():
            hazards = value
            if isinstance(value, str):
                try:
                    hazards = json.loads(value)
                except Exception:
                    hazards = [x.strip() for x in value.replace("、", ",").split(",") if x.strip()]
            if not isinstance(hazards, list):
                hazards = []
            for h in hazards:
                counter[str(h)] = counter.get(str(h), 0) + 1
        out["main_hazard_counts"] = dict(sorted(counter.items(), key=lambda kv: kv[1], reverse=True))

    if "conflict_level" in geo_states_df.columns:
        out["conflict_level_counts"] = _value_counts_dict(geo_states_df["conflict_level"])
    if "uncertainty_level" in geo_states_df.columns:
        out["uncertainty_level_counts"] = _value_counts_dict(geo_states_df["uncertainty_level"])

    return _json_clean(out)


# =============================================================================
# main pipeline
# =============================================================================

def run_geology_v2_context(
    df_plc: Optional[pd.DataFrame] = None,
    evidence_df: Optional[pd.DataFrame] = None,
    current_chainage: Optional[float] = None,
    analysis_date: Optional[Any] = None,
    mode: str = "online",
    advance_direction: int = 1,
    lookahead_m: float = 30.0,
    cell_length: float = 10.0,
    review_back_m: float = 20.0,
    review_forward_m: float = 40.0,
    extra_min: Optional[float] = None,
    extra_max: Optional[float] = None,
    response_cell_df: Optional[pd.DataFrame] = None,
    coupled_df: Optional[pd.DataFrame] = None,
    base_context: Optional[Dict[str, Any]] = None,
    build_report: bool = True,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    统一运行 geology_v2 上下文构建流程。
    """
    warnings: List[str] = []
    diagnostics: Dict[str, Any] = {
        "pipeline_version": PIPELINE_VERSION,
        "steps": [],
    }

    if evidence_df is None or len(evidence_df) == 0:
        return {
            "ok": False,
            "message": "evidence_df 为空，无法运行 geology_v2 pipeline。",
            "warnings": ["empty evidence_df"],
            "diagnostics": diagnostics,
        }

    df_plc_work = _ensure_chainage_column(df_plc)
    current_chainage_value = _infer_current_chainage(df_plc_work, current_chainage)
    if current_chainage_value is None:
        return {
            "ok": False,
            "message": "缺少 current_chainage，且无法从 df_plc 推断。",
            "warnings": ["missing current_chainage"],
            "diagnostics": diagnostics,
        }

    # 1. normalize
    normalize_fn = _resolve_function(
        ["geology_v2.evidence_normalizer"],
        [
            "normalize_evidence_df",
            "normalize_evidence",
            "normalize_evidence_records",
            "build_normalized_evidence_df",
        ],
        required=True,
    )
    normalized_result = _call_with_supported_kwargs(
        normalize_fn,
        evidence_df=evidence_df,
        df=evidence_df,
        raw_evidence_df=evidence_df,
    )
    normalized_df_all, normalize_attrs = _extract_data_and_attrs(normalized_result)
    if normalized_df_all is None or len(normalized_df_all) == 0:
        return {
            "ok": False,
            "message": "evidence 标准化结果为空。",
            "warnings": ["empty normalized_df_all"],
            "diagnostics": diagnostics,
        }
    diagnostics["steps"].append(
        {
            "name": "normalize",
            "shape": _df_shape(normalized_df_all),
            "summary": summarize_normalized_evidence(normalized_df_all),
            "attrs": _json_clean(normalize_attrs),
        }
    )

    # 2. availability filter
    filter_fn = _resolve_function(
        [
            "geology_v2.evidence_normalizer",
            "geology_v2.evidence_availability",
            "geology_v2.availability",
            "geology_v2.evidence_filter",
        ],
        ["filter_available_evidence"],
        required=True,
    )
    filtered_result = _call_with_supported_kwargs(
        filter_fn,
        normalized_df=normalized_df_all,
        evidence_df=normalized_df_all,
        current_chainage=current_chainage_value,
        analysis_date=analysis_date,
        mode=mode,
        advance_direction=advance_direction,
        chainage_tolerance_m=1.0,
    )
    normalized_df, availability_attrs = _extract_data_and_attrs(filtered_result)
    if normalized_df is None:
        normalized_df = pd.DataFrame()
    diagnostics["steps"].append(
        {
            "name": "availability_filter",
            "shape": _df_shape(normalized_df),
            "summary": summarize_normalized_evidence(normalized_df),
            "attrs": _json_clean(availability_attrs),
        }
    )

    # 2.x HSP anomaly_point dedup
    dedup_attrs: Dict[str, Any] = {}
    dedup_fn = _resolve_function(
        ["geology_v2.evidence_dedup"],
        ["deduplicate_hsp_anomaly_points"],
        required=False,
    )
    if dedup_fn is not None and not normalized_df.empty:
        dedup_result = _call_with_supported_kwargs(
            dedup_fn,
            normalized_df=normalized_df,
            df=normalized_df,
            chainage_tol_m=0.5,
            face_tol_m=1.0,
        )
        normalized_df, dedup_attrs = _extract_data_and_attrs(dedup_result)
        if normalized_df is None:
            normalized_df = pd.DataFrame()
        diagnostics["steps"].append(
            {
                "name": "hsp_anomaly_point_dedup",
                "shape": _df_shape(normalized_df),
                "summary": summarize_normalized_evidence(normalized_df),
                "attrs": _json_clean(dedup_attrs),
            }
        )
    else:
        diagnostics["steps"].append(
            {
                "name": "hsp_anomaly_point_dedup",
                "skipped": True,
                "reason": "deduplicate_hsp_anomaly_points not found or normalized_df empty",
            }
        )

    # 3. cells
    cells_df = _build_cells_auto(
        normalized_df=normalized_df,
        current_chainage=current_chainage_value,
        cell_length=cell_length,
        extra_min=extra_min,
        extra_max=extra_max,
    )
    diagnostics["steps"].append(
        {
            "name": "build_cells",
            "shape": _df_shape(cells_df),
            "cell_count": int(len(cells_df)) if isinstance(cells_df, pd.DataFrame) else 0,
        }
    )

    # 4. projection
    project_fn = _resolve_function(
        [
            "geology_v2.evidence_projector",
            "geology_v2.evidence_projection",
            "geology_v2.projection",
            "geology_v2.cell_projection",
        ],
        [
            "project_evidence_to_cells",
            "project_to_cells",
            "build_cell_evidence",
            "project_evidence",
        ],
        required=True,
    )
    projection_result = _call_with_supported_kwargs(
        project_fn,
        normalized_df=normalized_df,
        normalized_evidence_df=normalized_df,
        evidence_df=normalized_df,
        cells_df=cells_df,
        cell_df=cells_df,
        current_chainage=current_chainage_value,
        advance_direction=advance_direction,
    )
    cell_evidence_df, projection_attrs = _extract_data_and_attrs(projection_result)
    if cell_evidence_df is None:
        cell_evidence_df = pd.DataFrame()
    diagnostics["steps"].append(
        {
            "name": "project_evidence_to_cells",
            "shape": _df_shape(cell_evidence_df),
            "attrs": _json_clean(projection_attrs),
        }
    )

    # 5. geo states
    fusion_fn = _resolve_function(
        [
            "geology_v2.fusion_engine",
            "geology_v2.geo_fusion",
            "geology_v2.cell_fusion",
        ],
        [
            "build_geo_states",
            "fuse_geo_states",
            "fuse_cells",
            "build_cell_geo_states",
            "build_geo_states_df",
        ],
        required=True,
    )
    fusion_result = _call_with_supported_kwargs(
        fusion_fn,
        cells_df=cells_df,
        cell_df=cells_df,
        cell_evidence_df=cell_evidence_df,
        evidence_df=normalized_df,
        normalized_evidence_df=normalized_df,
        normalized_df=normalized_df,
    )
    geo_states_df, fusion_attrs = _extract_data_and_attrs(fusion_result)
    if geo_states_df is None:
        geo_states_df = pd.DataFrame()
    diagnostics["steps"].append(
        {
            "name": "build_geo_states",
            "shape": _df_shape(geo_states_df),
            "summary": summarize_geo_states(geo_states_df),
            "attrs": _json_clean(fusion_attrs),
        }
    )

    # 6. forward profile
    forward_profile = None
    forward_summary: Dict[str, Any] = {}
    forward_fn = _resolve_function(
        [
            "geology_v2.forward_profile",
            "geology_v2.forward",
            "geology_v2.forward_context",
        ],
        [
            "build_forward_profile",
            "generate_forward_profile",
            "build_forward_attention_profile",
            "build_forward_geology_profile",
        ],
        required=False,
    )
    if forward_fn is not None:
        forward_result = _call_with_supported_kwargs(
            forward_fn,
            geo_states_df=geo_states_df,
            cell_evidence_df=cell_evidence_df,
            normalized_df=normalized_df,
            cells_df=cells_df,
            current_chainage=current_chainage_value,
            lookahead_m=lookahead_m,
            step_m=cell_length,
            advance_direction=advance_direction,
            cell_length=cell_length,
        )
        forward_profile, forward_attrs = _extract_data_and_attrs(forward_result)
        if isinstance(forward_profile, dict):
            forward_summary = forward_profile.get("summary", forward_profile.get("forward_profile_summary", {})) or {}
        elif isinstance(forward_profile, pd.DataFrame):
            forward_summary = {"profile_count": int(len(forward_profile))}
        elif isinstance(forward_attrs, dict):
            forward_summary = forward_attrs
        diagnostics["steps"].append(
            {
                "name": "build_forward_profile",
                "type": type(forward_profile).__name__,
                "summary": _json_clean(forward_summary),
                "attrs": _json_clean(forward_attrs if "forward_attrs" in locals() else {}),
            }
        )
    else:
        warnings.append("forward_profile builder not found; forward_text may be unavailable")
        diagnostics["steps"].append(
            {"name": "build_forward_profile", "skipped": True, "reason": "builder not found"}
        )

    # 7. coupling 可选：如果外部传入 coupled_df 就直接使用；如果没有，且传入 response_cell_df，则尝试计算
    coupling_summary: Dict[str, Any] = {}
    if coupled_df is None and response_cell_df is not None:
        coupling_fn = _resolve_function(
            [
                "geology_v2.coupling_adapter",
                "geology_v2.response_coupling",
                "geology_v2.grci",
            ],
            [
                "run_geology_response_coupling",
                "build_coupled_context",
                "compute_coupled_cells",
                "build_coupling_context",
                "compute_grci",
            ],
            required=False,
        )
        if coupling_fn is not None:
            try:
                coupling_result = _call_with_supported_kwargs(
                    coupling_fn,
                    geo_states_df=geo_states_df,
                    response_cell_df=response_cell_df,
                    cell_response_df=response_cell_df,
                    cells_df=cells_df,
                    current_chainage=current_chainage_value,
                )
                coupled_df, coupling_attrs = _extract_data_and_attrs(coupling_result)
                if isinstance(coupling_attrs, dict):
                    coupling_summary.update(coupling_attrs)
            except Exception as exc:
                warnings.append(f"coupling computation failed: {exc}")
                coupled_df = None

    if isinstance(coupled_df, pd.DataFrame) and not coupled_df.empty:
        if "GRCI" in coupled_df.columns:
            grci = pd.to_numeric(coupled_df["GRCI"], errors="coerce").fillna(0)
            coupling_summary.update(
                {
                    "cell_count": int(len(coupled_df)),
                    "computed_grci_cell_count": int((grci > 0).sum()),
                    "GRCI_max": float(grci.max()),
                    "GRCI_mean": float(grci.mean()),
                }
            )
        if "coupling_level" in coupled_df.columns:
            coupling_summary["coupling_level_counts"] = _value_counts_dict(coupled_df["coupling_level"])
        if "coupling_type" in coupled_df.columns:
            coupling_summary["coupling_type_counts"] = _value_counts_dict(coupled_df["coupling_type"])

    diagnostics["steps"].append(
        {
            "name": "coupling",
            "shape": _df_shape(coupled_df),
            "summary": _json_clean(coupling_summary),
        }
    )

    # 8. report_context + render
    report_context = None
    rendered_report_text = ""
    texts: Dict[str, str] = {}
    focus_geo_states_df = _focus_by_cell_center(
        geo_states_df,
        current_chainage=current_chainage_value,
        review_back_m=review_back_m,
        review_forward_m=review_forward_m,
    )
    focus_coupled_df = _focus_by_cell_center(
        coupled_df,
        current_chainage=current_chainage_value,
        review_back_m=review_back_m,
        review_forward_m=review_forward_m,
    )

    if build_report:
        context_fn = _resolve_function(
            [
                "geology_v2.report_context_builder",
                "geology_v2.report_context",
                "geology_v2.context_builder",
            ],
            [
                "build_report_context",
                "build_geology_v2_report_context",
                "build_context",
            ],
            required=False,
        )
        if context_fn is not None:
            context_result = _call_with_supported_kwargs(
                context_fn,
                geo_states_df=focus_geo_states_df,
                all_geo_states_df=geo_states_df,
                forward_profile=forward_profile,
                forward_profile_summary=forward_summary,
                coupled_df=focus_coupled_df,
                all_coupled_df=coupled_df,
                normalized_df=normalized_df,
                cell_evidence_df=cell_evidence_df,
                cells_df=cells_df,
                all_normalized_df=normalized_df,
                all_cell_evidence_df=cell_evidence_df,
                current_chainage=current_chainage_value,
                analysis_date=analysis_date,
                report_date=analysis_date,
                review_back_m=review_back_m,
                review_forward_m=review_forward_m,
                base_context=base_context or {},
                operation_context={"text": "pipeline 阶段暂未接入真实基础工况上下文。"},
                gas_context={"text": "pipeline 阶段暂未接入真实气体监测上下文。"},
                face_context={
                    "has_face_evidence": True,
                    "text": "pipeline 阶段使用地质融合结果作为掌子面上下文占位，正式接入时可替换为掌子面素描解析结果。",
                },
                chainage_min=current_chainage_value - review_back_m,
                chainage_max=current_chainage_value + review_forward_m,
                include_data_preview=True,
                metadata={
                    "pipeline_version": PIPELINE_VERSION,
                    "current_chainage": current_chainage_value,
                    "mode": mode,
                    "lookahead_m": lookahead_m,
                },
            )
            report_context, report_attrs = _extract_data_and_attrs(context_result)
            if not isinstance(report_context, dict):
                report_context = {"ok": True, "texts": {}, "raw_context": report_context}
            texts = report_context.get("texts", {}) or {}
            diagnostics["steps"].append(
                {
                    "name": "build_report_context",
                    "ok": bool(isinstance(report_context, dict)),
                    "attrs": _json_clean(report_attrs if "report_attrs" in locals() else {}),
                }
            )
        else:
            warnings.append("report_context_builder not found")
            report_context = {"ok": False, "texts": {}, "warnings": ["report_context_builder not found"]}

        render_fn = _resolve_function(
            ["geology_v2.report_renderer", "geology_v2.renderer"],
            [
                "render_report_context",
                "render_geology_v2_report_context",
                "render_report_text",
                "render_context",
            ],
            required=False,
        )
        if render_fn is not None and report_context is not None:
            try:
                render_result = _call_with_supported_kwargs(
                    render_fn,
                    report_context=report_context,
                    context=report_context,
                    include_operation=True,
                    include_gas=True,
                )
                rendered_report_text = str(render_result or "")
                if rendered_report_text:
                    texts["rendered_report_text"] = rendered_report_text
            except Exception as exc:
                warnings.append(f"render_report_context failed: {exc}")

    data_summary = {
        "normalized_summary": summarize_normalized_evidence(normalized_df),
        "geo_states_summary": summarize_geo_states(geo_states_df),
        "forward_profile_summary": _json_clean(forward_summary),
        "coupled_summary": _json_clean(coupling_summary),
    }

    return {
        "ok": True,
        "version": PIPELINE_VERSION,
        "current_chainage": current_chainage_value,
        "mode": mode,
        "analysis_date": analysis_date,
        "normalized_df_all": normalized_df_all,
        "normalized_df": normalized_df,
        "cells_df": cells_df,
        "cell_evidence_df": cell_evidence_df,
        "geo_states_df": geo_states_df,
        "focus_geo_states_df": focus_geo_states_df,
        "forward_profile": forward_profile,
        "coupled_df": coupled_df,
        "focus_coupled_df": focus_coupled_df,
        "report_context": report_context,
        "rendered_report_text": rendered_report_text,
        "texts": texts,
        "data_summary": _json_clean(data_summary),
        "diagnostics": _json_clean(diagnostics),
        "warnings": warnings,
    }


def geology_v2_prompt_block(result: Dict[str, Any]) -> str:
    """从 pipeline 返回结果中取 prompt_block。"""
    if not result:
        return ""

    texts = result.get("texts") or {}
    if texts.get("prompt_block"):
        return str(texts["prompt_block"])

    context = result.get("report_context") or {}
    if isinstance(context, dict):
        ctx_texts = context.get("texts") or {}
        if ctx_texts.get("prompt_block"):
            return str(ctx_texts["prompt_block"])

    parts = []
    for key in ["geo_brief_text", "forward_text", "coupling_text"]:
        value = texts.get(key)
        if value:
            parts.append(str(value))
    return "\n\n".join(parts)


def print_pipeline_debug_summary(result: Dict[str, Any]) -> None:
    """方便 ceshi.py 或临时脚本打印 pipeline 摘要。"""
    print("=" * 80)
    print("geology_v2 pipeline summary")
    print("=" * 80)
    print("ok:", result.get("ok"))
    print("version:", result.get("version"))
    print("current_chainage:", result.get("current_chainage"))
    print("warnings:", result.get("warnings"))

    for key in [
        "normalized_df_all",
        "normalized_df",
        "cells_df",
        "cell_evidence_df",
        "geo_states_df",
        "focus_geo_states_df",
        "coupled_df",
        "focus_coupled_df",
    ]:
        value = result.get(key)
        if isinstance(value, pd.DataFrame):
            print(f"{key}: shape={value.shape}")
        else:
            print(f"{key}: {type(value).__name__}")

    print("\ndata_summary:")
    print(json.dumps(result.get("data_summary", {}), ensure_ascii=False, indent=2))

    texts = result.get("texts") or {}
    print("\ntexts keys:", list(texts.keys()))
    for key in ["geo_brief_text", "forward_text", "coupling_text", "prompt_block"]:
        if texts.get(key):
            print(f"\n=== {key} preview ===")
            print(str(texts[key])[:1000])
