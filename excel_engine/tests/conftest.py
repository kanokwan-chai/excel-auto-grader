"""Pytest fixtures generating real Excel (.xlsx) workbooks for all grading test scenarios."""

from __future__ import annotations

from pathlib import Path
import openpyxl
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
import pytest


def create_sample_workbook(
    path: Path,
    *,
    sum_formula: str = "=SUM(B2:B5)",
    avg_formula: str = "=AVERAGE(B2:B5)",
    if_formula_d2: str = '=IF(B2>=50,"ผ่าน","ไม่ผ่าน")',
    if_formula_d3: str = '=IF(B3>=50,"ผ่าน","ไม่ผ่าน")',
    abs_formula_e2: str = "=B2*$G$1",
    cross_sheet_formula: str = "=Summary!B2+10",
    number_format_b6: str = "#,##0.00",
    include_summary_sheet: bool = True,
    chart_type: str = "bar",
    put_sum_in_wrong_cell: bool = False,
) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Scores"

    ws["A1"] = "ชื่อนักเรียน"
    ws["B1"] = "คะแนน"
    ws["C1"] = "หมายเหตุ"
    ws["D1"] = "ผลการประเมิน"
    ws["E1"] = "คะแนนถ่วงน้ำหนัก"
    ws["G1"] = 1.5

    rows = [
        ("สมชาย", 80),
        ("สมหญิง", 45),
        ("วิชัย", 70),
        ("สุดา", 90),
    ]
    for idx, (name, score) in enumerate(rows, start=2):
        ws[f"A{idx}"] = name
        ws[f"B{idx}"] = score

    if put_sum_in_wrong_cell:
        ws["B6"] = None
        ws["C6"] = sum_formula
    else:
        ws["B6"] = sum_formula

    ws["B7"] = avg_formula
    ws["D2"] = if_formula_d2
    ws["D3"] = if_formula_d3
    ws["E2"] = abs_formula_e2
    ws["F2"] = cross_sheet_formula

    # Styling
    thin = Side(style="thin", color="000000")
    ws["A1"].font = Font(name="Sarabun", size=12, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")
    ws["A1"].alignment = Alignment(horizontal="center")
    ws["A1"].border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws["B6"].number_format = number_format_b6

    # Chart
    data_ref = Reference(ws, min_col=2, min_row=1, max_row=5)
    cats_ref = Reference(ws, min_col=1, min_row=2, max_row=5)
    if chart_type == "bar":
        chart = BarChart()
        chart.type = "col"
        chart.title = "กราฟคะแนนนักเรียน"
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats_ref)
        ws.add_chart(chart, "I2")
    elif chart_type == "pie":
        chart = PieChart()
        chart.title = "กราฟคะแนนนักเรียน"
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats_ref)
        ws.add_chart(chart, "I2")

    if include_summary_sheet:
        ws2 = wb.create_sheet("Summary")
        ws2["A1"] = "สรุป"
        ws2["B2"] = 100

    wb.save(path)
    return path


@pytest.fixture
def tmp_excel_dir(tmp_path: Path) -> Path:
    return tmp_path
