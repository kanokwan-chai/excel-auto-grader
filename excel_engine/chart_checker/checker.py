"""Chart & Chart Elements Checker: smart, forgiving, multi-chart & XML-aware grading for Excel & Google Sheets charts."""

from __future__ import annotations

import re
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
    "bubblechart": "scatter",
}

LEGEND_POS_TH = {
    "r": "ด้านขวา (Right)",
    "b": "ด้านล่าง (Bottom)",
    "t": "ด้านบน (Top)",
    "l": "ด้านซ้าย (Left)",
    "tr": "มุมบนขวา (Top Right)",
}

PLACEHOLDER_TITLES = {"", "chart title", "ชื่อแผนภูมิ", "axis title", "ชื่อแกน", "title"}


def _resolve_formula_ref_text(wb: Workbook | None, formula_ref: str | None) -> str:
    """Resolve a cell/range reference like 'Sheet1!$A$1' to its actual text in wb."""
    if not wb or not formula_ref:
        return ""
    ref = str(formula_ref).strip().lstrip("=")
    if "!" not in ref:
        return ""
    sh_part, cell_part = ref.split("!", 1)
    sh_name = sh_part.strip().strip("'")
    if sh_name not in wb.sheetnames:
        return ""
    ws = wb[sh_name]
    coord = cell_part.replace("$", "").split(":")[0].strip()
    try:
        v = ws[coord].value
        return str(v).strip() if v is not None else ""
    except Exception:
        return ""


def _extract_title_text(title_obj: Any, wb: Workbook | None = None) -> str:
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
                # Also check direct field/text elements inside paragraph XML if rich run is empty
                if not parts and hasattr(p, "to_tree"):
                    try:
                        tree = p.to_tree()
                        for elem in tree.iter():
                            if elem.tag.endswith("}t") and elem.text:
                                parts.append(elem.text)
                    except Exception:
                        pass
            if parts:
                return "".join(parts).strip()
        str_ref = getattr(tx, "strRef", None)
        if str_ref:
            if getattr(str_ref, "strCache", None) and getattr(str_ref.strCache, "pt", None):
                pts = [pt.v for pt in str_ref.strCache.pt if getattr(pt, "v", None)]
                if pts:
                    return "".join(pts).strip()
            f_str = getattr(str_ref, "f", None)
            if f_str:
                resolved = _resolve_formula_ref_text(wb, f_str)
                if resolved:
                    return resolved
                return str(f_str).strip()
    # XML tree fallback for titles inside AlternateContent or custom rich blocks
    if hasattr(title_obj, "to_tree"):
        try:
            tree = title_obj.to_tree()
            texts = [el.text for el in tree.iter() if el.tag.endswith("}t") and el.text]
            if texts:
                return "".join(texts).strip()
        except Exception:
            pass
    return ""


def _extract_single_series_auto_title(chart: Any, wb: Workbook | None = None) -> str:
    """In Excel, a 1-series chart without autoTitleDeleted automatically displays the series name as Chart Title."""
    if getattr(chart, "autoTitleDeleted", False) is True:
        return ""
    series_list = list(getattr(chart, "series", []) or [])
    if len(series_list) != 1:
        return ""
    s0 = series_list[0]
    tx = getattr(s0, "tx", None) or getattr(s0, "title", None)
    if isinstance(tx, str):
        return tx.strip()
    if tx is not None:
        if getattr(tx, "v", None):
            return str(tx.v).strip()
        str_ref = getattr(tx, "strRef", None)
        if str_ref:
            if getattr(str_ref, "strCache", None) and getattr(str_ref.strCache, "pt", None):
                pts = [pt.v for pt in str_ref.strCache.pt if getattr(pt, "v", None)]
                if pts:
                    return "".join(pts).strip()
            if getattr(str_ref, "f", None):
                return _resolve_formula_ref_text(wb, str_ref.f)
    return ""


def _extract_chart_type(chart: Any) -> str:
    # Unwrap composite/combo charts if needed
    sub_charts = getattr(chart, "_charts", None)
    if sub_charts and isinstance(sub_charts, list) and len(sub_charts) > 0:
        return _extract_chart_type(sub_charts[0])

    cls_name = type(chart).__name__.lower()
    mapped = CHART_TYPE_MAP.get(cls_name, cls_name)
    if mapped == "bar" and getattr(chart, "type", None) == "col":
        return "column"
    return mapped


