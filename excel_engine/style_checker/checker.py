"""Style, Position, Worksheet Structure, and Completeness Checkers."""

from __future__ import annotations

from typing import Any

from openpyxl.workbook import Workbook

from excel_engine.formula_checker.checker import expand_cell_targets
from excel_engine.models import GradingErrorRecord, RubricItemConfig, RubricItemResult


def _normalize_color(color_obj: Any) -> str | None:
    if color_obj is None:
        return None
    rgb = getattr(color_obj, "rgb", None)
    if rgb and isinstance(rgb, str) and rgb != "00000000":
        return rgb.upper()[-6:]
    return None


def check_style_item(
    item: RubricItemConfig,
    student_wb: Workbook,
    reference_wb: Workbook | None = None,
) -> RubricItemResult:
    """
    Check cell formatting & aesthetics rules.
    Supports `match_reference_layout_ignore_color=True`:
    Verifies neat borders, bold headers, merged cells, alignment, and number formats
    against the reference workbook — while allowing ANY decorative color chosen by the student.
    """
    cfg = item.rule_config or {}
    sheet_name = item.sheet_name or (student_wb.sheetnames[0] if student_wb.sheetnames else None)
    if not sheet_name or sheet_name not in student_wb.sheetnames:
        return _missing_sheet_result(item, sheet_name)

    ws = student_wb[sheet_name]

    # Auto aesthetics comparison against reference template (color-agnostic!)
    if cfg.get("match_reference_layout_ignore_color") or (not cfg and reference_wb is not None):
        ref_ws = (
            reference_wb[sheet_name]
            if (reference_wb is not None and sheet_name in reference_wb.sheetnames)
            else (reference_wb[reference_wb.sheetnames[0]] if reference_wb and reference_wb.sheetnames else None)
        )
        if ref_ws is not None:
            return _check_aesthetics_against_reference(item, ws, ref_ws, sheet_name)

    targets = expand_cell_targets(item.target_cell) if item.target_cell else ["A1"]

    checks_total = 0
    checks_passed = 0
    errors: list[GradingErrorRecord] = []

    # Check merged range if requested
    if "merged_range" in cfg:
        checks_total += 1
        expected_merge = str(cfg["merged_range"]).upper()
        merged_ranges = {str(rng).upper() for rng in ws.merged_cells.ranges}
        if expected_merge in merged_ranges:
            checks_passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_MERGE_CELLS",
                    severity="warning",
                    sheet_name=sheet_name,
                    cell_reference=expected_merge,
                    message_th=f"ไม่ได้ผสานเซลล์ (Merge Cells) ช่วง {expected_merge}",
                    expected_detail=expected_merge,
                    actual_detail=", ".join(sorted(merged_ranges)) or "ไม่มีการผสานเซลล์",
                    fix_suggestion_th=f"เลือกช่วง {expected_merge} แล้วกด Merge & Center",
                )
            )

    # Check column width
    if "min_column_width" in cfg and "column" in cfg:
        checks_total += 1
        col_letter = str(cfg["column"]).upper()
        actual_w = ws.column_dimensions[col_letter].width or 0
        min_w = float(cfg["min_column_width"])
        if actual_w >= min_w:
            checks_passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="COLUMN_WIDTH_TOO_NARROW",
                    severity="warning",
                    sheet_name=sheet_name,
                    cell_reference=f"Col {col_letter}",
                    message_th=f"ความกว้างคอลัมน์ {col_letter} น้อยกว่าที่กำหนด ({actual_w:.1f} < {min_w})",
                    fix_suggestion_th=f"ปรับความกว้างคอลัมน์ {col_letter} ให้ไม่น้อยกว่า {min_w}",
                )
            )

    # Check row height
    if "min_row_height" in cfg and "row" in cfg:
        checks_total += 1
        row_idx = int(cfg["row"])
        actual_h = ws.row_dimensions[row_idx].height or 0
        min_h = float(cfg["min_row_height"])
        if actual_h >= min_h:
            checks_passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="ROW_HEIGHT_TOO_SMALL",
                    severity="warning",
                    sheet_name=sheet_name,
                    cell_reference=f"Row {row_idx}",
                    message_th=f"ความสูงแถวที่ {row_idx} น้อยกว่าที่กำหนด ({actual_h:.1f} < {min_h})",
                    fix_suggestion_th=f"ปรับความสูงแถวที่ {row_idx} ให้ไม่น้อยกว่า {min_h}",
                )
            )

    # Check any merged title cell if requested
    if cfg.get("require_any_merge"):
        checks_total += 1
        if len(ws.merged_cells.ranges) > 0:
            checks_passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_ANY_MERGE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่มีการผสานเซลล์ (Merge Cells) เช่น หัวตารางหรือหัวเรื่อง",
                    fix_suggestion_th="คลุมหัวเรื่องแล้วกด Merge & Center",
                )
            )

    # Check if student adjusted column widths nicely for decoration
    if cfg.get("require_adjusted_column_width"):
        checks_total += 1
        adjusted = any(
            (dim.width is not None and dim.width >= 12)
            for dim in ws.column_dimensions.values()
        )
        if adjusted:
            checks_passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="UNADJUSTED_COLUMN_WIDTH",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้ปรับความกว้างคอลัมน์ให้พอดีกับข้อมูล",
                    fix_suggestion_th="ปรับความกว้างคอลัมน์ (AutoFit) เพื่อไม่ให้ข้อความถูกตัด",
                )
            )

    # Per-cell style checks
    # If teacher did not specify a cell (or left default 'A1') and asked for general decoration
    # (has_fill_color / has_border / bold), scan the whole table area so shifted headers or Excel Theme Colors pass!
    sheet_has_table_style = len(getattr(ws, "tables", {})) > 0
    if not item.target_cell or (item.target_cell.upper() == "A1" and cfg.get("has_fill_color")):
        used_cells = [
            ws.cell(row=r, column=c)
            for r in range(1, min(ws.max_row or 1, 100) + 1)
            for c in range(1, min(ws.max_column or 1, 30) + 1)
            if ws.cell(row=r, column=c).value is not None or _cell_has_any_fill(ws.cell(row=r, column=c))
        ]
        if cfg.get("has_fill_color"):
            checks_total += 1
            if sheet_has_table_style or any(_cell_has_any_fill(c) for c in used_cells):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_FILL_COLOR",
                        severity="warning",
                        sheet_name=sheet_name,
                        message_th="ยังไม่ได้ใส่สีพื้นหลังตกแต่งตาราง",
                        fix_suggestion_th="เติมสีพื้นหลัง (Fill Color) ให้กับหัวตารางหรือส่วนสรุป",
                    )
                )
        if cfg.get("has_border"):
            checks_total += 1
            if sheet_has_table_style or any(_cell_has_border(c) for c in used_cells):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_BORDER",
                        severity="warning",
                        sheet_name=sheet_name,
                        message_th="ยังไม่ได้ใส่เส้นขอบตาราง (Border)",
                        fix_suggestion_th="คลุมตารางแล้วใส่เส้นขอบ (All Borders)",
                    )
                )
        if "bold" in cfg:
            checks_total += 1
            if sheet_has_table_style or any(bool(c.font and c.font.bold) for c in used_cells):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FONT_BOLD",
                        severity="warning",
                        sheet_name=sheet_name,
                        message_th="ยังไม่ได้กำหนดตัวหนา (Bold) ที่หัวตาราง",
                        fix_suggestion_th="กำหนดตัวหนา (Ctrl+B) ที่หัวตาราง",
                    )
                )
        if "alignment_horizontal" in cfg:
            checks_total += 1
            if any((c.alignment and c.alignment.horizontal == cfg["alignment_horizontal"]) for c in used_cells):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_ALIGNMENT",
                        severity="warning",
                        sheet_name=sheet_name,
                        message_th=f"ยังไม่ได้จัดแนวข้อความเป็น {cfg['alignment_horizontal']}",
                        fix_suggestion_th=f"จัดแนวข้อความหัวตารางเป็น {cfg['alignment_horizontal']}",
                    )
                )
        if "number_format" in cfg:
            checks_total += 1
            exp_fmt = str(cfg["number_format"])
            if any((exp_fmt in str(c.number_format or "") or str(c.number_format or "General") != "General") for c in used_cells):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_NUMBER_FORMAT",
                        severity="error",
                        sheet_name=sheet_name,
                        message_th=f"ยังไม่ได้จัดรูปแบบตัวเลข ({exp_fmt})",
                        fix_suggestion_th=f"เปลี่ยน Number Format ของช่องตัวเลขเป็น {exp_fmt}",
                    )
                )
        return _build_ratio_result(item, checks_passed, checks_total, errors)

    for coord in targets:
        cell = ws[coord]

        if cfg.get("has_fill_color"):
            checks_total += 1
            if sheet_has_table_style or _cell_has_any_fill(cell):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_FILL_COLOR",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ยังไม่ได้ใส่สีพื้นหลังตกแต่งตาราง",
                        fix_suggestion_th=f"เติมสีพื้นหลัง (Fill Color) ให้กับเซลล์ {coord}",
                    )
                )

        if "italic" in cfg:
            checks_total += 1
            if bool(cell.font and cell.font.italic) == bool(cfg["italic"]):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FONT_ITALIC",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ไม่ได้กำหนดตัวเอียง (Italic) ตามคำสั่ง",
                        fix_suggestion_th=f"กำหนดตัวเอียง (Ctrl+I) ที่เซลล์ {coord}",
                    )
                )

        if cfg.get("wrap_text"):
            checks_total += 1
            if bool(cell.alignment and cell.alignment.wrap_text):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_WRAP_TEXT",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ยังไม่ได้เปิดการตัดข้อความ (Wrap Text)",
                        fix_suggestion_th=f"เปิด Wrap Text ที่เซลล์ {coord}",
                    )
                )

        if "font_name" in cfg:
            checks_total += 1
            if cell.font and cell.font.name and cell.font.name.lower() == str(cfg["font_name"]).lower():
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FONT_NAME",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ใช้ฟอนต์ '{cell.font.name if cell.font else None}' (ควรเป็น '{cfg['font_name']}')",
                        expected_detail=str(cfg["font_name"]),
                        actual_detail=str(cell.font.name if cell.font else None),
                        fix_suggestion_th=f"เปลี่ยนฟอนต์เซลล์ {coord} เป็น {cfg['font_name']}",
                    )
                )

        if "font_size" in cfg:
            checks_total += 1
            if cell.font and cell.font.size == float(cfg["font_size"]):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FONT_SIZE",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ขนาดตัวอักษรไม่ตรง ({cell.font.size if cell.font else None} != {cfg['font_size']})",
                        fix_suggestion_th=f"ตั้งขนาดฟอนต์เป็น {cfg['font_size']}",
                    )
                )

        if "bold" in cfg:
            checks_total += 1
            if bool(cell.font and cell.font.bold) == bool(cfg["bold"]):
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FONT_BOLD",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ไม่ได้กำหนดตัวหนา (Bold) ตามเกณฑ์",
                        fix_suggestion_th=f"กำหนดตัวหนา (Ctrl+B) ที่เซลล์ {coord}",
                    )
                )

        if "font_color" in cfg:
            checks_total += 1
            expected_hex = str(cfg["font_color"]).upper().lstrip("#")[-6:]
            actual_hex = _normalize_color(cell.font.color if cell.font else None)
            if actual_hex == expected_hex:
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FONT_COLOR",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"สีตัวอักษรในเซลล์ {coord} ไม่ตรงกับที่กำหนด",
                        expected_detail=f"#{expected_hex}",
                        actual_detail=f"#{actual_hex}" if actual_hex else "Default",
                        fix_suggestion_th=f"เปลี่ยนสีตัวอักษรเซลล์ {coord} เป็น #{expected_hex}",
                    )
                )

        if "fill_color" in cfg:
            checks_total += 1
            expected_hex = str(cfg["fill_color"]).upper().lstrip("#")[-6:]
            actual_hex = _normalize_color(cell.fill.fgColor if cell.fill else None)
            if actual_hex == expected_hex:
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_FILL_COLOR",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"สีพื้นหลังเซลล์ {coord} ไม่ตรงกับที่กำหนด",
                        expected_detail=f"#{expected_hex}",
                        actual_detail=f"#{actual_hex}" if actual_hex else "ไม่มีสีพื้นหลัง",
                        fix_suggestion_th=f"เติมสีพื้นหลังเซลล์ {coord} เป็น #{expected_hex}",
                    )
                )

        if "alignment_horizontal" in cfg:
            checks_total += 1
            actual_align = cell.alignment.horizontal if cell.alignment else None
            if actual_align == cfg["alignment_horizontal"]:
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_ALIGNMENT",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"การจัดแนวข้อความเซลล์ {coord} ไม่ตรง (ได้ {actual_align}, ควรเป็น {cfg['alignment_horizontal']})",
                        fix_suggestion_th=f"จัดแนวเซลล์ {coord} เป็น {cfg['alignment_horizontal']}",
                    )
                )

        if "number_format" in cfg:
            checks_total += 1
            expected_fmt = str(cfg["number_format"])
            actual_fmt = str(cell.number_format or "General")
            if expected_fmt in actual_fmt or actual_fmt == expected_fmt:
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_NUMBER_FORMAT",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"รูปแบบตัวเลขเซลล์ {coord} ไม่ถูกต้อง (ได้ '{actual_fmt}' แต่ควรเป็น '{expected_fmt}')",
                        expected_detail=expected_fmt,
                        actual_detail=actual_fmt,
                        fix_suggestion_th=f"เปลี่ยน Number Format ของเซลล์ {coord} เป็น {expected_fmt}",
                    )
                )

        if cfg.get("has_border"):
            checks_total += 1
            b = cell.border
            has_any = bool(
                b and any(getattr(side, "style", None) for side in (b.left, b.right, b.top, b.bottom))
            )
            if has_any:
                checks_passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_BORDER",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ไม่มีเส้นขอบตาราง (Border)",
                        fix_suggestion_th=f"ใส่เส้นขอบ (All Borders) ที่เซลล์ {coord}",
                    )
                )

    return _build_ratio_result(item, checks_passed, checks_total, errors)


