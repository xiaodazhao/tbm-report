from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from geology_text.geology_extraction_writer import write_extraction_outputs  # noqa: E402
from geology_text.llm_geology_extractor import RawTextChunk, extract_from_chunks  # noqa: E402


SUPPORTED_FILE_SUFFIXES = {".txt", ".md", ".docx", ".csv", ".xlsx"}
SAMPLE_TEXT = (
    "DyK1014+545~DyK1014+645 section: surrounding rock is mainly grade III. "
    "\u5c40\u90e8\u56f4\u5ca9\u6781\u7834\u788e\uff0c\u88c2\u9699\u5bc6\u96c6\uff0c"
    "\u5b58\u5728\u6389\u5757\u73b0\u8c61\uff0c\u6c34\u5e73\u58f0\u6ce2\u5256\u9762"
    "\u663e\u793a\u660e\u663e\u53cd\u5c04\u5f02\u5e38\u3002"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Side-channel LLM geology text extraction into candidate evidence.")
    parser.add_argument("--input-file")
    parser.add_argument("--input-dir")
    parser.add_argument("--source-list")
    parser.add_argument("--source-type", default="auto")
    parser.add_argument("--text-column", default="raw_text")
    parser.add_argument("--provider", default="mock", help="mock, openai_or_compatible, or disabled.")
    parser.add_argument("--model")
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--allow-external-llm", action="store_true")
    parser.add_argument("--out-dir", default="outputs/geology_extraction")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    args = parser.parse_args()

    out_dir = _resolve_backend_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks, load_errors = collect_chunks(
        input_file=args.input_file,
        input_dir=args.input_dir,
        source_list=args.source_list,
        source_type=args.source_type,
        text_column=args.text_column,
        out_dir=out_dir,
        max_files=args.max_files,
    )
    result = extract_from_chunks(
        chunks,
        provider_name=args.provider,
        model=args.model,
        mock_llm=bool(args.mock_llm or args.provider == "mock"),
        allow_external_llm=args.allow_external_llm,
    )
    if load_errors:
        result["errors"] = list(result.get("errors", [])) + load_errors
        summary = dict(result.get("summary") or {})
        summary["failed_file_count"] = int(summary.get("failed_file_count") or 0) + len(load_errors)
        summary["error_message"] = "; ".join(
            [str(summary.get("error_message") or "")] + [str(item.get("error_message")) for item in load_errors]
        ).strip("; ")
        result["summary"] = summary
    paths = write_extraction_outputs(out_dir, result)
    print(json.dumps({"summary": result.get("summary", {}), "outputs": paths}, ensure_ascii=False, indent=2))


def collect_chunks(
    *,
    input_file: str | None,
    input_dir: str | None,
    source_list: str | None,
    source_type: str,
    text_column: str,
    out_dir: Path,
    max_files: int | None = None,
) -> tuple[list[RawTextChunk], list[dict[str, Any]]]:
    chunks: list[RawTextChunk] = []
    errors: list[dict[str, Any]] = []
    if input_file:
        path = _resolve_backend_path(input_file)
        if path.exists():
            chunk, error = _chunk_from_path(path, source_type=source_type)
            if chunk:
                chunks.append(chunk)
            if error:
                errors.append(error)
        else:
            sample = out_dir / "sample_geology_text.txt"
            sample.write_text(SAMPLE_TEXT, encoding="utf-8")
            chunk, error = _chunk_from_path(sample, source_type=source_type if source_type != "auto" else "HSP")
            if chunk:
                chunks.append(chunk)
            errors.append({"source_id": str(path), "error_message": f"input file not found; used sample text: {sample}"})
            if error:
                errors.append(error)
    if input_dir:
        root = _resolve_backend_path(input_dir)
        if root.exists():
            for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_FILE_SUFFIXES):
                if max_files is not None and len(chunks) >= max_files:
                    break
                chunk, error = _chunk_from_path(path, source_type=source_type)
                if chunk:
                    chunks.append(chunk)
                if error:
                    errors.append(error)
        else:
            errors.append({"source_id": str(root), "error_message": "input directory not found"})
    if source_list:
        rows, row_errors = _chunks_from_source_list(_resolve_backend_path(source_list), source_type=source_type, text_column=text_column)
        chunks.extend(rows[: max_files or None])
        errors.extend(row_errors)
    if not chunks:
        sample = out_dir / "sample_geology_text.txt"
        sample.write_text(SAMPLE_TEXT, encoding="utf-8")
        chunk, error = _chunk_from_path(sample, source_type="HSP")
        if chunk:
            chunks.append(chunk)
        if error:
            errors.append(error)
    return chunks, errors