def _extract_series_ranges(chart: Any) -> list[str]:
    ranges: list[str] = []
    all_series = list(getattr(chart, "series", []) or [])
    for sub in getattr(chart, "_charts", []) or []:
        all_series.extend(list(getattr(sub, "series", []) or []))

    for s in all_series:
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
    """Return (has_any_data_labels, has_percent_labels) via object attributes AND XML tree fallback."""
    has_any = False
    has_pct = False

    def _check_dl(dl: Any) -> None:
        nonlocal has_any, has_pct
        if dl is None or getattr(dl, "delete", False) is True:
            return
        flags = (
            getattr(dl, "showVal", None),
            getattr(dl, "showPercent", None),
            getattr(dl, "showCatName", None),
            getattr(dl, "showSerName", None),
            getattr(dl, "showLeaderLines", None),
        )
        if any(f is True for f in flags[:4]):
            has_any = True
        elif all(f is None for f in flags[:4]):
            has_any = True
        if getattr(dl, "showPercent", None) is True:
            has_pct = True
        # Check individual data point labels (dLbl) if student added label to specific slices/bars
        d_lbl_list = getattr(dl, "dLbl", None) or []
        if len(d_lbl_list) > 0:
            has_any = True

    _check_dl(getattr(chart, "dataLabels", None))
    for s in getattr(chart, "series", []) or []:
        _check_dl(getattr(s, "dLbls", None) or getattr(s, "data_labels", None))
    for sub in getattr(chart, "_charts", []) or []:
        _check_dl(getattr(sub, "dataLabels", None))
        for s in getattr(sub, "series", []) or []:
            _check_dl(getattr(s, "dLbls", None) or getattr(s, "data_labels", None))

    # XML tree scan fallback (catches Google Sheets & Excel 365 dLbls variations)
    if not has_any and hasattr(chart, "to_tree"):
        try:
            tree = chart.to_tree()
            for el in tree.iter():
                tag = el.tag.split("}")[-1]
                if tag in ("showVal", "showPercent", "showCatName", "showSerName"):
                    if el.attrib.get("val", "1") in ("1", "true"):
                        has_any = True
                        if tag == "showPercent":
                            has_pct = True
        except Exception:
            pass

    return has_any, has_pct


def inspect_chart_elements_summary(chart: Any, wb: Workbook | None = None) -> dict[str, Any]:
    """Return a structured summary of a chart and all its elements."""
    c_type = _extract_chart_type(chart)
    explicit_title = _extract_title_text(getattr(chart, "title", None), wb=wb)
    auto_title = _extract_single_series_auto_title(chart, wb=wb) if not explicit_title else ""
    title_txt = explicit_title or auto_title
    has_title = bool(title_txt) or (
        getattr(chart, "title", None) is not None and getattr(chart, "autoTitleDeleted", False) is not True
    )

    x_ax = getattr(chart, "x_axis", None)
    y_ax = getattr(chart, "y_axis", None)
    x_title = _extract_title_text(getattr(x_ax, "title", None), wb=wb) if x_ax else ""
    y_title = _extract_title_text(getattr(y_ax, "title", None), wb=wb) if y_ax else ""
    has_x_title = bool(x_title) or (x_ax is not None and getattr(x_ax, "title", None) is not None)
    has_y_title = bool(y_title) or (y_ax is not None and getattr(y_ax, "title", None) is not None)

    has_dl, has_pct = _inspect_data_labels(chart)
    leg = getattr(chart, "legend", None)
    has_legend = leg is not None and getattr(leg, "overlay", None) is not None or leg is not None
    leg_pos = getattr(leg, "position", None) if leg else None

    plot_area = getattr(chart, "plot_area", None)
    has_dtable = bool(plot_area and getattr(plot_area, "dTable", None) is not None)
    if not has_dtable and hasattr(chart, "to_tree"):
        try:
            has_dtable = any(el.tag.endswith("}dTable") for el in chart.to_tree().iter())
        except Exception:
            pass

    has_gridlines = bool(
        (y_ax and getattr(y_ax, "majorGridlines", None) is not None)
        or (x_ax and getattr(x_ax, "majorGridlines", None) is not None)
    )

    all_series = list(getattr(chart, "series", []) or [])
    for sub in getattr(chart, "_charts", []) or []:
        all_series.extend(list(getattr(sub, "series", []) or []))

    return {
        "type": c_type,
        "grouping": getattr(chart, "grouping", None),
        "title": title_txt,
        "has_explicit_title": bool(explicit_title),
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
        "series_count": len(all_series),
        "series_ranges": _extract_series_ranges(chart),
    }


