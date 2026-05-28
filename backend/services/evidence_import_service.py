from __future__ import annotations

import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from config import EVIDENCE_DB_PATH, HSP_DIR, SKETCH_DIR, TSP_DIR
from parsers.hsp_parser import parse_hsp_pdf
from parsers.sketch_parser import parse_sketch_pdf
from parsers.tsp_parser import parse_tsp_pdf
from schemas.schemas import EvidenceRecord
from services.sqlite_storage_service import sync_evidence_dataframe_to_db


ParserFunc = Callable[[Path], list[EvidenceRecord]]

SOURCE_ALIASES = {
    "tsp": "tsp",
    "hsp": "sonic",
    "sonic": "sonic",
    "sketch": "sketch",
}

PARSERS: dict[str, ParserFunc] = {
    "tsp": parse_tsp_pdf,
    "sonic": parse_hsp_pdf,
    "sketch": parse_sketch_pdf,
}

SOURCE_DIRS = {
    "tsp": TSP_DIR,
    "sonic": HSP_DIR,
    "sketch": SKETCH_DIR,
}


def canonical_source_type(source_type: str | None) -> str | None:
    """Return the parser source key used by the evidence database."""
    if source_type is None:
        return None
    key = str(source_type).strip().lower()
    if not key:
        return None
    if key not in SOURCE_ALIASES:
        allowed = ", ".join(sorted(SOURCE_ALIASES))
        raise ValueError(f"Unsupported source_type={source_type!r}; expected one of: {allowed}")
    return SOURCE_ALIASES[key]


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Internal helper for is relative to."""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def infer_source_type(pdf_path: Path, source_type: str | None = None) -> str:
    """
    Infer which parser should handle a PDF.

    Explicit source_type wins. Otherwise the function checks whether the PDF is
    under the configured TSP/HSP/SKETCH folders, then falls back to simple
    filename/folder keywords.
    """
    explicit = canonical_source_type(source_type)
    if explicit:
        return explicit

    for key, source_dir in SOURCE_DIRS.items():
        if _is_relative_to(pdf_path, source_dir):
            return key

    haystack = f"{pdf_path.parent.name} {pdf_path.stem}".lower()
    if "tsp" in haystack:
        return "tsp"
    if "hsp" in haystack or "sonic" in haystack:
        return "sonic"
    if "sketch" in haystack:
        return "sketch"

    raise ValueError(
        f"Cannot infer source_type for {pdf_path}. "
        "Pass source_type='tsp', 'hsp'/'sonic', or 'sketch'."
    )


def collect_pdf_paths(paths: list[str | Path], recursive: bool = False) -> list[Path]:
    """Expand files/directories into a sorted unique list of PDF paths."""
    pdf_paths: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if path.is_dir():
            pattern = "**/*.pdf" if recursive else "*.pdf"
            pdf_paths.extend(sorted(path.glob(pattern)))
        elif path.is_file():
            if path.suffix.lower() != ".pdf":
                raise ValueError(f"Only PDF files can be imported: {path}")
            pdf_paths.append(path)
        else:
            raise ValueError(f"Unsupported import path: {path}")

    seen = set()
    out: list[Path] = []
    for pdf_path in pdf_paths:
        key = str(pdf_path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(pdf_path)
    return out


def records_to_dataframe(records: list[EvidenceRecord]) -> pd.DataFrame:
    """Convert parsed EvidenceRecord objects into the evidence_db CSV schema."""
    return pd.DataFrame([asdict(record) for record in records])


def clean_evidence_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the same safety checks needed for incremental and full evidence DB writes.

    The cleaner preserves point evidence, drops rows without usable mileage,
    removes duplicate evidence_id values, and limits segment records to plausible
    section lengths.
    """
    if df.empty:
        return df

    required_cols = ["evidence_id", "start_num", "end_num"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Evidence records are missing required columns: {missing_cols}")

    df = df.drop_duplicates(subset=["evidence_id"], keep="last").copy()
    df["start_num"] = pd.to_numeric(df["start_num"], errors="coerce")
    df["end_num"] = pd.to_numeric(df["end_num"], errors="coerce")
    df = df.dropna(subset=["start_num", "end_num"]).copy()
    df = df[df["start_num"] <= df["end_num"]].copy()

    if "source_level" in df.columns:
        source_level = df["source_level"].astype(str).str.strip()
        seg_mask = source_level == "segment"
        seg_df = df[seg_mask].copy()
        other_df = df[~seg_mask].copy()
        if not seg_df.empty:
            seg_len = seg_df["end_num"] - seg_df["start_num"]
            seg_df = seg_df[(seg_len >= 0) & (seg_len <= 300)].copy()
        df = pd.concat([seg_df, other_df], ignore_index=True)
    else:
        seg_len = df["end_num"] - df["start_num"]
        df = df[(seg_len >= 0) & (seg_len <= 300)].copy()

    sort_cols = [col for col in ["source_type", "report_id", "start_num", "end_num"] if col in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)
    return df


def parse_evidence_pdf(pdf_path: Path, source_type: str | None = None) -> tuple[str, list[EvidenceRecord]]:
    """Parse one evidence PDF with the matching TSP/HSP/sketch parser."""
    source = infer_source_type(pdf_path, source_type)
    parser = PARSERS[source]
    return source, parser(pdf_path)


def import_evidence_files(
    paths: list[str | Path],
    source_type: str | None = None,
    evidence_db_path: str | Path = EVIDENCE_DB_PATH,
    dry_run: bool = False,
    replace_existing: bool = False,
    recursive: bool = False,
) -> dict:
    """
    Incrementally parse new forecast PDFs and append them to evidence_db.csv.

    This avoids reparsing all historical PDFs. Duplicate evidence_id values are
    skipped by default; set replace_existing=True to refresh existing rows from
    the newly parsed PDF. A backup CSV is created before every write.
    """
    evidence_db_path = Path(evidence_db_path)
    pdf_paths = collect_pdf_paths(paths, recursive=recursive)

    parsed_records: list[EvidenceRecord] = []
    file_results = []
    errors = []

    for pdf_path in pdf_paths:
        try:
            source, records = parse_evidence_pdf(pdf_path, source_type=source_type)
            parsed_records.extend(records)
            file_results.append({
                "path": str(pdf_path),
                "source_type": source,
                "record_count": len(records),
                "status": "ok" if records else "empty",
            })
        except Exception as exc:
            errors.append({"path": str(pdf_path), "error": str(exc)})
            file_results.append({
                "path": str(pdf_path),
                "source_type": source_type,
                "record_count": 0,
                "status": "failed",
                "error": str(exc),
            })

    new_df = clean_evidence_dataframe(records_to_dataframe(parsed_records)) if parsed_records else pd.DataFrame()

    if evidence_db_path.exists():
        existing_df = pd.read_csv(evidence_db_path)
        existing_df = clean_evidence_dataframe(existing_df)
    else:
        existing_df = pd.DataFrame()

    total_before = len(existing_df)
    new_ids = set(new_df["evidence_id"].astype(str)) if not new_df.empty else set()
    existing_ids = set(existing_df["evidence_id"].astype(str)) if not existing_df.empty else set()

    if replace_existing and new_ids and not existing_df.empty:
        replaced_mask = existing_df["evidence_id"].astype(str).isin(new_ids)
        replaced_count = int(replaced_mask.sum())
        append_df = new_df
        frames = [frame for frame in [existing_df[~replaced_mask], append_df] if not frame.empty]
        combined_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        skipped_existing_ids: list[str] = []
    else:
        replaced_count = 0
        if not new_df.empty and existing_ids:
            duplicate_mask = new_df["evidence_id"].astype(str).isin(existing_ids)
            skipped_existing_ids = new_df.loc[duplicate_mask, "evidence_id"].astype(str).tolist()
            append_df = new_df[~duplicate_mask].copy()
        else:
            skipped_existing_ids = []
            append_df = new_df
        frames = [frame for frame in [existing_df, append_df] if not frame.empty]
        combined_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    combined_df = clean_evidence_dataframe(combined_df) if not combined_df.empty else combined_df
    inserted_count = len(append_df)
    total_after = len(combined_df)

    backup_path = None
    written = False
    if not dry_run and (inserted_count > 0 or replaced_count > 0):
        evidence_db_path.parent.mkdir(parents=True, exist_ok=True)
        if evidence_db_path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = evidence_db_path.with_name(f"{evidence_db_path.stem}.bak_{stamp}{evidence_db_path.suffix}")
            shutil.copy2(evidence_db_path, backup_path)
        combined_df.to_csv(evidence_db_path, index=False, encoding="utf-8-sig")
        sync_evidence_dataframe_to_db(combined_df)
        written = True

    return {
        "ok": len(errors) == 0,
        "dry_run": dry_run,
        "written": written,
        "evidence_db_path": str(evidence_db_path),
        "backup_path": str(backup_path) if backup_path else None,
        "pdf_count": len(pdf_paths),
        "parsed_record_count": len(parsed_records),
        "clean_record_count": len(new_df),
        "inserted_count": inserted_count,
        "replaced_count": replaced_count,
        "skipped_existing_count": len(skipped_existing_ids),
        "skipped_existing_ids": skipped_existing_ids,
        "total_before": total_before,
        "total_after": total_after,
        "file_results": file_results,
        "errors": errors,
    }