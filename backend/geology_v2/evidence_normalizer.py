"""
geology_v2.evidence_normalizer

把旧 evidence_df 标准化为 geology_v2 使用的 normalized_evidence_df。

本模块只做“证据标准化”，不做 cell 构建、不做空间投影、不做融合。
后续流程应为：

evidence_df
  -> normalize_evidence_df
  -> build_chainage_cells
  -> project_evidence_to_cells
  -> fuse_geo_states
  -> build_forward_profile

设计原则：
1. 不修改旧 evidence_df；
2. 不删除旧字段；
3. 解析失败不抛异常，保留 parse_warnings；
4. overview / background 不参与强逐里程融合；
5. HSP collapse_points 拆成 anomaly_point；
6. 所有输出尽量 JSON 可序列化。
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from geology_v2.config import (
    CONFIDENCE_WEIGHT,
    SOURCE_LEVEL_STRENGTH,
    SOURCE_ROLE_MAP,
    SPATIAL_TYPE_STRENGTH,
    get_source_reliability,
    normalize_hazard_tag,
    normalize_source_type,
)


# ============================================================
# 1. 输出字段定义
# ============================================================

NORMALIZED_EVIDENCE_COLUMNS = [
    "evidence_id",
    "report_id",

    "source_type_raw",
    "source_type_norm",
    "evidence_role",
    "source_level",
    "spatial_type",

    "start_chainage",
    "end_chainage",
    "center_chainage",
    "face_chainage",

    "grade",
    "lithology",
    "weathering",
    "joint_development",
    "rock_mass_state",
    "stability",

    "water_flag",
    "water_type",
    "collapse_flag",
    "deformation_flag",

    "hazard_tags",

    "source_reliability",
    "evidence_strength",
    "confidence_text",

    "raw_text",
    "attrs_obj",
    "parse_warnings",
]


# ============================================================
# 2. 基础安全工具
# ============================================================

def _is_missing(value: Any) -> bool:
    """
    判断一个值是否为空。

    pandas 的 NaN / None / 空字符串都视为 missing。
    """
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _safe_str(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    return str(value).strip()


def _safe_float(value: Any) -> Optional[float]:
    """
    将 value 安全转为 float。
    转换失败返回 None。
    """
    if _is_missing(value):
        return None
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        return None
    return None


def _safe_int_flag(value: Any) -> int:
    """
    将各种 flag 安全转为 0/1。
    """
    if _is_missing(value):
        return 0

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        try:
            return 1 if float(value) != 0 else 0
        except Exception:
            return 0

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "有", "是", "存在"}:
        return 1
    if text in {"0", "false", "no", "n", "无", "否", "不存在"}:
        return 0

    return 0


def _safe_json_loads(value: Any) -> tuple[Dict[str, Any], List[str]]:
    """
    安全解析 attrs_json。

    返回：
    - attrs_obj
    - parse_warnings

    注意：
    attrs_json 解析失败时不报错，只保留 warning。
    """
    warnings: List[str] = []

    if _is_missing(value):
        return {}, []

    if isinstance(value, dict):
        return dict(value), []

    text = str(value).strip()
    if not text:
        return {}, []

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, []
        warnings.append("attrs_json parsed but is not a dict")
        return {}, warnings
    except Exception as exc:
        warnings.append(f"attrs_json_parse_failed: {exc}")
        return {}, warnings


def _first_non_empty(*values: Any) -> Any:
    """
    返回第一个非空值。
    """
    for value in values:
        if not _is_missing(value):
            return value
    return None


def _dedup_keep_order(items: Iterable[Any]) -> List[str]:
    """
    去重但保持顺序。
    """
    out: List[str] = []
    seen = set()

    for item in items:
        if _is_missing(item):
            continue
        text = str(item).strip()
        if not text:
            continue
        if text not in seen:
            out.append(text)
            seen.add(text)

    return out


def _jsonable_attrs(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    轻量清洗 attrs_obj，确保尽量可 JSON 序列化。

    这里只做保守处理：
    - dict/list/str/int/float/bool/None 原样保留；
    - 其他对象转字符串。
    """
    out: Dict[str, Any] = {}

    for key, value in dict(attrs or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = [
                item if isinstance(item, (str, int, float, bool)) or item is None else str(item)
                for item in value
            ]
        elif isinstance(value, dict):
            nested = {}
            for k2, v2 in value.items():
                if isinstance(v2, (str, int, float, bool)) or v2 is None:
                    nested[str(k2)] = v2
                else:
                    nested[str(k2)] = str(v2)
            out[str(key)] = nested
        else:
            out[str(key)] = str(value)

    return out


# ============================================================
# 3. 字段推断
# ============================================================

def _infer_evidence_role(source_type_norm: str, source_level: str, attrs: Dict[str, Any]) -> str:
    """
    推断 evidence_role。

    优先级：
    1. overview/background -> background
    2. config.SOURCE_ROLE_MAP
    3. fact_type/source_semantics 辅助判断
    """
    level = _safe_str(source_level).lower()

    if level in {"overview", "background"}:
        return "background"

    fact_type = _safe_str(attrs.get("fact_type")).lower()
    semantics = _safe_str(attrs.get("source_semantics")).lower()

    if "overview" in fact_type or "overview" in semantics:
        return "background"

    if "sketch" in fact_type or "observation" in fact_type:
        return "observed"

    if "conclusion" in fact_type or "conclusion" in semantics:
        return "interpreted"

    return SOURCE_ROLE_MAP.get(source_type_norm, "unknown")


def _infer_spatial_type(source_type_norm: str, source_level: str, attrs: Dict[str, Any]) -> str:
    """
    推断空间类型。

    输出：
    - point
    - anomaly_point
    - segment
    - overview
    - background
    - unknown
    """
    level = _safe_str(source_level).lower()
    fact_type = _safe_str(attrs.get("fact_type")).lower()

    if level in {"overview", "background"}:
        return "overview"

    if "overview" in fact_type:
        return "overview"

    if level == "point":
        return "point"

    if level in {"segment", "report_conclusion"}:
        return "segment"

    if "segment" in fact_type or "table" in fact_type:
        return "segment"

    if "conclusion" in fact_type:
        return "segment"

    if source_type_norm == "face_sketch":
        return "point"

    return "unknown"


def _normalize_chainage_interval(
    start_num: Any,
    end_num: Any,
    face_num: Any,
    spatial_type: str,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    统一里程字段。

    返回：
    - start_chainage
    - end_chainage
    - center_chainage
    - face_chainage
    """
    start_chainage = _safe_float(start_num)
    end_chainage = _safe_float(end_num)
    face_chainage = _safe_float(face_num)

    if start_chainage is not None and end_chainage is None:
        end_chainage = start_chainage
    if end_chainage is not None and start_chainage is None:
        start_chainage = end_chainage

    if start_chainage is not None and end_chainage is not None:
        if start_chainage > end_chainage:
            start_chainage, end_chainage = end_chainage, start_chainage

    if spatial_type == "point":
        point = _first_non_empty(face_chainage, start_chainage, end_chainage)
        point = _safe_float(point)
        start_chainage = point
        end_chainage = point
        center_chainage = point
        if face_chainage is None:
            face_chainage = point
        return start_chainage, end_chainage, center_chainage, face_chainage

    if start_chainage is not None and end_chainage is not None:
        center_chainage = 0.5 * (start_chainage + end_chainage)
    else:
        center_chainage = _safe_float(_first_non_empty(face_chainage, start_chainage, end_chainage))

    return start_chainage, end_chainage, center_chainage, face_chainage


def _normalize_grade(attrs: Dict[str, Any]) -> Optional[str]:
    """
    统一围岩等级字段。

    旧 parser 中常见字段：
    - support_grade
    - support_grade_final
    - grade
    - fused_grade
    """
    value = _first_non_empty(
        attrs.get("support_grade_final"),
        attrs.get("support_grade"),
        attrs.get("grade"),
        attrs.get("fused_grade"),
        attrs.get("rock_grade"),
    )
    if _is_missing(value):
        return None
    return str(value).strip()


def _normalize_lithology(attrs: Dict[str, Any]) -> Optional[str]:
    value = _first_non_empty(attrs.get("lithology"), attrs.get("rock_name"), attrs.get("岩性"))
    return None if _is_missing(value) else str(value).strip()


def _normalize_weathering(attrs: Dict[str, Any]) -> Optional[str]:
    value = _first_non_empty(attrs.get("weathering"), attrs.get("weathering_degree"), attrs.get("风化程度"))
    return None if _is_missing(value) else str(value).strip()


def _normalize_joint_development(attrs: Dict[str, Any]) -> Optional[str]:
    value = _first_non_empty(
        attrs.get("joint_development"),
        attrs.get("joint_degree"),
        attrs.get("joint_state"),
        attrs.get("裂隙发育"),
    )
    return None if _is_missing(value) else str(value).strip()


def _normalize_rock_mass_state(attrs: Dict[str, Any]) -> Optional[str]:
    value = _first_non_empty(
        attrs.get("rock_mass_state"),
        attrs.get("rockmass_state"),
        attrs.get("rock_mass_integrity"),
        attrs.get("岩体状态"),
    )
    return None if _is_missing(value) else str(value).strip()


def _normalize_stability(attrs: Dict[str, Any]) -> Optional[str]:
    value = _first_non_empty(attrs.get("stability"), attrs.get("self_stability"), attrs.get("稳定性"))
    return None if _is_missing(value) else str(value).strip()


def _normalize_hazard_tags(attrs: Dict[str, Any]) -> List[str]:
    """
    统一 hazard_tags。

    来源：
    1. attrs.risk_tags
    2. attrs.hazard_tags
    3. water/collapse/deformation flags
    4. joint/rock_mass/stability 等描述
    """
    tags: List[Any] = []

    for key in ["risk_tags", "hazard_tags", "source_risk_tags"]:
        value = attrs.get(key)
        if isinstance(value, list):
            tags.extend(value)
        elif not _is_missing(value):
            tags.append(value)

    water_flag = _safe_int_flag(attrs.get("water_flag"))
    water_type = attrs.get("water_type")
    collapse_flag = _safe_int_flag(attrs.get("collapse_flag"))
    deformation_flag = _safe_int_flag(attrs.get("deformation_flag"))

    if water_type:
        tags.append(water_type)
    elif water_flag:
        tags.append("出水")

    if collapse_flag:
        tags.append("掉块")

    if deformation_flag:
        tags.append("变形")

    joint = _normalize_joint_development(attrs)
    if joint:
        if "密集" in joint:
            tags.append("裂隙密集")
        elif "发育" in joint:
            tags.append("裂隙发育")

    rock_mass = _normalize_rock_mass_state(attrs)
    if rock_mass:
        if "极破碎" in rock_mass:
            tags.append("围岩极破碎")
        elif "破碎" in rock_mass:
            tags.append("围岩破碎")

    if _safe_int_flag(attrs.get("mud_filling_flag")):
        tags.append("泥质填充")

    rock_uniformity = attrs.get("rock_uniformity")
    if not _is_missing(rock_uniformity) and "软硬不均" in str(rock_uniformity):
        tags.append("软硬不均")

    stability = _normalize_stability(attrs)
    if stability and "差" in stability:
        tags.append("稳定性较差")

    anomaly_level = _safe_str(attrs.get("anomaly_level"))
    if anomaly_level == "strong":
        tags.append("明显反射异常")
    elif anomaly_level == "medium":
        tags.append("较明显反射异常")

    # 先保留中文标签，后续 fusion_engine 里再映射成 canonical hazard key。
    # 这里额外调用 normalize_hazard_tag 是为了过滤空值，同时检查 config 中是否已有别名。
    out = []
    for tag in _dedup_keep_order(tags):
        normalized = normalize_hazard_tag(tag)
        out.append(str(tag if normalized is not None else tag))

    return _dedup_keep_order(out)


def _normalize_confidence_text(value: Any) -> str:
    text = _safe_str(value, default="unknown").lower()
    if text in {"high", "medium", "low"}:
        return text
    if text in {"高", "较高"}:
        return "high"
    if text in {"中", "中等", "一般"}:
        return "medium"
    if text in {"低", "较低"}:
        return "low"
    return "unknown"


def _compute_evidence_strength(
    source_level: str,
    spatial_type: str,
    confidence_text: str,
    attrs: Dict[str, Any],
) -> float:
    """
    计算证据强度。

    注意：
    evidence_strength 是融合权重的一部分，不是风险概率。
    """
    level_key = _safe_str(source_level, default="unknown")
    spatial_key = _safe_str(spatial_type, default="unknown")
    conf_key = _safe_str(confidence_text, default="unknown")

    level_weight = float(SOURCE_LEVEL_STRENGTH.get(level_key, SOURCE_LEVEL_STRENGTH["unknown"]))
    spatial_weight = float(SPATIAL_TYPE_STRENGTH.get(spatial_key, SPATIAL_TYPE_STRENGTH["unknown"]))
    confidence_weight = float(CONFIDENCE_WEIGHT.get(conf_key, CONFIDENCE_WEIGHT["unknown"]))

    # 如果 parser 认为是 high risk，不直接当成概率，只轻微提高证据强度；
    # 真实 hazard 分数在 fusion_engine 阶段再算。
    risk_level = _safe_str(attrs.get("risk_level"), default="").lower()
    if risk_level == "high":
        risk_hint_weight = 1.10
    elif risk_level == "medium":
        risk_hint_weight = 1.00
    elif risk_level == "low":
        risk_hint_weight = 0.90
    else:
        risk_hint_weight = 1.00

    value = level_weight * spatial_weight * confidence_weight * risk_hint_weight
    return float(max(0.0, min(value, 2.0)))


# ============================================================
# 4. HSP anomaly_point 拆分
# ============================================================

def _resolve_collapse_point_chainage(
    point_value: Any,
    start_chainage: Optional[float],
    end_chainage: Optional[float],
) -> Optional[float]:
    """
    将 HSP collapse_points 中的点位转换为完整里程。

    旧 hsp_parser 里 collapse_points 可能来自文本中的 '+190.2'，
    这类值可能只保存为 190.2，而不是 1013190.2。

    处理策略：
    1. 如果 point_value 本身已经像完整里程，例如 > 10000，直接使用；
    2. 如果 point_value 较小，且 start_chainage 可用，则使用 start_chainage 的千米段补齐；
       例如 start=1013180.2, point=190.2 -> 1013190.2。
    """
    point = _safe_float(point_value)
    if point is None:
        return None

    if abs(point) >= 10000:
        return point

    base = _safe_float(start_chainage)
    if base is None:
        base = _safe_float(end_chainage)

    if base is None:
        return point

    # 以 1000m 为一个桩号千米段补齐。
    km_base = math.floor(base / 1000.0) * 1000.0
    candidate = km_base + point

    # 如果 candidate 明显落在 segment 外太远，尝试用 end 的千米段。
    end_base = _safe_float(end_chainage)
    if end_base is not None:
        min_bound = min(base, end_base) - 50.0
        max_bound = max(base, end_base) + 50.0
        if not (min_bound <= candidate <= max_bound):
            km_base_2 = math.floor(end_base / 1000.0) * 1000.0
            candidate_2 = km_base_2 + point
            if min_bound <= candidate_2 <= max_bound:
                candidate = candidate_2

    return float(candidate)


def _iter_hsp_anomaly_points(normalized_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    如果一条 HSP segment 证据中 attrs_obj.collapse_points 非空，
    则拆出若干 anomaly_point 证据。

    anomaly_point 证据会继承原证据的大部分属性，但：
    - evidence_id 追加 _collapse_point_i
    - spatial_type = anomaly_point
    - start/end/center_chainage = point_chainage
    - collapse_flag = 1
    - hazard_tags 至少包含 掉块
    """
    attrs = normalized_row.get("attrs_obj") or {}
    source_type_norm = normalized_row.get("source_type_norm")

    if source_type_norm != "HSP":
        return []

    collapse_points = attrs.get("collapse_points", [])
    if not isinstance(collapse_points, list) or not collapse_points:
        return []

    out: List[Dict[str, Any]] = []

    for idx, point_value in enumerate(collapse_points):
        point_chainage = _resolve_collapse_point_chainage(
            point_value=point_value,
            start_chainage=normalized_row.get("start_chainage"),
            end_chainage=normalized_row.get("end_chainage"),
        )
        if point_chainage is None:
            continue

        item = dict(normalized_row)
        item["evidence_id"] = f"{normalized_row.get('evidence_id')}_collapse_point_{idx}"
        item["spatial_type"] = "anomaly_point"
        item["evidence_role"] = "prediction"
        item["source_level"] = "anomaly_point"

        item["start_chainage"] = point_chainage
        item["end_chainage"] = point_chainage
        item["center_chainage"] = point_chainage

        item["collapse_flag"] = 1
        item["hazard_tags"] = _dedup_keep_order(list(item.get("hazard_tags") or []) + ["掉块"])

        item_attrs = dict(attrs)
        item_attrs["parent_evidence_id"] = normalized_row.get("evidence_id")
        item_attrs["anomaly_point_type"] = "collapse_point"
        item_attrs["anomaly_point_raw_value"] = point_value
        item_attrs["anomaly_point_chainage"] = point_chainage
        item["attrs_obj"] = _jsonable_attrs(item_attrs)

        # anomaly point 的局部性更强，证据强度略增。
        item["evidence_strength"] = float(max(item.get("evidence_strength", 0.0), 1.20))

        out.append(item)

    return out


# ============================================================
# 5. 单行标准化
# ============================================================

def _normalize_one_row(row: pd.Series, row_idx: int) -> Dict[str, Any]:
    """
    将旧 evidence_df 中的一行转换为 normalized evidence dict。
    """
    attrs_obj, parse_warnings = _safe_json_loads(row.get("attrs_json"))

    # 兼容 attrs_obj 中已有 parse_warnings。
    existing_warnings = attrs_obj.get("parse_warnings")
    if isinstance(existing_warnings, list):
        parse_warnings.extend([str(x) for x in existing_warnings if not _is_missing(x)])

    source_type_raw = _safe_str(row.get("source_type"), default="unknown")
    source_type_norm = normalize_source_type(source_type_raw)

    source_level = _safe_str(row.get("source_level"), default="unknown")
    evidence_role = _infer_evidence_role(source_type_norm, source_level, attrs_obj)
    spatial_type = _infer_spatial_type(source_type_norm, source_level, attrs_obj)

    # overview 不强逐里程融合。
    if evidence_role == "background" or spatial_type == "overview":
        spatial_type = "overview"
        evidence_role = "background"

    start_chainage, end_chainage, center_chainage, face_chainage = _normalize_chainage_interval(
        start_num=row.get("start_num"),
        end_num=row.get("end_num"),
        face_num=row.get("face_num"),
        spatial_type=spatial_type,
    )

    confidence_text = _normalize_confidence_text(row.get("confidence"))

    grade = _normalize_grade(attrs_obj)
    lithology = _normalize_lithology(attrs_obj)
    weathering = _normalize_weathering(attrs_obj)
    joint_development = _normalize_joint_development(attrs_obj)
    rock_mass_state = _normalize_rock_mass_state(attrs_obj)
    stability = _normalize_stability(attrs_obj)

    water_flag = _safe_int_flag(attrs_obj.get("water_flag"))
    water_type = None if _is_missing(attrs_obj.get("water_type")) else str(attrs_obj.get("water_type")).strip()
    collapse_flag = _safe_int_flag(attrs_obj.get("collapse_flag"))
    deformation_flag = _safe_int_flag(attrs_obj.get("deformation_flag"))

    hazard_tags = _normalize_hazard_tags(attrs_obj)

    source_reliability = get_source_reliability(source_type_norm)
    evidence_strength = _compute_evidence_strength(
        source_level=source_level,
        spatial_type=spatial_type,
        confidence_text=confidence_text,
        attrs=attrs_obj,
    )

    # background / overview 证据保留，但降低强逐里程融合影响。
    if evidence_role == "background" or spatial_type == "overview":
        source_reliability = min(source_reliability, 0.35)
        evidence_strength = min(evidence_strength, 0.40)

    evidence_id = _safe_str(row.get("evidence_id"))
    if not evidence_id:
        evidence_id = f"evidence_{row_idx}"

    normalized = {
        "evidence_id": evidence_id,
        "report_id": None if _is_missing(row.get("report_id")) else str(row.get("report_id")).strip(),

        "source_type_raw": source_type_raw,
        "source_type_norm": source_type_norm,
        "evidence_role": evidence_role,
        "source_level": source_level,
        "spatial_type": spatial_type,

        "start_chainage": start_chainage,
        "end_chainage": end_chainage,
        "center_chainage": center_chainage,
        "face_chainage": face_chainage,

        "grade": grade,
        "lithology": lithology,
        "weathering": weathering,
        "joint_development": joint_development,
        "rock_mass_state": rock_mass_state,
        "stability": stability,

        "water_flag": int(water_flag),
        "water_type": water_type,
        "collapse_flag": int(collapse_flag),
        "deformation_flag": int(deformation_flag),

        "hazard_tags": hazard_tags,

        "source_reliability": float(source_reliability),
        "evidence_strength": float(evidence_strength),
        "confidence_text": confidence_text,

        "raw_text": None if _is_missing(row.get("raw_text")) else str(row.get("raw_text")),
        "attrs_obj": _jsonable_attrs(attrs_obj),
        "parse_warnings": _dedup_keep_order(parse_warnings),
    }

    return normalized


# ============================================================
# 6. 主函数
# ============================================================

def normalize_evidence_df(evidence_df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化旧 evidence_df。

    输入字段可能包括：
    - evidence_id
    - source_type
    - source_level
    - report_id
    - start_num
    - end_num
    - face_num
    - confidence
    - attrs_json
    - raw_text

    输出字段至少包括 NORMALIZED_EVIDENCE_COLUMNS。

    注意：
    1. 不会修改原始 evidence_df；
    2. attrs_json 解析失败不报错；
    3. sketch -> face_sketch；
    4. tsp -> TSP；
    5. sonic/hsp -> HSP；
    6. overview -> background / overview；
    7. HSP collapse_points 会额外拆成 anomaly_point。
    """
    if evidence_df is None or evidence_df.empty:
        return pd.DataFrame(columns=NORMALIZED_EVIDENCE_COLUMNS)

    records: List[Dict[str, Any]] = []

    df = evidence_df.copy()

    # 确保常用列存在，避免 row.get 不稳定。
    for col in [
        "evidence_id",
        "source_type",
        "source_level",
        "report_id",
        "start_num",
        "end_num",
        "face_num",
        "confidence",
        "attrs_json",
        "raw_text",
    ]:
        if col not in df.columns:
            df[col] = None

    for idx, row in df.iterrows():
        normalized = _normalize_one_row(row, row_idx=int(idx) if isinstance(idx, int) else len(records))
        records.append(normalized)

        # HSP collapse_points 拆出 anomaly_point。
        anomaly_points = _iter_hsp_anomaly_points(normalized)
        records.extend(anomaly_points)

    out = pd.DataFrame(records)

    # 补齐列并排序。
    for col in NORMALIZED_EVIDENCE_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[NORMALIZED_EVIDENCE_COLUMNS].copy()

    # 数值字段统一转换，避免后续 projector 出现 object 类型问题。
    numeric_cols = [
        "start_chainage",
        "end_chainage",
        "center_chainage",
        "face_chainage",
        "source_reliability",
        "evidence_strength",
        "water_flag",
        "collapse_flag",
        "deformation_flag",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # flag 空值填 0。
    for col in ["water_flag", "collapse_flag", "deformation_flag"]:
        out[col] = out[col].fillna(0).astype(int)

    # object 列中的 list/dict 保持原样，后续统一由 serialize_for_json 处理。
    return out


# ============================================================
# 7. 便捷检查函数，可选使用
# ============================================================

def summarize_normalized_evidence(normalized_df: pd.DataFrame) -> Dict[str, Any]:
    """
    对 normalized_evidence_df 做一个轻量摘要。

    这个函数不是主流程必需，只用于调试第二阶段是否正常。
    """
    if normalized_df is None or normalized_df.empty:
        return {
            "evidence_count": 0,
            "source_type_counts": {},
            "spatial_type_counts": {},
            "role_counts": {},
            "anomaly_point_count": 0,
            "parse_warning_count": 0,
        }

    warning_count = 0
    if "parse_warnings" in normalized_df.columns:
        for item in normalized_df["parse_warnings"].tolist():
            if isinstance(item, list) and item:
                warning_count += 1

    return {
        "evidence_count": int(len(normalized_df)),
        "source_type_counts": normalized_df["source_type_norm"].value_counts(dropna=False).to_dict()
        if "source_type_norm" in normalized_df.columns else {},
        "spatial_type_counts": normalized_df["spatial_type"].value_counts(dropna=False).to_dict()
        if "spatial_type" in normalized_df.columns else {},
        "role_counts": normalized_df["evidence_role"].value_counts(dropna=False).to_dict()
        if "evidence_role" in normalized_df.columns else {},
        "anomaly_point_count": int((normalized_df.get("spatial_type") == "anomaly_point").sum())
        if "spatial_type" in normalized_df.columns else 0,
        "parse_warning_count": int(warning_count),
    }