def _chart_types_compatible(actual_type: str, expected_type: str, strict_orientation: bool = False) -> bool:
    act = actual_type.lower().strip()
    exp = expected_type.lower().strip()
    if act == exp:
        return True
    if exp == "bar_or_column" and act in {"bar", "column"}:
        return True
    # In Thai Excel assignments, "แผนภูมิแท่ง" is used interchangeably for Column (vertical) and Bar (horizontal)!
    if not strict_orientation and exp in {"bar", "column"} and act in {"bar", "column"}:
        return True
    if not strict_orientation and exp in {"pie", "doughnut"} and act in {"pie", "doughnut"}:
        return True
    return False


def _titles_forgiving_match(actual_txt: str, expected_txt: str, has_title_obj: bool, strict_exact: bool = False) -> bool:
    """
    Human-teacher style title check:
    Students rarely write the exact same 30-character sentence as the teacher's Answer Key!
    As long as the student set a meaningful non-placeholder title (unless strict_exact=True), give full credit.
    """
    act = (actual_txt or "").strip()
    exp = (expected_txt or "").strip()
    if not exp:
        return has_title_obj and act.lower() not in PLACEHOLDER_TITLES

    if exp.lower() in act.lower() or (act and act.lower() in exp.lower()):
        return True

    if strict_exact:
        return False

    # If student wrote ANY meaningful non-placeholder title on their chart/axis, accept it!
    if act and act.lower() not in PLACEHOLDER_TITLES and len(act) >= 2:
        return True

    return False


