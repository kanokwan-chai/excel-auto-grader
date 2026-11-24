"""Chart Checker: validates chart type, title, data range, axis titles, series."""

from __future__ import annotations

from typing import Any

from openpyxl.workbook import Workbook

from excel_engine.models import GradingErrorRecord, RubricItemConfig, RubricItemResult

CHART_TYPE_MAP = {
    "barchart": "bar",
    "barchart3d": "bar",
    "linechart": "line",
    "linechart3d": "line",
    "piechart": "pie",
    "piechart3d": "pie",
    "projectedpiechart": "pie",
    "doughnutchart": "doughnut",
    "scatterchart": "scatter",
    "areachart": "area",
    "radarchart": "radar",
}


def _extract_title_text(title_obj: Any) -> str:
    if title_obj is None:
        return ""
    if isinstance(title_obj, str):
        return title_obj.strip()
    tx = getattr(title_obj, "tx", None)
    if tx and getattr(tx, "rich", None):
        parts: list[str] = []
        for p in tx.rich.p or []:
            for r in p.r or []:
                if getattr(r, "t", None):
                    parts.append(r.t)
        return "".join(parts).strip()
    return ""


def _extract_chart_type(chart: Any) -> str:
    cls_name = type(chart).__name__.lower()
    mapped = CHART_TYPE_MAP.get(cls_name, cls_name)
    # Distinguish Bar (horizontal) vs Column (vertical) when type='col'
    if mapped == "bar" and getattr(chart, "type", None) == "col":
        return "column"
    return mapped


def _extract_series_ranges(chart: Any) -> list[str]:
    ranges: list[str] = []
    for s in getattr(chart, "series", []) or []:
        val = getattr(s, "val", None)
        if val and getattr(val, "numRef", None) and getattr(val.numRef, "f", None):
            ranges.append(val.numRef.f.upper().replace("$", ""))
        cat = getattr(s, "cat", None)
        if cat:
            for attr in ("strRef", "numRef"):
                ref = getattr(cat, attr, None)
                if ref and getattr(ref, "f", None):
                    ranges.append(ref.f.upper().replace("$", ""))
    return ranges


