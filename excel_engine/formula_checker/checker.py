"""Formula Checker: validates real Excel formulas (never just cached values)."""

from __future__ import annotations

from typing import Any

from openpyxl.utils import range_boundaries
from openpyxl.workbook import Workbook

from excel_engine.formula_checker.normalizer import analyze_formula, are_formulas_equivalent
from excel_engine.models import GradingErrorRecord, RubricItemConfig, RubricItemResult


def expand_cell_targets(target_cell: str) -> list[str]:
    """Expand 'D2' -> ['D2'], or 'D2:D5' -> ['D2', 'D3', 'D4', 'D5']."""
    if ":" not in target_cell:
        return [target_cell.strip().upper()]
    min_col, min_row, max_col, max_row = range_boundaries(target_cell.strip().upper())
    from openpyxl.utils import get_column_letter

    coords: list[str] = []
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            coords.append(f"{get_column_letter(c)}{r}")
    return coords


def check_formula_item(
    item: RubricItemConfig,
    student_formula_wb: Workbook,
    reference_formula_wb: Workbook | None = None,
) -> RubricItemResult:
    """
    Evaluate a 'formula' rubric item against the student's workbook (data_only=False).

    Supported rule_config keys:
    - expected_formula: str (optional; if omitted, read from reference_formula_wb)
    - accepted_formulas: list[str] (optional alternative valid formulas)
    - required_functions: list[str] (e.g. ["SUM"], ["IF"])
    - required_ranges: list[str] (e.g. ["B2:B10"])
    - require_absolute_reference: bool (checks '$' presence or strict match)
    - strict_reference_mode: bool (distinguish $A$1 vs A1 strictly)
    - min_nested_if_depth: int (e.g. 2 for nested IF)
    - require_cross_sheet: str | None (expected referenced sheet name)
    """
    cfg: dict[str, Any] = item.rule_config or {}
    sheet_name = item.sheet_name or (student_formula_wb.sheetnames[0] if student_formula_wb.sheetnames else None)

    if not sheet_name or sheet_name not in student_formula_wb.sheetnames:
        err = GradingErrorRecord(
            error_code="MISSING_WORKSHEET",
            severity="error",
            sheet_name=sheet_name,
            cell_reference=item.target_cell,
            message_th=f"ไม่พบ Worksheet ชื่อ '{sheet_name}' ในไฟล์ของนักเรียน",
            expected_detail=f"Worksheet '{sheet_name}'",
            actual_detail=", ".join(student_formula_wb.sheetnames),
            fix_suggestion_th=f"ตรวจสอบชื่อแผ่นงานให้ตรงกับ '{sheet_name}'",
        )
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category="formula",
            target_cell=item.target_cell,
            earned_points=0.0,
            deducted_points=item.max_points,
            max_points=item.max_points,
            passed=False,
            reason=err.message_th,
            suggestion=err.fix_suggestion_th,
            errors=[err],
        )

    ws = student_formula_wb[sheet_name]
    ref_ws = (
        reference_formula_wb[sheet_name]
        if (reference_formula_wb is not None and sheet_name in reference_formula_wb.sheetnames)
        else None
    )

    if not item.target_cell:
        return _check_formula_auto_detect(
            item=item,
            student_formula_wb=student_formula_wb,
            reference_formula_wb=reference_formula_wb,
        )

    targets = expand_cell_targets(item.target_cell)
    strict_ref = bool(cfg.get("strict_reference_mode", False))
    require_abs = bool(cfg.get("require_absolute_reference", False))
    required_funcs = [f.upper() for f in cfg.get("required_functions", [])]
    required_ranges = [r.upper().replace("$", "") for r in cfg.get("required_ranges", [])]
    min_if_depth = int(cfg.get("min_nested_if_depth", 0))
    require_cross_sheet = cfg.get("require_cross_sheet")
    accepted_formulas: list[str] = list(cfg.get("accepted_formulas", []))

    passed_cells = 0
    errors: list[GradingErrorRecord] = []
    actual_samples: list[str] = []
    expected_samples: list[str] = []

    for coord in targets:
        raw_val = ws[coord].value
        actual_formula = raw_val if isinstance(raw_val, str) and raw_val.strip().startswith("=") else None

        expected_formula = cfg.get("expected_formula")
        if expected_formula is None and ref_ws is not None:
            ref_val = ref_ws[coord].value
            if isinstance(ref_val, str) and ref_val.strip().startswith("="):
                expected_formula = ref_val

        actual_samples.append(actual_formula or f"(ค่าคงที่: {raw_val!r})")
        if expected_formula:
            expected_samples.append(expected_formula)

        # 1. Must actually be a formula, not a hardcoded value
        if not actual_formula:
            errors.append(
                GradingErrorRecord(
                    error_code="NOT_A_FORMULA",
                    severity="error",
                    sheet_name=sheet_name,
                    cell_reference=coord,
                    message_th=f"เซลล์ {coord} ไม่ได้ใช้สูตร Excel (พบค่าคงที่หรือเซลล์ว่าง: {raw_val!r})",
                    expected_detail=expected_formula or f"สูตรที่มี {', '.join(required_funcs)}",
                    actual_detail=str(raw_val),
                    fix_suggestion_th=f"ให้พิมพ์สูตรขึ้นต้นด้วย '=' ในเซลล์ {coord}"
                    + (f" เช่น {expected_formula}" if expected_formula else ""),
                )
            )
            continue

        analysis = analyze_formula(actual_formula)
        cell_ok = True

        # 2. Check required functions
        if required_funcs:
            missing_funcs = [f for f in required_funcs if f not in analysis.functions]
            if missing_funcs:
                cell_ok = False
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_REQUIRED_FUNCTION",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ไม่ได้ใช้ฟังก์ชันที่กำหนด ({', '.join(missing_funcs)})",
                        expected_detail=", ".join(required_funcs),
                        actual_detail=actual_formula,
                        fix_suggestion_th=f"ใช้ฟังก์ชัน {', '.join(missing_funcs)} ในเซลล์ {coord}",
                    )
                )

        # 3. Check required ranges
        if required_ranges and cell_ok:
            actual_refs_clean = [r.upper().replace("$", "") for r in analysis.references]
            missing_ranges = [rng for rng in required_ranges if rng not in actual_refs_clean]
            if missing_ranges:
                cell_ok = False
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_DATA_RANGE",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} อ้างอิงช่วงข้อมูลไม่ครบหรือไม่ถูกต้อง (ขาดช่วง {', '.join(missing_ranges)})",
                        expected_detail=", ".join(required_ranges),
                        actual_detail=actual_formula,
                        fix_suggestion_th=f"ตรวจสอบช่วงเซลล์ในสูตรให้ครอบคลุม {', '.join(missing_ranges)}",
                    )
                )

        # 4. Check absolute reference requirement
        if require_abs and cell_ok and not analysis.has_absolute_ref:
            cell_ok = False
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_ABSOLUTE_REFERENCE",
                    severity="error",
                    sheet_name=sheet_name,
                    cell_reference=coord,
                    message_th=f"เซลล์ {coord} ไม่ได้ล็อกตำแหน่งเซลล์แบบ Absolute Reference ($)",
                    expected_detail=expected_formula or "ต้องมีเครื่องหมาย $ ในการอ้างอิงเซลล์",
                    actual_detail=actual_formula,
                    fix_suggestion_th="ใช้เครื่องหมาย $ เช่น $B$2 เพื่อล็อกตำแหน่งเซลล์ก่อนคัดลอกสูตร",
                )
            )

        # 5. Check nested IF depth
        if min_if_depth > 0 and cell_ok and analysis.nested_if_depth < min_if_depth:
            cell_ok = False
            errors.append(
                GradingErrorRecord(
                    error_code="INSUFFICIENT_NESTED_IF",
                    severity="error",
                    sheet_name=sheet_name,
                    cell_reference=coord,
                    message_th=f"เซลล์ {coord} ใช้สูตร IF ซ้อนกันเพียง {analysis.nested_if_depth} ชั้น (ต้องการอย่างน้อย {min_if_depth} ชั้น)",
                    expected_detail=expected_formula or f"Nested IF >= {min_if_depth} ชั้น",
                    actual_detail=actual_formula,
                    fix_suggestion_th="ตรวจสอบเงื่อนไข IF ซ้อน IF ให้ครบทุกกรณีตามโจทย์",
                )
            )

        # 6. Check cross-sheet reference
        if require_cross_sheet and cell_ok:
            referenced_sheets = [s.upper() for s, _ in analysis.cross_sheet_refs]
            if require_cross_sheet.upper() not in referenced_sheets:
                cell_ok = False
                errors.append(
                    GradingErrorRecord(
                        error_code="MISSING_CROSS_SHEET_REF",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} ไม่ได้อ้างอิงข้าม Sheet ไปยัง '{require_cross_sheet}'",
                        expected_detail=f"อ้างอิง '{require_cross_sheet}!'",
                        actual_detail=actual_formula,
                        fix_suggestion_th=f"แก้สูตรให้อ้างอิงข้อมูลจากแผ่นงาน '{require_cross_sheet}' เช่น {require_cross_sheet}!A1",
                    )
                )

        # 7. Compare with expected_formula / accepted_formulas (if provided and no structural error yet)
        candidates = []
        if expected_formula:
            candidates.append(expected_formula)
        candidates.extend(accepted_formulas)

        if candidates and cell_ok:
            matched = False
            for cand in candidates:
                is_eq, _ = are_formulas_equivalent(
                    actual_formula,
                    cand,
                    strict_reference_mode=strict_ref or require_abs,
                )
                if is_eq:
                    matched = True
                    break
            if not matched:
                cell_ok = False
                errors.append(
                    GradingErrorRecord(
                        error_code="FORMULA_MISMATCH",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"สูตรในเซลล์ {coord} ไม่ตรงกับเฉลย",
                        expected_detail=candidates[0],
                        actual_detail=actual_formula,
                        fix_suggestion_th=f"ตรวจสอบสูตรในเซลล์ {coord} สูตรที่ถูกต้องคือ {candidates[0]}",
                    )
                )

        if cell_ok:
            passed_cells += 1

    total_cells = len(targets)
    ratio = passed_cells / total_cells if total_cells > 0 else 0.0
    all_passed = passed_cells == total_cells

    if all_passed:
        earned = item.max_points
        reason = f"สูตรถูกต้องครบทั้ง {total_cells} เซลล์ ({item.target_cell})"
        suggestion = None
    elif item.zero_on_error:
        earned = 0.0
        reason = f"พบข้อผิดพลาดในสูตร (เกณฑ์นี้กำหนดให้ได้ 0 คะแนนเมื่อผิดพลาด: ถูก {passed_cells}/{total_cells} เซลล์)"
        suggestion = errors[0].fix_suggestion_th if errors else None
    elif item.allow_partial_credit and total_cells > 1:
        earned = round(item.max_points * ratio, 2)
        reason = f"สูตรถูกต้องบางส่วน {passed_cells}/{total_cells} เซลล์"
        suggestion = errors[0].fix_suggestion_th if errors else None
    else:
        earned = 0.0
        reason = errors[0].message_th if errors else "สูตรไม่ถูกต้อง"
        suggestion = errors[0].fix_suggestion_th if errors else None

    earned = max(item.min_points if all_passed else 0.0, min(item.max_points, earned))

    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category="formula",
        target_cell=item.target_cell,
        earned_points=earned,
        deducted_points=round(item.max_points - earned, 2),
        max_points=item.max_points,
        passed=all_passed,
        expected_formula=expected_samples[0] if expected_samples else cfg.get("expected_formula"),
        actual_formula=actual_samples[0] if actual_samples else None,
        reason=reason,
        suggestion=suggestion,
        evidence={"passed_cells": passed_cells, "total_cells": total_cells},
        errors=errors,
    )