def _cell_has_border(cell: Any) -> bool:
    b = getattr(cell, "border", None)
    return bool(b and any(getattr(side, "style", None) for side in (b.left, b.right, b.top, b.bottom)))


def _cell_has_any_fill(cell: Any) -> bool:
    fill = getattr(cell, "fill", None)
    if not fill or not getattr(fill, "fill_type", None) or fill.fill_type == "none":
        return False
    for color_attr in ("fgColor", "start_color"):
        cobj = getattr(fill, color_attr, None)
        if not cobj:
            continue
        ctype = getattr(cobj, "type", None)
        if ctype == "theme":
            theme_idx = getattr(cobj, "theme", None)
            tint = float(getattr(cobj, "tint", 0.0) or 0.0)
            # theme 0 with tint 0 is plain white background; any other theme or tinted shade is real color
            if theme_idx is not None and not (theme_idx == 0 and abs(tint) < 0.01):
                return True
        elif ctype == "indexed":
            idx = getattr(cobj, "indexed", None)
            # 64 = system auto/transparent, 9 = pure white
            if isinstance(idx, int) and 0 <= idx < 64 and idx != 9:
                return True
        else:
            fg = _normalize_color(cobj)
            if fg and fg not in {"FFFFFF", "000000"}:
                return True
    return False


