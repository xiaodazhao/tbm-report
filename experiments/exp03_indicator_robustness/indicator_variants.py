from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from weighting_methods import critic_weights, entropy_weights, equal_weights, weighted_mean


RAI_COMPONENTS = [
    "stop_ratio",
    "abnormal_ratio",
    "speed_drop_score",
    "torque_volatility_score",
    "speed_volatility_score",
]

GRS_COMPONENTS = [
    "grade_score_component",
    "hazard_component",
    "confidence_component",
]

VARIANT_NAMES = [
    "V0_current",
    "V1_percentile_equal",
    "V2_percentile_interaction",
    "V3_percentile_entropy",
    "V4_percentile_critic",
    "V5_strict_min",
]


@dataclass(frozen=True)
class VariantResult:
    cells: pd.DataFrame
    summary: pd.DataFrame
    warnings: list[str]


def compute_indicator_variants(cells: pd.DataFrame) -> VariantResult:
    """Compute sidecar RAI/GRS/GRCI variants without mutating pipeline outputs."""
    if cells.empty:
        return VariantResult(cells=cells.copy(), summary=pd.DataFrame(), warnings=["input_cells_empty"])

    out = cells.copy()
    warnings: list[str] = []
    out["eligible_for_grci_variant"] = _eligible_for_grci(out)

    for column in RAI_COMPONENTS + GRS_COMPONENTS + ["RAI", "GRS_geo_base", "GRCI"]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    for column in RAI_COMPONENTS:
        out[f"{column}_pct"] = _percentile_series(out[column]) if column in out.columns else np.nan
    for column in GRS_COMPONENTS:
        out[f"{column}_pct"] = _percentile_series(out[column]) if column in out.columns else np.nan

    rai_pct_cols = [f"{column}_pct" for column in RAI_COMPONENTS]
    grs_pct_cols = [f"{column}_pct" for column in GRS_COMPONENTS]
    out["coupling_confidence"] = _coupling_confidence(out)

    # V0: keep existing project formula results.
    out["V0_current_RAI"] = out.get("RAI")
    out["V0_current_GRS"] = out.get("GRS_geo_base")
    out["V0_current_GRCI"] = out.get("GRCI").where(out["eligible_for_grci_variant"])

    # V1: percentile-normalized components with equal weights and simple GRS/RAI mean coupling.
    out["V1_percentile_equal_RAI"] = weighted_mean(out, equal_weights(rai_pct_cols))
    out["V1_percentile_equal_GRS"] = weighted_mean(out, equal_weights(grs_pct_cols))
    out["V1_percentile_equal_GRCI"] = (
        0.5 * out["V1_percentile_equal_RAI"] + 0.5 * out["V1_percentile_equal_GRS"]
    ).where(out["eligible_for_grci_variant"])

    # V2: percentile indicators and interaction-style coupling.
    out["V2_percentile_interaction_RAI"] = out["V1_percentile_equal_RAI"]
    out["V2_percentile_interaction_GRS"] = out["V1_percentile_equal_GRS"]
    out["V2_percentile_interaction_GRCI"] = _interaction_grci(
        out["V2_percentile_interaction_RAI"],
        out["V2_percentile_interaction_GRS"],
        out["coupling_confidence"],
    ).where(out["eligible_for_grci_variant"])

    # V3: entropy-weighted RAI and GRS components.
    rai_entropy = entropy_weights(out, rai_pct_cols)
    grs_entropy = entropy_weights(out, grs_pct_cols)
    out["V3_percentile_entropy_RAI"] = weighted_mean(out, rai_entropy)
    out["V3_percentile_entropy_GRS"] = weighted_mean(out, grs_entropy)
    out["V3_percentile_entropy_GRCI"] = _interaction_grci(
        out["V3_percentile_entropy_RAI"],
        out["V3_percentile_entropy_GRS"],
        out["coupling_confidence"],
    ).where(out["eligible_for_grci_variant"])

    # V4: CRITIC-weighted RAI and GRS components.
    rai_critic = critic_weights(out, rai_pct_cols)
    grs_critic = critic_weights(out, grs_pct_cols)
    out["V4_percentile_critic_RAI"] = weighted_mean(out, rai_critic)
    out["V4_percentile_critic_GRS"] = weighted_mean(out, grs_critic)
    out["V4_percentile_critic_GRCI"] = _interaction_grci(
        out["V4_percentile_critic_RAI"],
        out["V4_percentile_critic_GRS"],
        out["coupling_confidence"],
    ).where(out["eligible_for_grci_variant"])

    # V5: strict coupling; high value only when both response and geology attention are high.
    out["V5_strict_min_RAI"] = out["V1_percentile_equal_RAI"]
    out["V5_strict_min_GRS"] = out["V1_percentile_equal_GRS"]
    out["V5_strict_min_GRCI"] = (
        pd.concat([out["V5_strict_min_RAI"], out["V5_strict_min_GRS"]], axis=1).min(axis=1)
        * out["coupling_confidence"]
    ).where(out["eligible_for_grci_variant"])

    for variant in VARIANT_NAMES:
        for metric in ["RAI", "GRS", "GRCI"]:
            column = f"{variant}_{metric}"
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce").clip(0.0, 1.0).round(6)

    if out[GRS_COMPONENTS].notna().sum().sum() == 0:
        warnings.append("grs_components_missing_all_variants_use_existing_grs_only")
    if out[RAI_COMPONENTS].notna().sum().sum() == 0:
        warnings.append("rai_components_missing_all_percentile_variants_unavailable")

    summary = _variant_summary(out, rai_entropy, grs_entropy, rai_critic, grs_critic)
    return VariantResult(cells=out, summary=summary, warnings=warnings)


