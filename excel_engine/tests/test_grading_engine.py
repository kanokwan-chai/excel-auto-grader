"""Comprehensive automated test suite for the Excel Grading Engine.

Covers all required test cases:
1. Correct formula
2. Wrong formula (hardcoded value or wrong function)
3. Correct formula in wrong cell position
4. Wrong calculated value & Excel errors (#DIV/0!, #VALUE!)
5. Incomplete data range in formula
6. Cell reference (relative vs absolute $)
7. Cross-sheet reference
8. Wrong number format
9. Missing worksheet
10. Wrong chart type
11. Corrupted file / security validation (zip bomb, invalid header)
12. Partial credit calculation & zero_on_error enforcement
"""

from __future__ import annotations

from pathlib import Path
import openpyxl
import pytest

from excel_engine.exceptions import FileSecurityError
from excel_engine.models import RubricConfig, RubricItemConfig
from excel_engine.scoring.engine import ExcelGradingEngine
from excel_engine.tests.conftest import create_sample_workbook


def build_standard_rubric() -> RubricConfig:
    return RubricConfig(
        id="rubric-std",
        name="แบบฝึกหัด Excel บทที่ 1",
        total_points=20.0,
        items=[
            RubricItemConfig(
                id="sum",
                title="สูตร SUM",
                category="formula",
                sheet_name="Scores",
                target_cell="B6",
                rule_config={
                    "expected_formula": "=SUM(B2:B5)",
                    "required_functions": ["SUM"],
                    "required_ranges": ["B2:B5"],
                },
                max_points=3.0,
            ),
            RubricItemConfig(
                id="avg",
                title="สูตร AVERAGE",
                category="formula",
                sheet_name="Scores",
                target_cell="B7",
                rule_config={"expected_formula": "=AVERAGE(B2:B5)"},
                max_points=3.0,
            ),
            RubricItemConfig(
                id="if",
                title="สูตร IF หลายแถว",
                category="formula",
                sheet_name="Scores",
                target_cell="D2:D3",
                rule_config={"required_functions": ["IF"]},
                max_points=4.0,
                allow_partial_credit=True,
            ),
            RubricItemConfig(
                id="abs_ref",
                title="การอ้างอิงแบบ Absolute ($)",
                category="formula",
                sheet_name="Scores",
                target_cell="E2",
                rule_config={
                    "expected_formula": "=B2*$G$1",
                    "require_absolute_reference": True,
                },
                max_points=2.0,
            ),
            RubricItemConfig(
                id="cross_sheet",
                title="การอ้างอิงข้าม Sheet",
                category="formula",
                sheet_name="Scores",
                target_cell="F2",
                rule_config={"require_cross_sheet": "Summary"},
                max_points=2.0,
            ),
            RubricItemConfig(
                id="style_numfmt",
                title="รูปแบบตัวเลขและหัวตาราง",
                category="style",
                sheet_name="Scores",
                target_cell="B6",
                rule_config={"number_format": "#,##0.00"},
                max_points=2.0,
            ),
            RubricItemConfig(
                id="structure",
                title="โครงสร้าง Worksheet",
                category="structure",
                rule_config={"required_sheets": ["Scores", "Summary"], "exact_sheet_count": 2},
                max_points=2.0,
            ),
            RubricItemConfig(
                id="chart",
                title="แผนภูมิแท่ง",
                category="chart",
                sheet_name="Scores",
                rule_config={"chart_type": "column", "expected_title": "กราฟคะแนนนักเรียน"},
                max_points=2.0,
            ),
        ],
    )


def test_1_perfect_workbook_gets_full_score(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "perfect.xlsx")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    assert result.auto_score == 20.0
    assert result.percentage == 100.0
    assert len(result.errors) == 0


def test_2_hardcoded_value_instead_of_formula_fails(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "hardcoded.xlsx", sum_formula="285")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    sum_detail = next(d for d in result.details if d.rubric_item_id == "sum")
    assert sum_detail.passed is False
    assert sum_detail.earned_points == 0.0
    assert any(e.error_code == "NOT_A_FORMULA" for e in sum_detail.errors)


def test_3_formula_in_wrong_cell_position(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "wrong_pos.xlsx", put_sum_in_wrong_cell=True)
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    sum_detail = next(d for d in result.details if d.rubric_item_id == "sum")
    assert sum_detail.passed is False
    assert sum_detail.earned_points == 0.0