def _check_aesthetics_against_reference(
    item: RubricItemConfig,
    student_ws: Any,
    ref_ws: Any,
    sheet_name: str,
) -> RubricItemResult:
    """
    Compare visual neatness & layout against reference workbook:
    - Borders match reference cells (neat borders)
    - Merged cells match reference
    - Bold headers match reference
    - Number formats match reference (where non-General)
    - Decorative fill color exists where reference has fill color, WITHOUT requiring the exact same color!
    """
    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []

    max_r = min(ref_ws.max_row or 0, 200)
    max_c = min(ref_ws.max_column or 0, 40)

    # 1. Merged cells match reference
    ref_merges = {str(rng).upper() for rng in ref_ws.merged_cells.ranges}
    if ref_merges:
        stu_merges = {str(rng).upper() for rng in student_ws.merged_cells.ranges}
        for rng in sorted(ref_merges):
            total += 1
            if rng in stu_merges:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_MERGE_CELLS",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=rng,
                        message_th=f"ไม่ได้ผสานเซลล์ช่วง {rng} ให้เหมือนต้นฉบับ",
                        fix_suggestion_th=f"ผสานเซลล์ช่วง {rng} ให้ตรงตามต้นฉบับ",
                    )
                )

    # 2. Scan styled cells in reference
    ref_border_cells: list[str] = []
    ref_bold_cells: list[str] = []
    ref_fill_cells: list[str] = []
    ref_numfmt_cells: list[tuple[str, str]] = []

    for r in range(1, max_r + 1):
        for c in range(1, max_c + 1):
            rc = ref_ws.cell(row=r, column=c)
            coord = rc.coordinate
            if _cell_has_border(rc):
                ref_border_cells.append(coord)
            if rc.font and rc.font.bold and rc.value is not None:
                ref_bold_cells.append(coord)
            if _cell_has_any_fill(rc):
                ref_fill_cells.append(coord)
            if rc.number_format and rc.number_format != "General" and rc.value is not None:
                ref_numfmt_cells.append((coord, str(rc.number_format)))

    # Border neatness check
    if ref_border_cells:
        total += 1
        stu_bordered = sum(1 for coord in ref_border_cells if _cell_has_border(student_ws[coord]))
        if stu_bordered >= len(ref_border_cells) * 0.85:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INCOMPLETE_BORDERS",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"เส้นขอบตารางยังไม่ครบเรียบร้อยตามต้นฉบับ (ใส่เส้นขอบ {stu_bordered}/{len(ref_border_cells)} ช่อง)",
                    fix_suggestion_th="คลุมตารางข้อมูลแล้วใส่เส้นขอบ (All Borders) ให้ครบเรียบร้อยเหมือนต้นฉบับ",
                )
            )

    # Bold formatting check
    if ref_bold_cells:
        total += 1
        stu_bold = sum(
            1 for coord in ref_bold_cells if bool(student_ws[coord].font and student_ws[coord].font.bold)
        )
        if stu_bold >= len(ref_bold_cells) * 0.85:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INCOMPLETE_BOLD_STYLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ยังไม่ได้เน้นตัวหนาหัวตาราง/หัวข้อให้ครบตามต้นฉบับ ({stu_bold}/{len(ref_bold_cells)} ช่อง)",
                    fix_suggestion_th="กำหนดตัวหนา (Bold) ที่หัวตารางและส่วนสรุปให้เหมือนต้นฉบับ",
                )
            )

    # Color decoration check (ANY color allowed — supports RGB, Theme Colors, Indexed Colors & Excel Tables!)
    if ref_fill_cells:
        total += 1
        stu_has_table = len(getattr(student_ws, "tables", {})) > 0
        stu_filled_exact = sum(1 for coord in ref_fill_cells if _cell_has_any_fill(student_ws[coord]))
        # Also count total colored cells across student's sheet in case student shifted rows slightly
        stu_total_filled = sum(
            1
            for r in range(1, min(student_ws.max_row or 0, 200) + 1)
            for c in range(1, min(student_ws.max_column or 0, 40) + 1)
            if _cell_has_any_fill(student_ws.cell(row=r, column=c))
        )
        if stu_has_table or stu_filled_exact >= len(ref_fill_cells) * 0.6 or stu_total_filled >= max(2, int(len(ref_fill_cells) * 0.6)):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_DECORATIVE_COLOR",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ยังไม่ได้เติมสีตกแต่งตารางให้ครบ ({max(stu_filled_exact, stu_total_filled)}/{len(ref_fill_cells)} ช่อง — สามารถเลือกใช้โทนสีใดก็ได้)",
                    fix_suggestion_th="เติมสีพื้นหลังตกแต่งหัวตารางหรือแถวสรุปให้สวยงาม (ไม่จำเป็นต้องใช้สีเดียวกับต้นฉบับ)",
                )
            )

    # Number format check
    if ref_numfmt_cells:
        total += 1
        stu_fmt = sum(
            1
            for coord, exp_fmt in ref_numfmt_cells
            if str(student_ws[coord].number_format or "General") != "General"
        )
        if stu_fmt >= len(ref_numfmt_cells) * 0.85:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INCOMPLETE_NUMBER_FORMAT",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"รูปแบบตัวเลข (เช่น ทศนิยม/สกุลเงิน) ยังไม่ครบตามต้นฉบับ ({stu_fmt}/{len(ref_numfmt_cells)} ช่อง)",
                    fix_suggestion_th="จัดรูปแบบตัวเลข (Number Format) ให้เรียบร้อยตามต้นฉบับ",
                )
            )

    return _build_ratio_result(item, passed, total, errors)


