#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TBM SCI Smoke Test

放置位置建议：
  backend/scripts/run_sci_smoke_test.py

运行方式：
  cd backend
  python scripts/run_sci_smoke_test.py --date 2023-12-30 --clear-cache --no-llm

如果你已经配置好 LLM，并希望测试真实报告质量：
  python scripts/run_sci_smoke_test.py --date 2023-12-30 --clear-cache --with-llm

如果 FastAPI 已经启动，还想顺便测接口：
  uvicorn app:app --reload --port 8000
  python scripts/run_sci_smoke_test.py --date 2023-12-30 --api-base http://127.0.0.1:8000 --no-llm

输出目录：
  outputs/sci_smoke_test/<date>/
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# ============================================================
# 路径初始化
# ============================================================

def _guess_backend_dir() -> Path:
    here = Path(__file__).resolve()
    # scripts/run_sci_smoke_test.py -> backend
    if here.parent.name == "scripts":
        return here.parent.parent
    # 如果直接放在 backend 根目录
    if (here.parent / "app.py").exists():
        return here.parent
    return Path.cwd().resolve()


BACKEND_DIR = _guess_backend_dir()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ============================================================
# 小工具
# ============================================================

@dataclass
class TestItem:
    name: str
    ok: bool
    score: str = ""
    detail: str = ""
    seconds: float = 0.0


