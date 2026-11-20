"""Google Classroom Selector, Assignment Selector, Submission Manager & 8-Step Wizard API.

Strict Multi-Account & Multi-Teacher Isolation:
- Every classroom references (google_connection_id, google_course_id).
- Classrooms from one Google Account never mix with another account.
- Calls REAL Google Classroom API & Google Drive API (never mocks in production).
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.storage import storage_service
from backend.app.integrations.google_classroom import (
    GoogleAPIError,
    download_drive_excel_file,
    fetch_classroom_courses,
    fetch_course_students,
    fetch_course_work,
    fetch_drive_file_metadata,
    fetch_student_submissions,
    is_supported_excel_attachment,
)
from backend.app.models.models import (
    Assignment,
    ClassroomAssignment,
    ClassroomCourseMembership,
    ClassroomSubmission,
    GoogleClassroom,
    GoogleConnection,
    GradingJob,
    GradingRubric,
    Submission,
    SubmissionFile,
    User,
)
from backend.app.schemas.schemas import ClassroomGradeWizardRequest, SelectClassroomFileRequest
from backend.app.services.grading_service import get_or_create_latest_rubric_version, grade_single_submission
from excel_engine.exceptions import ExcelEngineError
from excel_engine.readers import validate_excel_file

router = APIRouter(prefix="/classroom", tags=["Google Classroom"])
settings = get_settings()


@router.get("/courses")
def list_saved_classrooms(
    google_connection_id: str | None = None,
    search: str | None = None,
    sort_by: str = "name",
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = (
        db.query(GoogleClassroom, GoogleConnection)
        .join(GoogleConnection, GoogleClassroom.google_connection_id == GoogleConnection.id)
        .filter(
            GoogleClassroom.owner_user_id == current_teacher.id,
            GoogleConnection.deleted_at.is_(None),
        )
    )
    if google_connection_id:
        q = q.filter(GoogleClassroom.google_connection_id == google_connection_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter((GoogleClassroom.name.ilike(like)) | (GoogleClassroom.section.ilike(like)))

    if sort_by == "recent":
        q = q.order_by(GoogleClassroom.last_synced_at.desc().nullslast())
    else:
        q = q.order_by(GoogleClassroom.name.asc())

    rows = q.all()
    return [
        {
            "id": gc.id,
            "google_connection_id": gc.google_connection_id,
            "google_account_email": conn.google_email,
            "google_account_status": conn.status,
            "google_course_id": gc.google_course_id,
            "name": gc.name,
            "section": gc.section,
            "description_heading": gc.description_heading,
            "room": gc.room,
            "course_state": gc.course_state,
            "student_count": gc.student_count,
            "alternate_link": gc.alternate_link,
            "last_synced_at": gc.last_synced_at.isoformat() if gc.last_synced_at else None,
        }
        for gc, conn in rows
    ]


@router.post("/accounts/{connection_id}/sync-courses")
async def sync_google_courses(
    connection_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Fetch live courses from Google Classroom API for a specific connected Google Account."""
    conn = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.id == connection_id,
            GoogleConnection.owner_user_id == current_teacher.id,
            GoogleConnection.deleted_at.is_(None),
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="ไม่พบบัญชี Google ที่เลือก")

    try:
        courses = await fetch_classroom_courses(db, conn)
    except GoogleAPIError as exc:
        conn.last_error = exc.message
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    now = datetime.now(timezone.utc)
    synced = 0
    for c in courses:
        course_id = str(c["id"])
        existing = (
            db.query(GoogleClassroom)
            .filter(
                GoogleClassroom.google_connection_id == conn.id,
                GoogleClassroom.google_course_id == course_id,
            )
            .first()
        )
        if existing:
            existing.name = c.get("name", existing.name)
            existing.section = c.get("section")
            existing.description_heading = c.get("descriptionHeading")
            existing.room = c.get("room")
            existing.course_state = c.get("courseState", "ACTIVE")
            existing.alternate_link = c.get("alternateLink")
            existing.last_synced_at = now
        else:
            db.add(
                GoogleClassroom(
                    owner_user_id=current_teacher.id,
                    google_connection_id=conn.id,
                    google_course_id=course_id,
                    name=c.get("name", "Untitled Course"),
                    section=c.get("section"),
                    description_heading=c.get("descriptionHeading"),
                    room=c.get("room"),
                    course_state=c.get("courseState", "ACTIVE"),
                    alternate_link=c.get("alternateLink"),
                    last_synced_at=now,
                )
            )
        synced += 1

    conn.last_synced_at = now
    conn.last_error = None
    db.commit()
    return {"synced_courses": synced, "google_email": conn.google_email}


