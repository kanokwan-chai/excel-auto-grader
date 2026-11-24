"""Chart & Chart Elements Checker: validates chart type, title, axis titles, data labels, legend, data table, gridlines, data range, and series."""

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
    "areachart3d": "area",
    "radarchart": "radar",
}

LEGEND_POS_TH = {
    "r": "ด้านขวา (Right)",
    "b": "ด้านล่าง (Bottom)",
    "t": "ด้านบน (Top)",
    "l": "ด้านซ้าย (Left)",
    "tr": "มุมบนขวา (Top Right)",
}


def _extract_title_text(title_obj: Any) -> str:
    if title_obj is None:
        return ""
    if isinstance(title_obj, str):
        return title_obj.strip()
    tx = getattr(title_obj, "tx", None)
    if tx:
        if getattr(tx, "rich", None):
            parts: list[str] = []
            for p in tx.rich.p or []:
                for r in p.r or []:
                    if getattr(r, "t", None):
                        parts.append(r.t)
            if parts:
                return "".join(parts).strip()
        str_ref = getattr(tx, "strRef", None)
        if str_ref:
            # Title linked to a cell formula (e.g. =Sheet1!$A$1)
            if getattr(str_ref, "strCache", None) and getattr(str_ref.strCache, "pt", None):
                pts = [pt.v for pt in str_ref.strCache.pt if getattr(pt, "v", None)]
                if pts:
                    return "".join(pts).strip()
            if getattr(str_ref, "f", None):
                return str(str_ref.f).strip()
    return ""


def _has_axis_or_chart_title(title_obj: Any) -> bool:
    if title_obj is None:
        return False
    txt = _extract_title_text(title_obj)
    if txt:
        return True
    # Even if openpyxl loads default rich text placeholder without cached string, presence of Title object means enabled
    return True


def _extract_chart_type(chart: Any) -> str:
    cls_name = type(chart).__name__.lower()
    mapped = CHART_TYPE_MAP.get(cls_name, cls_name)
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


def _inspect_data_labels(chart: Any) -> tuple[bool, bool]:
    """Return (has_any_data_labels, has_percent_labels) across chart-level and series-level dataLabels."""
    has_any = False
    has_pct = False

    def _check_dl(dl: Any) -> None:
        nonlocal has_any, has_pct
        if dl is None:
            return
        if getattr(dl, "delete", False) is True:
            return
        show_val = getattr(dl, "showVal", None)
        show_pct = getattr(dl, "showPercent", None)
        show_cat = getattr(dl, "showCatName", None)
        show_ser = getattr(dl, "showSerName", None)
        if any(flag is True for flag in (show_val, show_pct, show_cat, show_ser)):
            has_any = True
        elif all(flag is None for flag in (show_val, show_pct, show_cat, show_ser)):
            # DataLabelList object exists without delete=True -> Excel added data labels with default settings
            has_any = True
        if show_pct is True:
            has_pct = True

    _check_dl(getattr(chart, "dataLabels", None))
    for s in getattr(chart, "series", []) or []:
        _check_dl(getattr(s, "dLbls", None) or getattr(s, "data_labels", None))

    return has_any, has_pct