def _check_formula_auto_detect(
    item: RubricItemConfig,
    student_formula_wb: Workbook,
    reference_formula_wb: Workbook | None,
) -> RubricItemResult:
    """
    Auto-detect mode when teacher does not specify sheet/cell/expected formula manually:
    - If a reference workbook is attached: scan ALL sheets of the reference workbook for cells using
      `required_functions` (or all formulas if none specified) and verify every matching cell in student's workbook.
    - If no reference workbook is attached: scan ALL sheets of the student's workbook to verify that
      the required function(s) are genuinely used as Excel formulas.
    """
    cfg: dict[str, Any] = item.rule_config or {}
    required_funcs = [f.upper() for f in cfg.get("required_functions", [])]
    strict_ref = bool(cfg.get("strict_reference_mode", False))
    require_abs = bool(cfg.get("require_absolute_reference", False))

    # Case 1: Reference workbook attached -> auto-discover all target cells from reference file
    if reference_formula_wb is not None:
        discovered: list[tuple[str, str, str]] = []  # (sheet_name, coord, expected_formula)
        for sname in reference_formula_wb.sheetnames:
            rws = reference_formula_wb[sname]
            for r in range(1, min(rws.max_row or 0, 500) + 1):
                for c in range(1, min(rws.max_column or 0, 50) + 1):
                    val = rws.cell(row=r, column=c).value
                    if isinstance(val, str) and val.strip().startswith("="):
                        analysis = analyze_formula(val)
                        if not required_funcs or any(fn in analysis.functions for fn in required_funcs):
                            discovered.append((sname, rws.cell(row=r, column=c).coordinate, val))

        if discovered:
            passed_cnt = 0
            errors: list[GradingErrorRecord] = []
            first_expected = discovered[0][2]
            first_actual = None

            for sname, coord, exp_formula in discovered:
                if sname not in student_formula_wb.sheetnames:
                    errors.append(
                        GradingErrorRecord(
                            error_code="MISSING_WORKSHEET",
                            severity="error",
                            sheet_name=sname,
                            cell_reference=coord,
                            message_th=f"ไม่พบแผ่นงาน '{sname}' ตามไฟล์ต้นฉบับเฉลย",
                            expected_detail=exp_formula,
                            fix_suggestion_th=f"ตรวจสอบชื่อแผ่นงานให้ตรงกับ '{sname}'",
                        )
                    )
                    continue

                raw_val = student_formula_wb[sname][coord].value
                actual_formula = raw_val if isinstance(raw_val, str) and raw_val.strip().startswith("=") else None
                if first_actual is None:
                    first_actual = actual_formula or f"(ค่าคงที่: {raw_val!r})"

                if not actual_formula:
                    errors.append(
                        GradingErrorRecord(
                            error_code="NOT_A_FORMULA",
                            severity="error",
                            sheet_name=sname,
                            cell_reference=coord,
                            message_th=f"เซลล์ {sname}!{coord} ไม่ได้ใช้สูตรตามไฟล์เฉลย (พบ {raw_val!r})",
                            expected_detail=exp_formula,
                            actual_detail=str(raw_val),
                            fix_suggestion_th=f"ใส่สูตร {exp_formula} ในเซลล์ {sname}!{coord}",
                        )
                    )
                    continue

                is_eq, _ = are_formulas_equivalent(
                    actual_formula,
                    exp_formula,
                    strict_reference_mode=strict_ref or require_abs,
                )
                if is_eq:
                    passed_cnt += 1
                else:
                    errors.append(
                        GradingErrorRecord(
                            error_code="FORMULA_MISMATCH",
                            severity="error",
                            sheet_name=sname,
                            cell_reference=coord,
                            message_th=f"สูตรใน {sname}!{coord} ไม่ตรงกับไฟล์เฉลย",
                            expected_detail=exp_formula,
                            actual_detail=actual_formula,
                            fix_suggestion_th=f"แก้สูตรใน {sname}!{coord} เป็น {exp_formula}",
                        )
                    )

            total = len(discovered)
            all_passed = passed_cnt == total
            if all_passed:
                earned = item.max_points
                reason = f"ตรวจอัตโนมัติเทียบไฟล์เฉลย: สูตรถูกต้องครบทั้ง {total} ตำแหน่ง"
                suggestion = None
            elif item.zero_on_error:
                earned = 0.0
                reason = f"สูตรไม่ตรงกับไฟล์เฉลย ({passed_cnt}/{total} ตำแหน่ง) — เกณฑ์กำหนดผิดได้ 0"
                suggestion = errors[0].fix_suggestion_th if errors else None
            elif item.allow_partial_credit:
                earned = round(item.max_points * (passed_cnt / total), 2)
                reason = f"ตรวจเทียบไฟล์เฉลย: สูตรถูกต้องบางส่วน {passed_cnt}/{total} ตำแหน่ง"
                suggestion = errors[0].fix_suggestion_th if errors else None
            else:
                earned = 0.0
                reason = errors[0].message_th if errors else "สูตรไม่ตรงกับไฟล์เฉลย"
                suggestion = errors[0].fix_suggestion_th if errors else None

            return RubricItemResult(
                rubric_item_id=item.id,
                item_title=item.title,
                category="formula",
                target_cell=f"Auto ({total} เซลล์)",
                earned_points=earned,
                deducted_points=round(item.max_points - earned, 2),
                max_points=item.max_points,
                passed=all_passed,
                expected_formula=first_expected,
                actual_formula=first_actual,
                reason=reason,
                suggestion=suggestion,
                evidence={"mode": "auto_reference", "passed_cells": passed_cnt, "total_cells": total},
                errors=errors,
            )

    # Case 2: No reference file (or function not in reference) -> scan student's entire workbook
    found_cells: list[tuple[str, str, str]] = []
    for sname in student_formula_wb.sheetnames:
        ws = student_formula_wb[sname]
        for r in range(1, min(ws.max_row or 0, 500) + 1):
            for c in range(1, min(ws.max_column or 0, 50) + 1):
                val = ws.cell(row=r, column=c).value
                if isinstance(val, str) and val.strip().startswith("="):
                    analysis = analyze_formula(val)
                    if not required_funcs or any(fn in analysis.functions for fn in required_funcs):
                        found_cells.append((sname, ws.cell(row=r, column=c).coordinate, val))

    if found_cells:
        sample_loc = f"{found_cells[0][0]}!{found_cells[0][1]}"
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category="formula",
            target_cell=sample_loc,
            earned_points=item.max_points,
            deducted_points=0.0,
            max_points=item.max_points,
            passed=True,
            actual_formula=found_cells[0][2],
            reason=f"พบการใช้สูตร {', '.join(required_funcs) or 'Excel'} ถูกต้องทั้งหมด {len(found_cells)} ตำแหน่ง (เช่น {sample_loc})",
            evidence={"mode": "auto_student_scan", "found_count": len(found_cells)},
        )

    fn_label = ", ".join(required_funcs) if required_funcs else "สูตร Excel"
    err = GradingErrorRecord(
        error_code="MISSING_REQUIRED_FUNCTION",
        severity="error",
        message_th=f"ไม่พบการใช้ฟังก์ชัน {fn_label} ในไฟล์งานของนักเรียน",
        expected_detail=f"ต้องมีสูตร {fn_label}",
        actual_detail="ไม่พบสูตรในทุกแผ่นงาน",
        fix_suggestion_th=f"ใช้สูตร ={required_funcs[0]}(...) ตามโจทย์ที่กำหนด" if required_funcs else "ใช้สูตร Excel ในการคำนวณ",
    )
    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category="formula",
        target_cell="Auto",
        earned_points=0.0,
        deducted_points=item.max_points,
        max_points=item.max_points,
        passed=False,
        reason=err.message_th,
        suggestion=err.fix_suggestion_th,
        errors=[err],
    )
