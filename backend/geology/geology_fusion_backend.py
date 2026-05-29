# geology_fusion_backend.py
import json
import pandas as pd
from geology.fusion import annotate_unique_chainage

from config import EVIDENCE_DB_PATH
from services.sqlite_storage_service import load_evidence_dataframe_from_db, sync_evidence_dataframe_to_db

DEFAULT_EVIDENCE_DB_PATH = EVIDENCE_DB_PATH


def _safe_load_attrs(x):
    """Safely load serialized evidence attributes."""
    try:
        obj = json.loads(x)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _expand_evidence_attrs(df: pd.DataFrame) -> pd.DataFrame:
    """Internal helper for expand evidence attrs."""
    if "attrs_json" in df.columns:
        df["attrs_obj"] = df["attrs_json"].apply(_safe_load_attrs)

        # 常用字段展开，便于调试或后续分析
        df["risk_level"] = df["attrs_obj"].apply(lambda x: x.get("risk_level"))
        df["water_flag"] = df["attrs_obj"].apply(lambda x: x.get("water_flag", 0))
        df["collapse_flag"] = df["attrs_obj"].apply(lambda x: x.get("collapse_flag", 0))
        df["deformation_flag"] = df["attrs_obj"].apply(lambda x: x.get("deformation_flag", 0))
        df["support_grade"] = df["attrs_obj"].apply(
            lambda x: x.get("support_grade") or x.get("rock_grade")
        )
        df["water_type"] = df["attrs_obj"].apply(lambda x: x.get("water_type"))
        df["risk_tags"] = df["attrs_obj"].apply(lambda x: x.get("risk_tags", []))

    return df


def load_evidence_db(path=DEFAULT_EVIDENCE_DB_PATH):
    """
    读取证据库，并展开常用 attrs_json 字段
    """
    try:
        df = load_evidence_dataframe_from_db(path)
        if not df.empty:
            return _expand_evidence_attrs(df)
    except Exception as exc:
        print(f"SQLite evidence load failed, fallback to CSV: {exc}")

    df = pd.read_csv(path)
    try:
        sync_evidence_dataframe_to_db(df)
    except Exception as exc:
        print(f"SQLite evidence sync skipped: {exc}")
    return _expand_evidence_attrs(df)


def _ensure_chainage_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保存在统一的 chainage 字段
    优先使用：导向盾首里程，其次开累进尺
    """
    out = df.copy()

    if "chainage" in out.columns:
        out["chainage"] = pd.to_numeric(out["chainage"], errors="coerce")
        return out

    if "导向盾首里程" in out.columns:
        out["chainage"] = pd.to_numeric(out["导向盾首里程"], errors="coerce")
        return out

    if "开累进尺" in out.columns:
        out["chainage"] = pd.to_numeric(out["开累进尺"], errors="coerce")
        return out

    return out

# 将多源地质证据 evidence_df 按里程范围匹配到 TBM/PLC 数据 df_plc 上，
# 生成带地质风险、围岩等级、灾害标签、多源证据数量等字段的 df_geo。
def attach_geology_labels(df_plc: pd.DataFrame, evidence_df: pd.DataFrame) -> pd.DataFrame:
    """
    将多源地质证据按里程融合到 TBM 施工数据中。

    参数：
        df_plc:
            单日 TBM/PLC 运行数据表，每一行是一条施工参数记录。
            通常包含时间、里程、推力、刀盘扭矩、推进速度、掘进状态等字段。

        evidence_df:
            地质证据库表，每一行是一条来自 TSP、HSP、掌子面素描、
            超前钻孔等资料的结构化证据。
            通常包含 start_num、end_num、source_type、attrs_json 等字段。

    返回：
        df_geo:
            在 df_plc 基础上增加地质标签后的数据表。
            后续地质摘要、前方风险、GRS/RAI/GRCI 耦合分析都依赖它。
    """

    # 1. 统一 PLC 数据中的里程字段
    # 不同数据源里的里程字段名称可能不同，例如“导向盾首里程”“开累进尺”“chainage”等。
    # 这里通过 _ensure_chainage_column 统一生成 df["chainage"]，后续融合都基于这个字段。
    df = _ensure_chainage_column(df_plc)

    # 2. 如果找不到里程字段，则无法进行空间匹配，只能返回原始数据
    if "chainage" not in df.columns:
        print("未找到可用里程字段，返回原始数据。")
        return df

    # 3. 如果地质证据库为空，则没有可融合的 TSP/HSP/素描/钻孔证据
    if evidence_df is None or len(evidence_df) == 0:
        print("证据库为空，返回原始数据。")
        return df

    # 4. 删除没有里程值的 PLC 记录
    # 没有 chainage 的记录无法判断其位于哪个地质证据区间。
    df = df.dropna(subset=["chainage"]).copy()
    if df.empty:
        print("PLC 里程为空，返回原始数据。")
        return df

    # 5. 过滤可参与逐里程融合的地质证据层级
    # segment：明确里程段证据；
    # report_conclusion：报告结论中的区段级证据；
    # point：掌子面素描等点状证据，可通过点位缓冲参与匹配；
    # overview：整份报告概览，空间约束不明确，因此不参与逐里程融合。
    if "source_level" in evidence_df.columns:
        evidence_df = evidence_df.copy()
        evidence_df["source_level"] = evidence_df["source_level"].astype(str).str.strip()
        evidence_df = evidence_df[
            evidence_df["source_level"].isin(["segment", "report_conclusion", "point"])
        ].copy()

    # 6. 提取唯一里程，减少重复计算
    # 原始 PLC 数据可能有大量重复 chainage。
    # 先对唯一 chainage 做地质标注，再 merge 回原表，可以提高效率。
    unique_chainage = (
        df[["chainage"]]
        .drop_duplicates()
        .sort_values("chainage")
        .reset_index(drop=True)
    )

    # 7. 对每一个唯一里程执行地质证据匹配与标签生成
    # 真正的证据命中、风险等级、灾害标签、围岩等级、多源证据数等，
    # 主要是在 annotate_unique_chainage 内部完成。
    anno_unique = annotate_unique_chainage(unique_chainage, evidence_df)

    # 8. 将唯一里程的地质标注结果合并回原始 PLC 数据
    # how="left" 表示保留所有原始 PLC 记录。
    df = df.merge(anno_unique, on="chainage", how="left")

    # 9. 标记当前地质融合字段版本，便于后续调试、兼容和方法说明
    df["geo_fusion_field_version"] = "geo_fusion_v2"

    return df