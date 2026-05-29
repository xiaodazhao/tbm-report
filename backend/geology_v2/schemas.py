
"""
geology_v2.schemas

地质融合 v2 的结构化数据模型。

说明：
1. 这里用 dataclass，避免引入 pydantic 依赖；
2. 每个结构都提供 to_dict()，方便后续转成 DataFrame 或 JSON；
3. 字段设计保持宽松，便于兼容旧 evidence_df；
4. “无证据”只表达 has_geology_evidence=False，不表达“无风险”。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


def _clean_dict(obj: JsonDict) -> JsonDict:
    """
    Convert dataclass dict into a JSON-friendly plain dict.

    这里只做轻量清洗：
    - 保留 None；
    - 保留 list/dict；
    - 不做 pandas/numpy 类型处理，后续统一在 serialization 层处理。
    """
    return dict(obj)


@dataclass
class GeoEvidence:
    """
    标准化后的地质证据。

    它对应第二阶段 normalize_evidence_df 输出中的一条证据。
    注意：
    - source_type_raw 保留旧 evidence_df 原始来源；
    - source_type_norm 是 v2 标准来源；
    - evidence_role 表示 observed / prediction / interpreted / background；
    - spatial_type 表示 point / anomaly_point / segment / overview / background；
    - evidence_strength 不是风险概率，只是融合权重的一部分。
    """

    evidence_id: str
    report_id: Optional[str] = None

    source_type_raw: Optional[str] = None
    source_type_norm: str = "unknown"
    evidence_role: str = "unknown"
    source_level: Optional[str] = None
    spatial_type: str = "unknown"

    start_chainage: Optional[float] = None
    end_chainage: Optional[float] = None
    center_chainage: Optional[float] = None
    face_chainage: Optional[float] = None

    grade: Optional[str] = None
    lithology: Optional[str] = None
    weathering: Optional[str] = None
    joint_development: Optional[str] = None
    rock_mass_state: Optional[str] = None
    stability: Optional[str] = None

    water_flag: int = 0
    water_type: Optional[str] = None
    collapse_flag: int = 0
    deformation_flag: int = 0

    hazard_tags: List[str] = field(default_factory=list)

    source_reliability: float = 0.0
    evidence_strength: float = 0.0
    confidence_text: str = "unknown"

    raw_text: Optional[str] = None
    attrs_obj: JsonDict = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return _clean_dict(asdict(self))


@dataclass
class GeoCell:
    """
    沿里程方向构建的融合单元。

    一个 cell 通常对应 10m。
    后续所有 evidence 会先投影到 cell，再进行融合。
    """

    cell_id: str
    cell_start: float
    cell_end: float
    cell_center: float
    cell_length: float = 10.0

    def to_dict(self) -> JsonDict:
        return _clean_dict(asdict(self))


@dataclass
class CellEvidence:
    """
    evidence 投影到 cell 后的关系。

    它不是原始证据，而是“某条证据对某个 cell 的影响关系”。
    effective_weight = spatial_weight * source_reliability * evidence_strength
    """

    cell_id: str
    evidence_id: str

    source_type_norm: str = "unknown"
    spatial_type: str = "unknown"

    distance_m: Optional[float] = None
    spatial_weight: float = 0.0
    source_reliability: float = 0.0
    evidence_strength: float = 0.0
    effective_weight: float = 0.0

    def to_dict(self) -> JsonDict:
        return _clean_dict(asdict(self))


@dataclass
class GeoState:
    """
    每个 cell 融合后的地质状态。

    这是第四阶段 fuse_geo_states 的目标结构。
    注意：
    - has_geology_evidence=False 只表示没有可用地质证据；
    - fused_grade 是融合结果，不应简单理解为“最差等级”；
    - hazard_scores 是结构化分数，不再只拼 hazard 字符串；
    - conflict_level 用于表达多源证据冲突。
    """

    cell_id: str
    cell_start: float
    cell_end: float
    cell_center: float

    has_geology_evidence: bool = False

    fused_grade: Optional[str] = None
    grade_distribution: JsonDict = field(default_factory=dict)

    hazard_scores: JsonDict = field(default_factory=dict)
    main_hazards: List[str] = field(default_factory=list)

    water_score: float = 0.0
    collapse_score: float = 0.0
    deformation_score: float = 0.0

    source_support: JsonDict = field(default_factory=dict)
    source_type_count: int = 0
    evidence_count: int = 0

    confidence_score: float = 0.0
    uncertainty_level: str = "unknown"

    conflict_level: str = "none"
    conflict_reasons: List[str] = field(default_factory=list)

    supporting_evidence_ids: List[str] = field(default_factory=list)
    source_trace: List[JsonDict] = field(default_factory=list)

    # 预留给第七阶段传递纯地质基础关注度。
    grade_score_component: float = 0.0
    hazard_component: float = 0.0
    confidence_component: float = 0.0
    GRS_formula_text: str = ""
    GRS_component_method: str = "empty"
    GRS_geo_base: Optional[float] = None

    def to_dict(self) -> JsonDict:
        return _clean_dict(asdict(self))


@dataclass
class ForwardProfileItem:
    """
    前方剖面中的一个分段提示。

    例如：
    - 0-10m
    - 10-20m
    - 20-30m

    注意：
    attention_level 表示关注等级，不表示灾害概率。
    """

    range_label: str

    start_chainage: float
    end_chainage: float

    main_hazards: List[str] = field(default_factory=list)
    fused_grade: Optional[str] = None

    attention_level: str = "none"
    confidence_score: float = 0.0
    uncertainty_level: str = "unknown"

    monitoring_focus: List[str] = field(default_factory=list)
    support_actions: List[str] = field(default_factory=list)

    supporting_cell_ids: List[str] = field(default_factory=list)
    supporting_evidence_ids: List[str] = field(default_factory=list)
    source_trace: List[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return _clean_dict(asdict(self))


def dataclass_to_dict(obj: Any) -> JsonDict:
    """
    通用 dataclass 转 dict 工具。
    """
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return _clean_dict(asdict(obj))
    if isinstance(obj, dict):
        return dict(obj)
    raise TypeError(f"Unsupported object type: {type(obj)}")


