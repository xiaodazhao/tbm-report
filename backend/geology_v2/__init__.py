"""
geology_v2

地质融合 v2 模块。

设计目标：
1. 与旧 geology / analysis 逻辑并行，不直接破坏旧接口；
2. 将证据标准化、空间投影、多源融合、前方剖面、报告文字生成逐步拆开；
3. 分析函数优先返回结构化数据，不在分析阶段生成大段自然语言；
4. GRCI 只表示“地质-施工响应耦合关注度”，不表示灾害概率。
"""

from geology_v2.schemas import (
    GeoEvidence,
    GeoCell,
    CellEvidence,
    GeoState,
    ForwardProfileItem,
)

__all__ = [
    "GeoEvidence",
    "GeoCell",
    "CellEvidence",
    "GeoState",
    "ForwardProfileItem",
]