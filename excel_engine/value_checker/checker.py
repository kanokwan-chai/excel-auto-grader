"""Value Checker: compares calculated results with tolerance, types, empty checks, and Excel errors."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from openpyxl.workbook import Workbook

from excel_engine.formula_checker.checker import expand_cell_targets
from excel_engine.models import GradingErrorRecord, RubricItemConfig, RubricItemResult

EXCEL_ERROR_TOKENS = {"#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}


def _is_numeric(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _compare_values(
    actual: Any,
    expected: Any,
    tolerance: float = 0.01,
    case_sensitive: bool = False,
    is_percentage: bool = False,
) -> tuple[bool, str]:
    if actual is None and expected is None:
        return True, "both_empty"
    if actual is None:
        return False, "empty_cell"

    if isinstance(actual, str) and actual.strip().upper() in EXCEL_ERROR_TOKENS:
        return False, f"excel_error:{actual.strip().upper()}"

    if _is_numeric(expected) and _is_numeric(actual):
        a_num = float(actual)
        e_num = float(expected)
        if abs(a_num - e_num) <= tolerance:
            return True, "numeric_match"
        if is_percentage and abs(a_num * 100.0 - e_num) <= tolerance:
            return True, "percentage_match"
        return False, "numeric_mismatch"

    if isinstance(expected, (datetime, date)) and isinstance(actual, (datetime, date)):
        a_d = actual.date() if isinstance(actual, datetime) else actual
        e_d = expected.date() if isinstance(expected, datetime) else expected
        return (a_d == e_d), ("date_match" if a_d == e_d else "date_mismatch")

    a_str = str(actual).strip()
    e_str = str(expected).strip()
    if not case_sensitive:
        if a_str.lower() == e_str.lower():
            return True, "text_match"
    else:
        if a_str == e_str:
            return True, "text_match_exact"

    # Try numeric string coercion if expected is numeric
    if _is_numeric(expected):
        try:
            a_num = float(a_str.replace(",", "").replace("%", ""))
            if "%" in a_str:
                a_num /= 100.0
            if abs(a_num - float(expected)) <= tolerance:
                return True, "numeric_string_match"
        except ValueError:
            pass

    return False, "value_mismatch"


def check_value_item(
    item: RubricItemConfig,
    student_value_wb: Workbook,
    reference_value_wb: Workbook | None = None,
) -> RubricItemResult:
    """
    Evaluate calculated cell values (data_only=True, ideally after LibreOffice recalculation).

    Supported rule_config keys:
    - expected_value: Any (if omitted, read from reference_value_wb)
    - tolerance: float (default 0.01)
    - case_sensitive: bool (default False)
    - is_percentage: bool (default False)
    - allow_empty: bool (default False)
    """
    from excel_engine.readers.excel_reader import resolve_worksheet_forgiving

    cfg = item.rule_config or {}
    ws, sheet_name = resolve_worksheet_forgiving(student_value_wb, item.sheet_name, reference_value_wb)

    if ws is None:
        err = GradingErrorRecord(
            error_code="MISSING_WORKSHEET",
            severity="error",
            sheet_name=item.sheet_name,
            cell_reference=item.target_cell,
            message_th=f"ไม่พบ Worksheet '{item.sheet_name}' สำหรับตรวจผลลัพธ์",
            fix_suggestion_th=f"ตรวจสอบว่ามีแผ่นงานชื่อ '{item.sheet_name}'",
        )
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category="value",
            target_cell=item.target_cell,
            earned_points=0.0,
            deducted_points=item.max_points,
            max_points=item.max_points,
            passed=False,
            reason=err.message_th,
            suggestion=err.fix_suggestion_th,
            errors=[err],
        )

    ref_ws = None
    if reference_value_wb is not None:
        ref_ws, _ = resolve_worksheet_forgiving(reference_value_wb, item.sheet_name or sheet_name)

    if not item.target_cell:
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category="value",
            earned_points=0.0,
            deducted_points=item.max_points,
            max_points=item.max_points,
            passed=False,
            reason="ไม่ได้กำหนดเซลล์เป้าหมาย",
        )

    targets = expand_cell_targets(item.target_cell)
    tolerance = float(cfg.get("tolerance", 0.01))
    case_sensitive = bool(cfg.get("case_sensitive", False))
    is_percentage = bool(cfg.get("is_percentage", False))

    passed_cells = 0
    errors: list[GradingErrorRecord] = []
    first_expected = None
    first_actual = None

    for coord in targets:
        actual = ws[coord].value
        expected = cfg.get("expected_value")
        if expected is None and ref_ws is not None:
            expected = ref_ws[coord].value

        if first_expected is None:
            first_expected = expected
            first_actual = actual

        ok, detail = _compare_values(
            actual=actual,
            expected=expected,
            tolerance=tolerance,
            case_sensitive=case_sensitive,
            is_percentage=is_percentage,
        )
        if ok:
            passed_cells += 1
        else:
            if detail.startswith("excel_error:"):
                err_tok = detail.split(":", 1)[1]
                errors.append(
                    GradingErrorRecord(
                        error_code="EXCEL_CALCULATION_ERROR",
                        severity="critical",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} แสดงข้อผิดพลาดของ Excel ({err_tok})",
                        expected_detail=str(expected),
                        actual_detail=err_tok,
                        fix_suggestion_th=f"แก้ไขสูตรในเซลล์ {coord} ที่ทำให้เกิดข้อผิดพลาด {err_tok}",
                    )
                )
            elif detail == "empty_cell":
                errors.append(
                    GradingErrorRecord(
                        error_code="EMPTY_CELL",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"เซลล์ {coord} เป็นค่าว่าง ไม่มีผลลัพธ์",
                        expected_detail=str(expected),
                        actual_detail="(ว่าง)",
                        fix_suggestion_th=f"กรอกข้อมูลหรือสูตรให้ได้ผลลัพธ์ในเซลล์ {coord}",
                    )
                )
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="VALUE_MISMATCH",
                        severity="error",
                        sheet_name=sheet_name,
                        cell_reference=coord,
                        message_th=f"ผลลัพธ์ในเซลล์ {coord} ไม่ถูกต้อง (ได้ {actual!r} แต่ควรเป็น {expected!r})",
                        expected_detail=str(expected),
                        actual_detail=str(actual),
                        fix_suggestion_th=f"ตรวจสอบการคำนวณในเซลล์ {coord} ผลลัพธ์ที่ถูกต้องคือ {expected}",
                    )
                )

    total = len(targets)
    all_passed = passed_cells == total
    if all_passed:
        earned = item.max_points
        reason = f"ผลลัพธ์ถูกต้องครบ {total} เซลล์"
        suggestion = None
    elif item.zero_on_error:
        earned = 0.0
        reason = f"ผลลัพธ์ผิดพลาด ({passed_cells}/{total} เซลล์) — เกณฑ์กำหนดให้ได้ 0 คะแนน"
        suggestion = errors[0].fix_suggestion_th if errors else None
    elif item.allow_partial_credit and total > 1:
        earned = round(item.max_points * (passed_cells / total), 2)
        reason = f"ผลลัพธ์ถูกต้องบางส่วน {passed_cells}/{total} เซลล์"
        suggestion = errors[0].fix_suggestion_th if errors else None
    else:
        earned = 0.0
        reason = errors[0].message_th if errors else "ผลลัพธ์ไม่ถูกต้อง"
        suggestion = errors[0].fix_suggestion_th if errors else None

    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category="value",
        target_cell=item.target_cell,
        earned_points=earned,
        deducted_points=round(item.max_points - earned, 2),
        max_points=item.max_points,
        passed=all_passed,
        expected_value=str(first_expected) if first_expected is not None else None,
        actual_value=str(first_actual) if first_actual is not None else None,
        reason=reason,
        suggestion=suggestion,
        evidence={"passed_cells": passed_cells, "total_cells": total, "tolerance": tolerance},
        errors=errors,
    )
