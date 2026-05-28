import json
from pathlib import Path

from parsers.hsp_parser import _parse_hsp_row_to_record
from parsers.sketch_parser import _extract_collapse_flag, parse_sketch_pdf
from parsers.tsp_parser import (
    _parse_grade_records,
    _parse_water_records,
    extract_meta,
    parse_table2_structured_row,
)


META = {
    "report_id": "sample_report",
    "report_date": "2023年12月30日",
    "issue_date": "2023年12月30日",
    "tunnel_name": "伯舒拉岭隧道进口右线",
    "forecast_start_num": 36620.0,
    "forecast_end_num": 36680.0,
    "face_num": 36640.0,
    "next_forecast_num": 36690.0,
}


def test_tsp_meta_and_conclusion_records_extract_key_ranges():
    """Test tsp meta and conclusion records extract key ranges."""
    text = """
    伯舒拉岭隧道进口右线
    检测日期：2023年12月30日
    预报范围 DyK36+620~DyK36+680
    开挖面里程 DyK36+640
    下次物探预报里程为 DyK36+690
    """
    meta = extract_meta(text, "sample_report.pdf")

    assert meta["report_id"] == "sample_report"
    assert meta["forecast_start_num"] == 36620.0
    assert meta["forecast_end_num"] == 36680.0
    assert meta["face_num"] == 36640.0
    assert meta["next_forecast_num"] == 36690.0

    grade_records = _parse_grade_records("DyK36+620~DyK36+640段建议按Ⅴ级围岩施工。", meta)
    water_records = _parse_water_records(
        "DyK36+640~DyK36+660、DyK36+660~DyK36+680段掌子面存在线-股状出水，存在出水风险。",
        meta,
    )

    assert len(grade_records) == 1
    grade_attrs = grade_records[0].attrs()
    assert grade_attrs["support_grade"] == "Ⅴ"
    assert grade_attrs["risk_level"] == "medium"

    assert len(water_records) == 2
    water_attrs = water_records[0].attrs()
    assert water_attrs["water_type"] == "线-股状出水"
    assert water_attrs["risk_level"] == "high"
    assert water_records[1].start_num == 36660.0


def test_tsp_table2_row_parses_high_risk_segment_fields():
    """Test tsp table2 row parses high risk segment fields."""
    row_data = {
        "mileage": "DyK36+620~DyK36+640",
        "params": (
            "纵波速度Vp：1871~5312m/s 横波速度Vs：793~2000m/s "
            "速度比Vp/Vs：1.8~2.5 泊松比：0.23~0.31 动态杨氏模量E：12~20"
        ),
        "conclusion": (
            "板岩夹变质砂岩，弱风化，岩体破碎-极破碎，节理裂隙发育密集，泥质充填，"
            "围岩整体稳定性较差，掌子面存在线-股状出水，存在掉块风险，按Ⅴ级围岩施工。"
        ),
    }

    record = parse_table2_structured_row(row_data, META, 0)
    attrs = record.attrs()

    assert record.start_num == 36620.0
    assert record.end_num == 36640.0
    assert attrs["fact_type"] == "table2_segment"
    assert attrs["risk_level"] == "high"
    assert attrs["support_grade"] == "Ⅴ"
    assert attrs["water_type"] == "线-股状出水"
    assert attrs["collapse_flag"] == 1
    assert attrs["rock_mass_state"] == "破碎-极破碎"
    assert attrs["joint_degree"] == "发育密集"
    assert attrs["vp_min"] == 1871.0
    assert attrs["vp_max"] == 5312.0


def test_hsp_row_parser_extracts_anomaly_and_collapse_points():
    """Test hsp row parser extracts anomaly and collapse points."""
    row_data = {
        "range": "DyK36+620~DyK36+640",
        "detect": "明显反射异常",
        "conclusion": "板岩夹变质砂岩，弱风化，岩体破碎，节理裂隙发育密集，围岩整体稳定性较差。",
        "risk_hint": "掉块风险位于+635附近",
        "grade": "建议Ⅴ级围岩",
    }

    record = _parse_hsp_row_to_record(row_data, META, 0)
    attrs = record.attrs()

    assert record.source_type == "sonic"
    assert attrs["anomaly_level"] == "strong"
    assert attrs["collapse_flag"] == 1
    assert attrs["collapse_points"] == [635.0]
    assert attrs["risk_level"] == "high"
    assert "掉块" in attrs["risk_tags"]
    assert "裂隙密集" in attrs["risk_tags"]


def test_sketch_parser_marks_observed_drop_block_and_water(monkeypatch):
    """Test sketch parser marks observed drop block and water."""
    sketch_text = """
    伯舒拉岭隧道进口右线洞身段地质素描记录表
    日期：2023年12月30日
    DyK36+635
    建议围岩级别Ⅴ
    板岩夹变质砂岩 弱风化 节理裂隙发育密集 岩体破碎 泥质充填 线-股状出水 掌子面掉块
    """

    class FakePage:
        def get_text(self):
            """Handle get text."""
            return sketch_text

    class FakeDoc:
        def __iter__(self):
            """Internal helper for iter."""
            return iter([FakePage()])

        def close(self):
            """Handle close."""
            return None

    monkeypatch.setattr("fitz.open", lambda path: FakeDoc())

    records = parse_sketch_pdf(Path("sample_sketch.pdf"))

    assert len(records) == 1
    attrs = json.loads(records[0].attrs_json)
    assert records[0].start_num == 36635.0
    assert attrs["risk_level"] == "high"
    assert attrs["collapse_flag"] == 1
    assert attrs["water_type"] == "线-股状出水"
    assert "围岩破碎" in attrs["risk_tags"]


def test_sketch_collapse_flag_ignores_generic_safety_wording():
    """Test sketch collapse flag ignores generic safety wording."""
    assert _extract_collapse_flag("施工中应防止掉块并加强支护") == 0
    assert _extract_collapse_flag("掌子面掉块明显") == 1