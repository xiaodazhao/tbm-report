# hsp_parser.py
import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any

import pdfplumber
import fitz

from schemas.schemas import EvidenceRecord
from utils.chainage_utils import mileage_to_num


PARSER_NAME = "hsp_parser"
PARSER_VERSION = "v2"
EVIDENCE_ATTRS_SCHEMA_VERSION = "evidence_attrs_v2"


def _infer_source_semantics(fact_type: str | None) -> str:
    """Infer normalized evidence semantics from fact_type."""
    ft = str(fact_type or "")
    if "sketch" in ft or "observation" in ft:
        return "face_observation"
    if "overview" in ft:
        return "report_overview"
    if "conclusion" in ft:
        return "forecast_conclusion"
    if "segment" in ft or "table" in ft or "hsp" in ft:
        return "forecast_segment"
    return "forecast_evidence"


def _finalize_attrs(attrs: Dict[str, Any] | dict, parse_warnings=None) -> dict:
    """Add schema/parser metadata while preserving old keys for compatibility."""
    out = dict(attrs or {})
    warnings = parse_warnings or []
    out.setdefault("evidence_attrs_schema_version", EVIDENCE_ATTRS_SCHEMA_VERSION)
    out.setdefault("parser_name", PARSER_NAME)
    out.setdefault("parser_version", PARSER_VERSION)
    out.setdefault("parse_quality", "rule_based")
    out.setdefault("parse_warnings", warnings)
    out.setdefault("source_semantics", _infer_source_semantics(out.get("fact_type")))

    # source_* is the parser-internal interpretation. System-wide geo_attention
    # should be produced later by fusion/model layers, not by parser risk_level.
    out.setdefault("source_risk_level", out.get("risk_level"))
    out.setdefault("source_risk_tags", out.get("risk_tags", []))
    return out


