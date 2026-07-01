from __future__ import annotations

import pandas as pd


def topk_jaccard(
    frame: pd.DataFrame,
    *,
    baseline_col: str,
    variant_cols: list[str],
    keys: list[int] = [10, 20, 50],
    id_col: str = "global_cell_key",
) -> pd.DataFrame:
    rows = []
    baseline = _ranked_ids(frame, baseline_col, id_col)
    for variant_col in variant_cols:
        variant = _ranked_ids(frame, variant_col, id_col)
        for k in keys:
            base_set = set(baseline[:k])
            var_set = set(variant[:k])
            union = base_set | var_set
            intersection = base_set & var_set
            rows.append(
                {
                    "variant": _variant_name(variant_col),
                    "k": k,
                    "baseline_topk_count": len(base_set),
                    "variant_topk_count": len(var_set),
                    "overlap_count": len(intersection),
                    "jaccard": len(intersection) / len(union) if union else None,
                    "overlap_ids": ";".join(sorted(intersection)),
                }
            )
    return pd.DataFrame(rows)


def spearman_rank_correlation(
    frame: pd.DataFrame,
    *,
    baseline_col: str,
    variant_cols: list[str],
) -> pd.DataFrame:
    rows = []
    baseline = pd.to_numeric(frame.get(baseline_col), errors="coerce")
    for variant_col in variant_cols:
        variant = pd.to_numeric(frame.get(variant_col), errors="coerce")
        valid = baseline.notna() & variant.notna()
        corr = baseline[valid].corr(variant[valid], method="spearman") if valid.sum() > 1 else None
        rows.append(
            {
                "variant": _variant_name(variant_col),
                "common_cell_count": int(valid.sum()),
                "spearman_correlation": float(corr) if corr is not None and pd.notna(corr) else None,
            }
        )
    return pd.DataFrame(rows)


def high_attention_date_overlap(
    frame: pd.DataFrame,
    *,
    baseline_col: str,
    variant_cols: list[str],
    top_n_dates: int = 10,
) -> pd.DataFrame:
    rows = []
    baseline_dates = _top_dates(frame, baseline_col, top_n_dates)
    for variant_col in variant_cols:
        variant_dates = _top_dates(frame, variant_col, top_n_dates)
        base_set = set(baseline_dates)
        var_set = set(variant_dates)
        union = base_set | var_set
        intersection = base_set & var_set
        rows.append(
            {
                "variant": _variant_name(variant_col),
                "top_n_dates": top_n_dates,
                "baseline_dates": ";".join(baseline_dates),
                "variant_dates": ";".join(variant_dates),
                "overlap_count": len(intersection),
                "jaccard": len(intersection) / len(union) if union else None,
            }
        )
    return pd.DataFrame(rows)


def compare_top_cells(
    frame: pd.DataFrame,
    *,
    variant_cols: list[str],
    top_n: int = 50,
    id_col: str = "global_cell_key",
) -> pd.DataFrame:
    rows = []
    for variant_col in variant_cols:
        ranked = frame.dropna(subset=[variant_col]).sort_values(variant_col, ascending=False).head(top_n)
        for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
            rows.append(
                {
                    "variant": _variant_name(variant_col),
                    "rank": rank,
                    "date": row.get("date"),
                    "cell_id": row.get("cell_id"),
                    "global_cell_key": row.get(id_col),
                    "cell_role": row.get("cell_role"),
                    "RAI": row.get("RAI"),
                    "GRS_geo_base": row.get("GRS_geo_base"),
                    "V0_current_GRCI": row.get("V0_current_GRCI"),
                    "variant_GRCI": row.get(variant_col),
                    "main_hazards": row.get("main_hazards"),
                }
            )
    return pd.DataFrame(rows)


def _ranked_ids(frame: pd.DataFrame, value_col: str, id_col: str) -> list[str]:
    if value_col not in frame.columns:
        return []
    work = frame[[id_col, value_col]].dropna(subset=[value_col]).copy()
    return work.sort_values(value_col, ascending=False)[id_col].astype(str).tolist()


def _top_dates(frame: pd.DataFrame, value_col: str, top_n: int) -> list[str]:
    if value_col not in frame.columns:
        return []
    work = frame.dropna(subset=[value_col]).groupby("date", as_index=False)[value_col].max()
    return work.sort_values(value_col, ascending=False).head(top_n)["date"].astype(str).tolist()


def _variant_name(column: str) -> str:
    return column.removesuffix("_GRCI")