def inspect_chart_elements_summary(chart: Any) -> dict[str, Any]:
    """Return a structured summary of a chart and all its elements (used by Answer Key extractor & checker)."""
    c_type = _extract_chart_type(chart)
    title_txt = _extract_title_text(getattr(chart, "title", None))
    has_title = bool(title_txt) or (getattr(chart, "title", None) is not None and not getattr(chart, "autoTitleDeleted", False))

    x_ax = getattr(chart, "x_axis", None)
    y_ax = getattr(chart, "y_axis", None)
    x_title = _extract_title_text(getattr(x_ax, "title", None)) if x_ax else ""
    y_title = _extract_title_text(getattr(y_ax, "title", None)) if y_ax else ""
    has_x_title = _has_axis_or_chart_title(getattr(x_ax, "title", None)) if x_ax else False
    has_y_title = _has_axis_or_chart_title(getattr(y_ax, "title", None)) if y_ax else False

    has_dl, has_pct = _inspect_data_labels(chart)
    leg = getattr(chart, "legend", None)
    has_legend = leg is not None
    leg_pos = getattr(leg, "position", None) if leg else None

    plot_area = getattr(chart, "plot_area", None)
    has_dtable = bool(plot_area and getattr(plot_area, "dTable", None) is not None)
    has_gridlines = bool(
        (y_ax and getattr(y_ax, "majorGridlines", None) is not None)
        or (x_ax and getattr(x_ax, "majorGridlines", None) is not None)
    )

    return {
        "type": c_type,
        "grouping": getattr(chart, "grouping", None),
        "title": title_txt,
        "has_title": has_title,
        "has_x_axis_title": has_x_title,
        "x_axis_title": x_title,
        "has_y_axis_title": has_y_title,
        "y_axis_title": y_title,
        "has_data_labels": has_dl,
        "has_percent_labels": has_pct,
        "has_legend": has_legend,
        "legend_position": leg_pos,
        "has_data_table": has_dtable,
        "has_gridlines": has_gridlines,
        "series_count": len(getattr(chart, "series", []) or []),
        "series_ranges": _extract_series_ranges(chart),
    }