def _eligible_for_grci(frame: pd.DataFrame) -> pd.Series:
    role = frame.get("cell_role", pd.Series("", index=frame.index)).astype(str)
    return (
        role.eq("daily_review")
        & frame.get("is_excavated_today", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
        & frame.get("has_plc_response", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
        & frame.get("has_geology_evidence", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
        & pd.to_numeric(frame.get("RAI"), errors="coerce").notna()
        & pd.to_numeric(frame.get("GRS_geo_base"), errors="coerce").notna()
    )


def _percentile_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() <= 1:
        return numeric.where(numeric.notna(), np.nan)
    return numeric.rank(pct=True, method="average").clip(0.0, 1.0)


def _coupling_confidence(frame: pd.DataFrame) -> pd.Series:
    candidates = []
    for column in [
        "max_overlap_ratio",
        "evidence_overlap_ratio",
        "trace_completeness",
        "source_reliability",
        "evidence_confidence",
    ]:
        if column in frame.columns:
            candidates.append(pd.to_numeric(frame[column], errors="coerce").clip(0.0, 1.0))
    if not candidates:
        return pd.Series(1.0, index=frame.index)
    combined = pd.concat(candidates, axis=1).mean(axis=1, skipna=True)
    return combined.fillna(1.0).clip(0.0, 1.0)


def _interaction_grci(rai: pd.Series, grs: pd.Series, confidence: pd.Series) -> pd.Series:
    product = pd.to_numeric(rai, errors="coerce") * pd.to_numeric(grs, errors="coerce")
    return product.clip(lower=0.0).map(lambda value: math.sqrt(value) if pd.notna(value) else np.nan) * confidence


def _variant_summary(
    frame: pd.DataFrame,
    rai_entropy: dict[str, float],
    grs_entropy: dict[str, float],
    rai_critic: dict[str, float],
    grs_critic: dict[str, float],
) -> pd.DataFrame:
    rows = []
    weight_lookup = {
        "V0_current": {"RAI": "pipeline_formula", "GRS": "pipeline_formula", "GRCI": "pipeline_formula"},
        "V1_percentile_equal": {
            "RAI": equal_weights([f"{column}_pct" for column in RAI_COMPONENTS]),
            "GRS": equal_weights([f"{column}_pct" for column in GRS_COMPONENTS]),
            "GRCI": "0.5*RAI+0.5*GRS",
        },
        "V2_percentile_interaction": {"RAI": "V1", "GRS": "V1", "GRCI": "sqrt(RAI*GRS)*C"},
        "V3_percentile_entropy": {"RAI": rai_entropy, "GRS": grs_entropy, "GRCI": "sqrt(RAI*GRS)*C"},
        "V4_percentile_critic": {"RAI": rai_critic, "GRS": grs_critic, "GRCI": "sqrt(RAI*GRS)*C"},
        "V5_strict_min": {"RAI": "V1", "GRS": "V1", "GRCI": "min(RAI,GRS)*C"},
    }
    for variant in VARIANT_NAMES:
        grci_col = f"{variant}_GRCI"
        values = pd.to_numeric(frame.get(grci_col), errors="coerce")
        rows.append(
            {
                "variant": variant,
                "available_cell_count": int(values.notna().sum()),
                "mean_grci": float(values.mean()) if values.notna().any() else None,
                "max_grci": float(values.max()) if values.notna().any() else None,
                "formula_or_method": str(weight_lookup.get(variant)),
                "uses_forward_attention_grci": False,
            }
        )
    return pd.DataFrame(rows)
