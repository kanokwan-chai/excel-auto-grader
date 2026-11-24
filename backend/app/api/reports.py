"""Class Reports, Statistics, Score Distribution & Excel/CSV/PDF Exports API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.models.models import (
    Assignment,
    ClassroomAssignment,
    GoogleClassroom,
    GradingDetail,
    GradingResult,
    RubricVersion,
    Student,
    Submission,
    User,
)
from backend.app.services.export_service import (
    generate_class_report_csv,
    generate_class_report_excel,
    generate_classroom_gradebook_csv,
    generate_classroom_gradebook_excel,
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

    # Deduplicate by student so an older duplicate submission/result never lingers alongside a newer re-grade
    results_sorted_newest = sorted(
        results,
        key=lambda item: item[0].graded_at.timestamp() if item[0].graded_at else 0.0,
        reverse=True,
    )
    seen_student_keys: set[str] = set()
    deduped_results = []
    for gr, sub, st in results_sorted_newest:
        s_key = (
            f"st:{st.id}"
            if st
            else (
                f"gs:{sub.google_submission_id}"
                if sub.google_submission_id
                else f"nm:{(sub.student_display_name or sub.id).strip().lower()}"
            )
        )
        if s_key in seen_student_keys:
            continue
        seen_student_keys.add(s_key)
        deduped_results.append((gr, sub, st))
    results = deduped_results

    # Bulk-load all GradingDetail rows in ONE query (zero N+1 queries, 100% SQLAlchemy-safe)
    details_by_result: dict[str, list[GradingDetail]] = {}
    res_ids = [gr.id for gr, _, _ in results]
    if res_ids:
        for d_row in db.query(GradingDetail).filter(GradingDetail.grading_result_id.in_(res_ids)).all():
            details_by_result.setdefault(d_row.grading_result_id, []).append(d_row)

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

        gr_details = details_by_result.get(gr.id, [])
        deducted_lines = [
            f"- {d.item_title} (หัก {d.deducted_points:g} คะแนน): {d.reason or 'ไม่ตรงตามเกณฑ์'}"
            for d in gr_details
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
                for d in gr_details
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
    last_rubric_name: str | None = None
    last_rubric_version: int | None = None
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
                last_rubric_version = int(rv_obj.version_number or 1)
                snap = rv_obj.snapshot_json or {}
                last_rubric_name = str(snap.get("name") or "")
                break

    classroom_link: str | None = None
    ca_obj = (
        db.query(ClassroomAssignment).filter(ClassroomAssignment.id == assignment.classroom_assignment_id).first()
        if assignment.classroom_assignment_id
        else db.query(ClassroomAssignment)
        .filter(
            ClassroomAssignment.local_assignment_id == assignment.id,
            ClassroomAssignment.owner_user_id == owner_user_id,
        )
        .first()
    )
    if ca_obj and ca_obj.alternate_link:
        classroom_link = ca_obj.alternate_link

    summary = {
        "assignment_id": assignment.id,
        "assignment_title": assignment.title,
        "classroom_alternate_link": classroom_link,
        "last_rubric_id": last_rubric_id,
        "last_rubric_name": last_rubric_name,
        "last_rubric_version": last_rubric_version,
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


def _build_classroom_gradebook_data(
    db: Session,
    owner_user_id: str,
    classroom_id: str,
) -> tuple[str, list[dict], list[dict], dict[str, list[dict]]]:
    """Aggregate all graded assignments & students for a single Google Classroom room."""
    gc = (
        db.query(GoogleClassroom)
        .filter(GoogleClassroom.id == classroom_id, GoogleClassroom.owner_user_id == owner_user_id)
        .first()
    )
    if not gc:
        raise HTTPException(status_code=404, detail="ไม่พบห้องเรียนที่ระบุ")

    room_label = gc.name or "Classroom"
    if gc.section and gc.section.strip() and gc.section.strip() not in room_label:
        room_label = f"{room_label} ({gc.section.strip()})"
    if gc.room and gc.room.strip() and gc.room.strip() not in room_label:
        room_label = f"{room_label} • ห้อง {gc.room.strip()}"

    ca_list = (
        db.query(ClassroomAssignment)
        .filter(
            ClassroomAssignment.owner_user_id == owner_user_id,
            ClassroomAssignment.google_classroom_id == gc.id,
        )
        .order_by(ClassroomAssignment.created_at.asc())
        .all()
    )
    ca_ids = [c.id for c in ca_list]
    local_ids = [c.local_assignment_id for c in ca_list if c.local_assignment_id]

    assign_q = db.query(Assignment).filter(
        Assignment.owner_user_id == owner_user_id,
        Assignment.deleted_at.is_(None),
    )
    all_assigns = assign_q.order_by(Assignment.created_at.asc()).all()
    room_assigns = [
        a for a in all_assigns
        if (a.classroom_assignment_id and a.classroom_assignment_id in ca_ids) or (a.id in local_ids)
    ]

    assignments_meta: list[dict] = []
    per_assignment_rows: dict[str, list[dict]] = {}
    students_map: dict[str, dict] = {}

    for a in room_assigns:
        report_data = _build_class_report_data(db, owner_user_id, a.id, sort_by="seat")
        a_rows = report_data["rows"]
        if not a_rows:
            continue
        a_rows_sorted = sorted(a_rows, key=lambda r: str(r.get("student_name") or ""))
        actual_max = float(a_rows_sorted[0].get("max_score") or a.max_score or 0)
        assignments_meta.append({
            "assignment_id": a.id,
            "title": a.title,
            "max_score": actual_max,
            "graded_count": len(a_rows_sorted),
            "average_score": report_data["summary"]["average_score"],
            "passed_count": report_data["summary"]["passed_count"],
        })
        per_assignment_rows[a.id] = a_rows_sorted
        for r in a_rows_sorted:
            sname = str(r.get("student_name") or "-").strip()
            skey = sname.lower()
            if skey not in students_map:
                students_map[skey] = {"student_name": sname, "scores": {}}
            students_map[skey]["scores"][a.id] = float(r.get("final_score") or 0.0)

    student_rows = sorted(students_map.values(), key=lambda x: x["student_name"])
    return room_label, assignments_meta, student_rows, per_assignment_rows


@router.get("/classrooms/summary")
def list_classroom_export_summaries(
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """List every Classroom room with its graded assignments ready for per-room Excel/CSV export."""
    classrooms = (
        db.query(GoogleClassroom)
        .filter(GoogleClassroom.owner_user_id == current_teacher.id)
        .order_by(GoogleClassroom.name.asc())
        .all()
    )
    out = []
    for gc in classrooms:
        room_label, assignments_meta, student_rows, _ = _build_classroom_gradebook_data(
            db, current_teacher.id, gc.id
        )
        if not assignments_meta:
            continue
        total_max = round(sum(float(a["max_score"]) for a in assignments_meta), 2)
        out.append({
            "classroom_id": gc.id,
            "classroom_name": room_label,
            "section": gc.section,
            "room": gc.room,
            "total_students": len(student_rows),
            "total_assignments": len(assignments_meta),
            "total_max_score": total_max,
            "assignments": assignments_meta,
        })
    return {"classrooms": out}


@router.get("/classrooms/{classroom_id}/export/excel")
def export_classroom_excel(
    classroom_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    room_label, assignments_meta, student_rows, per_assignment_rows = _build_classroom_gradebook_data(
        db, current_teacher.id, classroom_id
    )
    if not assignments_meta:
        raise HTTPException(status_code=400, detail="ยังไม่มีผลตรวจคะแนนสำหรับห้องเรียนนี้")
    content = generate_classroom_gradebook_excel(
        classroom_name=room_label,
        assignments_meta=assignments_meta,
        student_rows=student_rows,
        per_assignment_rows=per_assignment_rows,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="gradebook_{classroom_id[:8]}.xlsx"'},
    )


@router.get("/classrooms/{classroom_id}/export/csv")
def export_classroom_csv(
    classroom_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    _, assignments_meta, student_rows, _ = _build_classroom_gradebook_data(
        db, current_teacher.id, classroom_id
    )
    if not assignments_meta:
        raise HTTPException(status_code=400, detail="ยังไม่มีผลตรวจคะแนนสำหรับห้องเรียนนี้")
    content = generate_classroom_gradebook_csv(
        assignments_meta=assignments_meta,
        student_rows=student_rows,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="gradebook_{classroom_id[:8]}.csv"'},
    )
