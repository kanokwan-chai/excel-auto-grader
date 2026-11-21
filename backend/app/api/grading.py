"""Grading Execution, Individual Results, Teacher Adjustments, Confirmation & History API."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.core.storage import storage_service
from backend.app.models.models import (
    Assignment,
    GradeAdjustment,
    GradingDetail,
    GradingError,
    GradingJob,
    GradingResult,
    GradingRubric,
    RubricVersion,
    Submission,
    SubmissionFile,
    User,
)
from excel_engine.readers import load_workbooks
from backend.app.schemas.schemas import (
    ExemptDetailRequest,
    GradeAdjustmentRequest,
    StartGradingRequest,
)
from backend.app.services.grading_service import (
    get_or_create_latest_rubric_version,
    grade_single_submission,
)

router = APIRouter(prefix="/grading", tags=["Grading & History"])


@router.post("/run")
def run_grading_job(
    payload: StartGradingRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Execute automatic Excel grading for an assignment using the selected rubric version."""
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == payload.assignment_id,
            Assignment.owner_user_id == current_teacher.id,
            Assignment.deleted_at.is_(None),
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="ไม่พบงานที่ระบุ")

    rubric = (
        db.query(GradingRubric)
        .filter(
            GradingRubric.id == payload.rubric_id,
            GradingRubric.owner_user_id == current_teacher.id,
            GradingRubric.deleted_at.is_(None),
        )
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="ไม่พบชุดเกณฑ์การตรวจ")

    rubric_ver = get_or_create_latest_rubric_version(db, current_teacher.id, rubric)

    sub_q = db.query(Submission).filter(
        Submission.owner_user_id == current_teacher.id,
        Submission.assignment_id == assignment.id,
    )
    if payload.submission_ids:
        sub_q = sub_q.filter(Submission.id.in_(payload.submission_ids))
    submissions = sub_q.all()

    job = GradingJob(
        owner_user_id=current_teacher.id,
        assignment_id=assignment.id,
        rubric_version_id=rubric_ver.id,
        status="processing",
        total_files=len(submissions),
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()

    processed = 0
    failed = 0
    result_ids: list[str] = []

    for sub in submissions:
        try:
            res = grade_single_submission(
                db,
                owner_user_id=current_teacher.id,
                assignment=assignment,
                submission=sub,
                rubric_version=rubric_ver,
                grading_job=job,
            )
            processed += 1
            if res.status == "error":
                failed += 1
            result_ids.append(res.id)
        except Exception:
            processed += 1
            failed += 1
            db.rollback()

    job.processed_files = processed
    job.failed_files = failed
    job.status = "completed" if failed == 0 else ("partial_failed" if processed > failed else "failed")
    job.completed_at = datetime.now(timezone.utc)
    assignment.status = "completed"
    db.commit()

    return {
        "job_id": job.id,
        "status": job.status,
        "total_files": job.total_files,
        "processed_files": job.processed_files,
        "failed_files": job.failed_files,
        "rubric_version": rubric_ver.version_number,
        "result_ids": result_ids,
    }


@router.get("/results")
def list_grading_results(
    assignment_id: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = (
        db.query(GradingResult, Assignment, Submission)
        .join(Assignment, GradingResult.assignment_id == Assignment.id)
        .join(Submission, GradingResult.submission_id == Submission.id)
        .filter(GradingResult.owner_user_id == current_teacher.id)
    )
    if assignment_id:
        q = q.filter(GradingResult.assignment_id == assignment_id)
    rows = q.order_by(GradingResult.graded_at.desc()).all()

    return [
        {
            "id": gr.id,
            "assignment_id": a.id,
            "assignment_title": a.title,
            "submission_id": sub.id,
            "student_id": gr.student_id,
            "student_name": sub.student_display_name or "ไม่ระบุชื่อ",
            "student_code": sub.student_code_matched or "-",
            "auto_score": gr.auto_score,
            "final_score": gr.final_score,
            "max_score": gr.max_score,
            "percentage": gr.percentage,
            "status": gr.status,
            "is_confirmed": gr.is_confirmed,
            "recalculated_with_libreoffice": gr.recalculated_with_libreoffice,
            "graded_at": gr.graded_at.isoformat() if gr.graded_at else None,
        }
        for gr, a, sub in rows
    ]


@router.get("/results/{result_id}")
def get_grading_result_detail(
    result_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    gr = (
        db.query(GradingResult)
        .filter(GradingResult.id == result_id, GradingResult.owner_user_id == current_teacher.id)
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="ไม่พบผลการตรวจนี้")

    assignment = db.query(Assignment).filter(Assignment.id == gr.assignment_id).first()
    submission = db.query(Submission).filter(Submission.id == gr.submission_id).first()
    rubric_ver = (
        db.query(RubricVersion).filter(RubricVersion.id == gr.rubric_version_id).first()
        if gr.rubric_version_id
        else None
    )

    return {
        "id": gr.id,
        "assignment_id": gr.assignment_id,
        "assignment_title": assignment.title if assignment else "-",
        "submission_id": gr.submission_id,
        "student_name": submission.student_display_name if submission else "-",
        "student_code": submission.student_code_matched if submission else "-",
        "rubric_version": rubric_ver.version_number if rubric_ver else 1,
        "auto_score": gr.auto_score,
        "final_score": gr.final_score,
        "max_score": gr.max_score,
        "percentage": gr.percentage,
        "status": gr.status,
        "is_confirmed": gr.is_confirmed,
        "confirmed_at": gr.confirmed_at.isoformat() if gr.confirmed_at else None,
        "teacher_comment": gr.teacher_comment,
        "recalculated_with_libreoffice": gr.recalculated_with_libreoffice,
        "graded_at": gr.graded_at.isoformat() if gr.graded_at else None,
        "details": [
            {
                "id": d.id,
                "item_title": d.item_title,
                "category": d.category,
                "target_cell": d.target_cell,
                "earned_points": d.earned_points,
                "deducted_points": d.deducted_points,
                "max_points": d.max_points,
                "passed": d.passed,
                "is_exempted": d.is_exempted,
                "expected_value": d.expected_value,
                "actual_value": d.actual_value,
                "expected_formula": d.expected_formula,
                "actual_formula": d.actual_formula,
                "reason": d.reason,
                "suggestion": d.suggestion,
            }
            for d in gr.details
        ],
        "errors": [
            {
                "id": e.id,
                "error_code": e.error_code,
                "severity": e.severity,
                "sheet_name": e.sheet_name,
                "cell_reference": e.cell_reference,
                "message_th": e.message_th,
                "expected_detail": e.expected_detail,
                "actual_detail": e.actual_detail,
                "fix_suggestion_th": e.fix_suggestion_th,
            }
            for e in gr.errors
        ],
        "adjustments": [
            {
                "id": adj.id,
                "previous_score": adj.previous_score,
                "new_score": adj.new_score,
                "reason": adj.reason,
                "action_type": adj.action_type,
                "created_at": adj.created_at.isoformat() if adj.created_at else None,
            }
            for adj in gr.adjustments
        ],
    }


@router.get("/results/{result_id}/preview")
def get_grading_result_excel_preview(
    result_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Return an interactive Excel-like grid preview (values, formulas, colors, borders, merges, charts, error cells)."""
    from openpyxl.utils import get_column_letter

    gr = (
        db.query(GradingResult)
        .filter(GradingResult.id == result_id, GradingResult.owner_user_id == current_teacher.id)
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="ไม่พบผลการตรวจนี้")

    sub_file = (
        db.query(SubmissionFile)
        .filter(
            SubmissionFile.id == gr.submission_file_id,
            SubmissionFile.owner_user_id == current_teacher.id,
        )
        .first()
        if gr.submission_file_id
        else None
    )
    if not sub_file:
        sub_file = (
            db.query(SubmissionFile)
            .filter(
                SubmissionFile.submission_id == gr.submission_id,
                SubmissionFile.owner_user_id == current_teacher.id,
            )
            .order_by(SubmissionFile.is_primary.desc())
            .first()
        )
    if not sub_file:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ Excel สำหรับพรีวิว")

    try:
        local_path = storage_service.get_local_path(sub_file.storage_path, current_teacher.id)
        loaded = load_workbooks(local_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"ไม่สามารถเปิดไฟล์ Excel เพื่อพรีวิวได้: {exc}")

    # Build error lookup: (sheet_lower, cell_upper) -> message_th
    error_map: dict[tuple[str, str], str] = {}
    for err in gr.errors:
        if err.cell_reference:
            key_sheet = (err.sheet_name or "").lower()
            error_map[(key_sheet, err.cell_reference.upper())] = err.message_th

    # Standard Microsoft Office Theme palette (indices 0..9)
    OFFICE_THEME_PALETTE = [
        (255, 255, 255),  # 0: Light 1 (White)
        (0, 0, 0),        # 1: Dark 1 (Black)
        (231, 230, 230),  # 2: Light 2
        (68, 84, 106),    # 3: Dark 2
        (68, 114, 196),   # 4: Accent 1 (Blue)
        (237, 125, 49),   # 5: Accent 2 (Orange)
        (165, 165, 165),  # 6: Accent 3 (Gray)
        (255, 192, 0),    # 7: Accent 4 (Gold)
        (91, 155, 213),   # 8: Accent 5 (Sky Blue)
        (112, 173, 71),   # 9: Accent 6 (Green)
    ]

    def _apply_tint(rgb_tuple: tuple[int, int, int], tint: float) -> str:
        r, g, b = rgb_tuple
        if tint > 0:
            r = int(r + (255 - r) * tint)
            g = int(g + (255 - g) * tint)
            b = int(b + (255 - b) * tint)
        elif tint < 0:
            r = int(r * (1.0 + tint))
            g = int(g * (1.0 + tint))
            b = int(b * (1.0 + tint))
        return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"

    def _hex_color(color_obj) -> str | None:
        if not color_obj:
            return None
        ctype = getattr(color_obj, "type", None)
        if ctype == "theme":
            t_idx = getattr(color_obj, "theme", None)
            tint = float(getattr(color_obj, "tint", 0.0) or 0.0)
            if isinstance(t_idx, int) and 0 <= t_idx < len(OFFICE_THEME_PALETTE):
                return _apply_tint(OFFICE_THEME_PALETTE[t_idx], tint)
            return None
        rgb = getattr(color_obj, "rgb", None)
        if isinstance(rgb, str) and len(rgb) >= 6 and rgb != "00000000":
            hex6 = rgb[-6:].upper()
            return f"#{hex6}"
        return None

    try:
        sheets_out = []
        for sname in loaded.formula_wb.sheetnames:
            f_ws = loaded.formula_wb[sname]
            v_ws = loaded.value_wb[sname]

            max_r = max(min(f_ws.max_row or 1, 80), 10)
            max_c = max(min(f_ws.max_column or 1, 20), 8)
            col_headers = [get_column_letter(c) for c in range(1, max_c + 1)]

            # Map merged cell spans & skipped covered cells
            merge_spans: dict[tuple[int, int], tuple[int, int]] = {}
            covered_cells: set[tuple[int, int]] = set()
            for rng in f_ws.merged_cells.ranges:
                r1, c1, r2, c2 = rng.min_row, rng.min_col, rng.max_row, rng.max_col
                if r1 <= max_r and c1 <= max_c:
                    merge_spans[(r1, c1)] = (min(r2, max_r) - r1 + 1, min(c2, max_c) - c1 + 1)
                    for rr in range(r1, min(r2, max_r) + 1):
                        for cc in range(c1, min(c2, max_c) + 1):
                            if (rr, cc) != (r1, c1):
                                covered_cells.add((rr, cc))

            rows_out = []
            for r in range(1, max_r + 1):
                row_cells = []
                for c in range(1, max_c + 1):
                    if (r, c) in covered_cells:
                        row_cells.append({"covered": True})
                        continue
                    fc = f_ws.cell(row=r, column=c)
                    vc = v_ws.cell(row=r, column=c)
                    coord = fc.coordinate
                    raw_f = fc.value
                    is_formula = isinstance(raw_f, str) and raw_f.strip().startswith("=")
                    disp_val = vc.value if is_formula else raw_f
                    if is_formula and disp_val is None:
                        disp_val = raw_f

                    bg = None
                    if fc.fill and fc.fill.fill_type and fc.fill.fill_type != "none":
                        bg = _hex_color(fc.fill.fgColor)
                        if bg in ("#000000", "#FFFFFF"):
                            bg = None

                    fg = _hex_color(fc.font.color if fc.font else None)
                    if fg == "#000000":
                        fg = None

                    b = fc.border
                    has_border = bool(
                        b and any(getattr(side, "style", None) for side in (b.left, b.right, b.top, b.bottom))
                    )
                    span = merge_spans.get((r, c), (1, 1))
                    err_msg = error_map.get((sname.lower(), coord.upper())) or error_map.get(("", coord.upper()))

                    row_cells.append({
                        "coord": coord,
                        "value": "" if disp_val is None else str(disp_val),
                        "formula": raw_f if is_formula else None,
                        "bold": bool(fc.font and fc.font.bold),
                        "italic": bool(fc.font and fc.font.italic),
                        "bg_color": bg,
                        "font_color": fg,
                        "align": (fc.alignment.horizontal if fc.alignment else None) or ("right" if isinstance(disp_val, (int, float)) else "left"),
                        "has_border": has_border,
                        "number_format": str(fc.number_format or "General"),
                        "row_span": span[0],
                        "col_span": span[1],
                        "error_msg": err_msg,
                    })
                rows_out.append({"row_num": r, "cells": row_cells})

            charts_out = []
            for ch in getattr(f_ws, "_charts", []) or []:
                cls_low = type(ch).__name__.lower()
                ch_type = "pie" if "pie" in cls_low or "doughnut" in cls_low else ("line" if "line" in cls_low else ("area" if "area" in cls_low else "bar"))
                # Extract title
                ch_title = ""
                t_obj = getattr(ch, "title", None)
                if isinstance(t_obj, str):
                    ch_title = t_obj
                elif t_obj and getattr(t_obj, "tx", None) and getattr(t_obj.tx, "rich", None):
                    ch_title = "".join(
                        r.t for p in (t_obj.tx.rich.p or []) for r in (p.r or []) if getattr(r, "t", None)
                    )

                # Resolve first series values & categories from workbook
                data_points: list[dict[str, object]] = []
                series_list = list(getattr(ch, "series", []) or [])
                if series_list:
                    s0 = series_list[0]
                    val_ref = getattr(getattr(s0, "val", None), "numRef", None)
                    cat_obj = getattr(s0, "cat", None)
                    cat_ref = getattr(cat_obj, "strRef", None) or getattr(cat_obj, "numRef", None) if cat_obj else None

                    def _read_range_values(formula_ref: str | None) -> list[object]:
                        if not formula_ref:
                            return []
                        try:
                            if "!" in formula_ref:
                                sh_part, rng_part = formula_ref.split("!", 1)
                                sh_clean = sh_part.strip("'")
                                target_ws = loaded.value_wb[sh_clean] if sh_clean in loaded.value_wb.sheetnames else v_ws
                            else:
                                rng_part = formula_ref
                                target_ws = v_ws
                            rng_clean = rng_part.replace("$", "")
                            vals_list = []
                            for row_cells_t in target_ws[rng_clean]:
                                if isinstance(row_cells_t, tuple):
                                    for cell_t in row_cells_t:
                                        vals_list.append(cell_t.value)
                                else:
                                    vals_list.append(row_cells_t.value)
                            return vals_list
                        except Exception:
                            return []

                    raw_vals = _read_range_values(getattr(val_ref, "f", None))
                    raw_cats = _read_range_values(getattr(cat_ref, "f", None))
                    # Drop header cell if titles_from_data was included (first val is non-numeric string)
                    if raw_vals and isinstance(raw_vals[0], str):
                        raw_vals = raw_vals[1:]
                    for idx_p, v_item in enumerate(raw_vals[:30]):
                        num_v = float(v_item) if isinstance(v_item, (int, float)) else 0.0
                        lbl = str(raw_cats[idx_p]) if idx_p < len(raw_cats) and raw_cats[idx_p] is not None else f"รายการ {idx_p + 1}"
                        data_points.append({"name": lbl, "value": num_v})

                charts_out.append({
                    "type": ch_type,
                    "title": ch_title or f"แผนภูมิ ({type(ch).__name__})",
                    "data": data_points,
                })

            sheets_out.append({
                "name": sname,
                "col_headers": col_headers,
                "rows": rows_out,
                "charts": charts_out,
            })

        return {
            "filename": sub_file.original_filename,
            "sheet_names": list(loaded.formula_wb.sheetnames),
            "sheets": sheets_out,
        }
    finally:
        loaded.close()


@router.put("/results/{result_id}/adjust")
def adjust_score(
    result_id: str,
    payload: GradeAdjustmentRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    gr = (
        db.query(GradingResult)
        .filter(GradingResult.id == result_id, GradingResult.owner_user_id == current_teacher.id)
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="ไม่พบผลการตรวจ")
    if payload.new_score > gr.max_score:
        raise HTTPException(status_code=400, detail=f"คะแนนใหม่ ({payload.new_score}) ต้องไม่เกินคะแนนเต็ม ({gr.max_score})")

    prev = gr.final_score
    gr.final_score = round(payload.new_score, 2)
    gr.percentage = round((gr.final_score / gr.max_score * 100.0) if gr.max_score > 0 else 0.0, 2)
    if payload.teacher_comment is not None:
        gr.teacher_comment = payload.teacher_comment

    db.add(
        GradeAdjustment(
            owner_user_id=current_teacher.id,
            grading_result_id=gr.id,
            adjusted_by=current_teacher.id,
            rubric_version_id=gr.rubric_version_id,
            previous_score=prev,
            new_score=gr.final_score,
            reason=payload.reason,
            action_type="score_override",
        )
    )
    db.commit()
    return {"id": gr.id, "final_score": gr.final_score, "percentage": gr.percentage}


@router.put("/results/{result_id}/exempt")
def exempt_rubric_detail(
    result_id: str,
    payload: ExemptDetailRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    gr = (
        db.query(GradingResult)
        .filter(GradingResult.id == result_id, GradingResult.owner_user_id == current_teacher.id)
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="ไม่พบผลการตรวจ")

    detail = (
        db.query(GradingDetail)
        .filter(GradingDetail.id == payload.detail_id, GradingDetail.grading_result_id == gr.id)
        .first()
    )
    if not detail:
        raise HTTPException(status_code=404, detail="ไม่พบเกณฑ์ย่อยนี้")

    prev = gr.final_score
    detail.is_exempted = payload.exempt
    if payload.exempt:
        detail.earned_points = detail.max_points
        detail.deducted_points = 0.0

    new_total = min(gr.max_score, sum(d.earned_points for d in gr.details))
    gr.final_score = round(new_total, 2)
    gr.percentage = round((gr.final_score / gr.max_score * 100.0) if gr.max_score > 0 else 0.0, 2)

    db.add(
        GradeAdjustment(
            owner_user_id=current_teacher.id,
            grading_result_id=gr.id,
            adjusted_by=current_teacher.id,
            rubric_version_id=gr.rubric_version_id,
            previous_score=prev,
            new_score=gr.final_score,
            reason=payload.reason,
            action_type="exempt_item",
        )
    )
    db.commit()
    return {"id": gr.id, "final_score": gr.final_score, "percentage": gr.percentage}


@router.post("/results/{result_id}/confirm")
def confirm_grade(
    result_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    gr = (
        db.query(GradingResult)
        .filter(GradingResult.id == result_id, GradingResult.owner_user_id == current_teacher.id)
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="ไม่พบผลการตรวจ")
    gr.is_confirmed = True
    gr.status = "confirmed"
    gr.confirmed_at = datetime.now(timezone.utc)
    gr.confirmed_by = current_teacher.id
    db.add(
        GradeAdjustment(
            owner_user_id=current_teacher.id,
            grading_result_id=gr.id,
            adjusted_by=current_teacher.id,
            rubric_version_id=gr.rubric_version_id,
            previous_score=gr.final_score,
            new_score=gr.final_score,
            reason="ครูยืนยันคะแนนแล้ว",
            action_type="confirm",
        )
    )
    db.commit()
    return {"id": gr.id, "is_confirmed": True, "status": "confirmed"}


@router.post("/results/{result_id}/unconfirm")
def unconfirm_grade(
    result_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    gr = (
        db.query(GradingResult)
        .filter(GradingResult.id == result_id, GradingResult.owner_user_id == current_teacher.id)
        .first()
    )
    if not gr:
        raise HTTPException(status_code=404, detail="ไม่พบผลการตรวจ")
    gr.is_confirmed = False
    gr.status = "graded"
    gr.confirmed_at = None
    db.add(
        GradeAdjustment(
            owner_user_id=current_teacher.id,
            grading_result_id=gr.id,
            adjusted_by=current_teacher.id,
            rubric_version_id=gr.rubric_version_id,
            previous_score=gr.final_score,
            new_score=gr.final_score,
            reason="ครูยกเลิกการยืนยันคะแนน",
            action_type="unconfirm",
        )
    )
    db.commit()
    return {"id": gr.id, "is_confirmed": False, "status": "graded"}


@router.get("/history")
def get_grading_history(
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Full audit trail of grading jobs and manual grade adjustments for this teacher."""
    jobs = (
        db.query(GradingJob, Assignment)
        .join(Assignment, GradingJob.assignment_id == Assignment.id)
        .filter(GradingJob.owner_user_id == current_teacher.id)
        .order_by(GradingJob.created_at.desc())
        .limit(50)
        .all()
    )
    adjustments = (
        db.query(GradeAdjustment, GradingResult, Submission, Assignment)
        .join(GradingResult, GradeAdjustment.grading_result_id == GradingResult.id)
        .join(Submission, GradingResult.submission_id == Submission.id)
        .join(Assignment, GradingResult.assignment_id == Assignment.id)
        .filter(GradeAdjustment.owner_user_id == current_teacher.id)
        .order_by(GradeAdjustment.created_at.desc())
        .limit(100)
        .all()
    )

    return {
        "jobs": [
            {
                "id": j.id,
                "assignment_id": a.id,
                "assignment_title": a.title,
                "status": j.status,
                "total_files": j.total_files,
                "processed_files": j.processed_files,
                "failed_files": j.failed_files,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j, a in jobs
        ],
        "adjustments": [
            {
                "id": adj.id,
                "result_id": gr.id,
                "assignment_title": a.title,
                "student_name": sub.student_display_name or "-",
                "previous_score": adj.previous_score,
                "new_score": adj.new_score,
                "reason": adj.reason,
                "action_type": adj.action_type,
                "is_confirmed": gr.is_confirmed,
                "created_at": adj.created_at.isoformat() if adj.created_at else None,
            }
            for adj, gr, sub, a in adjustments
        ],
    }


@router.delete("/jobs/{job_id}")
def delete_grading_job_history(
    job_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Delete a local grading job history record ONLY.
    NEVER modifies or deletes any student submission in Google Classroom / Google Drive.
    """
    job = (
        db.query(GradingJob)
        .filter(GradingJob.id == job_id, GradingJob.owner_user_id == current_teacher.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="ไม่พบประวัติรอบการตรวจนี้")

    # Detach grading_results so deleting the job record safely removes only history metadata
    db.query(GradingResult).filter(
        GradingResult.grading_job_id == job.id,
        GradingResult.owner_user_id == current_teacher.id,
    ).update({"grading_job_id": None})
    db.delete(job)
    db.commit()
    return {"message": "ลบประวัติรอบการตรวจเรียบร้อยแล้ว (ไม่มีผลกระทบต่องานนักเรียนใน Google Classroom)"}


@router.delete("/adjustments/{adjustment_id}")
def delete_grade_adjustment_history(
    adjustment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Delete a local grade adjustment history entry ONLY (never touches Google Classroom)."""
    adj = (
        db.query(GradeAdjustment)
        .filter(GradeAdjustment.id == adjustment_id, GradeAdjustment.owner_user_id == current_teacher.id)
        .first()
    )
    if not adj:
        raise HTTPException(status_code=404, detail="ไม่พบประวัติการปรับคะแนนนี้")
    db.delete(adj)
    db.commit()
    return {"message": "ลบประวัติการปรับคะแนนเรียบร้อยแล้ว (ไม่มีผลกระทบต่องานนักเรียนใน Google Classroom)"}
