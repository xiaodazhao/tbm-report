# geology/fusion.py
import json
import re
import pandas as pd
from config import TOLERANCE_M


GRADE_ORDER = {
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
}


def get_active(chainage, evidence, point_buffer=5.0):
    """
    获取当前里程命中的所有地质证据。

    参数：
        chainage:
            当前 TBM/PLC 记录对应的里程值。

        evidence:
            地质证据库表，每一行是一条地质证据。
            通常包含 start_num、end_num、source_level、source_type、attrs_json 等字段。

        point_buffer:
            点状证据的匹配缓冲范围，单位为米。
            例如掌子面素描是一个点位，不是区间，因此允许前后一定范围内匹配。

    匹配规则：
        1. segment / report_conclusion：
           按 start_num ~ end_num 区间匹配，并加入 TOLERANCE_M 容差。

        2. point：
           按点位前后 point_buffer 米进行缓冲匹配。

    返回：
        当前 chainage 命中的所有地质证据 hit_df。
    """

    # 1. 如果证据库为空，则当前里程没有可匹配的地质证据
    if evidence is None or evidence.empty:
        return evidence

    # 2. 兼容旧版 evidence 表
    # 如果没有 source_level 字段，则默认所有证据都是区间证据，
    # 直接按照 start_num ~ end_num 区间进行匹配。
    if "source_level" not in evidence.columns:
        return evidence[
            (evidence["start_num"] - TOLERANCE_M <= chainage) &
            (evidence["end_num"] + TOLERANCE_M >= chainage)
        ]

    # 3. 将证据分成两类：
    #    - seg_df：区间型证据，包括 segment、report_conclusion 等
    #    - point_df：点状证据，例如掌子面素描、现场点位观测等
    seg_df = evidence[evidence["source_level"] != "point"].copy()
    point_df = evidence[evidence["source_level"] == "point"].copy()

    # 4. 区间型证据匹配
    # 当前 chainage 落在 start_num ~ end_num 范围内，则认为命中。
    # TOLERANCE_M 用于处理里程解析误差或数据对齐误差。
    hit_seg = seg_df[
        (seg_df["start_num"] - TOLERANCE_M <= chainage) &
        (seg_df["end_num"] + TOLERANCE_M >= chainage)
    ]

    # 5. 点状证据匹配
    # 点状证据没有严格区间，因此使用 point_buffer 做前后缓冲。
    # 例如掌子面素描点位前后 5 m 内都认为可以参考。
    hit_point = point_df[
        (point_df["start_num"] - point_buffer <= chainage) &
        (point_df["end_num"] + point_buffer >= chainage)
    ]

    # 6. 将区间命中的证据和点位缓冲命中的证据合并返回
    return pd.concat([hit_seg, hit_point], ignore_index=True)

def normalize_report_id(report_id: str) -> str:
    """
    规范化报告ID，避免同一报告因命名差异被重复统计
    """
    if pd.isna(report_id):
        return ""

    report_id = str(report_id).strip()
    report_id = re.sub(r"_[0-9]+$", "", report_id)
    report_id = report_id.replace("-_", "_")
    report_id = re.sub(r"[-_]+", "_", report_id)
    report_id = report_id.rstrip("_")
    return report_id


def _safe_load_attrs(attrs_json_str):
    """Safely load serialized evidence attributes."""
    try:
        data = json.loads(attrs_json_str)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_grade(x):
    """
    统一围岩等级字段
    """
    if x is None:
        return None

    x = str(x).strip()
    if not x:
        return None

    mapping = {
        "1": "Ⅰ",
        "2": "Ⅱ",
        "3": "Ⅲ",
        "4": "Ⅳ",
        "5": "Ⅴ",
        "I": "Ⅰ",
        "II": "Ⅱ",
        "III": "Ⅲ",
        "IV": "Ⅳ",
        "V": "Ⅴ",
        "Ⅰ": "Ⅰ",
        "Ⅱ": "Ⅱ",
        "Ⅲ": "Ⅲ",
        "Ⅳ": "Ⅳ",
        "Ⅴ": "Ⅴ",
    }
    return mapping.get(x, x)