def check_position_item(
    item: RubricItemConfig,
    student_value_wb: Workbook,
    reference_value_wb: Workbook | None = None,
) -> RubricItemResult:
    """Check that required cells contain data at exact positions (not shifted/missing)."""
    cfg = item.rule_config or {}
    sheet_name = item.sheet_name or (student_value_wb.sheetnames[0] if student_value_wb.sheetnames else None)
    if not sheet_name or sheet_name not in student_value_wb.sheetnames:
        return _missing_sheet_result(item, sheet_name)

    ws = student_value_wb[sheet_name]
    expected_cells: dict[str, Any] = cfg.get("expected_cells", {})
    required_non_empty: list[str] = cfg.get("required_non_empty", [])

    if not expected_cells and not required_non_empty and item.target_cell:
        required_non_empty = expand_cell_targets(item.target_cell)

    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []

    for coord, expected_val in expected_cells.items():
        total += 1
        actual_val = ws[coord].value
        if actual_val is not None and str(actual_val).strip().lower() == str(expected_val).strip().lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CELL_POSITION",
                    severity="error",
                    sheet_name=sheet_name,
                    cell_reference=coord,
                    message_th=f"ข้อมูลในตำแหน่ง {coord} ไม่ตรงตามตำแหน่งที่กำหนด (พบ {actual_val!r} ควรเป็น {expected_val!r})",
                    expected_detail=str(expected_val),
                    actual_detail=str(actual_val),
                    fix_suggestion_th=f"ย้ายหรือกรอกข้อมูล '{expected_val}' ให้ตรงกับเซลล์ {coord}",
                )
            )

    for coord in required_non_empty:
        total += 1
        val = ws[coord].value
        if val is not None and str(val).strip() != "":
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CELL_DATA",
                    severity="error",
                    sheet_name=sheet_name,
                    cell_reference=coord,
                    message_th=f"ไม่พบข้อมูลในเซลล์ {coord} (เซลล์ว่างหรือข้อมูลอยู่ผิดตำแหน่ง)",
                    expected_detail="ต้องมีข้อมูล",
                    actual_detail="(ว่าง)",
                    fix_suggestion_th=f"ตรวจสอบตำแหน่งข้อมูลในเซลล์ {coord}",
                )
            )

    return _build_ratio_result(item, passed, total, errors)


