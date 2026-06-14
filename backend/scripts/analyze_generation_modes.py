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

from scripts.batch_io import resolve_output_dir, safe_float, safe_int, write_csv, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare exported report generation modes.")
    parser.add_argument("--mode-dir", action="append", default=[], help="Mode directory as name=path. Can be repeated.")
    parser.add_argument("--out-dir", default="outputs/analysis/generation_modes")
    args = parser.parse_args()
    if not args.mode_dir:
        raise SystemExit("Provide at least one --mode-dir name=path.")
    payload = analyze_generation_modes(mode_dirs=_parse_mode_dirs(args.mode_dir), out_dir=resolve_output_dir(args.out_dir))
    print(payload["summary"])


def analyze_generation_modes(*, mode_dirs: dict[str, Path], out_dir: Path) -> dict[str, Any]:
    dates = sorted({date.name for path in mode_dirs.values() if path.exists() for date in path.iterdir() if date.is_dir()})
    rows: list[dict[str, Any]] = []
    for date in dates:
        for mode, root in mode_dirs.items():
            rows.append(_mode_row(mode, root / date, date))

    write_csv(out_dir / "generation_mode_comparison.csv", rows)
    summary = _summary(rows, template_mode=_template_mode(mode_dirs))
    write_json(out_dir / "generation_mode_comparison_summary.json", summary)
    write_csv(out_dir / "generation_mode_error_type_summary.csv", _error_summary(rows))
    return {"rows": rows, "summary": summary}


def _mode_row(mode: str, date_dir: Path, date: str) -> dict[str, Any]:
    quality = _read_json(date_dir / "quality.json")
    trace = _read_json(date_dir / "trace.json")
    summary = _read_json(date_dir / "summary.json")
    report_text = _read_text(date_dir / "report.txt")
    errors = _dict(summary.get("error_type_counts") or quality.get("error_type_counts"))
    grounding = _dict(quality.get("grounding_summary") or quality.get("stats"))
    return {
        "date": date,
        "generation_mode": mode,
        "missing": not date_dir.exists(),
        "passed": _coalesce(summary.get("passed"), True if date_dir.exists() else False),
        "report_length_chars": len(report_text),
        "report_length_words_or_tokens_if_available": len(report_text.split()),
        "quality_score": _coalesce(summary.get("quality_score"), quality.get("score")),
        "grounding_rate": _coalesce(summary.get("grounding_rate"), grounding.get("grounding_rate")),
        "trace_coverage": _coalesce(summary.get("trace_coverage"), trace.get("trace_coverage"), _dict(trace.get("summary")).get("trace_coverage")),
        "claim_count": _coalesce(summary.get("claim_count"), grounding.get("claim_count")),
        "unsupported_claim_count": _coalesce(summary.get("unsupported_claim_count"), grounding.get("unsupported_claim_count")),
        "warning_count": len(summary.get("warnings") or []),
        "error_type_counts": errors,
        **{str(key): safe_int(value) for key, value in errors.items()},
    }


def _summary(rows: list[dict[str, Any]], *, template_mode: str | None) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_mode.setdefault(str(row.get("generation_mode")), []).append(row)
    mode_summary = {mode: _mode_stats(items) for mode, items in by_mode.items()}
    if template_mode and template_mode in by_mode:
        template_by_date = {row["date"]: row for row in by_mode[template_mode]}
        for mode, items in by_mode.items():
            if mode == template_mode:
                continue
            deltas = []
            unsupported = []
            for row in items:
                base = template_by_date.get(row["date"])
                if not base:
                    continue
                if safe_float(row.get("grounding_rate")) is not None and safe_float(base.get("grounding_rate")) is not None:
                    deltas.append(safe_float(row.get("grounding_rate")) - safe_float(base.get("grounding_rate")))
                if safe_float(row.get("unsupported_claim_count")) is not None and safe_float(base.get("unsupported_claim_count")) is not None:
                    unsupported.append(safe_float(row.get("unsupported_claim_count")) - safe_float(base.get("unsupported_claim_count")))
            mode_summary[mode]["grounding_rate_delta_vs_template_mean"] = _mean(deltas)
            mode_summary[mode]["unsupported_claim_delta_vs_template_mean"] = _mean(unsupported)
    return {"mode_count": len(by_mode), "date_count": len({row["date"] for row in rows}), "modes": mode_summary}


def _mode_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"date_count": len(rows), "missing_count": sum(1 for row in rows if row.get("missing"))}
    for key in ["quality_score", "grounding_rate", "trace_coverage", "unsupported_claim_count", "report_length_chars"]:
        values = [safe_float(row.get(key)) for row in rows if safe_float(row.get(key)) is not None]
        series = pd.Series(values, dtype=float)
        out[f"{key}_mean"] = float(series.mean()) if not series.empty else None
        out[f"{key}_median"] = float(series.median()) if not series.empty else None
        out[f"{key}_min"] = float(series.min()) if not series.empty else None
        out[f"{key}_max"] = float(series.max()) if not series.empty else None
    return out


def _error_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({key for row in rows for key in row if str(key).startswith("E")})
    out = []
    for mode in sorted({str(row.get("generation_mode")) for row in rows}):
        subset = [row for row in rows if row.get("generation_mode") == mode]
        for key in keys:
            out.append({"generation_mode": mode, "error_type": key, "count": sum(safe_int(row.get(key)) for row in subset)})
    return out


def _parse_mode_dirs(values: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid --mode-dir value: {value}; expected name=path")
        name, raw_path = value.split("=", 1)
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        out[name.strip()] = path
    return out


def _template_mode(mode_dirs: dict[str, Path]) -> str | None:
    for name in mode_dirs:
        if name.lower() == "template":
            return name
    return next(iter(mode_dirs), None)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


if __name__ == "__main__":
    main()