def _chunk_from_path(path: Path, *, source_type: str) -> tuple[RawTextChunk | None, dict[str, Any] | None]:
    try:
        text = _read_text_file(path)
        if not text.strip():
            return None, {"source_id": str(path), "error_message": "empty text"}
        return (
            RawTextChunk(
                source_id=path.stem,
                text=text,
                source_type=_infer_source_type(path, source_type),
                file_name=path.name,
                file_path=str(path),
            ),
            None,
        )
    except Exception as exc:
        return None, {"source_id": str(path), "error_message": str(exc)}


def _chunks_from_source_list(path: Path, *, source_type: str, text_column: str) -> tuple[list[RawTextChunk], list[dict[str, Any]]]:
    if not path.exists():
        return [], [{"source_id": str(path), "error_message": "source list not found"}]
    try:
        frame = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    except Exception as exc:
        return [], [{"source_id": str(path), "error_message": f"read source list failed: {exc}"}]
    chunks: list[RawTextChunk] = []
    errors: list[dict[str, Any]] = []
    path_col = _first_existing(frame, ["source_path", "file_path", "path"])
    source_id_col = _first_existing(frame, ["source_id", "report_id", "evidence_id"])
    for index, row in frame.iterrows():
        source_id = str(row.get(source_id_col) if source_id_col else f"{path.stem}_{index}")
        row_source_type = source_type if source_type != "auto" else str(row.get("source_type", "unknown"))
        text = str(row.get(text_column) or "").strip() if text_column in frame.columns else ""
        if not text and path_col and row.get(path_col):
            file_path = _resolve_backend_path(str(row.get(path_col)))
            chunk, error = _chunk_from_path(file_path, source_type=row_source_type)
            if chunk:
                chunk.source_id = source_id
                chunks.append(chunk)
            if error:
                errors.append(error)
            continue
        if text:
            chunks.append(
                RawTextChunk(
                    source_id=source_id,
                    text=text,
                    source_type=row_source_type,
                    file_name=str(row.get(path_col) or path.name),
                    file_path=str(row.get(path_col)) if path_col and row.get(path_col) else str(path),
                    page_or_section=f"row:{index}",
                )
            )
        else:
            errors.append({"source_id": source_id, "error_message": f"missing text column: {text_column}"})
    return chunks, errors


def _read_text_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".csv":
        frame = pd.read_csv(path)
        return _frame_to_text(frame)
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
        return _frame_to_text(frame)
    if suffix == ".pdf":
        raise RuntimeError("PDF OCR/text extraction is not implemented in P3; convert it to text first.")
    raise RuntimeError(f"unsupported input file suffix: {suffix}")


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as docx:
        xml = docx.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = [node.text or "" for node in root.findall(".//w:t", namespace)]
    return "\n".join(texts)


def _frame_to_text(frame: pd.DataFrame) -> str:
    columns = [column for column in ["raw_text", "source_text", "original_text", "original_text_span", "description", "conclusion"] if column in frame.columns]
    if columns:
        return "\n".join(str(value) for column in columns for value in frame[column].dropna().tolist())
    return "\n".join(",".join(str(value) for value in row) for row in frame.fillna("").astype(str).values.tolist())


def _infer_source_type(path: Path, source_type: str) -> str:
    if source_type and source_type != "auto":
        return source_type
    name = path.name.lower()
    if "tsp" in name:
        return "TSP"
    if "hsp" in name or "sonic" in name:
        return "HSP"
    if "sketch" in name or "face" in name:
        return "sketch"
    return "unknown"


def _first_existing(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(col).lower(): str(col) for col in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def _resolve_backend_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


if __name__ == "__main__":
    main()