def check_structure_item(
    item: RubricItemConfig,
    student_wb: Workbook,
) -> RubricItemResult:
    """Check worksheet structure: sheet names, count, order, hidden state, tables, charts."""
    cfg = item.rule_config or {}
    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []
    sheet_names = list(student_wb.sheetnames)

    if "required_sheets" in cfg:
        for req_name in cfg["required_sheets"]:
            total += 1
            if req_name in sheet_names:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_WORKSHEET",
                        severity="error",
                        sheet_name=req_name,
                        message_th=f"ไม่พบแผ่นงาน (Worksheet) ชื่อ '{req_name}'",
                        expected_detail=req_name,
                        actual_detail=", ".join(sheet_names),
                        fix_suggestion_th=f"สร้างหรือเปลี่ยนชื่อแผ่นงานเป็น '{req_name}'",
                    )
                )

    if "exact_sheet_count" in cfg:
        total += 1
        expected_cnt = int(cfg["exact_sheet_count"])
        if len(sheet_names) == expected_cnt:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_SHEET_COUNT",
                    severity="error",
                    message_th=f"จำนวน Worksheet ไม่ตรงตามกำหนด (มี {len(sheet_names)} แผ่น ควรมี {expected_cnt} แผ่น)",
                    expected_detail=str(expected_cnt),
                    actual_detail=str(len(sheet_names)),
                    fix_suggestion_th=f"ตรวจสอบจำนวนแผ่นงานให้มีทั้งหมด {expected_cnt} แผ่น",
                )
            )

    if "expected_sheet_order" in cfg:
        total += 1
        expected_order = list(cfg["expected_sheet_order"])
        if sheet_names[: len(expected_order)] == expected_order:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_SHEET_ORDER",
                    severity="warning",
                    message_th=f"ลำดับ Worksheet ไม่ตรงตามกำหนด",
                    expected_detail=" -> ".join(expected_order),
                    actual_detail=" -> ".join(sheet_names),
                    fix_suggestion_th=f"จัดเรียงลำดับแผ่นงานเป็น: {', '.join(expected_order)}",
                )
            )

    if cfg.get("no_hidden_sheets"):
        total += 1
        hidden = [name for name in sheet_names if student_wb[name].sheet_state != "visible"]
        if not hidden:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="HIDDEN_WORKSHEET_FOUND",
                    severity="warning",
                    message_th=f"พบแผ่นงานที่ถูกซ่อนอยู่: {', '.join(hidden)}",
                    fix_suggestion_th="ยกเลิกการซ่อนแผ่นงาน (Unhide Sheet)",
                )
            )

    if cfg.get("require_table"):
        total += 1
        target_sheet = item.sheet_name or (sheet_names[0] if sheet_names else None)
        ws = student_wb[target_sheet] if target_sheet and target_sheet in student_wb.sheetnames else None
        if ws and len(getattr(ws, "tables", {})) > 0:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_EXCEL_TABLE",
                    severity="warning",
                    sheet_name=target_sheet,
                    message_th="ไม่พบตารางรูปแบบ Excel Table (Format as Table)",
                    fix_suggestion_th="คลุมข้อมูลแล้วเลือก Insert > Table",
                )
            )

    if (
        cfg.get("require_autofilter")
        or cfg.get("require_filter_applied")
        or cfg.get("require_no_active_filter")
        or cfg.get("filter_conditions")
    ):
        ws, resolved_sheet = _resolve_worksheet_fuzzy(student_wb, item.sheet_name)
        if ws is None:
            total += 1
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_WORKSHEET",
                    severity="error",
                    sheet_name=item.sheet_name,
                    message_th=f"ไม่พบแผ่นงาน (แท็บ) '{item.sheet_name}' สำหรับตรวจตัวกรองข้อมูล",
                    expected_detail=item.sheet_name or "",
                    actual_detail=", ".join(sheet_names),
                    fix_suggestion_th=f"ตรวจสอบชื่อแท็บแผ่นงานให้ตรงกับ '{item.sheet_name}'",
                )
            )
            return _build_ratio_result(item, passed, total, errors)

        af_ref, has_filter_col = _inspect_worksheet_autofilter(ws)
        header_row, data_rows = _find_table_header_and_data_rows(ws, cfg, af_ref)
        visible_rows = [r for r in data_rows if not bool(getattr(ws.row_dimensions[r], "hidden", False))]
        hidden_rows = [r for r in data_rows if bool(getattr(ws.row_dimensions[r], "hidden", False))]

        # Case A: Clear all filters check (e.g., ข้อ 6 ยกเลิกตัวกรองทั้งหมด แสดงครบ 30 รายการ)
        if cfg.get("require_no_active_filter"):
            total += 1
            if not has_filter_col and len(hidden_rows) == 0:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="FILTER_STILL_ACTIVE",
                        severity="error",
                        sheet_name=resolved_sheet,
                        message_th=(
                            f"แท็บ '{resolved_sheet}' ยังไม่ได้ยกเลิกตัวกรองข้อมูลทั้งหมด "
                            f"(ยังมีแถวที่ถูกซ่อนอยู่ {len(hidden_rows)} แถว)"
                        ),
                        expected_detail="ไม่มีตัวกรองค้างอยู่และไม่มีแถวที่ถูกซ่อน",
                        actual_detail=f"ซ่อนอยู่ {len(hidden_rows)} แถว",
                        fix_suggestion_th="ไปที่แท็บ Data > Clear (ล้างตัวกรอง) เพื่อให้ข้อมูลกลับมาแสดงครบทุกแถว",
                    )
                )

            exp_vis = cfg.get("expected_visible_rows") or cfg.get("min_visible_rows")
            if exp_vis is not None:
                total += 1
                exp_vis_int = int(exp_vis)
                if len(visible_rows) >= exp_vis_int:
                    passed += 1
                else:
                    errors.append(
                        GradingErrorRecord(
                            error_code="INSUFFICIENT_VISIBLE_ROWS",
                            severity="error",
                            sheet_name=resolved_sheet,
                            message_th=(
                                f"แท็บ '{resolved_sheet}' แสดงข้อมูลไม่ครบตามกำหนด "
                                f"(แสดงอยู่ {len(visible_rows)} รายการ ควรแสดงครบ {exp_vis_int} รายการ)"
                            ),
                            expected_detail=f"{exp_vis_int} รายการ",
                            actual_detail=f"{len(visible_rows)} รายการ",
                            fix_suggestion_th=f"ยกเลิกตัวกรองข้อมูลทั้งหมดเพื่อให้แสดงครบ {exp_vis_int} รายการ",
                        )
                    )
        else:
            # Case B: AutoFilter enabled check
            if cfg.get("require_autofilter") or cfg.get("require_filter_applied") or cfg.get("filter_conditions"):
                total += 1
                if af_ref:
                    passed += 1
                else:
                    errors.append(
                        GradingErrorRecord(
                            error_code="MISSING_AUTOFILTER",
                            severity="error",
                            sheet_name=resolved_sheet,
                            message_th=f"แท็บ '{resolved_sheet}' ยังไม่ได้เปิดใช้งานตัวกรองข้อมูล (Filter / AutoFilter)",
                            expected_detail="เปิด AutoFilter",
                            actual_detail="ไม่ได้เปิด AutoFilter",
                            fix_suggestion_th="คลุมหัวตารางแล้วไปที่แท็บ Data > Filter (หรือกด Ctrl+Shift+L)",
                        )
                    )

            # Case C: At least one filter applied
            if cfg.get("require_filter_applied") and not cfg.get("filter_conditions"):
                total += 1
                if has_filter_col or len(hidden_rows) > 0:
                    passed += 1
                else:
                    errors.append(
                        GradingErrorRecord(
                            error_code="FILTER_NOT_APPLIED",
                            severity="warning",
                            sheet_name=resolved_sheet,
                            message_th=f"แท็บ '{resolved_sheet}' เปิดปุ่ม Filter แล้ว แต่ยังไม่ได้เลือกเงื่อนไขกรองข้อมูล",
                            expected_detail="มีการกรองข้อมูลตามเงื่อนไข",
                            actual_detail="ยังแสดงข้อมูลครบทุกแถว (ไม่ได้กรอง)",
                            fix_suggestion_th="คลิกปุ่มลูกศร Filter ที่หัวคอลัมน์แล้วเลือกเงื่อนไขกรองตามโจทย์",
                        )
                    )

            # Case D: Detailed filter_conditions verification (supports ALL operators & multi-column AND!)
            conditions = cfg.get("filter_conditions") or []
            if conditions and data_rows:
                total += 1
                cond_evals: list[tuple[int | None, dict[str, Any]]] = []
                missing_cols: list[str] = []
                for cond in conditions:
                    col_idx = _resolve_filter_column_index(ws, header_row, data_rows, cond)
                    if col_idx is None:
                        missing_cols.append(str(cond.get("column") or cond.get("value") or "?"))
                    cond_evals.append((col_idx, cond))

                if missing_cols:
                    errors.append(
                        GradingErrorRecord(
                            error_code="FILTER_COLUMN_NOT_FOUND",
                            severity="error",
                            sheet_name=resolved_sheet,
                            message_th=f"แท็บ '{resolved_sheet}' ไม่พบคอลัมน์สำหรับเงื่อนไขกรอง: {', '.join(missing_cols)}",
                            fix_suggestion_th="ตรวจสอบชื่อหัวคอลัมน์หรือตำแหน่งตารางให้ครบถ้วน",
                        )
                    )
                else:
                    expected_match_rows = [
                        r
                        for r in data_rows
                        if all(
                            _eval_filter_condition(
                                ws.cell(row=r, column=c_idx).value,
                                str(cond.get("operator") or "equals"),
                                cond.get("value"),
                                cond.get("value2"),
                            )
                            for c_idx, cond in cond_evals
                            if c_idx is not None
                        )
                    ]
                    expected_set = set(expected_match_rows)
                    visible_set = set(visible_rows)
                    wrongly_visible = visible_set - expected_set
                    wrongly_hidden = expected_set - visible_set

                    if len(wrongly_visible) == 0 and len(wrongly_hidden) == 0 and (len(expected_set) == 0 or len(visible_set) > 0):
                        passed += 1
                    else:
                        reason_parts = []
                        if len(hidden_rows) == 0 and len(expected_set) < len(data_rows):
                            reason_parts.append("ยังไม่ได้กรองข้อมูล (ยังคงแสดงครบทุกแถว)")
                        else:
                            if wrongly_visible:
                                reason_parts.append(f"มีแถวที่ไม่ตรงเงื่อนไขแสดงเกินมา {len(wrongly_visible)} แถว")
                            if wrongly_hidden:
                                reason_parts.append(f"มีแถวที่ตรงเงื่อนไขถูกซ่อนหายไป {len(wrongly_hidden)} แถว")
                        cond_desc = " และ ".join(_format_filter_condition_th(c) for c in conditions)
                        errors.append(
                            GradingErrorRecord(
                                error_code="FILTER_CONDITION_MISMATCH",
                                severity="error",
                                sheet_name=resolved_sheet,
                                message_th=(
                                    f"แท็บ '{resolved_sheet}' ผลการกรองไม่ตรงเงื่อนไข ({cond_desc}): "
                                    + " / ".join(reason_parts)
                                ),
                                expected_detail=f"ควรแสดงเฉพาะ {len(expected_set)} แถวที่ตรงเงื่อนไข ({cond_desc})",
                                actual_detail=f"แสดงอยู่ {len(visible_set)} แถว",
                                fix_suggestion_th=f"ตั้งค่าตัวกรองข้อมูลในแท็บ '{resolved_sheet}' ให้ตรงเงื่อนไข: {cond_desc}",
                            )
                        )

    return _build_ratio_result(item, passed, total, errors)


