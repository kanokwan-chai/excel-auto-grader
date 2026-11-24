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


def _safe_sheet_title(raw: str, used: set[str]) -> str:
    import re
    cleaned = re.sub(r"[:\\/?*\[\]]+", " ", raw or "Sheet").strip() or "Sheet"
    base = cleaned[:28]
    cand = base
    n = 2
    while cand in used:
        cand = f"{base[:25]}_{n}"
        n += 1
    used.add(cand)
    return cand


def generate_classroom_gradebook_excel(
    classroom_name: str,
    assignments_meta: list[dict[str, Any]],
    student_rows: list[dict[str, Any]],
    per_assignment_rows: dict[str, list[dict[str, Any]]],
) -> bytes:
    """Create a multi-sheet Excel (.xlsx) Gradebook for an entire Classroom (Summary + 1 tab per assignment)."""
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "สรุปคะแนนรวมทั้งห้อง"
    used_titles = {ws.title}

    header_fill = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")
    sub_fill = PatternFill(start_color="F1F8E9", end_color="F1F8E9", fill_type="solid")
    total_fill = PatternFill(start_color="DCEDC8", end_color="DCEDC8", fill_type="solid")
    header_font = Font(name="Sarabun", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Sarabun", size=15, bold=True, color="1B5E20")
    body_font = Font(name="Sarabun", size=11)
    bold_font = Font(name="Sarabun", size=11, bold=True, color="1B5E20")
    thin = Side(style="thin", color="C5E1A5")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    num_assign = len(assignments_meta)
    total_cols = 2 + num_assign + 3  # เลขที่, ชื่อ-นามสกุล, [งาน...], รวม, เต็ม, %
    last_col_let = get_column_letter(total_cols)

    ws.merge_cells(f"A1:{last_col_let}1")
    ws["A1"] = f"สมุดบันทึกคะแนนรวมทั้งห้อง — {classroom_name}"
    ws["A1"].font = title_font
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    total_max = round(sum(float(a.get("max_score") or 0) for a in assignments_meta), 2)
    ws["A2"] = f"วันที่ส่งออก: {datetime.now().strftime('%Y-%m-%d %H:%M')}  •  จำนวนนักเรียน {len(student_rows)} คน  •  จำนวนงาน {num_assign} งาน (คะแนนเต็มรวม {total_max:g} คะแนน)"
    ws["A2"].font = Font(name="Sarabun", size=10, italic=True, color="33691E")

    headers = ["เลขที่", "ชื่อ-นามสกุล"]
    for a in assignments_meta:
        headers.append(f"{a['title']} ({float(a.get('max_score') or 0):g})")
    headers.extend(["คะแนนรวม", "คะแนนเต็มรวม", "ร้อยละ (%)"])

    ws.row_dimensions[4].height = 28
    for c_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=c_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    first_assign_col = 3
    last_assign_col = 2 + num_assign
    sum_col = last_assign_col + 1
    max_col = last_assign_col + 2
    pct_col = last_assign_col + 3

    for r_offset, st in enumerate(student_rows):
        row_num = 5 + r_offset
        c1 = ws.cell(row=row_num, column=1, value=r_offset + 1)
        c2 = ws.cell(row=row_num, column=2, value=st["student_name"])
        c1.alignment = Alignment(horizontal="center")
        c2.alignment = Alignment(horizontal="left")
        c1.font = body_font
        c2.font = body_font
        c1.border = border
        c2.border = border

        scores_map: dict[str, float | None] = st.get("scores", {})
        for a_idx, a in enumerate(assignments_meta):
            col_i = first_assign_col + a_idx
            sc = scores_map.get(a["assignment_id"])
            c_sc = ws.cell(row=row_num, column=col_i, value=round(float(sc), 2) if sc is not None else 0.0)
            c_sc.font = body_font
            c_sc.border = border
            c_sc.alignment = Alignment(horizontal="right")
            c_sc.number_format = "0.00"

        if num_assign > 0:
            sum_formula = f"=SUM({get_column_letter(first_assign_col)}{row_num}:{get_column_letter(last_assign_col)}{row_num})"
        else:
            sum_formula = 0.0
        c_sum = ws.cell(row=row_num, column=sum_col, value=sum_formula)
        c_max = ws.cell(row=row_num, column=max_col, value=total_max)
        sum_let = get_column_letter(sum_col)
        max_let = get_column_letter(max_col)
        c_pct = ws.cell(
            row=row_num,
            column=pct_col,
            value=f"=IF({max_let}{row_num}>0,ROUND({sum_let}{row_num}/{max_let}{row_num}*100,2),0)",
        )
        for c_tot in (c_sum, c_max, c_pct):
            c_tot.font = bold_font
            c_tot.border = border
            c_tot.alignment = Alignment(horizontal="right")
            c_tot.number_format = "0.00"

        if row_num % 2 == 1:
            for ci in range(1, total_cols + 1):
                ws.cell(row=row_num, column=ci).fill = sub_fill

    # Bottom class average row
    if student_rows:
        avg_row = 5 + len(student_rows)
        ws.cell(row=avg_row, column=1, value="").border = border
        lbl_avg = ws.cell(row=avg_row, column=2, value="ค่าเฉลี่ยทั้งห้อง")
        lbl_avg.font = bold_font
        lbl_avg.border = border
        for ci in range(first_assign_col, pct_col + 1):
            col_l = get_column_letter(ci)
            c_a = ws.cell(row=avg_row, column=ci, value=f"=AVERAGE({col_l}5:{col_l}{avg_row - 1})")
            c_a.font = bold_font
            c_a.border = border
            c_a.alignment = Alignment(horizontal="right")
            c_a.number_format = "0.00"
        for ci in range(1, total_cols + 1):
            ws.cell(row=avg_row, column=ci).fill = total_fill

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 30
    for ci in range(first_assign_col, last_assign_col + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 20
    ws.column_dimensions[get_column_letter(sum_col)].width = 14
    ws.column_dimensions[get_column_letter(max_col)].width = 15
    ws.column_dimensions[get_column_letter(pct_col)].width = 14
    ws.freeze_panes = "C5"

    # Additional sheet per assignment with deduction details
    for a in assignments_meta:
        aid = a["assignment_id"]
        a_rows = per_assignment_rows.get(aid, [])
        tab_ws = wb.create_sheet(title=_safe_sheet_title(a["title"], used_titles))
        tab_ws.merge_cells("A1:G1")
        tab_ws["A1"] = f"{a['title']} — {classroom_name}"
        tab_ws["A1"].font = title_font
        tab_ws.row_dimensions[1].height = 26

        sub_headers = ["เลขที่", "ชื่อ-นามสกุล", "คะแนนที่ได้", "คะแนนเต็ม", "ร้อยละ (%)", "สถานะ", "รายการที่ถูกหักคะแนน"]
        tab_ws.row_dimensions[3].height = 24
        for ci, h_txt in enumerate(sub_headers, start=1):
            cell = tab_ws.cell(row=3, column=ci, value=h_txt)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        for r_i, r_row in enumerate(a_rows, start=4):
            vals = [
                r_i - 3,
                r_row.get("student_name") or "-",
                float(r_row.get("final_score", 0)),
                float(r_row.get("max_score", 0)),
                float(r_row.get("percentage", 0)),
                r_row.get("status_label") or "-",
                r_row.get("deduction_summary") or "ไม่ถูกหักคะแนน",
            ]
            for ci, val in enumerate(vals, start=1):
                c = tab_ws.cell(row=r_i, column=ci, value=val)
                c.font = body_font
                c.border = border
                if ci in (1, 6):
                    c.alignment = Alignment(horizontal="center")
                elif ci in (3, 4, 5):
                    c.alignment = Alignment(horizontal="right")
                    c.number_format = "0.00"
                elif ci == 7:
                    c.alignment = Alignment(horizontal="left", wrap_text=True)
                if r_i % 2 == 1:
                    c.fill = sub_fill

        for ci, w in enumerate([8, 28, 14, 12, 13, 14, 52], start=1):
            tab_ws.column_dimensions[get_column_letter(ci)].width = w
        tab_ws.freeze_panes = "C4"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_classroom_gradebook_csv(
    assignments_meta: list[dict[str, Any]],
    student_rows: list[dict[str, Any]],
) -> bytes:
    """Create UTF-8 BOM CSV Gradebook for an entire classroom (all graded assignments side-by-side)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    total_max = round(sum(float(a.get("max_score") or 0) for a in assignments_meta), 2)
    header = ["เลขที่", "ชื่อ-นามสกุล"] + [
        f"{a['title']} ({float(a.get('max_score') or 0):g})" for a in assignments_meta
    ] + ["คะแนนรวม", "คะแนนเต็มรวม", "ร้อยละ (%)"]
    writer.writerow(header)

    for idx, st in enumerate(student_rows, start=1):
        scores_map = st.get("scores", {})
        sc_vals = [float(scores_map.get(a["assignment_id"]) or 0.0) for a in assignments_meta]
        tot = round(sum(sc_vals), 2)
        pct = round((tot / total_max * 100.0) if total_max > 0 else 0.0, 2)
        writer.writerow(
            [idx, st["student_name"]]
            + [f"{v:.2f}" for v in sc_vals]
            + [f"{tot:.2f}", f"{total_max:.2f}", f"{pct:.2f}%"]
        )
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