def _evaluate_single_chart(
    chart: Any,
    sheet_name: str,
    cfg: dict[str, Any],
    wb: Workbook,
) -> tuple[int, int, list[GradingErrorRecord], dict[str, Any]]:
    info = inspect_chart_elements_summary(chart, wb=wb)
    actual_type = info["type"]
    actual_title = info["title"]
    actual_ranges = info["series_ranges"]
    strict_orientation = bool(cfg.get("strict_chart_orientation", False))
    strict_title = bool(cfg.get("strict_exact_title", False))

    total = 0
    passed = 0
    errors: list[GradingErrorRecord] = []

    # 1. Chart Type
    if cfg.get("chart_type"):
        total += 1
        expected_type = str(cfg["chart_type"]).lower().strip()
        if _chart_types_compatible(actual_type, expected_type, strict_orientation=strict_orientation):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_TYPE",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"ประเภทแผนภูมิไม่ตรง (ใช้แบบ '{actual_type}' แต่โจทย์กำหนด '{expected_type}')",
                    expected_detail=expected_type,
                    actual_detail=actual_type,
                    fix_suggestion_th=f"เปลี่ยนประเภทแผนภูมิเป็นแบบ {expected_type}",
                )
            )

    # 2. Chart Title
    exp_title = str(cfg.get("expected_title") or "").strip()
    if exp_title or cfg.get("require_title"):
        total += 1
        if _titles_forgiving_match(actual_title, exp_title, info["has_title"], strict_exact=strict_title):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CHART_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th=(
                        f"ชื่อแผนภูมิไม่ตรง (พบ '{actual_title or '(ไม่มีชื่อ)'}' ควรมี '{exp_title}')"
                        if (exp_title and strict_title)
                        else "ยังไม่ได้ใส่ชื่อแผนภูมิ (Chart Title) หรือยังเป็นคำว่า Chart Title"
                    ),
                    expected_detail=exp_title or "มีชื่อแผนภูมิ",
                    actual_detail=actual_title or "(ไม่มีชื่อ)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊ก Chart Title แล้วตั้งชื่อแผนภูมิให้สื่อความหมาย",
                )
            )

    # 3. Horizontal Axis Title (X) — auto-skip on Pie/Doughnut which have no axes!
    exp_x = str(cfg.get("x_axis_title") or "").strip()
    if (exp_x or cfg.get("require_x_axis_title")) and actual_type not in {"pie", "doughnut", "radar"}:
        total += 1
        if _titles_forgiving_match(info["x_axis_title"], exp_x, info["has_x_axis_title"], strict_exact=strict_title):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_X_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้ใส่ชื่อแกนแนวนอน (Axis Title แกน X)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊ก Axis Titles แล้วพิมพ์ชื่อแกนแนวนอน",
                )
            )

    # 4. Vertical Axis Title (Y) — auto-skip on Pie/Doughnut which have no axes!
    exp_y = str(cfg.get("y_axis_title") or "").strip()
    if (exp_y or cfg.get("require_y_axis_title")) and actual_type not in {"pie", "doughnut", "radar"}:
        total += 1
        if _titles_forgiving_match(info["y_axis_title"], exp_y, info["has_y_axis_title"], strict_exact=strict_title):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_Y_AXIS_TITLE",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้ใส่ชื่อแกนแนวตั้ง (Axis Title แกน Y)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊ก Axis Titles แล้วพิมพ์ชื่อแกนแนวตั้ง",
                )
            )

    # 5. Data Labels / Percent Labels
    if cfg.get("require_percent_labels"):
        total += 1
        # Forgiving: if student turned on Data Labels on Pie chart (even value or percent), check percent first
        if info["has_percent_labels"] or (actual_type not in {"pie", "doughnut"} and info["has_data_labels"]):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_PERCENT_DATA_LABELS",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้แสดงค่าเปอร์เซ็นต์ (%) บนป้ายกำกับข้อมูลของแผนภูมิ",
                    fix_suggestion_th="กด [+] > Data Labels > More Options > ติ๊กถูกช่อง Percentage",
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
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Data Labels",
                )
            )

    # 6. Legend (note: 1-series column/bar charts in Excel often omit Legend by default unless requested; check cleanly)
    if cfg.get("require_legend") or cfg.get("legend_position"):
        total += 1
        if not info["has_legend"]:
            errors.append(
                GradingErrorRecord(
                    error_code="MISSING_CHART_LEGEND",
                    severity="warning",
                    sheet_name=sheet_name,
                    message_th="ยังไม่ได้เปิดแสดงคำอธิบายแผนภูมิ (Legend)",
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Legend",
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

    # 7. Data Table
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
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Data Table",
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
                    fix_suggestion_th="กดปุ่ม [+] ข้างแผนภูมิ > ติ๊กถูกช่อง Gridlines",
                )
            )

    # 9. Data Range (forgiving: strip sheet prefix so 'Sheet1!B2:B10' matches 'แผ่นงาน1!B2:B10' or 'B1:B10'!)
    if cfg.get("required_data_range"):
        total += 1
        raw_req = str(cfg["required_data_range"]).upper().replace("$", "").strip()
        req_coords = raw_req.split("!")[-1]
        norm_actuals = [r.split("!")[-1] for r in actual_ranges]
        # Also allow header-included vs header-excluded range (e.g. B1:B10 vs B2:B10 -> same end cell B10!)
        req_end = req_coords.split(":")[-1]
        if any(req_coords in a or a in req_coords or (":" in req_coords and a.endswith(f":{req_end}")) for a in norm_actuals):
            passed += 1
        else:
            errors.append(
                GradingErrorRecord(
                    error_code="WRONG_CHART_DATA_RANGE",
                    severity="error",
                    sheet_name=sheet_name,
                    message_th=f"ช่วงข้อมูลของแผนภูมิไม่ตรง ({', '.join(norm_actuals) or 'ไม่พบ'} ควรใช้ {req_coords})",
                    expected_detail=req_coords,
                    actual_detail=", ".join(actual_ranges) or "(ไม่พบช่วงข้อมูล)",
                    fix_suggestion_th=f"ตรวจสอบช่วงข้อมูลที่นำมาสร้างแผนภูมิ ({req_coords})",
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
                    message_th=f"จำนวนชุดข้อมูลในแผนภูมิไม่ครบ ({series_cnt} ชุด ควรมีอย่างน้อย {cfg['min_series_count']} ชุด)",
                    fix_suggestion_th="คลิกขวาที่แผนภูมิ > Select Data เพื่อเลือกชุดข้อมูลให้ครบ",
                )
            )

    if total == 0:
        total = 1
        passed = 1

    return passed, total, errors, info


