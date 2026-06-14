from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.batch_io import resolve_output_dir, safe_float, write_csv, write_json


DEFAULT_WEIGHTS = {"grs_weight": 0.55, "rai_weight": 0.35, "interaction_weight": 0.10}
BUILTIN_SCHEMES = {
    "default": DEFAULT_WEIGHTS,
    "default_plus_10_percent": {"grs_weight": 0.605, "rai_weight": 0.315, "interaction_weight": 0.080},
    "default_minus_10_percent": {"grs_weight": 0.495, "rai_weight": 0.385, "interaction_weight": 0.120},
    "default_plus_20_percent": {"grs_weight": 0.660, "rai_weight": 0.280, "interaction_weight": 0.060},
    "default_minus_20_percent": {"grs_weight": 0.440, "rai_weight": 0.420, "interaction_weight": 0.140},
    "GRS-dominant": {"grs_weight": 0.70, "rai_weight": 0.20, "interaction_weight": 0.10},
    "RAI-dominant": {"grs_weight": 0.35, "rai_weight": 0.55, "interaction_weight": 0.10},
    "interaction-dominant": {"grs_weight": 0.45, "rai_weight": 0.25, "interaction_weight": 0.30},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze GRCI heuristic weight sensitivity from exported cells.")
    parser.add_argument("--input-dir", default="outputs/pipeline_exports")
    parser.add_argument("--input-csv", help="Optional direct construction_state_cells.csv file.")
    parser.add_argument("--out-dir", default="outputs/analysis/weight_sensitivity")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--weights-json", help="Optional custom scheme JSON file.")
    args = parser.parse_args()

    payload = analyze_grci_weight_sensitivity(
        input_dir=_backend_path(args.input_dir),
        input_csv=_backend_path(args.input_csv) if args.input_csv else None,
        out_dir=resolve_output_dir(args.out_dir),
        top_k=args.top_k,
        custom_weights_path=_backend_path(args.weights_json) if args.weights_json else None,
    )
    print(payload["summary"])


def analyze_grci_weight_sensitivity(
    *,
    input_dir: Path,
    out_dir: Path,
    top_k: int = 5,
    input_csv: Path | None = None,
    custom_weights_path: Path | None = None,
) -> dict[str, Any]:
    schemes = _schemes(custom_weights_path)
    source_rows = _load_cells(input_dir=input_dir, input_csv=input_csv)
    eligible = _eligible_cells(source_rows)

    cell_rows: list[dict[str, Any]] = []
    for row in eligible:
        for scheme, weights in schemes.items():
            new_grci = _compute_grci(row, weights)
            cell_rows.append(
                {
                    **row,
                    "scheme": scheme,
                    "original_GRCI": safe_float(row.get("GRCI")),
                    "recomputed_GRCI": new_grci,
                    "grs_weight": weights["grs_weight"],
                    "rai_weight": weights["rai_weight"],
                    "interaction_weight": weights["interaction_weight"],
                }
            )

    cell_rows = _add_ranks(cell_rows)
    summary_rows = _summary_rows(cell_rows)
    stability_rows = _topk_stability(cell_rows, top_k=top_k)
    summary = {
        "input_cell_count": len(source_rows),
        "eligible_cell_count": len(eligible),
        "scheme_count": len(schemes),
        "top_k": top_k,
        "mean_topk_overlap_vs_default": _mean([safe_float(row.get("topk_overlap_ratio")) for row in stability_rows if row.get("scheme") != "default"]),
        "note": "This is heuristic sensitivity analysis, not disaster prediction accuracy.",
    }

    write_csv(out_dir / "grci_weight_sensitivity_cells.csv", cell_rows)
    write_csv(out_dir / "grci_weight_sensitivity_summary.csv", summary_rows)
    write_json(out_dir / "grci_weight_sensitivity_summary.json", {"summary": summary, "schemes": schemes, "rows": summary_rows})
    write_csv(out_dir / "grci_topk_stability.csv", stability_rows)
    return {"summary": summary, "rows": cell_rows, "stability": stability_rows}


def _load_cells(*, input_dir: Path, input_csv: Path | None) -> list[dict[str, Any]]:
    paths = [input_csv] if input_csv else sorted(input_dir.glob("*/construction_state_cells.csv"))
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path is None or not path.exists():
            continue
        frame = pd.read_csv(path)
        date = path.parent.name
        for item in frame.to_dict(orient="records"):
            item["date"] = str(item.get("date") or date)
            rows.append(item)
    return rows


def _eligible_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if str(row.get("cell_role")) != "daily_review":
            continue
        if str(row.get("is_forward_cell")).lower() in {"true", "1", "yes"}:
            continue
        grs = safe_float(row.get("GRS_geo_base"))
        rai = safe_float(row.get("RAI"))
        if grs is None or rai is None:
            continue
        if row.get("GRCI_available") not in {True, "True", "true", "1", 1} and safe_float(row.get("GRCI")) is None:
            continue
        out.append(row)
    return out


def _compute_grci(row: dict[str, Any], weights: dict[str, float]) -> float | None:
    grs = safe_float(row.get("GRS_geo_base"))
    rai = safe_float(row.get("RAI"))
    if grs is None or rai is None:
        return None
    w = _normalize_weights(weights)
    return max(0.0, min(1.0, w["grs_weight"] * grs + w["rai_weight"] * rai + w["interaction_weight"] * grs * rai))


def _add_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return rows
    frame["recomputed_rank"] = frame.groupby(["date", "scheme"])["recomputed_GRCI"].rank(method="dense", ascending=False)
    return frame.to_dict(orient="records")


def _summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    out = []
    for (date, scheme), part in frame.groupby(["date", "scheme"]):
        values = pd.to_numeric(part["recomputed_GRCI"], errors="coerce")
        out.append(
            {
                "date": date,
                "scheme": scheme,
                "cell_count": int(len(part)),
                "high_cell_count": int((values >= 0.75).sum()),
                "medium_cell_count": int(((values >= 0.50) & (values < 0.75)).sum()),
                "low_cell_count": int(((values >= 0.25) & (values < 0.50)).sum()),
                "mean_recomputed_GRCI": float(values.mean()) if not values.empty else None,
                "max_recomputed_GRCI": float(values.max()) if not values.empty else None,
            }
        )
    return out


def _topk_stability(rows: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    out = []
    for date, date_part in frame.groupby("date"):
        default = date_part[date_part["scheme"] == "default"].copy()
        if default.empty:
            continue
        default_ranked = default.sort_values("recomputed_GRCI", ascending=False)
        default_top = set(default_ranked.head(top_k)["cell_id"].astype(str).tolist())
        default_scores = default.set_index("cell_id")["recomputed_GRCI"]
        for scheme, part in date_part.groupby("scheme"):
            ranked = part.sort_values("recomputed_GRCI", ascending=False)
            top = set(ranked.head(top_k)["cell_id"].astype(str).tolist())
            joined = pd.DataFrame({"default": default_scores, "scheme": part.set_index("cell_id")["recomputed_GRCI"]}).dropna()
            out.append(
                {
                    "date": date,
                    "scheme": scheme,
                    "top_k": top_k,
                    "topk_overlap_ratio": len(default_top & top) / max(len(default_top), 1),
                    "rank_correlation_vs_default": float(joined["default"].corr(joined["scheme"], method="spearman")) if len(joined) >= 2 else None,
                    "default_top_cells": sorted(default_top),
                    "scheme_top_cells": sorted(top),
                }
            )
    return out


def _schemes(custom_path: Path | None) -> dict[str, dict[str, float]]:
    schemes = {name: _normalize_weights(weights) for name, weights in BUILTIN_SCHEMES.items()}
    if custom_path and custom_path.exists():
        payload = json.loads(custom_path.read_text(encoding="utf-8"))
        for name, weights in payload.items():
            if isinstance(weights, dict):
                schemes[str(name)] = _normalize_weights(weights)
    return schemes


def _normalize_weights(weights: dict[str, Any]) -> dict[str, float]:
    raw = {
        "grs_weight": max(float(weights.get("grs_weight", 0.0) or 0.0), 0.0),
        "rai_weight": max(float(weights.get("rai_weight", 0.0) or 0.0), 0.0),
        "interaction_weight": max(float(weights.get("interaction_weight", 0.0) or 0.0), 0.0),
    }
    total = sum(raw.values()) or 1.0
    return {key: value / total for key, value in raw.items()}


def _mean(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    return float(sum(cleaned) / len(cleaned)) if cleaned else None


def _backend_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


if __name__ == "__main__":
    main()