def _record_weight(row, attrs):
    """
    这里只作为“证据强度/可信度”的权重，不再用于风险评定
    """
    weight = 1.0

    source_level = str(row.get("source_level", "")).strip()
    confidence = str(row.get("confidence", "")).strip().lower()

    if source_level == "report_conclusion":
        weight *= 1.20
    elif source_level == "segment":
        weight *= 1.00
    elif source_level == "point":
        weight *= 1.10

    if confidence == "high":
        weight *= 1.15
    elif confidence == "medium":
        weight *= 1.00
    elif confidence == "low":
        weight *= 0.90

    if attrs.get("consistency_flag") == 0:
        weight *= 0.90
    if attrs.get("grade_conflict") == 1:
        weight *= 0.95

    return weight


def _pick_mode(values):
    """Internal helper for pick mode."""
    values = [v for v in values if v not in [None, "", [], {}]]
    if not values:
        return None
    s = pd.Series(values)
    mode = s.mode()
    if len(mode) == 0:
        return values[0]
    return mode.iloc[0]


def _pick_worst_grade(grades):
    """Internal helper for pick worst grade."""
    grades = [_normalize_grade(g) for g in grades if g]
    if not grades:
        return ""
    return sorted(
        grades,
        key=lambda x: GRADE_ORDER.get(str(x), 0),
        reverse=True
    )[0]


def _dedup_preserve_order(items):
    """Internal helper for dedup preserve order."""
    out = []
    seen = set()
    for x in items:
        if x in [None, ""]:
            continue
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _merge_hazard_tags(parsed_rows):
    """Internal helper for merge hazard tags."""
    hazard_set = []

    for row, attrs in parsed_rows:
        water_type = attrs.get("water_type")
        if water_type:
            hazard_set.append(str(water_type))
        elif attrs.get("water_flag"):
            hazard_set.append("出水")

        if attrs.get("collapse_flag"):
            hazard_set.append("掉块")

        if attrs.get("deformation_flag"):
            hazard_set.append("变形")

        tags = attrs.get("risk_tags", [])
        if isinstance(tags, list):
            for t in tags:
                if t:
                    hazard_set.append(str(t))

    hazard_list = _dedup_preserve_order(hazard_set)
    return hazard_list, "+".join(hazard_list) if hazard_list else "无明显异常"


def _merge_water_type(parsed_rows):
    """Internal helper for merge water type."""
    vals = []
    for _, attrs in parsed_rows:
        x = attrs.get("water_type")
        if x:
            vals.append(str(x))
    vals = _dedup_preserve_order(vals)
    return ";".join(vals) if vals else None


def _weighted_mean(values, weights):
    """Internal helper for weighted mean."""
    pairs = [(v, w) for v, w in zip(values, weights) if v is not None]
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    return round(sum(v * w for v, w in pairs) / total_w, 4)


def _count_true_flags(parsed_rows, key):
    """Internal helper for count true flags."""
    vals = []
    for _, attrs in parsed_rows:
        vals.append(1 if attrs.get(key) else 0)
    return int(sum(vals))


def _merge_field_mode(parsed_rows, key):
    """Internal helper for merge field mode."""
    vals = []
    for _, attrs in parsed_rows:
        x = attrs.get(key)
        if x not in [None, ""]:
            vals.append(x)
    return _pick_mode(vals)