def _collect_all_workbook_charts(wb: Workbook) -> list[tuple[str, Any]]:
    """Collect charts from ALL normal worksheets AND dedicated Chartsheets ('New sheet' charts!)."""
    out: list[tuple[str, Any]] = []
    for name in wb.sheetnames:
        sh = wb[name]
        for ch in getattr(sh, "_charts", []) or []:
            out.append((name, ch))
    for cs in getattr(wb, "chartsheets", []) or []:
        cs_title = getattr(cs, "title", "Chart")
        for ch in getattr(cs, "_charts", []) or []:
            out.append((cs_title, ch))
    return out


def check_chart_item(
    item: RubricItemConfig,
    student_wb: Workbook,
) -> RubricItemResult:
    """
    Validate Excel charts & Chart Elements:
    - Evaluates ALL candidate charts on the matched sheet (and falls back across all sheets/chartsheets!)
      and picks the BEST-MATCHING chart so multi-chart sheets never check the wrong chart!
    - Forgives student wording differences on Chart Title & Axis Titles!
    - Forgives Thai 'แผนภูมิแท่ง' (Column vs Bar) and header-inclusive vs header-exclusive ranges!
    """
    from excel_engine.readers.excel_reader import resolve_worksheet_forgiving

    cfg = item.rule_config or {}
    ws, resolved_sheet = resolve_worksheet_forgiving(student_wb, item.sheet_name)

    candidates: list[tuple[str, Any]] = []
    if ws is not None:
        for ch in getattr(ws, "_charts", []) or []:
            candidates.append((resolved_sheet, ch))

    # Also gather all charts across the workbook (including Chartsheets!) in case student placed chart on another sheet
    all_wb_charts = _collect_all_workbook_charts(student_wb)
    if not candidates:
        candidates = all_wb_charts

    if not candidates:
        err = GradingErrorRecord(
            error_code="MISSING_CHART",
            severity="error",
            sheet_name=resolved_sheet or item.sheet_name,
            message_th="ไม่พบแผนภูมิ (Chart) ในไฟล์งานของนักเรียน",
            expected_detail=cfg.get("chart_type", "Chart"),
            actual_detail="ไม่มีแผนภูมิ",
            fix_suggestion_th="คลุมข้อมูลแล้วสร้างแผนภูมิผ่านเมนู Insert > Charts (หากทำในรูปภาพจะไม่นับเป็นแผนภูมิ Excel จริง)",
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

    # Evaluate every candidate chart on target sheet first; if none get 100% and workbook has other charts, check all!
    best_eval: tuple[float, int, int, list[GradingErrorRecord], dict[str, Any], str] | None = None

    def _try_pool(pool: list[tuple[str, Any]]) -> None:
        nonlocal best_eval
        for sh_n, ch_obj in pool:
            p, t, errs, inf = _evaluate_single_chart(ch_obj, sh_n, cfg, student_wb)
            ratio = (p / t) if t > 0 else 1.0
            if best_eval is None or (ratio, p) > (best_eval[0], best_eval[1]):
                best_eval = (ratio, p, t, errs, inf, sh_n)

    _try_pool(candidates)
    if best_eval is not None and best_eval[0] < 1.0 and len(all_wb_charts) > len(candidates):
        _try_pool(all_wb_charts)

    assert best_eval is not None
    _, passed, total, errors, info, matched_sheet = best_eval
    actual_type = info["type"]

    all_passed = passed == total
    err_summary = "; ".join(e.message_th for e in errors[:3]) if errors else ""
    if all_passed:
        earned = item.max_points
        reason = f"แผนภูมิและองค์ประกอบถูกต้องครบทั้ง {total} รายการ ({actual_type} แท็บ {matched_sheet})"
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
        evidence={"chart_info": info, "matched_sheet": matched_sheet},
        errors=errors,
    )
