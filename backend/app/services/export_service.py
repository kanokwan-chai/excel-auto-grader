"""Export Service: Generates formatted Excel (.xlsx), CSV, and PDF reports."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_class_report_excel(
    assignment_title: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> bytes:
    """Create a professionally formatted Excel (.xlsx) class gradebook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "รายงานคะแนน"

    header_fill = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")
    sub_fill = PatternFill(start_color="F3E8FF", end_color="F3E8FF", fill_type="solid")
    header_font = Font(name="Sarabun", size=12, bold=True, color="FFFFFF")
    title_font = Font(name="Sarabun", size=15, bold=True, color="4C1D95")
    body_font = Font(name="Sarabun", size=11)
    thin = Side(style="thin", color="D8B4FE")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:G1")
    ws["A1"] = f"รายงานผลคะแนน Excel Auto Grader — {assignment_title}"
    ws["A1"].font = title_font
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    ws["A2"] = f"วันที่ส่งออก: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws["D2"] = f"คะแนนเฉลี่ย: {summary.get('average_score', 0):.2f}"
    ws["F2"] = f"ผ่านเกณฑ์: {summary.get('passed_count', 0)} / {summary.get('total_students', 0)} คน"
    for col in ("A2", "D2", "F2"):
        ws[col].font = Font(name="Sarabun", size=10, italic=True, color="5B21B6")

    headers = [
        "เลขที่",
        "รหัสนักเรียน",
        "ชื่อ-นามสกุล",
        "คะแนนที่ได้",
        "คะแนนเต็ม",
        "เปอร์เซ็นต์ (%)",
        "สถานะ",
        "รายการที่ถูกหักคะแนนและสาเหตุ",
    ]
    ws.row_dimensions[4].height = 24
    for col_idx, text in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_idx, value=text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for idx, row in enumerate(rows, start=5):
        vals = [
            row.get("seat_number") or (idx - 4),
            row.get("student_code") or "-",
            row.get("student_name") or "-",
            float(row.get("final_score", 0)),
            float(row.get("max_score", 0)),
            float(row.get("percentage", 0)),
            row.get("status_label") or row.get("status", "-"),
            row.get("deduction_summary") or "ไม่ถูกหักคะแนน",
        ]
        for col_idx, val in enumerate(vals, start=1):
            cell = ws.cell(row=idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = border
            if col_idx in (1, 2, 7):
                cell.alignment = Alignment(horizontal="center")
            elif col_idx in (4, 5, 6):
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = "0.00"
            elif col_idx == 8:
                cell.alignment = Alignment(horizontal="left", wrap_text=True)
            if idx % 2 == 1:
                cell.fill = sub_fill

    widths = [10, 18, 28, 14, 13, 15, 16, 52]
    for col_idx, width in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_class_report_csv(rows: list[dict[str, Any]]) -> bytes:
    """Create UTF-8 BOM CSV for seamless opening in Microsoft Excel with Thai characters."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["เลขที่", "รหัสนักเรียน", "ชื่อ-นามสกุล", "คะแนนที่ได้", "คะแนนเต็ม", "เปอร์เซ็นต์", "สถานะ"])
    for idx, r in enumerate(rows, start=1):
        writer.writerow([
            r.get("seat_number") or idx,
            r.get("student_code") or "-",
            r.get("student_name") or "-",
            f"{float(r.get('final_score', 0)):.2f}",
            f"{float(r.get('max_score', 0)):.2f}",
            f"{float(r.get('percentage', 0)):.2f}%",
            r.get("status_label") or r.get("status", "-"),
        ])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def generate_individual_report_pdf(report_data: dict[str, Any]) -> bytes:
    """Generate a clean PDF individual grading report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Excel Auto Grader Report")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("<b>Excel Auto Grader - Individual Grading Report</b>", styles["Title"]),
        Spacer(1, 10),
        Paragraph(f"<b>Student:</b> {report_data.get('student_name', '-')} ({report_data.get('student_code', '-')})", styles["Normal"]),
        Paragraph(f"<b>Assignment:</b> {report_data.get('assignment_title', '-')}", styles["Normal"]),
        Paragraph(
            f"<b>Score:</b> {report_data.get('final_score', 0):.2f} / {report_data.get('max_score', 0):.2f} "
            f"({report_data.get('percentage', 0):.2f}%)",
            styles["Normal"],
        ),
        Paragraph(f"<b>Status:</b> {report_data.get('status', '-')}", styles["Normal"]),
        Spacer(1, 14),
    ]

    table_data = [["Item", "Cell", "Earned / Max", "Deducted", "Reason"]]
    for d in report_data.get("details", []):
        deducted = float(d.get("deducted_points", 0) or 0)
        table_data.append([
            str(d.get("item_title", ""))[:32],
            str(d.get("target_cell") or "-"),
            f"{d.get('earned_points', 0):.2f} / {d.get('max_points', 0):.2f}",
            f"-{deducted:.2f}" if deducted > 0 else "0",
            str(d.get("reason") or ("PASS" if d.get("passed") else "FAIL"))[:55],
        ])

    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7C3AED")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDD6FE")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF5FF")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()
