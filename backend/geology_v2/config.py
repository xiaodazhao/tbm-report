"""
geology_v2.config

地质融合 v2 的配置项。

注意：
1. 这里的权重是工程启发式初值，不是统计学习得到的真实准确率；
2. source_reliability 表示证据来源在融合中的相对可信度；
3. spatial_sigma 表示证据向周边 cell 扩散的空间尺度；
4. hazard_weights 表示不同 hazard 在地质关注度中的相对贡献；
5. GRCI 不能被解释为风险概率。
"""

from __future__ import annotations

from typing import Dict, Tuple


# ============================================================
# 1. 总体开关
# ============================================================

GEOLOGY_FUSION_VERSION = "v1"
# 后续第九阶段接入 services/tbm_analysis_service.py 时再改成：
# GEOLOGY_FUSION_VERSION = "v2"

DEFAULT_CELL_LENGTH_M = 10.0


# ============================================================
# 2. source_type 标准化
# ============================================================
# 旧 evidence_df 里可能出现 sketch / tsp / sonic / hsp 等写法。
# v2 统一成较清晰的 source_type_norm。
# ============================================================

SOURCE_TYPE_ALIASES: Dict[str, str] = {
    "sketch": "face_sketch",
    "face_sketch": "face_sketch",
    "face_observation": "face_sketch",

    "drill": "borehole",
    "borehole": "borehole",
    "advanced_borehole": "borehole",

    "tsp": "TSP",
    "TSP": "TSP",

    "sonic": "HSP",
    "hsp": "HSP",
    "HSP": "HSP",

    "report_conclusion": "report_conclusion",
    "conclusion": "report_conclusion",

    "overview": "overview",
    "background": "overview",
}


# ============================================================
# 3. 证据角色
# ============================================================
# observed:
#   现场直接揭示，例如掌子面素描、钻孔揭示。
# prediction:
#   超前预报类证据，例如 TSP、HSP。
# background:
#   报告概述、区域背景，只作为背景，不强逐里程融合。
# interpreted:
#   报告结论类解释证据。
# ============================================================

SOURCE_ROLE_MAP: Dict[str, str] = {
    "face_sketch": "observed",
    "borehole": "observed",
    "TSP": "prediction",
    "HSP": "prediction",
    "report_conclusion": "interpreted",
    "overview": "background",
}


# ============================================================
# 4. 来源可靠性权重
# ============================================================
# 初始工程经验值：
# - face_sketch / borehole 是现场揭示，可靠性较高；
# - TSP / HSP 是超前预报，可靠性中等偏高；
# - report_conclusion 是人工解释结论，较高但可能概括；
# - overview 只作为背景，权重低。
# ============================================================

SOURCE_RELIABILITY: Dict[str, float] = {
    "face_sketch": 1.20,
    "borehole": 1.15,
    "TSP": 0.95,
    "HSP": 0.90,
    "report_conclusion": 1.00,
    "overview": 0.35,
    "unknown": 0.60,
}


# ============================================================
# 5. source_level / spatial_type 权重
# ============================================================
# 这个权重不是最终风险分，只是证据强度的一部分。
# ============================================================

SOURCE_LEVEL_STRENGTH: Dict[str, float] = {
    "point": 1.10,
    "anomaly_point": 1.20,
    "segment": 1.00,
    "report_conclusion": 1.05,
    "overview": 0.40,
    "background": 0.35,
    "unknown": 0.70,
}


SPATIAL_TYPE_STRENGTH: Dict[str, float] = {
    "point": 1.10,
    "anomaly_point": 1.20,
    "segment": 1.00,
    "overview": 0.35,
    "background": 0.30,
    "unknown": 0.70,
}


# ============================================================
# 6. 置信度权重
# ============================================================

CONFIDENCE_WEIGHT: Dict[str, float] = {
    "high": 1.15,
    "medium": 1.00,
    "low": 0.80,
    "unknown": 0.75,
}


