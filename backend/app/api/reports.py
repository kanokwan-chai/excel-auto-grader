"""Class Reports, Statistics, Score Distribution & Excel/CSV/PDF Exports API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.models.models import Assignment, GradingResult, RubricVersion, Student, Submission, User
from backend.app.services.export_service import (
    generate_class_report_csv,
    generate_class_report_excel,
    generate_individual_report_pdf,
)

router = APIRouter(prefix="/reports", tags=["Reports & Exports"])


def _build_class_report_data(
    db: Session,
    owner_user_id: str,
    assignment_id: str,
    sort_by: str = "seat",
    search: str | None = None,
    status_filter: str | None = None,
) -> dict:
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id,
            Assignment.owner_user_id == owner_user_id,
            Assignment.deleted_at.is_(None),
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="ไม่พบงานที่ระบุ")

    results = (
        db.query(GradingResult, Submission, Student)
        .join(Submission, GradingResult.submission_id == Submission.id)
        .outerjoin(Student, GradingResult.student_id == Student.id)
        .filter(
            GradingResult.owner_user_id == owner_user_id,
            GradingResult.assignment_id == assignment.id,
        )
        .all()
    )

    rows = []
    for idx, (gr, sub, st) in enumerate(results, start=1):
        name = f"{st.first_name} {st.last_name}" if st else (sub.student_display_name or "ไม่ระบุชื่อ")
        code = st.student_code if st else (sub.student_code_matched or "-")
        seat = st.seat_number if (st and st.seat_number is not None) else idx
        passed = gr.final_score >= assignment.pass_score

        if search:
            q = search.strip().lower()
            if q not in name.lower() and q not in code.lower():
                continue
        if status_filter == "passed" and not passed:
            continue
        if status_filter == "failed" and passed:
            continue
        if status_filter == "confirmed" and not gr.is_confirmed:
            continue

        deducted_lines = [
            f"- {d.item_title} (หัก {d.deducted_points:g} คะแนน): {d.reason or 'ไม่ตรงตามเกณฑ์'}"
            for d in gr.details
            if d.deducted_points > 0
        ]
        deduction_comment = (
            "รายการที่ถูกหักคะแนน:\n" + "\n".join(deducted_lines)
            if deducted_lines
            else "ไม่ถูกหักคะแนน (ทำถูกต้องครบทุกเกณฑ์)"
        )

        rows.append({
            "result_id": gr.id,
            "submission_id": sub.id,
            "seat_number": seat,
            "student_code": code,
            "student_name": name,
            "final_score": gr.final_score,
            "auto_score": gr.auto_score,
            "max_score": gr.max_score,
            "percentage": gr.percentage,
            "passed": passed,
            "is_confirmed": gr.is_confirmed,
            "status": gr.status,
            "status_label": "ยืนยันแล้ว" if gr.is_confirmed else ("ผ่าน" if passed else "ไม่ผ่าน"),
            "deduction_summary": "; ".join(
                f"{d.item_title} (-{d.deducted_points:g}: {d.reason or 'ไม่ตรงตามเกณฑ์'})"
                for d in gr.details
                if d.deducted_points > 0
            ) or "ไม่ถูกหักคะแนน",
            "deduction_comment": deduction_comment,
            "is_classroom_linked": sub.source == "google_classroom",
        })

    if sort_by == "score_desc":
        rows.sort(key=lambda r: r["final_score"], reverse=True)
    elif sort_by == "score_asc":
        rows.sort(key=lambda r: r["final_score"])
    else:
        rows.sort(key=lambda r: (r["seat_number"], r["student_code"]))

    scores = [r["final_score"] for r in rows]
    passed_count = sum(1 for r in rows if r["passed"])
    failed_count = len(rows) - passed_count

    # Histogram buckets (0-20%, 21-40%, 41-60%, 61-80%, 81-100%)
    buckets = [
        {"range": "0-20%", "count": 0},
        {"range": "21-40%", "count": 0},
        {"range": "41-60%", "count": 0},
        {"range": "61-80%", "count": 0},
        {"range": "81-100%", "count": 0},
    ]
    for r in rows:
        p = r["percentage"]
        if p <= 20:
            buckets[0]["count"] += 1
        elif p <= 40:
            buckets[1]["count"] += 1
        elif p <= 60:
            buckets[2]["count"] += 1
        elif p <= 80:
            buckets[3]["count"] += 1
        else:
            buckets[4]["count"] += 1

    last_rubric_id: str | None = None
    sorted_by_recent = sorted(
        results,
        key=lambda item: item[0].graded_at.timestamp() if item[0].graded_at else 0.0,
        reverse=True,
    )
    for gr_row, _, _ in sorted_by_recent:
        if gr_row.rubric_version_id:
            rv_obj = db.query(RubricVersion).filter(RubricVersion.id == gr_row.rubric_version_id).first()
            if rv_obj and rv_obj.rubric_id:
                last_rubric_id = str(rv_obj.rubric_id)
                break

    summary = {
        "assignment_id": assignment.id,
        "assignment_title": assignment.title,
        "last_rubric_id": last_rubric_id,
        "max_score": assignment.max_score,
        "pass_score": assignment.pass_score,
        "total_students": len(rows),
        "highest_score": max(scores) if scores else 0.0,
        "lowest_score": min(scores) if scores else 0.0,
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }

    return {"summary": summary, "distribution": buckets, "rows": rows}


@router.get("/assignments/{assignment_id}")
def get_class_report(
    assignment_id: str,
    sort_by: str = "seat",
    search: str | None = None,
    status_filter: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    return _build_class_report_data(db, current_teacher.id, assignment_id, sort_by, search, status_filter)


@router.get("/assignments/{assignment_id}/export/excel")
def export_class_excel(
    assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    data = _build_class_report_data(db, current_teacher.id, assignment_id)
    content = generate_class_report_excel(
        assignment_title=data["summary"]["assignment_title"],
        rows=data["rows"],
        summary=data["summary"],
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="report_{assignment_id[:8]}.xlsx"'},
    )


@router.get("/assignments/{assignment_id}/export/csv")
def export_class_csv(
    assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    data = _build_class_report_data(db, current_teacher.id, assignment_id)
    content = generate_class_report_csv(data["rows"])
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report_{assignment_id[:8]}.csv"'},
    )


@router.get("/results/{result_id}/export/pdf")
def export_individual_pdf(
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
    assignment = db.query(Assignment).filter(Assignment.id == gr.assignment_id).first()
    submission = db.query(Submission).filter(Submission.id == gr.submission_id).first()

    pdf_bytes = generate_individual_report_pdf({
        "student_name": submission.student_display_name if submission else "-",
        "student_code": submission.student_code_matched if submission else "-",
        "assignment_title": assignment.title if assignment else "-",
        "final_score": gr.final_score,
        "max_score": gr.max_score,
        "percentage": gr.percentage,
        "status": gr.status,
        "details": [
            {
                "item_title": d.item_title,
                "category": d.category,
                "target_cell": d.target_cell,
                "earned_points": d.earned_points,
                "deducted_points": d.deducted_points,
                "max_points": d.max_points,
                "passed": d.passed,
                "is_exempted": d.is_exempted,
                "reason": d.reason,
            }
            for d in gr.details
        ],
    })
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="student_report_{result_id[:8]}.pdf"'},
    )