@router.post("/courses/{classroom_id}/sync-assignments")
async def sync_course_assignments(
    classroom_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Fetch real coursework & student roster from Google Classroom API."""
    gc = (
        db.query(GoogleClassroom)
        .filter(GoogleClassroom.id == classroom_id, GoogleClassroom.owner_user_id == current_teacher.id)
        .first()
    )
    if not gc:
        raise HTTPException(status_code=404, detail="ไม่พบห้องเรียน Google Classroom นี้")
    conn = db.query(GoogleConnection).filter(GoogleConnection.id == gc.google_connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="ไม่พบบัญชี Google เจ้าของห้องเรียน")

    try:
        students = await fetch_course_students(db, conn, gc.google_course_id)
        coursework = await fetch_course_work(db, conn, gc.google_course_id)
    except GoogleAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    now = datetime.now(timezone.utc)
    gc.student_count = len(students)

    for st in students:
        profile = st.get("profile", {})
        uid = str(st.get("userId") or profile.get("id", ""))
        if not uid:
            continue
        full_name = profile.get("name", {}).get("fullName") or "Student"
        member = (
            db.query(ClassroomCourseMembership)
            .filter(
                ClassroomCourseMembership.google_classroom_id == gc.id,
                ClassroomCourseMembership.google_user_id == uid,
            )
            .first()
        )
        if member:
            member.full_name = full_name
            member.email = profile.get("emailAddress")
            member.photo_url = profile.get("photoUrl")
        else:
            db.add(
                ClassroomCourseMembership(
                    owner_user_id=current_teacher.id,
                    google_classroom_id=gc.id,
                    google_user_id=uid,
                    full_name=full_name,
                    email=profile.get("emailAddress"),
                    photo_url=profile.get("photoUrl"),
                    role="STUDENT",
                )
            )

    synced_cw = 0
    for cw in coursework:
        cw_id = str(cw["id"])
        due_dt = None
        if cw.get("dueDate"):
            dd = cw["dueDate"]
            dt_t = cw.get("dueTime") or {}
            due_dt = datetime(
                dd.get("year", 2026),
                dd.get("month", 1),
                dd.get("day", 1),
                dt_t.get("hours", 23),
                dt_t.get("minutes", 59),
                tzinfo=timezone.utc,
            )

        existing = (
            db.query(ClassroomAssignment)
            .filter(
                ClassroomAssignment.google_connection_id == conn.id,
                ClassroomAssignment.google_assignment_id == cw_id,
            )
            .first()
        )
        if existing:
            existing.title = cw.get("title", existing.title)
            existing.description = cw.get("description")
            existing.state = cw.get("state", "PUBLISHED")
            existing.max_points = cw.get("maxPoints")
            existing.due_at = due_dt
            existing.alternate_link = cw.get("alternateLink")
            existing.last_synced_at = now
        else:
            db.add(
                ClassroomAssignment(
                    owner_user_id=current_teacher.id,
                    google_connection_id=conn.id,
                    google_classroom_id=gc.id,
                    google_assignment_id=cw_id,
                    title=cw.get("title", "Untitled Assignment"),
                    description=cw.get("description"),
                    state=cw.get("state", "PUBLISHED"),
                    max_points=cw.get("maxPoints"),
                    due_at=due_dt,
                    alternate_link=cw.get("alternateLink"),
                    last_synced_at=now,
                )
            )
        synced_cw += 1

    db.commit()
    return {"synced_students": len(students), "synced_assignments": synced_cw}


@router.get("/courses/{classroom_id}/assignments")
def list_classroom_assignments(
    classroom_id: str,
    search: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = db.query(ClassroomAssignment).filter(
        ClassroomAssignment.owner_user_id == current_teacher.id,
        ClassroomAssignment.google_classroom_id == classroom_id,
    )
    if search:
        q = q.filter(ClassroomAssignment.title.ilike(f"%{search.strip()}%"))
    items = q.order_by(ClassroomAssignment.due_at.desc().nullslast()).all()
    return [
        {
            "id": a.id,
            "google_assignment_id": a.google_assignment_id,
            "title": a.title,
            "description": a.description,
            "state": a.state,
            "max_points": a.max_points,
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "turned_in_count": a.turned_in_count,
            "missing_count": a.missing_count,
            "local_assignment_id": a.local_assignment_id,
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        }
        for a in items
    ]


@router.post("/assignments/{classroom_assignment_id}/sync-submissions")
async def sync_classroom_submissions(
    classroom_assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Pull live student submissions & Drive attachments from Google Classroom API."""
    ca = (
        db.query(ClassroomAssignment)
        .filter(
            ClassroomAssignment.id == classroom_assignment_id,
            ClassroomAssignment.owner_user_id == current_teacher.id,
        )
        .first()
    )
    if not ca:
        raise HTTPException(status_code=404, detail="ไม่พบงานใน Google Classroom")

    gc = db.query(GoogleClassroom).filter(GoogleClassroom.id == ca.google_classroom_id).first()
    conn = db.query(GoogleConnection).filter(GoogleConnection.id == ca.google_connection_id).first()
    if not gc or not conn:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลห้องเรียนหรือบัญชี Google")

    try:
        raw_subs = await fetch_student_submissions(db, conn, gc.google_course_id, ca.google_assignment_id)
    except GoogleAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    roster_map = {
        m.google_user_id: m
        for m in db.query(ClassroomCourseMembership)
        .filter(ClassroomCourseMembership.google_classroom_id == gc.id)
        .all()
    }

    now = datetime.now(timezone.utc)
    turned_in = 0
    missing = 0

    for sub in raw_subs:
        sub_id = str(sub["id"])
        uid = str(sub.get("userId", ""))
        state = sub.get("state", "CREATED")
        if state in ("TURNED_IN", "RETURNED"):
            turned_in += 1
        else:
            missing += 1

        member = roster_map.get(uid)
        student_name = member.full_name if member else f"Student ({uid[:8]})"
        student_email = member.email if member else None

        # Parse real submission timestamp from Google Classroom updateTime / submissionHistory
        sub_time_dt = None
        raw_ts = sub.get("updateTime") or sub.get("creationTime")
        for hist in reversed(sub.get("submissionHistory", []) or []):
            st_hist = hist.get("stateHistory") or {}
            if st_hist.get("state") in ("TURNED_IN", "RETURNED") and st_hist.get("stateTimestamp"):
                raw_ts = st_hist["stateTimestamp"]
                break
        if raw_ts:
            try:
                sub_time_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except ValueError:
                sub_time_dt = None

        attachments = []
        excel_candidates: list[tuple[str, str]] = []  # (modified_time_iso, drive_file_id)
        for att in sub.get("assignmentSubmission", {}).get("attachments", []):
            df = att.get("driveFile")
            if not df:
                continue
            file_id = df.get("id")
            title = df.get("title", "file")
            mime = df.get("mimeType")
            is_excel = is_supported_excel_attachment(title, mime)

            mod_time = ""
            size_bytes = None
            if is_excel and file_id:
                meta = await fetch_drive_file_metadata(db, conn, file_id)
                if meta:
                    mod_time = str(meta.get("modifiedTime") or meta.get("createdTime") or "")
                    if meta.get("size"):
                        size_bytes = int(meta["size"])
                    if not mime and meta.get("mimeType"):
                        mime = meta["mimeType"]
                excel_candidates.append((mod_time, file_id))

            attachments.append({
                "drive_file_id": file_id,
                "title": title,
                "alternate_link": df.get("alternateLink"),
                "mime_type": mime,
                "modified_time": mod_time or None,
                "size_bytes": size_bytes,
                "is_supported_excel": is_excel,
            })

        # Pick the Excel file with the LATEST Drive modifiedTime (or last attached if timestamps unavailable)
        selected_excel_id = None
        if excel_candidates:
            # Sort by ISO modified_time ascending so [-1] is the newest
            if any(ts for ts, _ in excel_candidates):
                excel_candidates.sort(key=lambda x: x[0])
            selected_excel_id = excel_candidates[-1][1]

        existing = (
            db.query(ClassroomSubmission)
            .filter(
                ClassroomSubmission.google_connection_id == conn.id,
                ClassroomSubmission.google_submission_id == sub_id,
            )
            .first()
        )
        if existing:
            existing.state = state
            existing.late = bool(sub.get("late", False))
            if sub_time_dt:
                existing.submitted_at = sub_time_dt
            existing.attachments = attachments
            existing.has_supported_excel = selected_excel_id is not None
            if selected_excel_id:
                existing.selected_drive_file_id = selected_excel_id
            existing.last_synced_at = now
        else:
            db.add(
                ClassroomSubmission(
                    owner_user_id=current_teacher.id,
                    google_connection_id=conn.id,
                    classroom_assignment_id=ca.id,
                    google_submission_id=sub_id,
                    google_user_id=uid,
                    student_name=student_name,
                    student_email=student_email,
                    state=state,
                    late=bool(sub.get("late", False)),
                    submitted_at=sub_time_dt,
                    attachments=attachments,
                    selected_drive_file_id=selected_excel_id,
                    has_supported_excel=selected_excel_id is not None,
                    last_synced_at=now,
                )
            )

    ca.turned_in_count = turned_in
    ca.missing_count = missing
    db.commit()
    return {"total": len(raw_subs), "turned_in": turned_in, "missing": missing}


@router.get("/assignments/{classroom_assignment_id}/submissions")
def list_classroom_submissions(
    classroom_assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(ClassroomSubmission)
        .filter(
            ClassroomSubmission.owner_user_id == current_teacher.id,
            ClassroomSubmission.classroom_assignment_id == classroom_assignment_id,
        )
        .order_by(ClassroomSubmission.student_name.asc())
        .all()
    )
    return [
        {
            "id": s.id,
            "google_submission_id": s.google_submission_id,
            "student_name": s.student_name,
            "student_email": s.student_email,
            "state": s.state,
            "late": s.late,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "attachments": s.attachments,
            "selected_drive_file_id": s.selected_drive_file_id,
            "has_supported_excel": s.has_supported_excel,
            "ui_status": (
                "not_submitted"
                if s.state not in ("TURNED_IN", "RETURNED")
                else ("ready_for_grading" if s.has_supported_excel else "no_excel_file")
            ),
        }
        for s in subs
    ]


@router.put("/submissions/{classroom_submission_id}/select-file")
def select_primary_classroom_file(
    classroom_submission_id: str,
    payload: SelectClassroomFileRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    sub = (
        db.query(ClassroomSubmission)
        .filter(
            ClassroomSubmission.id == classroom_submission_id,
            ClassroomSubmission.owner_user_id == current_teacher.id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลการส่งงาน")
    sub.selected_drive_file_id = payload.drive_file_id
    db.commit()
    return {"message": "เลือกไฟล์หลักจาก Google Drive เรียบร้อยแล้ว"}


@router.post("/wizard/grade")
async def run_classroom_wizard_grading(
    payload: ClassroomGradeWizardRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Step 7 of Google Classroom Wizard: Download selected Excel files from Drive and grade automatically."""
    conn = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.id == payload.google_connection_id,
            GoogleConnection.owner_user_id == current_teacher.id,
        )
        .first()
    )
    ca = (
        db.query(ClassroomAssignment)
        .filter(
            ClassroomAssignment.id == payload.classroom_assignment_id,
            ClassroomAssignment.owner_user_id == current_teacher.id,
        )
        .first()
    )
    rubric = (
        db.query(GradingRubric)
        .filter(GradingRubric.id == payload.rubric_id, GradingRubric.owner_user_id == current_teacher.id)
        .first()
    )
    if not conn or not ca or not rubric:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลบัญชี Google, งาน หรือเกณฑ์การตรวจ")

    # Ensure linked local Assignment exists
    local_assignment = (
        db.query(Assignment).filter(Assignment.id == ca.local_assignment_id).first()
        if ca.local_assignment_id
        else None
    )
    if not local_assignment:
        local_assignment = Assignment(
            owner_user_id=current_teacher.id,
            classroom_assignment_id=ca.id,
            title=ca.title,
            description=ca.description,
            max_score=float(ca.max_points or rubric.total_points),
            status="grading",
        )
        db.add(local_assignment)
        db.flush()
        ca.local_assignment_id = local_assignment.id

    rubric_ver = get_or_create_latest_rubric_version(db, current_teacher.id, rubric)

    sub_q = db.query(ClassroomSubmission).filter(
        ClassroomSubmission.owner_user_id == current_teacher.id,
        ClassroomSubmission.classroom_assignment_id == ca.id,
        ClassroomSubmission.has_supported_excel.is_(True),
    )
    if payload.classroom_submission_ids:
        sub_q = sub_q.filter(ClassroomSubmission.id.in_(payload.classroom_submission_ids))
    c_subs = sub_q.all()

    job = GradingJob(
        owner_user_id=current_teacher.id,
        assignment_id=local_assignment.id,
        rubric_version_id=rubric_ver.id,
        status="processing",
        total_files=len(c_subs),
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()

    graded_results = []
    failed = 0
    for cs in c_subs:
        if not cs.selected_drive_file_id:
            continue
        chosen_att = next(
            (a for a in (cs.attachments or []) if a.get("drive_file_id") == cs.selected_drive_file_id),
            None,
        )
        try:
            content, ext = await download_drive_excel_file(
                db,
                conn,
                cs.selected_drive_file_id,
                mime_type=chosen_att.get("mime_type") if chosen_att else None,
            )
        except GoogleAPIError:
            failed += 1
            continue

        filename = (chosen_att.get("title") if chosen_att else None) or f"{cs.student_name}{ext}"
        if not filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
            filename += ".xlsx"

        storage_path = storage_service.save_bytes(
            user_id=current_teacher.id,
            folder="submissions",
            filename=filename,
            content=content,
        )

        local_sub = (
            db.query(Submission).filter(Submission.id == cs.local_submission_id).first()
            if cs.local_submission_id
            else None
        )
        if not local_sub:
            local_sub = Submission(
                owner_user_id=current_teacher.id,
                assignment_id=local_assignment.id,
                source="google_classroom",
                student_display_name=cs.student_name,
                submission_status="turned_in",
                google_submission_id=cs.google_submission_id,
                is_late=cs.late,
                submitted_at=cs.submitted_at or datetime.now(timezone.utc),
            )
            db.add(local_sub)
            db.flush()
            cs.local_submission_id = local_sub.id

        db.query(SubmissionFile).filter(SubmissionFile.submission_id == local_sub.id).update({"is_primary": False})
        sf = SubmissionFile(
            owner_user_id=current_teacher.id,
            submission_id=local_sub.id,
            original_filename=filename,
            storage_path=storage_path,
            file_extension=os.path.splitext(filename)[1].lower() or ".xlsx",
            file_size_bytes=len(content),
            sha256_hash=hashlib.sha256(content).hexdigest(),
            google_drive_file_id=cs.selected_drive_file_id,
            is_primary=True,
        )
        db.add(sf)
        db.flush()

        res = grade_single_submission(
            db,
            owner_user_id=current_teacher.id,
            assignment=local_assignment,
            submission=local_sub,
            rubric_version=rubric_ver,
            grading_job=job,
        )
        graded_results.append(res.id)
        if res.status == "error":
            failed += 1

    job.processed_files = len(graded_results)
    job.failed_files = failed
    job.status = "completed" if failed == 0 else "partial_failed"
    job.completed_at = datetime.now(timezone.utc)
    local_assignment.status = "completed"
    db.commit()

    return {
        "job_id": job.id,
        "assignment_id": local_assignment.id,
        "graded_count": len(graded_results),
        "failed_count": failed,
        "result_ids": graded_results,
    }