# fuse 是逐里程地质事实融合函数。
# 输入是当前 chainage 命中的多条地质证据 hit_df。
# 它不直接做风险等级评定，而是融合事实信息：
#   1. 围岩等级：提取所有 support_grade/rock_grade，并取最不利等级
#   2. 出水/掉块/变形：只要任一证据出现，就置为 1
#   3. 岩性、风化、裂隙、岩体状态：按字段众数或规则合并
#   4. 灾害标签：合并 risk_tags、水害、掉块、破碎等标签
#   5. 来源统计：统计 source_type + report_id 组合数
#   6. 不确定性：多源证据越多，不确定性越低
# 输出是一条当前里程的地质事实标签记录，后续会 merge 回 df_geo。
def fuse(chainage, df):
    """
    对某一里程的命中证据进行融合
    —— 只做“事实融合”，不做风险评定
    """
    if df.empty:
        return {
            "chainage": chainage,
            "coverage": "none",
            "geo_coverage_status": "none",

            # 事实型输出
            "hazard": "无明显异常",
            "hazard_list": "",
            "fused_grade": "",
            "water_flag_fused": 0,
            "water_type_fused": None,
            "collapse_flag_fused": 0,
            "deformation_flag_fused": 0,
            "joint_degree_fused": None,
            "rock_mass_state_fused": None,
            "rock_uniformity_fused": None,
            "weathering_fused": None,
            "stability_fused": None,
            "lithology_fused": None,
            # 第二阶段标准字段名（逐里程地质事实层）
            "geo_hazard_summary": "无明显异常",
            "geo_hazard_tags": "",
            "geo_fused_grade": "",
            "geo_water_flag": 0,
            "geo_water_type": None,
            "geo_collapse_flag": 0,
            "geo_deformation_flag": 0,
            "geo_joint_degree": None,
            "geo_rock_mass_state": None,
            "geo_rock_uniformity": None,
            "geo_weathering": None,
            "geo_stability": None,
            "geo_lithology": None,

            # 来源与命中
            "active_source_count": 0,
            "active_sources": "",
            "active_evidence_ids": "",
            "active_report_ids": "",
            "active_source_levels": "",
            "uncertainty": "high",
            # 第二阶段标准字段名（来源/命中/不确定性）
            "active_report_source_count": 0,
            "active_source_types": "",
            "matched_evidence_ids": "",
            "matched_report_ids": "",
            "matched_source_levels": "",
            "geo_fusion_uncertainty": "high",

            # 证据统计
            "evidence_count": 0,
            "weighted_evidence_strength": 0.0,
            "matched_evidence_record_count": 0,
            "evidence_support_weight_sum": 0.0,
            "grade_count": 0,
            "water_evidence_count": 0,
            "collapse_evidence_count": 0,
            "deformation_evidence_count": 0,
        }

    parsed_rows = []
    weights = []
    for _, row in df.iterrows():
        attrs = _safe_load_attrs(row.get("attrs_json", ""))
        parsed_rows.append((row, attrs))
        weights.append(_record_weight(row, attrs))

    # ===== 字段融合 =====
    grades = []
    for _, attrs in parsed_rows:
        g = _normalize_grade(attrs.get("support_grade") or attrs.get("rock_grade"))
        if g:
            grades.append(g)

    fused_grade = _pick_worst_grade(grades)

    water_flag_fused = 1 if _count_true_flags(parsed_rows, "water_flag") > 0 else 0
    collapse_flag_fused = 1 if _count_true_flags(parsed_rows, "collapse_flag") > 0 else 0
    deformation_flag_fused = 1 if _count_true_flags(parsed_rows, "deformation_flag") > 0 else 0

    water_type_fused = _merge_water_type(parsed_rows)
    joint_degree_fused = _merge_field_mode(parsed_rows, "joint_degree")
    rock_mass_state_fused = _merge_field_mode(parsed_rows, "rock_mass_state")
    rock_uniformity_fused = _merge_field_mode(parsed_rows, "rock_uniformity")
    weathering_fused = _merge_field_mode(parsed_rows, "weathering")
    stability_fused = _merge_field_mode(parsed_rows, "stability")
    lithology_fused = _merge_field_mode(parsed_rows, "lithology")

    hazard_list, hazard = _merge_hazard_tags(parsed_rows)

    # ===== 来源统计 =====
    unique_report_keys = set()
    unique_report_ids = set()
    unique_sources = set()
    unique_levels = set()

    for _, row in df.iterrows():
        source_type = str(row.get("source_type", "")).strip()
        source_level = str(row.get("source_level", "")).strip()
        report_id = normalize_report_id(row.get("report_id", ""))

        unique_report_keys.add((source_type, report_id))
        if report_id:
            unique_report_ids.add(report_id)
        if source_type:
            unique_sources.add(source_type)
        if source_level:
            unique_levels.add(source_level)

    active_source_count = len(unique_report_keys)

    if active_source_count >= 3:
        uncertainty = "low"
    elif active_source_count == 2:
        uncertainty = "medium"
    else:
        uncertainty = "high"

    # ===== 证据统计 =====
    evidence_count = len(parsed_rows)
    weighted_evidence_strength = round(sum(weights), 4)

    water_evidence_count = _count_true_flags(parsed_rows, "water_flag")
    collapse_evidence_count = _count_true_flags(parsed_rows, "collapse_flag")
    deformation_evidence_count = _count_true_flags(parsed_rows, "deformation_flag")

    return {
        "chainage": chainage,
        "coverage": "multi" if active_source_count > 1 else "single",
        "geo_coverage_status": "multi" if active_source_count > 1 else "single",

        # 事实型输出
        "hazard": hazard,
        "hazard_list": ";".join(hazard_list),
        "fused_grade": fused_grade,
        "water_flag_fused": water_flag_fused,
        "water_type_fused": water_type_fused,
        "collapse_flag_fused": collapse_flag_fused,
        "deformation_flag_fused": deformation_flag_fused,
        "joint_degree_fused": joint_degree_fused,
        "rock_mass_state_fused": rock_mass_state_fused,
        "rock_uniformity_fused": rock_uniformity_fused,
        "weathering_fused": weathering_fused,
        "stability_fused": stability_fused,
        "lithology_fused": lithology_fused,
        # 第二阶段标准字段名（逐里程地质事实层）
        "geo_hazard_summary": hazard,
        "geo_hazard_tags": ";".join(hazard_list),
        "geo_fused_grade": fused_grade,
        "geo_water_flag": water_flag_fused,
        "geo_water_type": water_type_fused,
        "geo_collapse_flag": collapse_flag_fused,
        "geo_deformation_flag": deformation_flag_fused,
        "geo_joint_degree": joint_degree_fused,
        "geo_rock_mass_state": rock_mass_state_fused,
        "geo_rock_uniformity": rock_uniformity_fused,
        "geo_weathering": weathering_fused,
        "geo_stability": stability_fused,
        "geo_lithology": lithology_fused,

        # 来源与命中
        "active_source_count": active_source_count,
        "active_sources": ";".join(sorted(unique_sources)),
        "active_evidence_ids": ";".join(df["evidence_id"].astype(str).tolist()),
        "active_report_ids": ";".join(sorted(unique_report_ids)),
        "active_source_levels": ";".join(sorted(unique_levels)),
        "uncertainty": uncertainty,
        # 第二阶段标准字段名（来源/命中/不确定性）
        "active_report_source_count": active_source_count,
        "active_source_types": ";".join(sorted(unique_sources)),
        "matched_evidence_ids": ";".join(df["evidence_id"].astype(str).tolist()),
        "matched_report_ids": ";".join(sorted(unique_report_ids)),
        "matched_source_levels": ";".join(sorted(unique_levels)),
        "geo_fusion_uncertainty": uncertainty,

        # 证据统计
        "evidence_count": evidence_count,
        "weighted_evidence_strength": weighted_evidence_strength,
        "matched_evidence_record_count": evidence_count,
        "evidence_support_weight_sum": weighted_evidence_strength,
        "grade_count": len(grades),
        "water_evidence_count": water_evidence_count,
        "collapse_evidence_count": collapse_evidence_count,
        "deformation_evidence_count": deformation_evidence_count,
    }


