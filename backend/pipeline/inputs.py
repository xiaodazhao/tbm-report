from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from config import CONFIG_WARNINGS, EVIDENCE_DB_PATH
from utils.io_utils import load_csv_by_date, load_latest_csv


@dataclass
class DailyInputs:
    date: str | None
    plc_path: Path
    df_plc: pd.DataFrame
    evidence_path: Path
    evidence_df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def load_daily_inputs(date: str | None) -> DailyInputs:
    """Load the PLC daily CSV and the multi-source geology evidence table."""
    warnings: list[str] = list(CONFIG_WARNINGS)
    plc_path, df_plc = load_csv_by_date(date) if date else load_latest_csv()
    loaded_date = date or _date_from_tbm_filename(plc_path.name)

    evidence_path = Path(EVIDENCE_DB_PATH)
    if evidence_path.exists():
        evidence_df = pd.read_csv(evidence_path)
    else:
        evidence_df = pd.DataFrame()
        warnings.append(f"evidence table not found: {evidence_path}")

    return DailyInputs(
        date=loaded_date,
        plc_path=Path(plc_path),
        df_plc=df_plc,
        evidence_path=evidence_path,
        evidence_df=evidence_df,
        warnings=warnings,
    )


def _date_from_tbm_filename(name: str) -> str | None:
    try:
        raw = name.replace("tbm_data_", "").replace(".csv", "")
        return pd.to_datetime(raw, format="%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return None


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy values into API-safe Python data."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return [json_safe(item) for item in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return json_safe(value.to_dict())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    return value