def _resolve_worksheet_fuzzy(wb: Workbook, requested_name: str | None) -> tuple[Any | None, str]:
    """Find worksheet by exact name, normalized name, Thai number match ('ข้อ 1' -> 'ข้อ1'), or tab index."""
    import re

    names = list(wb.sheetnames)
    if not names:
        return None, requested_name or ""
    if not requested_name or not requested_name.strip():
        return wb[names[0]], names[0]

    req = requested_name.strip()
    if req in wb.sheetnames:
        return wb[req], req

    norm_req = re.sub(r"\s+", "", req).lower()
    for n in names:
        if re.sub(r"\s+", "", n).lower() == norm_req:
            return wb[n], n
    for n in names:
        norm_n = re.sub(r"\s+", "", n).lower()
        if norm_req in norm_n or norm_n in norm_req:
            return wb[n], n

    # Match by exercise number (e.g. "ข้อ 3" -> tab containing "3" or 3rd tab)
    m_num = re.search(r"(\d+)", req)
    if m_num:
        num_str = m_num.group(1)
        for n in names:
            if re.search(rf"(?:ข้อ\s*|sheet\s*|^){num_str}(?:\D|$)", n, re.IGNORECASE):
                return wb[n], n
        idx = int(num_str) - 1
        if 0 <= idx < len(names):
            return wb[names[idx]], names[idx]

    return None, req


def _inspect_worksheet_autofilter(ws: Any) -> tuple[str | None, bool]:
    """Return (autofilter_ref, has_active_filter_column) from sheet auto_filter or Excel Table."""
    af = getattr(ws, "auto_filter", None)
    if af and getattr(af, "ref", None):
        has_col = len(getattr(af, "filterColumn", []) or []) > 0
        return str(af.ref), has_col

    if getattr(ws, "tables", None):
        for tbl in ws.tables.values():
            taf = getattr(tbl, "autoFilter", None)
            if taf and getattr(taf, "ref", None):
                has_col = len(getattr(taf, "filterColumn", []) or []) > 0
                return str(taf.ref), has_col
    return None, False


def _find_table_header_and_data_rows(ws: Any, cfg: dict[str, Any], af_ref: str | None) -> tuple[int, list[int]]:
    """Detect header row and all non-empty data row indices below it."""
    import re

    header_row: int | None = int(cfg["header_row"]) if cfg.get("header_row") else None
    max_r = min(ws.max_row or 0, 2000)
    max_c = min(ws.max_column or 0, 50)

    if header_row is None and af_ref:
        m = re.match(r"^[A-Za-z]+(\d+):[A-Za-z]+(\d+)$", af_ref.replace("$", ""))
        if m:
            header_row = int(m.group(1))

    if header_row is None:
        for r in range(1, min(max_r, 10) + 1):
            non_empty = [ws.cell(row=r, column=c).value for c in range(1, max_c + 1) if ws.cell(row=r, column=c).value is not None]
            if len(non_empty) >= 2:
                header_row = r
                break
        if header_row is None:
            header_row = 1

    data_rows: list[int] = []
    for r in range(header_row + 1, max_r + 1):
        if any(ws.cell(row=r, column=c).value is not None and str(ws.cell(row=r, column=c).value).strip() != "" for c in range(1, max_c + 1)):
            data_rows.append(r)
    return header_row, data_rows