def annotate_unique_chainage(unique_chainage_df, evidence):
    """
    对唯一里程表做逐里程注记。

    输入：
        unique_chainage_df:
            从 PLC 数据中提取出来的唯一里程表，通常只包含 chainage 一列。
            这样可以避免对相同里程重复执行地质证据匹配。

        evidence:
            地质证据库表，包含 TSP/HSP/掌子面素描/钻孔等多源地质证据。
            每条证据通常具有 start_num、end_num、source_type、source_level、attrs_json 等字段。

    输出：
        一个 DataFrame。
        每一行对应一个唯一 chainage 的地质融合结果。
        后续会按照 chainage merge 回原始 PLC 数据表。
    """

    # 用列表暂存每一个唯一里程的融合结果。
    # 每个元素通常是一个 dict，例如：
    # {"chainage": x, "risk": "...", "risk_score": ..., "hazard": "..."}
    results = []

    # 唯一里程数量，用于打印进度。
    total = len(unique_chainage_df)

    # 遍历每一个唯一里程 x。
    # 这里不是遍历原始 PLC 的每一行，而是遍历去重后的 chainage，
    # 可以显著减少重复计算。
    for i, x in enumerate(unique_chainage_df["chainage"], start=1):

        # 每处理 5000 个唯一里程打印一次进度，
        # 避免大数据量时用户误以为程序卡死。
        if i % 5000 == 0:
            print(f"已处理唯一里程: {i}/{total}")

        # 1. 根据当前里程 x，从 evidence 中筛选出有效地质证据。
        # get_active 负责判断哪些证据的 start_num/end_num 范围覆盖当前里程。
        hit_df = get_active(x, evidence)

        # 2. 将当前里程命中的多条证据融合成一条地质标签记录。
        # fuse 负责生成 risk、risk_score、hazard、fused_grade、
        # active_source_count、water_flag、collapse_flag 等字段。
        results.append(fuse(x, hit_df))

    # 将所有唯一里程的融合结果转成 DataFrame。
    # 之后 attach_geology_labels 会用 chainage 把它 merge 回原始 PLC 数据。
    return pd.DataFrame(results)