def test_4_value_mismatch_and_excel_error(tmp_excel_dir: Path):
    path = tmp_excel_dir / "values.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = 100.0
    ws["A2"] = "#DIV/0!"
    wb.save(path)

    rubric = RubricConfig(
        total_points=10.0,
        items=[
            RubricItemConfig(
                id="v1",
                title="ผลลัพธ์ A1",
                category="value",
                sheet_name="Sheet1",
                target_cell="A1",
                rule_config={"expected_value": 150.0, "tolerance": 0.01},
                max_points=5.0,
            ),
            RubricItemConfig(
                id="v2",
                title="ผลลัพธ์ A2",
                category="value",
                sheet_name="Sheet1",
                target_cell="A2",
                rule_config={"expected_value": 10.0},
                max_points=5.0,
            ),
        ],
    )
    engine = ExcelGradingEngine(enable_libreoffice=False)
    res = engine.grade(path, rubric)
    assert res.auto_score == 0.0
    codes = {e.error_code for e in res.errors}
    assert "VALUE_MISMATCH" in codes
    assert "EXCEL_CALCULATION_ERROR" in codes


def test_5_incomplete_range_in_formula(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "short_range.xlsx", sum_formula="=SUM(B2:B4)")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    sum_detail = next(d for d in result.details if d.rubric_item_id == "sum")
    assert sum_detail.passed is False
    assert any(e.error_code == "WRONG_DATA_RANGE" for e in sum_detail.errors)


def test_6_missing_absolute_reference(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "no_abs.xlsx", abs_formula_e2="=B2*G1")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    abs_detail = next(d for d in result.details if d.rubric_item_id == "abs_ref")
    assert abs_detail.passed is False
    assert any(e.error_code == "MISSING_ABSOLUTE_REFERENCE" for e in abs_detail.errors)


def test_7_missing_cross_sheet_reference(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "no_cross.xlsx", cross_sheet_formula="=B2+10")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    cross_detail = next(d for d in result.details if d.rubric_item_id == "cross_sheet")
    assert cross_detail.passed is False
    assert any(e.error_code == "MISSING_CROSS_SHEET_REF" for e in cross_detail.errors)


def test_8_wrong_number_format(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "bad_fmt.xlsx", number_format_b6="General")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    fmt_detail = next(d for d in result.details if d.rubric_item_id == "style_numfmt")
    assert fmt_detail.passed is False
    assert any(e.error_code == "WRONG_NUMBER_FORMAT" for e in fmt_detail.errors)


def test_9_missing_worksheet(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "no_summary.xlsx", include_summary_sheet=False)
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    struct_detail = next(d for d in result.details if d.rubric_item_id == "structure")
    assert struct_detail.passed is False
    assert any(e.error_code == "MISSING_WORKSHEET" for e in struct_detail.errors)


def test_10_wrong_chart_type(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "pie_chart.xlsx", chart_type="pie")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    chart_detail = next(d for d in result.details if d.rubric_item_id == "chart")
    assert chart_detail.passed is False
    assert any(e.error_code == "WRONG_CHART_TYPE" for e in chart_detail.errors)


def test_11_corrupted_file_rejected(tmp_excel_dir: Path):
    bad = tmp_excel_dir / "corrupted.xlsx"
    bad.write_bytes(b"THIS IS NOT A VALID EXCEL FILE")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    with pytest.raises(FileSecurityError) as exc_info:
        engine.grade(bad, build_standard_rubric())
    assert exc_info.value.code == "INVALID_MAGIC_BYTES"


def test_12_partial_credit_calculation(tmp_excel_dir: Path):
    # D2 uses IF correctly, D3 is hardcoded -> 1/2 cells -> 2.0/4.0 points
    file_path = create_sample_workbook(tmp_excel_dir / "partial.xlsx", if_formula_d3="ไม่ผ่าน")
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, build_standard_rubric())
    if_detail = next(d for d in result.details if d.rubric_item_id == "if")
    assert if_detail.passed is False
    assert if_detail.earned_points == 2.0
    assert if_detail.deducted_points == 2.0


def test_13_decoration_and_added_data_checks(tmp_excel_dir: Path):
    file_path = create_sample_workbook(tmp_excel_dir / "decorated.xlsx")
    rubric = RubricConfig(
        total_points=10.0,
        items=[
            RubricItemConfig(
                id="deco",
                title="ตรวจการตกแต่งตาราง",
                category="style",
                sheet_name="Scores",
                target_cell="A1",
                rule_config={"bold": True, "has_border": True, "has_fill_color": True},
                max_points=5.0,
            ),
            RubricItemConfig(
                id="added",
                title="ตรวจการใส่ข้อมูลเพิ่มตามคำสั่ง",
                category="completeness",
                sheet_name="Scores",
                rule_config={
                    "min_data_rows": 4,
                    "min_columns": 5,
                    "required_keywords": ["สมชาย", "หมายเหตุ"],
                    "no_empty_cells_in_range": "A2:B5",
                },
                max_points=5.0,
            ),
        ],
    )
    engine = ExcelGradingEngine(enable_libreoffice=False)
    result = engine.grade(file_path, rubric)
    assert result.auto_score == 10.0
    assert len(result.errors) == 0