# ============================================================
# 7. 空间 sigma 配置
# ============================================================
# 用于后续 project_evidence_to_cells：
#
# spatial_weight = exp(-0.5 * (distance / sigma) ** 2)
#
# 解释：
# - 掌子面素描是点状实测，对近邻里程影响强，但不应无限扩展；
# - HSP/TSP 是超前预报区段，segment 内权重为 1，区间外按 sigma 衰减；
# - anomaly_point 更局部，sigma 较小；
# - overview 只作为背景，不强融合。
# ============================================================

DEFAULT_SPATIAL_SIGMA_M = 10.0

SPATIAL_SIGMA_BY_SOURCE: Dict[str, float] = {
    "face_sketch": 6.0,
    "borehole": 5.0,
    "TSP": 15.0,
    "HSP": 12.0,
    "report_conclusion": 10.0,
    "overview": 30.0,
    "unknown": DEFAULT_SPATIAL_SIGMA_M,
}

SPATIAL_SIGMA_BY_TYPE: Dict[str, float] = {
    "point": 6.0,
    "anomaly_point": 4.0,
    "segment": 12.0,
    "overview": 30.0,
    "background": 30.0,
    "unknown": DEFAULT_SPATIAL_SIGMA_M,
}

# 更细粒度配置：优先级最高。
# key = (source_type_norm, spatial_type)
SPATIAL_SIGMA_BY_SOURCE_AND_TYPE: Dict[Tuple[str, str], float] = {
    ("face_sketch", "point"): 5.0,
    ("borehole", "point"): 4.0,
    ("HSP", "segment"): 12.0,
    ("HSP", "anomaly_point"): 4.0,
    ("TSP", "segment"): 15.0,
    ("TSP", "report_conclusion"): 12.0,
    ("report_conclusion", "segment"): 10.0,
    ("overview", "overview"): 30.0,
}


# ============================================================
# 8. hazard 权重
# ============================================================
# 这些权重后续用于 hazard_scores 计算。
# 注意：这是地质关注度权重，不是事故概率。
# ============================================================

HAZARD_WEIGHTS: Dict[str, float] = {
    "water": 0.35,
    "water_inrush": 0.45,
    "collapse": 0.40,
    "block_fall": 0.35,
    "deformation": 0.30,
    "fractured_rock": 0.30,
    "extremely_fractured_rock": 0.40,
    "joint_development": 0.25,
    "dense_joints": 0.35,
    "weak_interlayer": 0.30,
    "mud_filling": 0.30,
    "soft_hard_uneven": 0.25,
    "reflection_anomaly": 0.25,
    "strong_reflection_anomaly": 0.35,
    "poor_stability": 0.35,
}


HAZARD_TAG_ALIASES: Dict[str, str] = {
    "出水": "water",
    "渗水": "water",
    "线状出水": "water",
    "股状出水": "water",
    "线-股状出水": "water_inrush",
    "涌水": "water_inrush",
    "突水": "water_inrush",

    "掉块": "block_fall",
    "掉块风险": "block_fall",
    "坍塌": "collapse",
    "塌方": "collapse",

    "变形": "deformation",
    "大变形": "deformation",

    "围岩破碎": "fractured_rock",
    "岩体破碎": "fractured_rock",
    "围岩极破碎": "extremely_fractured_rock",
    "破碎-极破碎": "extremely_fractured_rock",

    "裂隙发育": "joint_development",
    "节理裂隙发育": "joint_development",
    "裂隙密集": "dense_joints",
    "节理裂隙发育密集": "dense_joints",

    "泥质填充": "mud_filling",
    "软硬不均": "soft_hard_uneven",

    "反射异常": "reflection_anomaly",
    "较明显反射异常": "reflection_anomaly",
    "明显反射异常": "strong_reflection_anomaly",

    "稳定性较差": "poor_stability",
    "自稳性较差": "poor_stability",
}