def _resolve_filter_column_index(
    ws: Any,
    header_row: int,
    data_rows: list[int],
    cond: dict[str, Any],
) -> int | None:
    """Resolve column index from letter ('C'), header text ('ยี่ห้อ'), or auto-detect from data."""
    import re
    from openpyxl.utils import column_index_from_string

    max_c = min(ws.max_column or 0, 50)
    col_spec = str(cond.get("column") or "").strip()

    if col_spec:
        if re.fullmatch(r"[A-Za-z]{1,2}", col_spec):
            return column_index_from_string(col_spec.upper())

        spec_low = col_spec.lower()
        # Exact header match first
        for c in range(1, max_c + 1):
            hv = str(ws.cell(row=header_row, column=c).value or "").strip().lower()
            if hv == spec_low:
                return c
        # Substring header match
        for c in range(1, max_c + 1):
            hv = str(ws.cell(row=header_row, column=c).value or "").strip().lower()
            if hv and (spec_low in hv or hv in spec_low):
                return c

    # Auto-detect column by scanning which column has values matching the condition
    op = str(cond.get("operator") or "equals").lower()
    val = cond.get("value")
    val2 = cond.get("value2")
    best_col = None
    best_hits = 0
    for c in range(1, max_c + 1):
        hits = 0
        for r in data_rows:
            cell_v = ws.cell(row=r, column=c).value
            if cell_v is None:
                continue
            if _eval_filter_condition(cell_v, op, val, val2):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_col = c
    return best_col


def _to_float_safe(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        cleaned = str(v).strip().replace(",", "").replace("฿", "").replace("%", "")
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _eval_filter_condition(cell_val: Any, operator: str, value: Any, value2: Any = None) -> bool:
    op = (operator or "equals").strip().lower()
    if cell_val is None:
        return False

    # Numeric operators
    if op in ("gt", "gte", "lt", "lte", "between"):
        num = _to_float_safe(cell_val)
        t1 = _to_float_safe(value)
        if num is None or t1 is None:
            return False
        if op == "gt":
            return num > t1
        if op == "gte":
            return num >= t1
        if op == "lt":
            return num < t1
        if op == "lte":
            return num <= t1
        if op == "between":
            t2 = _to_float_safe(value2)
            if t2 is None and isinstance(value, (list, tuple)) and len(value) >= 2:
                t1 = _to_float_safe(value[0])
                t2 = _to_float_safe(value[1])
            if t1 is None or t2 is None:
                return False
            return min(t1, t2) <= num <= max(t1, t2)

    s_cell = str(cell_val).strip().lower()
    if op == "in" and isinstance(value, (list, tuple, set)):
        targets = {str(x).strip().lower() for x in value}
        return s_cell in targets

    s_val = str(value if value is not None else "").strip().lower()
    if op == "equals":
        num_c = _to_float_safe(cell_val)
        num_v = _to_float_safe(value)
        if num_c is not None and num_v is not None:
            return abs(num_c - num_v) < 1e-9
        return s_cell == s_val
    if op == "not_equals":
        return not _eval_filter_condition(cell_val, "equals", value)
    if op == "contains":
        return s_val in s_cell
    if op == "not_contains":
        return s_val not in s_cell
    if op == "starts_with":
        return s_cell.startswith(s_val)
    if op == "ends_with":
        return s_cell.endswith(s_val)
    return s_cell == s_val


def _format_filter_condition_th(cond: dict[str, Any]) -> str:
    col = cond.get("column") or "ข้อมูล"
    op = str(cond.get("operator") or "equals").lower()
    val = cond.get("value")
    val2 = cond.get("value2")
    op_map = {
        "equals": f"{col} = '{val}'",
        "not_equals": f"{col} ≠ '{val}'",
        "contains": f"{col} มีคำว่า '{val}'",
        "not_contains": f"{col} ไม่มีคำว่า '{val}'",
        "starts_with": f"{col} ขึ้นต้นด้วย '{val}'",
        "ends_with": f"{col} ลงท้ายด้วย '{val}'",
        "gt": f"{col} > {val}",
        "gte": f"{col} >= {val}",
        "lt": f"{col} < {val}",
        "lte": f"{col} <= {val}",
        "between": f"{col} ระหว่าง {val} ถึง {val2}",
        "in": f"{col} อยู่ใน {val}",
    }
    return op_map.get(op, f"{col} {op} {val}")


def check_completeness_item(
    item: RubricItemConfig,
    student_value_wb: Workbook,
) -> RubricItemResult:
    """Check completeness: min_rows, required_headers, sorted_column."""
    cfg = item.rule_config or {}
    sheet_name = item.sheet_name or (student_value_wb.sheetnames[0] if student_value_wb.sheetnames else None)
    if not sheet_name or sheet_name not in student_value_wb.sheetnames:
        return _missing_sheet_result(item, sheet_name)

    ws = student_value_wb[sheet_name]
    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []

    if "required_headers" in cfg:
        header_row = int(cfg.get("header_row", 1))
        actual_headers = [
            str(ws.cell(row=header_row, column=c).value or "").strip().lower()
            for c in range(1, (ws.max_column or 0) + 1)
        ]
        for h in cfg["required_headers"]:
            total += 1
            if str(h).strip().lower() in actual_headers:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_HEADER",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=f"Row {header_row}",
                        message_th=f"ไม่พบหัวตาราง '{h}' ในแถวที่ {header_row}",
                        expected_detail=str(h),
                        fix_suggestion_th=f"เพิ่มหัวตาราง '{h}' ในแถวที่ {header_row}",
                    )
                )

    if "min_data_rows" in cfg:
        total += 1
        header_row = int(cfg.get("header_row", 1))
        non_empty_rows = 0
        for r in range(header_row + 1, (ws.max_row or 0) + 1):
            if any(ws.cell(row=r, column=c).value is not None for c in range(1, (ws.max_column or 0) + 1)):
                non_empty_rows += 1
        min_rows = int(cfg["min_data_rows"])
        if non_empty_rows >= min_rows:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INCOMPLETE_DATA_ROWS",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"จำนวนแถวข้อมูลไม่ครบ (พบ {non_empty_rows} แถว ต้องการอย่างน้อย {min_rows} แถว)",
                    expected_detail=f">= {min_rows} แถว",
                    actual_detail=f"{non_empty_rows} แถว",
                    fix_suggestion_th="ตรวจสอบและกรอกข้อมูลให้ครบทุกแถวตามโจทย์",
                )
            )

    if "min_columns" in cfg:
        total += 1
        actual_cols = ws.max_column or 0
        min_cols = int(cfg["min_columns"])
        if actual_cols >= min_cols:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INCOMPLETE_COLUMNS",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"จำนวนคอลัมน์ไม่ครบตามคำสั่ง (พบ {actual_cols} คอลัมน์ ต้องการอย่างน้อย {min_cols} คอลัมน์)",
                    expected_detail=f">= {min_cols} คอลัมน์",
                    actual_detail=f"{actual_cols} คอลัมน์",
                    fix_suggestion_th="เพิ่มคอลัมน์ข้อมูลให้ครบตามโจทย์กำหนด",
                )
            )

    if "required_keywords" in cfg:
        all_texts = []
        for r in range(1, min(ws.max_row or 0, 500) + 1):
            for c in range(1, min(ws.max_column or 0, 50) + 1):
                v = ws.cell(row=r, column=c).value
                if v is not None:
                    all_texts.append(str(v).strip().lower())
        joined_blob = " | ".join(all_texts)
        for kw in cfg["required_keywords"]:
            total += 1
            if str(kw).strip().lower() in joined_blob:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_ADDED_DATA",
                        severity="error",
                        sheet_name=sheet_name,
                        message_th=f"ไม่พบข้อมูลที่สั่งให้ใส่เพิ่ม: '{kw}'",
                        expected_detail=str(kw),
                        actual_detail="ไม่พบในแผ่นงาน",
                        fix_suggestion_th=f"กรอกข้อมูล '{kw}' เพิ่มลงในตารางตามคำสั่ง",
                    )
                )

    if "no_empty_cells_in_range" in cfg:
        rng_cells = expand_cell_targets(str(cfg["no_empty_cells_in_range"]))
        for coord in rng_cells:
            total += 1
            v = ws[coord].value
            if v is not None and str(v).strip() != "":
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_ADDED_CELL_DATA",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ยังว่างอยู่ (ไม่ได้ใส่ข้อมูลเพิ่มให้ครบตามคำสั่ง)",
                        expected_detail="ต้องมีข้อมูล",
                        actual_detail="(ว่าง)",
                        fix_suggestion_th=f"กรอกข้อมูลในเซลล์ {coord} ให้ครบถ้วน",
                    )
                )

    if "sorted_column" in cfg:
        total += 1
        col_letter = str(cfg["sorted_column"]).upper()
        direction = str(cfg.get("sort_direction", "asc")).lower()
        start_row = int(cfg.get("data_start_row", 2))
        end_row = int(cfg.get("data_end_row", ws.max_row or start_row))
        vals = [ws[f"{col_letter}{r}"].value for r in range(start_row, end_row + 1)]
        vals = [v for v in vals if v is not None]
        try:
            expected_sorted = sorted(vals, reverse=(direction == "desc"))
            if vals == expected_sorted:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_SORT_ORDER",
                        severity="warning",
                        sheet_name=sheet_name,
                        cell_reference=f"{col_letter}{start_row}:{col_letter}{end_row}",
                        message_th=f"ข้อมูลในคอลัมน์ {col_letter} ไม่ได้เรียงลำดับแบบ {direction.upper()}",
                        fix_suggestion_th=f"จัดเรียงข้อมูลคอลัมน์ {col_letter} แบบ {'จากมากไปน้อย' if direction == 'desc' else 'จากน้อยไปมาก'}",
                    )
                )
        except TypeError:
            errors.append(
                GradingErrorRecord(
                    error_code="SORT_TYPE_MISMATCH",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชนิดข้อมูลในคอลัมน์ {col_letter} ปะปนกัน ไม่สามารถตรวจสอบการเรียงลำดับได้",
                )
            )

    return _build_ratio_result(item, passed, total, errors)