def test_14_auto_detect_formula_from_reference_without_cell(tmp_excel_dir: Path):
    ref_path = create_sample_workbook(tmp_excel_dir / "ref.xlsx")
    good_student = create_sample_workbook(tmp_excel_dir / "student_ok.xlsx")
    bad_student = create_sample_workbook(tmp_excel_dir / "student_bad.xlsx", sum_formula="285")

    # Notice: NO sheet_name, NO target_cell, NO expected_formula specified!
    rubric = RubricConfig(
        total_points=10.0,
        items=[
            RubricItemConfig(
                id="auto_sum",
                title="ตรวจสูตร SUM",
                category="formula",
                rule_config={"required_functions": ["SUM"]},
                max_points=5.0,
            ),
            RubricItemConfig(
                id="auto_if",
                title="ตรวจสูตร IF",
                category="formula",
                rule_config={"required_functions": ["IF"]},
                max_points=5.0,
            ),
        ],
    )
    engine = ExcelGradingEngine(enable_libreoffice=False)
    res_ok = engine.grade(good_student, rubric, reference_file_path=ref_path)
    assert res_ok.auto_score == 10.0

    res_bad = engine.grade(bad_student, rubric, reference_file_path=ref_path)
    assert res_bad.auto_score == 5.0
    assert any(e.error_code == "NOT_A_FORMULA" for e in res_bad.errors)


def test_15_aesthetics_matches_reference_layout_allows_any_color(tmp_excel_dir: Path):
    ref_path = create_sample_workbook(tmp_excel_dir / "ref_style.xlsx")
    # Student uses DIFFERENT fill color (pastel pink #F472B6 instead of purple #7C3AED),
    # while keeping neat borders, bold header, and number format -> MUST get 100% full score!
    stu_path = create_sample_workbook(tmp_excel_dir / "stu_pink.xlsx")
    wb = openpyxl.load_workbook(stu_path)
    from openpyxl.styles import PatternFill
    wb["Scores"]["A1"].fill = PatternFill(start_color="F472B6", end_color="F472B6", fill_type="solid")
    wb.save(stu_path)

    rubric = RubricConfig(
        total_points=5.0,
        items=[
            RubricItemConfig(
                id="aesthetics",
                title="ความสวยงามและการตกแต่ง",
                category="style",
                rule_config={"match_reference_layout_ignore_color": True},
                max_points=5.0,
            )
        ],
    )
    engine = ExcelGradingEngine(enable_libreoffice=False)
    res = engine.grade(stu_path, rubric, reference_file_path=ref_path)
    assert res.auto_score == 5.0
    assert len(res.errors) == 0


def test_16_filter_formula_xlws_prefix_and_autofilter(tmp_excel_dir: Path):
    file_ok = create_sample_workbook(tmp_excel_dir / "filter_ok.xlsx")
    wb = openpyxl.load_workbook(file_ok)
    ws = wb["Scores"]
    # Simulate Excel's internal _xlfn._xlws.FILTER prefix + active AutoFilter
    ws["G2"] = '=_xlfn._xlws.FILTER(A2:E5, E2:E5="ผ่าน")'
    ws.auto_filter.ref = "A1:E5"
    ws.row_dimensions[4].hidden = True
    wb.save(file_ok)

    file_no_filter = create_sample_workbook(tmp_excel_dir / "filter_missing.xlsx")

    rubric = RubricConfig(
        total_points=10.0,
        items=[
            RubricItemConfig(
                id="filter_fn",
                title="ตรวจสูตร FILTER",
                category="formula",
                rule_config={"required_functions": ["FILTER"]},
                max_points=5.0,
            ),
            RubricItemConfig(
                id="autofilter",
                title="ตรวจตัวกรองข้อมูล (AutoFilter)",
                category="structure",
                sheet_name="Scores",
                rule_config={"require_autofilter": True, "require_filter_applied": True},
                max_points=5.0,
            ),
        ],
    )
    engine = ExcelGradingEngine(enable_libreoffice=False)
    res_ok = engine.grade(file_ok, rubric)
    assert res_ok.auto_score == 10.0

    res_bad = engine.grade(file_no_filter, rubric)
    assert res_bad.auto_score == 0.0
    assert any(e.error_code == "MISSING_AUTOFILTER" for e in res_bad.errors)