def _now_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _safe_jsonable(obj: Any) -> Any:
    try:
        from utils.serialization import serialize_for_json
        return serialize_for_json(obj)
    except Exception:
        pass

    if isinstance(obj, dict):
        return {str(k): _safe_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_safe_jsonable(v) for v in obj]
    if hasattr(obj, "to_dict"):
        try:
            return _safe_jsonable(obj.to_dict())
        except Exception:
            return str(obj)
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except Exception:
        return str(obj)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_safe_jsonable(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _print_table(items: list[TestItem]) -> None:
    print("\n" + "=" * 100)
    print("SCI Smoke Test Summary")
    print("=" * 100)
    print(f"{'状态':<8} {'测试项':<36} {'评分/指标':<18} 说明")
    print("-" * 100)
    for item in items:
        status = "PASS" if item.ok else "FAIL"
        print(f"{status:<8} {item.name:<36} {item.score:<18} {item.detail}")
    print("-" * 100)
    passed = sum(1 for x in items if x.ok)
    print(f"TOTAL: {passed}/{len(items)} passed")
    print("=" * 100 + "\n")


def _run_item(name: str, func) -> TestItem:
    t0 = time.perf_counter()
    try:
        ok, score, detail = func()
        return TestItem(
            name=name,
            ok=bool(ok),
            score=str(score or ""),
            detail=str(detail or ""),
            seconds=round(time.perf_counter() - t0, 3),
        )
    except Exception as exc:
        return TestItem(
            name=name,
            ok=False,
            score="EXCEPTION",
            detail=f"{type(exc).__name__}: {exc}",
            seconds=round(time.perf_counter() - t0, 3),
        )


def _http_get_json(url: str, timeout: int = 30) -> tuple[bool, Any, str]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return True, json.loads(raw), ""
            except json.JSONDecodeError:
                return False, raw[:1000], "response is not json"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        return False, body, f"HTTP {exc.code}"
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def _http_post_json(url: str, payload: dict[str, Any], timeout: int = 120) -> tuple[bool, Any, str]:
    try:
        raw_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw_payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return True, json.loads(raw), ""
            except json.JSONDecodeError:
                return False, raw[:1000], "response is not json"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        return False, body, f"HTTP {exc.code}"
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def _has_any_key(d: dict[str, Any], names: list[str]) -> bool:
    return any(name in d and d.get(name) not in (None, {}, [], "") for name in names)


def _nested_get(d: dict[str, Any], path: list[str], default=None):
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


# ============================================================
# 核心测试
# ============================================================

def test_py_compile() -> tuple[bool, str, str]:
    cmd = [sys.executable, "-m", "compileall", "-q", str(BACKEND_DIR)]
    proc = subprocess.run(
        cmd,
        cwd=str(BACKEND_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    ok = proc.returncode == 0
    detail = (proc.stderr or proc.stdout or "compileall ok").strip()
    return ok, f"return={proc.returncode}", detail[:500]


def test_imports() -> tuple[bool, str, str]:
    modules = [
        "services.tbm_analysis_service",
        "llm.prompt_builder",
        "llm.prompt_evidence_pack",
        "llm.report_quality_checker",
        "llm.report_trace_builder",
        "services.twin_state_builder",
        "routes.tbm",
        "app",
    ]
    failed = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            failed.append(f"{mod}: {type(exc).__name__}: {exc}")
    return not failed, f"{len(modules) - len(failed)}/{len(modules)}", "; ".join(failed) or "imports ok"


def run_analysis(date: str, clear_cache: bool, out_dir: Path) -> dict[str, Any]:
    from utils.io_utils import load_csv_by_date
    from services.tbm_analysis_service import analyze_tbm_data

    if clear_cache:
        try:
            from services.analysis_cache_service import clear_file_cache
            clear_file_cache()
        except Exception as exc:
            print(f"[WARN] clear_file_cache failed: {exc}")

    path, df = load_csv_by_date(date)
    result = analyze_tbm_data(
        df,
        context={
            "date": date,
            "analysis_mode": "daily",
            "source_path": str(path),
            "source_name": path.name,
            "persist_cst": False,
        },
    )
    _write_json(out_dir / f"analysis_{date}.json", result)
    return result


def check_analysis_fields(result: dict[str, Any]) -> tuple[bool, str, str]:
    required = [
        "run_metadata",
        "plc_quality_report",
        "operation_context",
        "cluster_context",
        "gas_context",
        "cell_response_summary",
        "geology_v2_context",
        "twin_state",
        "prompt_evidence_pack_summary",
        "report_quality",
        "report_trace_summary",
    ]
    present = [k for k in required if bool(result.get(k))]
    missing = [k for k in required if not bool(result.get(k))]
    return not missing, f"{len(present)}/{len(required)}", "missing: " + ", ".join(missing) if missing else "all required analysis fields exist"


def check_twin_state(result: dict[str, Any]) -> tuple[bool, str, str]:
    twin = result.get("twin_state", {}) if isinstance(result.get("twin_state"), dict) else {}

    # 兼容两种命名：position_state 和 position
    required_groups = {
        "position": ["position_state", "position"],
        "operation": ["operation_state", "operation"],
        "cluster": ["cluster_state", "cluster"],
        "gas": ["gas_state", "gas"],
        "geology": ["geology_state", "geology"],
        "response": ["response_state", "response"],
        "coupling": ["coupling_state", "coupling"],
        "forward": ["forward_state", "forward"],
        "quality": ["quality_state", "quality"],
        "source_refs": ["source_refs"],
        "run_metadata": ["run_metadata"],
    }

    missing = [group for group, keys in required_groups.items() if not _has_any_key(twin, keys)]
    ok = not missing
    _write_json(OUT_DIR / f"twin_state_{ARGS.date}.json", twin)
    return ok, f"{len(required_groups)-len(missing)}/{len(required_groups)}", "missing groups: " + ", ".join(missing) if missing else "TwinState structure ok"


def check_prompt_pack(result: dict[str, Any]) -> tuple[bool, str, str]:
    llm_summary = result.get("llm_summary", {}) if isinstance(result.get("llm_summary"), dict) else {}
    pack = llm_summary.get("prompt_evidence_pack", {})
    if not isinstance(pack, dict) or not pack:
        return False, "0", "llm_summary.prompt_evidence_pack missing"

    required = [
        "operation_evidence",
        "geology_evidence",
        "forward_evidence",
        "coupling_evidence",
        "quality_evidence",
        "source_trace",
        "generation_constraints",
    ]
    # cluster_evidence / gas_evidence 若存在也记录，但不设为硬失败，避免版本差异
    missing = [k for k in required if not bool(pack.get(k))]
    _write_json(OUT_DIR / f"prompt_pack_{ARGS.date}.json", pack)
    return not missing, f"{len(required)-len(missing)}/{len(required)}", "missing: " + ", ".join(missing) if missing else "PromptEvidencePack structure ok"


def build_report_pipeline(result: dict[str, Any], no_llm: bool, out_dir: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """
    如果 no_llm=True，只检查 analyze_tbm_data 自带的占位 quality/trace。
    如果 no_llm=False，调用你的现有 LLM pipeline 生成真实报告再检查。
    """
    if no_llm:
        report_text = ""
        quality = result.get("report_quality", {}) if isinstance(result.get("report_quality"), dict) else {}
        trace_summary = result.get("report_trace_summary", {}) if isinstance(result.get("report_trace_summary"), dict) else {}
        _write_json(out_dir / f"quality_{ARGS.date}.json", quality)
        _write_json(out_dir / f"trace_summary_{ARGS.date}.json", trace_summary)
        return report_text, quality, trace_summary

    from llm.llm_api import call_llm
    from llm.prompt_builder import build_prompt
    from llm.report_quality_checker import check_report_quality
    from llm.report_trace_builder import build_report_trace, summarize_report_trace

    llm_summary = result.get("llm_summary", {}) if isinstance(result.get("llm_summary"), dict) else {}

    prompt = build_prompt(
        seg_text=result.get("seg_text", ""),
        stats_text=result.get("stats_text", ""),
        state_text=result.get("state_text", ""),
        eff_text=result.get("eff_text", ""),
        state_stats_text=result.get("state_stats_text", ""),
        gas_text=result.get("gas_text", ""),
        geo_text=result.get("geo_text", ""),
        face_geo_text=result.get("face_geo_text", ""),
        llm_summary=llm_summary,
        risk_prob_text=result.get("risk_prob_text", ""),
    )
    (out_dir / f"prompt_{ARGS.date}.txt").write_text(prompt, encoding="utf-8")

    report_text = call_llm(prompt)
    (out_dir / f"report_{ARGS.date}.txt").write_text(report_text, encoding="utf-8")

    twin_state = result.get("twin_state", {})
    prompt_pack = llm_summary.get("prompt_evidence_pack", {})
    geology_context = result.get("geology_v2_context", {}) or llm_summary.get("geology_v2_context", {})

    quality = check_report_quality(
        report_text,
        llm_summary=llm_summary,
        geology_context=geology_context,
        twin_state=twin_state,
        prompt_evidence_pack=prompt_pack,
        include_claim_results=True,
    )


    trace = build_report_trace(
        report_text,
        grounding_result=quality,
        twin_state=twin_state,
        geology_context=geology_context,
        prompt_evidence_pack=prompt_pack,
    )
    trace_summary = summarize_report_trace(trace)

    _write_json(out_dir / f"quality_{ARGS.date}.json", quality)
    _write_json(out_dir / f"trace_{ARGS.date}.json", trace)
    _write_json(out_dir / f"trace_summary_{ARGS.date}.json", trace_summary)
    return report_text, quality, trace_summary


def check_quality(quality: dict[str, Any], *, no_llm: bool) -> tuple[bool, str, str]:
    score = int(quality.get("score", quality.get("quality_score", 0)))
    grounding_rate = float(_nested_get(quality, ["grounding_summary", "grounding_rate"], 0.0) or 0.0)
    violations = quality.get("violations", []) or []
    warnings = quality.get("warnings", []) or []

    if no_llm:
        # no_llm 下 quality 通常是 analyze 阶段占位，不按真实报告质量判死刑。
        ok = bool(quality)
        return ok, f"score={score}, grounding={grounding_rate:.2f}", f"no_llm mode; warnings={len(warnings)}, violations={len(violations)}"

    hard_bad_keywords = []
    text_blob = json.dumps(_safe_jsonable(quality), ensure_ascii=False)
    for kw in ["灾害概率", "风险概率", "浓度超限", "前方低风险"]:
        if kw in text_blob:
            hard_bad_keywords.append(kw)

    ok = score >= 80 and grounding_rate >= 0.80 and not hard_bad_keywords
    detail = f"warnings={len(warnings)}, violations={len(violations)}"
    if hard_bad_keywords:
        detail += "; hard_bad_keywords=" + ",".join(hard_bad_keywords)
    return ok, f"score={score}, grounding={grounding_rate:.2f}", detail


def check_trace(trace_summary: dict[str, Any], *, no_llm: bool) -> tuple[bool, str, str]:
    trace_available = bool(trace_summary.get("trace_available"))
    claim_count = int(trace_summary.get("claim_trace_count", 0) or 0)
    coverage = float(trace_summary.get("trace_coverage", 0.0) or 0.0)
    warnings = trace_summary.get("warnings", []) or []

    if no_llm:
        # analyze_tbm_data 没有 report_text 时通常只能返回占位 trace。
        ok = bool(trace_summary)
        return ok, f"available={trace_available}, coverage={coverage:.2f}", f"no_llm mode; claim_count={claim_count}, warnings={len(warnings)}"

    ok = trace_available and claim_count > 0 and coverage >= 0.80
    return ok, f"available={trace_available}, coverage={coverage:.2f}", f"claim_count={claim_count}, warnings={len(warnings)}"


def test_quality_checker_negative_case() -> tuple[bool, str, str]:
    from llm.report_quality_checker import check_report_quality

    bad_report = (
        "当前掌子面前方低风险。"
        "GRCI表示灾害概率为80%。"
        "气体alarm_flag说明浓度超限。"
        "前方预测结果已经揭示当前掌子面发生突涌水。"
    )
    quality = check_report_quality(
        bad_report,
        llm_summary={},
        geology_context={},
        twin_state={},
        prompt_evidence_pack={},
        include_claim_results=True,
    )
    _write_json(OUT_DIR / "negative_quality_case.json", quality)

    blob = json.dumps(_safe_jsonable(quality), ensure_ascii=False)
    expected_hits = ["GRCI", "概率", "气体", "前方"]
    hit_count = sum(1 for x in expected_hits if x in blob)
    score = int(quality.get("score", quality.get("quality_score", 100)))
    ok = hit_count >= 2 and score < 100
    return ok, f"hits={hit_count}, score={score}", "negative case should be penalized"


def test_existing_readiness_script(date: str, no_llm: bool, out_dir: Path) -> tuple[bool, str, str]:
    script_path = BACKEND_DIR / "scripts" / "run_sci_readiness_check.py"
    if not script_path.exists():
        return False, "missing", f"{script_path} not found"

    readiness_out = out_dir / "readiness"
    cmd = [
        sys.executable,
        str(script_path),
        "--dates",
        date,
        "--output-dir",
        str(readiness_out),
    ]
    if no_llm:
        cmd.append("--no-llm")
    proc = subprocess.run(
        cmd,
        cwd=str(BACKEND_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
    )

    summary_path = readiness_out / "summary.csv"
    ok = proc.returncode == 0 and summary_path.exists()

    detail = ""
    if summary_path.exists():
        detail = summary_path.read_text(encoding="utf-8-sig")[:1000]
    else:
        detail = (proc.stderr or proc.stdout or "").strip()[:1000]

    return ok, f"return={proc.returncode}", detail.replace("\n", " ")[:500]


def test_api(api_base: str, date: str, out_dir: Path) -> tuple[bool, str, str]:
    if not api_base:
        return True, "skipped", "未传 --api-base，跳过 API 测试"

    api_base = api_base.rstrip("/")
    endpoints = {
        "geology": f"{api_base}/api/tbm/geology?date={date}",
        "digital_twin_state": f"{api_base}/api/tbm/digital_twin_state?date={date}",
    }

    results: dict[str, Any] = {}
    failures = []

    for name, url in endpoints.items():
        ok, payload, err = _http_get_json(url, timeout=120)
        results[name] = {"ok": ok, "error": err, "payload_preview": payload if ok else str(payload)[:1000]}
        if not ok:
            failures.append(f"{name}: {err}")
            continue

        if name == "geology":
            blob = json.dumps(_safe_jsonable(payload), ensure_ascii=False)
            if "geology_v2_context" not in blob and "forward" not in blob:
                failures.append("geology: no geology_v2_context/forward in response")

        if name == "digital_twin_state":
            blob = json.dumps(_safe_jsonable(payload), ensure_ascii=False)
            if "twin_state" not in blob and "digital_twin_state" not in blob:
                failures.append("digital_twin_state: no twin_state/digital_twin_state in response")

    # report 接口不同项目可能是 POST/GET，这里先尝试 POST，失败不作为硬失败，只记录。
    ok_post, report_payload, err_post = _http_post_json(
        f"{api_base}/api/tbm/report",
        {"date": date},
        timeout=180,
    )
    results["report_post"] = {
        "ok": ok_post,
        "error": err_post,
        "payload_preview": report_payload if ok_post else str(report_payload)[:1000],
    }

    _write_json(out_dir / f"api_results_{date}.json", results)

    if failures:
        return False, f"fail={len(failures)}", "; ".join(failures)
    if not ok_post:
        return True, "partial", f"geology/digital_twin_state ok; report POST skipped/failed: {err_post}"
    return True, "ok", "API geology/digital_twin_state/report checked"


def build_final_verdict(items: list[TestItem], quality: dict[str, Any], trace_summary: dict[str, Any], no_llm: bool) -> dict[str, Any]:
    failed = [x.name for x in items if not x.ok]
    score = int((quality or {}).get("score", 0) or 0)
    grounding_rate = float(((quality or {}).get("grounding_summary", {}) or {}).get("grounding_rate", 0.0) or 0.0)
    trace_available = bool((trace_summary or {}).get("trace_available"))
    trace_coverage = float((trace_summary or {}).get("trace_coverage", 0.0) or 0.0)

    if failed:
        stage = "B/C 之间：主链路或验收脚本仍有失败项"
    elif no_llm:
        stage = "C-：分析链路可验收，但 no_llm 模式不能证明真实报告 grounding/trace"
    elif score >= 80 and grounding_rate >= 0.80 and trace_available and trace_coverage >= 0.80:
        stage = "C：SCI 方法框架原型已成型，可以进入修 bug + 批量验收"
    else:
        stage = "C-：架构已成型，但报告质量/grounding/trace 指标不足"

    return {
        "date": ARGS.date,
        "no_llm": no_llm,
        "failed_tests": failed,
        "quality_score": score,
        "grounding_rate": grounding_rate,
        "trace_available": trace_available,
        "trace_coverage": trace_coverage,
        "stage_verdict": stage,
        "outputs_dir": str(OUT_DIR),
    }


# ============================================================
# main
# ============================================================

def main() -> int:
    global ARGS, OUT_DIR

    parser = argparse.ArgumentParser(description="Run TBM SCI smoke tests.")
    parser.add_argument("--date", default="2023-12-30", help="测试日期，例如 2023-12-30")
    parser.add_argument("--output-dir", default="outputs/sci_smoke_test", help="输出目录")
    parser.add_argument("--clear-cache", action="store_true", help="测试前清空项目缓存")
    parser.add_argument("--api-base", default="", help="可选，例如 http://127.0.0.1:8000")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--no-llm", action="store_true", help="不调用 LLM，只测分析链路与占位 quality/trace")
    mode.add_argument("--with-llm", action="store_true", help="调用 LLM 生成报告并做真实 quality/trace")
    ARGS = parser.parse_args()

    no_llm = not ARGS.with_llm

    OUT_DIR = Path(ARGS.output_dir) / ARGS.date / _now_tag()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] BACKEND_DIR = {BACKEND_DIR}")
    print(f"[INFO] OUT_DIR     = {OUT_DIR}")
    print(f"[INFO] DATE        = {ARGS.date}")
    print(f"[INFO] MODE        = {'no_llm' if no_llm else 'with_llm'}")

    items: list[TestItem] = []
    artifacts: dict[str, Any] = {
        "backend_dir": str(BACKEND_DIR),
        "out_dir": str(OUT_DIR),
        "date": ARGS.date,
        "no_llm": no_llm,
    }

    items.append(_run_item("py_compile", test_py_compile))
    items.append(_run_item("imports", test_imports))

    result: dict[str, Any] = {}
    analysis_item = _run_item(
        "analyze_tbm_data",
        lambda: (
            True,
            "ok",
            "analysis completed",
        ),
    )
    try:
        t0 = time.perf_counter()
        result = run_analysis(ARGS.date, ARGS.clear_cache, OUT_DIR)
        analysis_item = TestItem(
            name="analyze_tbm_data",
            ok=True,
            score="ok",
            detail="analysis completed",
            seconds=round(time.perf_counter() - t0, 3),
        )
    except Exception as exc:
        analysis_item = TestItem(
            name="analyze_tbm_data",
            ok=False,
            score="EXCEPTION",
            detail=f"{type(exc).__name__}: {exc}",
            seconds=0.0,
        )
        (OUT_DIR / "analysis_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
    items.append(analysis_item)

    if result:
        items.append(_run_item("analysis_required_fields", lambda: check_analysis_fields(result)))
        items.append(_run_item("twin_state_structure", lambda: check_twin_state(result)))
        items.append(_run_item("prompt_evidence_pack_structure", lambda: check_prompt_pack(result)))

        report_text = ""
        quality: dict[str, Any] = {}
        trace_summary: dict[str, Any] = {}
        try:
            t0 = time.perf_counter()
            report_text, quality, trace_summary = build_report_pipeline(result, no_llm=no_llm, out_dir=OUT_DIR)
            items.append(TestItem(
                name="report_pipeline",
                ok=True,
                score="no_llm" if no_llm else "with_llm",
                detail="report/quality/trace pipeline completed",
                seconds=round(time.perf_counter() - t0, 3),
            ))
        except Exception as exc:
            items.append(TestItem(
                name="report_pipeline",
                ok=False,
                score="EXCEPTION",
                detail=f"{type(exc).__name__}: {exc}",
                seconds=0.0,
            ))
            (OUT_DIR / "report_pipeline_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")

        items.append(_run_item("report_quality", lambda: check_quality(quality, no_llm=no_llm)))
        items.append(_run_item("report_trace", lambda: check_trace(trace_summary, no_llm=no_llm)))
        items.append(_run_item("quality_checker_negative_case", test_quality_checker_negative_case))
        items.append(_run_item("existing_readiness_script", lambda: test_existing_readiness_script(ARGS.date, no_llm, OUT_DIR)))
        items.append(_run_item("api_routes", lambda: test_api(ARGS.api_base, ARGS.date, OUT_DIR)))

        verdict = build_final_verdict(items, quality, trace_summary, no_llm)
        artifacts["verdict"] = verdict
    else:
        artifacts["verdict"] = {
            "date": ARGS.date,
            "failed_tests": [x.name for x in items if not x.ok],
            "stage_verdict": "B-：analyze_tbm_data 未跑通，后续 SCI 主链路无法验收",
            "outputs_dir": str(OUT_DIR),
        }

    rows = [asdict(x) for x in items]
    _write_json(OUT_DIR / "smoke_test_results.json", artifacts | {"tests": rows})
    _write_csv(OUT_DIR / "smoke_test_results.csv", rows)

    _print_table(items)

    print("最终判断：", artifacts["verdict"]["stage_verdict"])
    print("结果文件：")
    print(" -", OUT_DIR / "smoke_test_results.json")
    print(" -", OUT_DIR / "smoke_test_results.csv")
    print(" -", OUT_DIR / f"analysis_{ARGS.date}.json")
    print(" -", OUT_DIR / f"twin_state_{ARGS.date}.json")
    print(" -", OUT_DIR / f"prompt_pack_{ARGS.date}.json")
    print(" -", OUT_DIR / f"quality_{ARGS.date}.json")
    print(" -", OUT_DIR / f"trace_summary_{ARGS.date}.json")

    return 0 if all(x.ok for x in items) else 1


if __name__ == "__main__":
    raise SystemExit(main())