def check_chart_item(
    item: RubricItemConfig,
    student_wb: Workbook,
) -> RubricItemResult:
    """
    Validate Excel charts and Chart Elements (องค์ประกอบของแผนภูมิ) on the target worksheet.
    """
    from excel_engine.readers.excel_reader import resolve_worksheet_forgiving

    cfg = item.rule_config or {}
    ws, sheet_name = resolve_worksheet_forgiving(student_wb, item.sheet_name)
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
            fix_suggestion_th="คลุมข้อมูลแล้วสร้างแผนภูมิผ่านเมนู Insert > Charts",
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
    # If multiple charts exist and chart_type is specified, prefer the chart matching expected chart_type
    expected_type_hint = str(cfg.get("chart_type") or "").lower().strip()
    chart = charts[chart_index] if chart_index < len(charts) else charts[0]
    if expected_type_hint and len(charts) > 1:
        for ch_cand in charts:
            ct_cand = _extract_chart_type(ch_cand)
            if ct_cand == expected_type_hint or (expected_type_hint == "bar_or_column" and ct_cand in {"bar", "column"}):
                chart = ch_cand
                break

    info = inspect_chart_elements_summary(chart)
    actual_type = info["type"]
    actual_title = info["title"]
    actual_ranges = info["series_ranges"]

    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []

    # 1. Chart Type
    if cfg.get("chart_type"):
        total += 1
        expected_type = str(cfg["chart_type"]).lower().strip()
        if (
            actual_type == expected_type
            or (expected_type == "bar_or_column" and actual_type in {"bar", "column"})
            or (expected_type in {"pie", "doughnut"} and actual_type == expected_type)
        ):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_TYPE",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"ประเภทแผนภูมิไม่ถูกต้อง (ส่งมาเป็น '{actual_type}' แต่กำหนด '{expected_type}')",
                    expected_detail=expected_type,
                    actual_detail=actual_type,
                    fix_suggestion_th=f"คลิกขวาที่แผนภูมิ > Change Chart Type แล้วเลือกแบบ {expected_type}",
                )
            )

    # 2. Chart Title (existence and/or specific text)
    exp_title = str(cfg.get("expected_title") or "").strip()
    if exp_title:
        total += 1
        if exp_title.lower() in actual_title.lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชื่อแผนภูมิ (Chart Title) ไม่ตรง (พบ '{actual_title or '(ไม่มีชื่อ)'}' ควรมีคำว่า '{exp_title}')",
                    expected_detail=exp_title,
                    actual_detail=actual_title or "(ไม่มีชื่อ)",
                    fix_suggestion_th=f"เพิ่มและแก้ไขชื่อแผนภูมิ (Chart Title) ให้มีคำว่า '{exp_title}'",
                )
            )
    elif cfg.get("require_title"):
        total += 1
        if info["has_title"] and actual_title.lower() not in {"chart title", "ชื่อแผนภูมิ"}:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CHART_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้ตั้งชื่อแผนภูมิ (Chart Title) หรือปล่อยเป็นข้อความเริ่มต้น",
                    expected_detail="มีชื่อแผนภูมิที่สื่อความหมาย",
                    actual_detail=actual_title or "(ไม่มีชื่อแผนภูมิ)",
                    fix_suggestion_th="กดปุ่ม [+] มุมบนขวาของแผนภูมิ > ติ๊ก Chart Title แล้วพิมพ์ชื่อเรื่องของกราฟ",
                )
            )

    # 3. Horizontal Axis Title (X-Axis)
    exp_x = str(cfg.get("x_axis_title") or "").strip()
    if exp_x:
        total += 1
        if exp_x.lower() in info["x_axis_title"].lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_X_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชื่อแกนแนวนอน (แกน X) ไม่ตรง (พบ '{info['x_axis_title'] or '(ไม่มี)'}' ควรมี '{exp_x}')",
                    fix_suggestion_th=f"กด [+] > Axis Titles > แกนแนวนอน แล้วตั้งชื่อเป็น '{exp_x}'",
                )
            )
    elif cfg.get("require_x_axis_title"):
        total += 1
        if info["has_x_axis_title"] and info["x_axis_title"].lower() not in {"axis title", "ชื่อแกน"}:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_X_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้ใส่ชื่อแกนแนวนอน (Horizontal Axis Title / แกน X)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊ก Axis Titles (ชื่อแกน) แล้วพิมพ์ชื่อแกนแนวนอน",
                )
            )

    # 4. Vertical Axis Title (Y-Axis)
    exp_y = str(cfg.get("y_axis_title") or "").strip()
    if exp_y:
        total += 1
        if exp_y.lower() in info["y_axis_title"].lower():
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_Y_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"ชื่อแกนแนวตั้ง (แกน Y) ไม่ตรง (พบ '{info['y_axis_title'] or '(ไม่มี)'}' ควรมี '{exp_y}')",
                    fix_suggestion_th=f"กด [+] > Axis Titles > แกนแนวตั้ง แล้วตั้งชื่อเป็น '{exp_y}'",
                )
            )
    elif cfg.get("require_y_axis_title"):
        total += 1
        if info["has_y_axis_title"] and info["y_axis_title"].lower() not in {"axis title", "ชื่อแกน"}:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_Y_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้ใส่ชื่อแกนแนวตั้ง (Vertical Axis Title / แกน Y)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊ก Axis Titles (ชื่อแกน) แล้วพิมพ์ชื่อแกนแนวตั้ง",
                )
            )

    # 5. Data Labels & Percentage Labels
    if cfg.get("require_percent_labels"):
        total += 1
        if info["has_percent_labels"]:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_PERCENT_DATA_LABELS",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้แสดงค่าเปอร์เซ็นต์ (%) บนป้ายกำกับข้อมูลของแผนภูมิ",
                    fix_suggestion_th="กด [+] > Data Labels > More Options > ติ๊กถูกช่อง Percentage (เปอร์เซ็นต์)",
                )
            )
    elif cfg.get("require_data_labels"):
        total += 1
        if info["has_data_labels"]:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_DATA_LABELS",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้เปิดแสดงป้ายกำกับข้อมูล (Data Labels / ตัวเลขบนกราฟ)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Data Labels (ป้ายกำกับข้อมูล)",
                )
            )

    # 6. Legend & Legend Position
    if cfg.get("require_legend") or cfg.get("legend_position"):
        total += 1
        if not info["has_legend"]:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CHART_LEGEND",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้เปิดแสดงคำอธิบายแผนภูมิ (Legend)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Legend (คำอธิบายแผนภูมิ)",
                )
            )
        elif cfg.get("legend_position"):
            exp_pos = str(cfg["legend_position"]).lower().strip()
            act_pos = str(info["legend_position"] or "r").lower().strip()
            if act_pos == exp_pos:
                passed += 1
            else:
                errors.append(
                    GradingErrorRecord(
                        error_code="WRONG_LEGEND_POSITION",
                        severity="warning",
                        sheet_name=sheet_name,
                        message_th=(
                            f"ตำแหน่งคำอธิบายแผนภูมิ (Legend) ไม่ตรง "
                            f"(อยู่ที่ {LEGEND_POS_TH.get(act_pos, act_pos)} ควรอยู่ที่ {LEGEND_POS_TH.get(exp_pos, exp_pos)})"
                        ),
                        fix_suggestion_th=f"กด [+] > Legend > เลือกตำแหน่ง {LEGEND_POS_TH.get(exp_pos, exp_pos)}",
                    )
                )
        else:
            passed += 1

    # 7. Data Table below chart
    if cfg.get("require_data_table"):
        total += 1
        if info["has_data_table"]:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CHART_DATA_TABLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้เปิดแสดงตารางข้อมูลใต้แผนภูมิ (Data Table)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Data Table (ตารางข้อมูล)",
                )
            )

    # 8. Gridlines
    if cfg.get("require_gridlines"):
        total += 1
        if info["has_gridlines"]:
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CHART_GRIDLINES",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้เปิดแสดงเส้นตารางในแผนภูมิ (Gridlines)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Gridlines (เส้นตาราง)",
                )
            )

    # 9. Data Range & Series Count
    if cfg.get("required_data_range"):
        total += 1
        req_range = str(cfg["required_data_range"]).upper().replace("$", "").strip()
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
                    fix_suggestion_th=f"คลิกขวาที่แผนภูมิ > Select Data แล้วเลือกช่วงข้อมูลให้ครอบคลุม {req_range}",
                )
            )

    if cfg.get("min_series_count"):
        total += 1
        series_cnt = info["series_count"]
        if series_cnt >= int(cfg["min_series_count"]):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="INSUFFICIENT_CHART_SERIES",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=f"จำนวนชุดข้อมูล (Series) ในแผนภูมิไม่ครบ ({series_cnt} ชุด ควรมีอย่างน้อย {cfg['min_series_count']} ชุด)",
                    fix_suggestion_th="คลิกขวาที่แผนภูมิ > Select Data เพื่อเลือกชุดข้อมูลให้ครบทุกคอลัมน์ที่เปรียบเทียบ",
                )
            )

    if total == 0:
        total = 1
        passed = 1

    all_passed = passed == total
    err_summary = "; ".join(e.message_th for e in errors[:3]) if errors else ""
    if all_passed:
        earned = item.max_points
        reason = f"แผนภูมิและองค์ประกอบถูกต้องครบทั้ง {total} รายการ ({actual_type})"
        suggestion = None
    elif item.zero_on_error:
        earned = 0.0
        reason = f"แผนภูมิไม่ผ่านเกณฑ์ ({passed}/{total} รายการ): {err_summary}"
        suggestion = errors[0].fix_suggestion_th if errors else None
    elif item.allow_partial_credit:
        earned = round(item.max_points * (passed / total), 2)
        reason = f"แผนภูมิผ่านบางส่วน {passed}/{total} รายการ: {err_summary}"
        suggestion = errors[0].fix_suggestion_th if errors else None
    else:
        earned = 0.0
        reason = err_summary or "แผนภูมิไม่ถูกต้อง"
        suggestion = errors[0].fix_suggestion_th if errors else None

    return RubricItemResult(
        rubric_item_id=item.id,
        item_title=item.title,
        category="chart",
        earned_points=earned,
        deducted_points=round(item.max_points - earned, 2),
        max_points=item.max_points,
        passed=all_passed,
        reason=reason,
        suggestion=suggestion,
        evidence={"chart_info": info},
        errors=errors,
    )