def check_chart_item(
    item: RubricItemConfig,
    student_wb: Workbook,
) -> RubricItemResult:
    """
    Validate Excel charts on the target worksheet.
    Supported rule_config keys:
    - chart_type: "bar" | "column" | "line" | "pie" | "scatter" | "area" | "doughnut"
    - expected_title: str (substring or exact match)
    - required_data_range: str (e.g. "B2:B10" or "Sheet1!B2:B10")
    - x_axis_title: str
    - y_axis_title: str
    - min_series_count: int
    """
    from excel_engine.readers.excel_reader import resolve_worksheet_forgiving

    cfg = item.rule_config or {}
    ws, sheet_name = resolve_worksheet_forgiving(student_wb, item.sheet_name)
    # If target sheet has no charts, also check if any other sheet has charts (in case student placed chart on a Chart sheet!)
    if ws is None:
        err = GradingErrorRecord(
            error_code="MISSING_WORKSHEET",
            severity="error",
            sheet_name=item.sheet_name,
            message_th=f"ไม่พบ Worksheet '{item.sheet_name}' สำหรับตรวจแผนภูมิ",
        )
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category="chart",
            earned_points=0.0,
            deducted_points=item.max_points,
            max_points=item.max_points,
            passed=False,
            reason=err.message_th,
            errors=[err],
        )

    charts = list(getattr(ws, "_charts", []) or [])
    if not charts:
        for alt_name in student_wb.sheetnames:
            alt_charts = list(getattr(student_wb[alt_name], "_charts", []) or [])
            if alt_charts:
                ws = student_wb[alt_name]
                sheet_name = alt_name
                charts = alt_charts
                break

    if not charts:
        err = GradingErrorRecord(
            error_code="MISSING_CHART",
            severity="error",
            sheet_name=sheet_name,
            message_th=f"ไม่พบแผนภูมิ (Chart) ในแผ่นงาน '{sheet_name}'",
            expected_detail=cfg.get("chart_type", "Chart"),
            actual_detail="ไม่มีแผนภูมิ",
            fix_suggestion_th="สร้างแผนภูมิจากช่วงข้อมูลที่กำหนดผ่านเมนู Insert > Charts",
        )
        return RubricItemResult(
            rubric_item_id=item.id,
            item_title=item.title,
            category="chart",
            earned_points=0.0,
            deducted_points=item.max_points,
            max_points=item.max_points,
            passed=False,
            reason=err.message_th,
            suggestion=err.fix_suggestion_th,
            errors=[err],
        )

    chart_index = int(cfg.get("chart_index", 0))
    chart = charts[chart_index] if chart_index < len(charts) else charts[0]

    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []

    actual_type = _extract_chart_type(chart)
    actual_title = _extract_title_text(getattr(chart, "title", None))
    actual_ranges = _extract_series_ranges(chart)

    if "chart_type" in cfg:
        total += 1
        expected_type = str(cfg["chart_type"]).lower()
        # Accept bar/column equivalence only if user specifies 'bar_or_column'
        if actual_type == expected_type or (expected_type == "bar_or_column" and actual_type in {"bar", "column"}):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_TYPE",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"ประเภทแผนภูมิไม่ถูกต้อง (ใช้แบบ '{actual_type}' แต่โจทย์กำหนด '{expected_type}')",
                    expected_detail=expected_type,
                    actual_detail=actual_type,
                    fix_suggestion_th=f"เปลี่ยนประเภทแผนภูมิเป็น {expected_type}",
                )
            )

    if "expected_title" in cfg:
        total += 1
        exp_title = str(cfg["expected_title"]).strip()
        if exp_title.lower() in actual_title.lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชื่อแผนภูมิไม่ตรง (พบ '{actual_title or '(ว่าง)'}' ควรมีคำว่า '{exp_title}')",
                    expected_detail=exp_title,
                    actual_detail=actual_title or "(ไม่มีชื่อ)",
                    fix_suggestion_th=f"ตั้งชื่อแผนภูมิเป็น '{exp_title}'",
                )
            )

    if "required_data_range" in cfg:
        total += 1
        req_range = str(cfg["required_data_range"]).upper().replace("$", "")
        if any(req_range in r for r in actual_ranges):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_DATA_RANGE",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"ช่วงข้อมูลของแผนภูมิไม่ตรงกับที่กำหนด ({req_range})",
                    expected_detail=req_range,
                    actual_detail=", ".join(actual_ranges) or "(ไม่พบช่วงข้อมูล)",
                    fix_suggestion_th=f"เลือกช่วงข้อมูลแผนภูมิให้ครอบคลุม {req_range}",
                )
            )

    if "x_axis_title" in cfg:
        total += 1
        x_title = _extract_title_text(getattr(getattr(chart, "x_axis", None), "title", None))
        if str(cfg["x_axis_title"]).lower() in x_title.lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_X_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชื่อแกน X ไม่ตรง (พบ '{x_title}', ควรเป็น '{cfg['x_axis_title']}')",
                    fix_suggestion_th=f"เพิ่มชื่อแกน X เป็น '{cfg['x_axis_title']}'",
                )
            )

    if "y_axis_title" in cfg:
        total += 1
        y_title = _extract_title_text(getattr(getattr(chart, "y_axis", None), "title", None))
        if str(cfg["y_axis_title"]).lower() in y_title.lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_Y_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชื่อแกน Y ไม่ตรง (พบ '{y_title}', ควรเป็น '{cfg['y_axis_title']}')",
                    fix_suggestion_th=f"เพิ่มชื่อแกน Y เป็น '{cfg['y_axis_title']}'",
                )
            )

    if "min_series_count" in cfg:
        total += 1
        series_cnt = len(getattr(chart, "series", []) or [])
        if series_cnt >= int(cfg["min_series_count"]):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INSUFFICIENT_CHART_SERIES",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"จำนวนชุดข้อมูลในแผนภูมิไม่ครบ ({series_cnt} < {cfg['min_series_count']})",
                )
            )

    if total == 0:
        # Chart existence alone satisfied the rule
        total = 1
        passed = 1

    all_passed = passed == total
    if all_passed:
        earned = item.max_points
        reason = f"แผนภูมิถูกต้องครบทั้ง {total} เงื่อนไข ({actual_type})"
        suggestion = None
    elif item.zero_on_error:
        earned = 0.0
        reason = f"แผนภูมิไม่ผ่านเกณฑ์ ({passed}/{total}) — เกณฑ์กำหนดให้ได้ 0 คะแนน"
        suggestion = errors[0].fix_suggestion_th if errors else None
    elif item.allow_partial_credit:
        earned = round(item.max_points * (passed / total), 2)
        reason = f"แผนภูมิผ่านบางส่วน {passed}/{total} เงื่อนไข"
        suggestion = errors[0].fix_suggestion_th if errors else None
    else:
        earned = 0.0
        reason = errors[0].message_th if errors else "แผนภูมิไม่ถูกต้อง"
        suggestion = errors[0].fix_suggestion_th if errors else None

    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category="chart",
        earned_points=earned,
        deducted_points=round(item.max_points - earned, 2),
        max_points=item.max_points,
        passed=all_passed,
        expected_value=cfg.get("chart_type"),
        actual_value=actual_type,
        reason=reason,
        suggestion=suggestion,
        evidence={"chart_type": actual_type, "chart_title": actual_title, "series_ranges": actual_ranges},
        errors=errors,
    )