def _missing_sheet_result(item: RubricItemConfig, sheet_name: str | None) -> RubricItemResult:
    err = GradingErrorRecord(
        error_code="MISSING_WORKSHEET",
        severity="error",
        sheet_name=sheet_name,
        message_th=f"ไม่พบ Worksheet '{sheet_name}' ในไฟล์ของนักเรียน",
        fix_suggestion_th=f"ตรวจสอบชื่อแผ่นงานให้ตรงกับ '{sheet_name}'",
    )
    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category=item.category,
        target_cell=item.target_cell,
        earned_points=0.0,
        deducted_points=item.max_points,
        max_points=item.max_points,
        passed=False,
        reason=err.message_th,
        suggestion=err.fix_suggestion_th,
        errors=[err],
    )


def _build_ratio_result(
    item: RubricItemConfig,
    passed: int,
    total: int,
    errors: list[GradingErrorRecord],
) -> RubricItemResult:
    if total == 0:
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category=item.category,
            target_cell=item.target_cell,
            earned_points=item.max_points,
            deducted_points=0.0,
            max_points=item.max_points,
            passed=True,
            reason="ผ่านเกณฑ์ (ไม่มีเงื่อนไขย่อยเพิ่มเติม)",
        )

    all_passed = passed == total
    if all_passed:
        earned = item.max_points
        reason = f"ผ่านเกณฑ์ครบทั้ง {total} รายการ"
        suggestion = None
    elif item.zero_on_error:
        earned = 0.0
        reason = f"ไม่ผ่านเกณฑ์ ({passed}/{total} รายการ) — เกณฑ์กำหนดให้ได้ 0 คะแนน"
        suggestion = errors[0].fix_suggestion_th if errors else None
    elif item.allow_partial_credit:
        earned = round(item.max_points * (passed / total), 2)
        reason = f"ผ่านบางส่วน {passed}/{total} รายการ"
        suggestion = errors[0].fix_suggestion_th if errors else None
    else:
        earned = 0.0
        reason = errors[0].message_th if errors else "ไม่ผ่านเกณฑ์"
        suggestion = errors[0].fix_suggestion_th if errors else None

    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category=item.category,
        target_cell=item.target_cell,
        earned_points=earned,
        deducted_points=round(item.max_points - earned, 2),
        max_points=item.max_points,
        passed=all_passed,
        reason=reason,
        suggestion=suggestion,
        evidence={"passed_checks": passed, "total_checks": total},
        errors=errors,
    )