def _norm_text(text: str) -> str:
    """Normalize text while preserving line breaks."""
    if not text:
        return ""
    text = text.replace("\u3000", " ")
    text = text.replace("～", "~")
    text = text.replace("—", "-").replace("−", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _flat_text(text: str) -> str:
    """Normalize text into a compact single-line string."""
    text = _norm_text(text)
    text = text.replace("\n", "")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _safe_search(pattern: str, text: str, flags=re.S) -> Optional[str]:
    """Safely search text with a regex pattern."""
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _safe_mileage(x: Optional[str]) -> Optional[float]:
    """Safely convert mileage text into a numeric chainage."""
    if not x:
        return None
    try:
        return float(mileage_to_num(x))
    except Exception:
        return None


def _extract_meta_from_text(text: str, pdf_name: str) -> Dict[str, Any]:
    """Extract report metadata from PDF text."""
    t = _norm_text(text)

    report_id = pdf_name.replace(".pdf", "")
    tunnel_name = _safe_search(r"(伯舒拉岭隧道进口右线)", t) or "伯舒拉岭隧道进口右线"

    report_date = (
        _safe_search(r"检测日期[:：]?\s*([0-9]{4}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日)", t)
        or _safe_search(r"测试日期[:：]?\s*([0-9]{4}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日)", t)
        or _safe_search(r"(二〇[^\n]+)", t)
    )

    forecast = _safe_search(r"预报范围\s*(DyK\d+\+\d+\.?\d*\s*~\s*DyK\d+\+\d+\.?\d*)", t)
    face = _safe_search(r"开挖面里\s*程\s*(DyK\d+\+\d+\.?\d*)", t) or _safe_search(
        r"开挖面里程\s*(DyK\d+\+\d+\.?\d*)", t
    )
    next_ = _safe_search(r"下次物探预报里程为\s*(DyK\d+\+\d+\.?\d*)", t)

    start_num, end_num = None, None
    if forecast:
        m = re.search(r"(DyK\d+\+\d+\.?\d*)\s*~\s*(DyK\d+\+\d+\.?\d*)", forecast)
        if m:
            start_num = _safe_mileage(m.group(1))
            end_num = _safe_mileage(m.group(2))

    return {
        "report_id": report_id,
        "tunnel_name": tunnel_name,
        "report_date": report_date,
        "issue_date": report_date,
        "forecast_start_num": start_num,
        "forecast_end_num": end_num,
        "face_num": _safe_mileage(face),
        "next_forecast_num": _safe_mileage(next_),
    }


def _parse_range_cell(text: str):
    """Parse chainage range cell."""
    if not text:
        return None

    flat = _flat_text(text)
    miles = re.findall(r"DyK\d+\+\d+\.?\d*", flat)
    if len(miles) < 2:
        return None

    return {
        "start_text": miles[0],
        "end_text": miles[1],
        "start_num": _safe_mileage(miles[0]),
        "end_num": _safe_mileage(miles[1]),
    }


def _infer_anomaly_level(text: str) -> str:
    """Infer HSP reflection anomaly level."""
    flat = _flat_text(text)

    # 顺序非常关键：先判断“未见”
    if "未见明显反射异常" in flat:
        return "none"
    if "较明显反射异常" in flat:
        return "medium"
    if "明显反射异常" in flat:
        return "strong"
    return "none"


def _extract_support_grade(text: str) -> Optional[str]:
    """Extract support grade from text."""
    flat = _flat_text(text)
    m = re.search(r"([ⅠⅡⅢⅣⅤIVX]+)级围岩", flat)
    if m:
        return m.group(1)
    return None


def _extract_joint_degree(text: str) -> Optional[str]:
    """Extract joint development degree."""
    flat = _flat_text(text)
    if "节理裂隙发育密集" in flat:
        return "发育密集"
    if "节理裂隙较发育" in flat:
        return "较发育"
    if "节理裂隙发育" in flat:
        return "发育"
    return None


def _extract_rock_mass_state(text: str) -> Optional[str]:
    """Extract rock mass state."""
    flat = _flat_text(text)
    if "岩体破碎-极破碎" in flat or "岩体破碎极破碎" in flat:
        return "破碎-极破碎"
    if "岩体极破碎" in flat:
        return "极破碎"
    if "岩体较破碎" in flat or "岩体相对破碎" in flat:
        return "较破碎"
    if "岩体破碎" in flat:
        return "破碎"
    return None


def _extract_weathering(text: str) -> Optional[str]:
    """Extract weathering degree."""
    flat = _flat_text(text)
    for x in ["全风化", "强风化", "弱风化", "微风化", "未风化"]:
        if x in flat:
            return x
    return None


def _extract_rock_uniformity(text: str) -> Optional[str]:
    """Extract rock uniformity."""
    flat = _flat_text(text)
    if "软硬不均" in flat:
        return "软硬不均"
    return None


def _extract_stability(text: str) -> Optional[str]:
    """Extract stability description."""
    flat = _flat_text(text)
    if "围岩整体稳定性差" in flat or "围岩整体稳定性较差" in flat or "围岩自稳性差" in flat:
        return "较差"
    if "围岩整体稳定性一般" in flat:
        return "一般"
    return None


def _extract_lithology(text: str) -> Optional[str]:
    """Extract lithology."""
    flat = _flat_text(text)
    if "板岩夹变质砂岩" in flat:
        return "板岩夹变质砂岩"
    return None


def _extract_collapse_info(risk_hint: str, conclusion: str):
    """Extract collapse information.

    修正原则：
    1. collapse_flag 可以来自风险提示或结论中的“掉块”；
    2. collapse_points 只能来自明确风险提示列；
    3. 如果 risk_hint 只是里程范围，例如 DyK1013+190.2~DyK1013+224，
       不能抽出 +190.2 / +224 当作掉块点；
    4. 避免把段起点、段终点误生成 anomaly_point。
    """
    flat_hint = _flat_text(risk_hint or "")
    flat_conc = _flat_text(conclusion or "")
    flat_all = flat_hint + flat_conc

    collapse_flag = 1 if "掉块" in flat_all else 0
    collapse_points = []

    # 必须是明确风险提示，不是普通里程范围。
    has_explicit_point_risk = (
        "掉块风险" in flat_hint
        or "附近有掉块" in flat_hint
        or "有掉块风险" in flat_hint
    )

    if not has_explicit_point_risk:
        return collapse_flag, collapse_points

    # 去掉完整里程段，避免 DyK1013+190.2~DyK1013+224 被拆成 +190.2 和 +224。
    hint_without_full_ranges = re.sub(
        r"DyK\d+\+\d+\.?\d*\s*[~～\-]\s*DyK\d+\+\d+\.?\d*",
        "",
        flat_hint,
    )

    # 只抽“+224、+232附近有掉块风险”这种短桩号。
    pts = re.findall(r"\+(\d+\.?\d*)", hint_without_full_ranges)
    for p in pts:
        try:
            collapse_points.append(float(p))
        except Exception:
            pass

    # 去重保序。
    out = []
    seen = set()
    for p in collapse_points:
        key = round(float(p), 3)
        if key in seen:
            continue
        seen.add(key)
        out.append(float(p))

    return collapse_flag, out


def _infer_risk_level(
    anomaly_level: str,
    collapse_flag: int,
    support_grade: Optional[str],
    rock_mass_state: Optional[str],
) -> str:
    """Infer parser-local source risk level."""
    if anomaly_level == "strong" or collapse_flag == 1 or rock_mass_state in {"破碎-极破碎", "极破碎"}:
        return "high"
    if anomaly_level == "medium" or support_grade == "Ⅴ" or rock_mass_state in {"破碎", "较破碎"}:
        return "medium"
    return "low"


def _build_risk_tags(
    anomaly_level: str,
    collapse_flag: int,
    joint_degree: Optional[str],
    rock_mass_state: Optional[str],
    support_grade: Optional[str],
):
    """Build parser-local risk tags."""
    tags = []

    if anomaly_level == "strong":
        tags.append("明显反射异常")
    elif anomaly_level == "medium":
        tags.append("较明显反射异常")

    if collapse_flag:
        tags.append("掉块")

    if joint_degree == "发育密集":
        tags.append("裂隙密集")
    elif joint_degree in {"发育", "较发育"}:
        tags.append("裂隙发育")

    if rock_mass_state in {"破碎-极破碎", "极破碎"}:
        tags.append("围岩极破碎")
    elif rock_mass_state in {"破碎", "较破碎"}:
        tags.append("围岩破碎")

    if support_grade:
        tags.append("围岩等级建议")

    out = []
    seen = set()
    for t in tags:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def _score_range_cell(text: str) -> int:
    """Score whether a cell is a chainage range cell."""
    flat = _flat_text(text)
    if re.search(r"DyK\d+\+\d+\.?\d*", flat) and "~" in flat:
        return 3
    return 0


def _score_detect_cell(text: str) -> int:
    """Score whether a cell is a geophysical detection result cell."""
    flat = _flat_text(text)
    keys = ["未见明显反射异常", "较明显反射异常", "明显反射异常", "反射异常"]
    return sum(1 for k in keys if k in flat)


def _score_conclusion_cell(text: str) -> int:
    """Score whether a cell is a forecast conclusion cell."""
    flat = _flat_text(text)
    keys = ["围岩", "岩性", "弱风化", "软硬不均", "裂隙", "岩体", "稳定性", "变差", "变好", "掌子面相当"]
    return sum(1 for k in keys if k in flat)


def _score_risk_hint_cell(text: str) -> int:
    """Score whether a cell is an explicit risk hint cell.

    只识别真正风险提示，不把普通里程范围当作 risk_hint。
    """
    flat = _flat_text(text)

    score = 0
    if "掉块风险" in flat:
        score += 3
    if "附近有掉块" in flat:
        score += 3
    if "有掉块风险" in flat:
        score += 3
    if "里程+" in flat and "掉块" in flat:
        score += 2

    # 表头不应被选成风险提示。
    if flat in {"风险提示", "风险提示建议"}:
        return 0

    return score


def _score_grade_cell(text: str) -> int:
    """Score whether a cell is a support grade cell."""
    flat = _flat_text(text)
    if re.search(r"[ⅠⅡⅢⅣⅤIVX]+级围岩", flat):
        return 3
    return 0


def _best_scored_cell(non_empty: List[str], score_func, min_score: int = 1) -> str:
    """Return the best scored cell only if its score reaches min_score."""
    if not non_empty:
        return ""

    scored = [(c, score_func(c)) for c in non_empty]
    best_cell, best_score = max(scored, key=lambda x: x[1])

    if best_score >= min_score:
        return best_cell

    return ""


def _pick_cells_from_row(row: List[str]) -> Dict[str, str]:
    """Pick semantic cells from one pdfplumber table row.

    修正点：
    - range_cell 必须识别到真实里程段；
    - detect / conclusion / risk_hint / grade 只有打分达到阈值才保留；
    - 避免在无风险提示时，把“里程范围”误当成 risk_hint。
    """
    cells = [("" if c is None else str(c).strip()) for c in row]
    non_empty = [c for c in cells if c]

    if not non_empty:
        return {"range": "", "detect": "", "conclusion": "", "risk_hint": "", "grade": ""}

    range_cell = _best_scored_cell(non_empty, _score_range_cell, min_score=3)
    detect_cell = _best_scored_cell(non_empty, _score_detect_cell, min_score=1)
    conclusion_cell = _best_scored_cell(non_empty, _score_conclusion_cell, min_score=1)
    risk_hint_cell = _best_scored_cell(non_empty, _score_risk_hint_cell, min_score=1)
    grade_cell = _best_scored_cell(non_empty, _score_grade_cell, min_score=3)

    return {
        "range": range_cell,
        "detect": detect_cell,
        "conclusion": conclusion_cell,
        "risk_hint": risk_hint_cell,
        "grade": grade_cell,
    }


def _is_valid_hsp_row(picked: Dict[str, str]) -> bool:
    """Check whether a picked row is a valid HSP forecast row."""
    range_text = picked.get("range", "") or ""
    detect_text = picked.get("detect", "") or ""
    conclusion_text = picked.get("conclusion", "") or ""
    grade_text = picked.get("grade", "") or ""

    # 必须有里程段。
    if not range_text:
        return False

    flat_range = _flat_text(range_text)
    if "~" not in flat_range:
        return False

    miles = re.findall(r"DyK\d+\+\d+\.?\d*", flat_range)
    if len(miles) < 2:
        return False

    # 排除“预报范围”这种假行。
    flat_detect = _flat_text(detect_text)
    flat_conc = _flat_text(conclusion_text)
    flat_grade = _flat_text(grade_text)

    if "预报范围" in flat_range or "预报范围" in flat_detect or "预报范围" in flat_conc:
        return False

    # 必须至少包含 检测结果 / 结论 / 等级 其中之一。
    useful = False
    if any(x in flat_detect for x in ["未见明显反射异常", "较明显反射异常", "明显反射异常", "反射异常"]):
        useful = True
    if "围岩" in flat_conc or "岩性" in flat_conc:
        useful = True
    if re.search(r"[ⅠⅡⅢⅣⅤIVX]+级围岩", flat_grade):
        useful = True

    return useful


def _parse_hsp_row_to_record(row_data: Dict[str, str], meta: Dict[str, Any], idx: int) -> Optional[EvidenceRecord]:
    """Parse one HSP table row into an EvidenceRecord."""
    range_info = _parse_range_cell(row_data.get("range", ""))
    if not range_info:
        return None

    detect_text = row_data.get("detect", "")
    conclusion_text = row_data.get("conclusion", "")
    risk_hint_text = row_data.get("risk_hint", "")
    grade_text = row_data.get("grade", "")

    anomaly_level = _infer_anomaly_level(detect_text)
    support_grade = _extract_support_grade(grade_text or conclusion_text)
    joint_degree = _extract_joint_degree(conclusion_text)
    rock_mass_state = _extract_rock_mass_state(conclusion_text)
    weathering = _extract_weathering(conclusion_text)
    rock_uniformity = _extract_rock_uniformity(conclusion_text)
    stability = _extract_stability(conclusion_text)
    lithology = _extract_lithology(conclusion_text)
    collapse_flag, collapse_points = _extract_collapse_info(risk_hint_text, conclusion_text)

    risk_level = _infer_risk_level(
        anomaly_level=anomaly_level,
        collapse_flag=collapse_flag,
        support_grade=support_grade,
        rock_mass_state=rock_mass_state,
    )

    risk_tags = _build_risk_tags(
        anomaly_level=anomaly_level,
        collapse_flag=collapse_flag,
        joint_degree=joint_degree,
        rock_mass_state=rock_mass_state,
        support_grade=support_grade,
    )

    attrs = {
        "fact_type": "hsp_segment",
        "lithology": lithology,
        "weathering": weathering,
        "support_grade": support_grade,
        "rock_hardness": None,
        "rock_uniformity": rock_uniformity,
        "joint_degree": joint_degree,
        "rock_mass_state": rock_mass_state,
        "mud_filling_flag": 0,
        "stability": stability,
        "water_flag": 0,
        "water_type": None,
        "collapse_flag": collapse_flag,
        "deformation_flag": 0,
        "anomaly_level": anomaly_level,
        "risk_hint_text": risk_hint_text or None,
        "collapse_points": collapse_points,
        "risk_level": risk_level,
        "risk_tags": risk_tags,
    }

    raw_text = "\n".join([
        f"里程范围: {row_data.get('range', '')}",
        f"物探探测结果: {detect_text}",
        f"预报结论: {conclusion_text}",
        f"风险提示: {risk_hint_text}",
        f"建议围岩等级: {grade_text}",
    ]).strip()

    return EvidenceRecord(
        evidence_id=f"{meta['report_id']}_hsp_{idx}",
        source_type="sonic",
        source_level="segment",
        report_id=meta["report_id"],
        report_date=meta["report_date"],
        issue_date=meta["issue_date"],
        tunnel_name=meta["tunnel_name"],
        start_num=range_info["start_num"],
        end_num=range_info["end_num"],
        face_num=meta["face_num"],
        next_forecast_num=meta["next_forecast_num"],
        confidence="medium",
        attrs_json=json.dumps(_finalize_attrs(attrs), ensure_ascii=False),
        raw_text=raw_text,
    )


def parse_hsp_pdf(pdf_path: Path) -> List[EvidenceRecord]:
    """Parse one HSP PDF into EvidenceRecord list."""
    doc = fitz.open(pdf_path)
    try:
        text = "\n".join([p.get_text() for p in doc])
    finally:
        doc.close()

    meta = _extract_meta_from_text(text, pdf_path.name)

    records: List[EvidenceRecord] = []

    with pdfplumber.open(pdf_path) as pdf:
        idx = 0
        for page in pdf.pages:
            page_text = page.extract_text() or ""

            # 只看表1那页。
            if ("表 1" not in page_text and "表1" not in page_text) or "隧道超前地质预报报表" not in page_text:
                continue

            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                table_text = str(table)

                if "里程范围" not in table_text and "预报结论" not in table_text:
                    continue

                for row in table:
                    if not row:
                        continue

                    row = [("" if c is None else str(c)) for c in row]
                    joined = "".join(row)

                    if "里程范围" in joined and "预报结论" in joined:
                        continue
                    if "下一次超前预报里程" in joined:
                        continue
                    if "备注" in joined:
                        continue

                    picked = _pick_cells_from_row(row)
                    if not _is_valid_hsp_row(picked):
                        continue

                    rec = _parse_hsp_row_to_record(picked, meta, idx)
                    if rec is not None:
                        records.append(rec)
                        idx += 1

    return records