# ============================================================
# 9. 围岩等级分值
# ============================================================
# 后续 GRS_geo_base 会用它作为地质基础关注度的一部分。
# ============================================================

GRADE_ATTENTION_SCORE: Dict[str, float] = {
    "Ⅰ": 0.05,
    "Ⅱ": 0.20,
    "Ⅲ": 0.40,
    "Ⅳ": 0.70,
    "Ⅴ": 1.00,
    "I": 0.05,
    "II": 0.20,
    "III": 0.40,
    "IV": 0.70,
    "V": 1.00,
    "1": 0.05,
    "2": 0.20,
    "3": 0.40,
    "4": 0.70,
    "5": 1.00,
}


GRADE_ORDER: Dict[str, int] = {
    "Ⅰ": 1,
    "Ⅱ": 2,
    "Ⅲ": 3,
    "Ⅳ": 4,
    "Ⅴ": 5,
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
}


# ============================================================
# 10. confidence / uncertainty 阈值
# ============================================================

CONFIDENCE_THRESHOLDS: Dict[str, float] = {
    "high": 0.75,
    "medium": 0.45,
    "low": 0.20,
}

UNCERTAINTY_THRESHOLDS: Dict[str, float] = {
    "low": 0.25,
    "medium": 0.50,
    "high": 0.75,
}

CONFLICT_THRESHOLDS: Dict[str, float] = {
    "low": 0.25,
    "medium": 0.50,
    "high": 0.75,
}


# ============================================================
# 11. 前方关注等级阈值
# ============================================================

ATTENTION_LEVEL_THRESHOLDS: Dict[str, float] = {
    "low": 0.25,
    "medium": 0.50,
    "high": 0.75,
}


def normalize_source_type(source_type: str | None) -> str:
    """
    Normalize raw source_type into v2 canonical source type.
    """
    if source_type is None:
        return "unknown"

    raw = str(source_type).strip()
    if not raw:
        return "unknown"

    return SOURCE_TYPE_ALIASES.get(raw, SOURCE_TYPE_ALIASES.get(raw.lower(), raw))


def get_source_reliability(source_type_norm: str | None) -> float:
    """
    Return reliability weight for normalized source type.
    """
    key = source_type_norm or "unknown"
    return float(SOURCE_RELIABILITY.get(key, SOURCE_RELIABILITY["unknown"]))


def get_spatial_sigma(source_type_norm: str | None, spatial_type: str | None) -> float:
    """
    Return spatial sigma by:
    1. source_type + spatial_type pair;
    2. spatial_type;
    3. source_type;
    4. default.
    """
    source_key = source_type_norm or "unknown"
    spatial_key = spatial_type or "unknown"

    if (source_key, spatial_key) in SPATIAL_SIGMA_BY_SOURCE_AND_TYPE:
        return float(SPATIAL_SIGMA_BY_SOURCE_AND_TYPE[(source_key, spatial_key)])

    if spatial_key in SPATIAL_SIGMA_BY_TYPE:
        return float(SPATIAL_SIGMA_BY_TYPE[spatial_key])

    if source_key in SPATIAL_SIGMA_BY_SOURCE:
        return float(SPATIAL_SIGMA_BY_SOURCE[source_key])

    return float(DEFAULT_SPATIAL_SIGMA_M)


def normalize_hazard_tag(tag: str | None) -> str | None:
    """
    Normalize Chinese/raw hazard tag into canonical hazard key.
    """
    if tag is None:
        return None

    text = str(tag).strip()
    if not text:
        return None

    return HAZARD_TAG_ALIASES.get(text, text)


def get_hazard_weight(hazard_key: str | None) -> float:
    """
    Return hazard weight for canonical hazard key.
    """
    if hazard_key is None:
        return 0.0
    return float(HAZARD_WEIGHTS.get(str(hazard_key).strip(), 0.0))