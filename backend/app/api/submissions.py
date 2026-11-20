"""Student Submissions & Multi-File Excel Upload API (Multi-Tenant Isolated)."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.storage import storage_service
from backend.app.models.models import Assignment, Student, Submission, SubmissionFile, User
from excel_engine.exceptions import ExcelEngineError
from excel_engine.readers import validate_excel_file

router = APIRouter(prefix="/submissions", tags=["Submissions"])
settings = get_settings()


def _match_student_from_filename(
    db: Session,
    owner_user_id: str,
    filename: str,
) -> Student | None:
    """Try to match filename against teacher's students by student_code or first_name."""
    students = (
        db.query(Student)
        .filter(Student.owner_user_id == owner_user_id, Student.deleted_at.is_(None))
        .all()
    )
    stem = os.path.splitext(filename)[0].lower()
    for s in students:
        if s.student_code and s.student_code.lower() in stem:
            return s
    for s in students:
        if s.first_name and s.first_name.lower() in stem:
            return s
    return None


@router.get("")
def list_submissions(
    assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(Submission)
        .filter(
            Submission.owner_user_id == current_teacher.id,
            Submission.assignment_id == assignment_id,
        )
        .order_by(Submission.created_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "assignment_id": s.assignment_id,
            "student_id": s.student_id,
            "student_display_name": s.student_display_name,
            "student_code_matched": s.student_code_matched,
            "source": s.source,
            "submission_status": s.submission_status,
            "is_late": s.is_late,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "files": [
                {
                    "id": f.id,
                    "original_filename": f.original_filename,
                    "file_extension": f.file_extension,
                    "file_size_bytes": f.file_size_bytes,
                    "is_primary": f.is_primary,
                    "is_duplicate": f.is_duplicate,
                    "has_macros": f.has_macros,
                    "security_status": f.security_status,
                    "security_note": f.security_note,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in sorted(s.files, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            ],
        }
        for s in subs
    ]


@router.post("/upload")
async def upload_student_files(
    assignment_id: str = Form(...),
    student_id: str | None = Form(default=None),
    files: list[UploadFile] = File(...),
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Upload one or many Excel files simultaneously, detect duplicates, validate security, and match students."""
    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id,
            Assignment.owner_user_id == current_teacher.id,
            Assignment.deleted_at.is_(None),
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="ไม่พบงานที่ระบุ")

    # Existing hashes for duplicate detection in this assignment
    existing_hashes = {
        row[0]
        for row in db.query(SubmissionFile.sha256_hash)
        .join(Submission, SubmissionFile.submission_id == Submission.id)
        .filter(
            Submission.owner_user_id == current_teacher.id,
            Submission.assignment_id == assignment.id,
        )
        .all()
    }

    uploaded_summary = []
    for f in files:
        filename = f.filename or "submission.xlsx"
        ext = os.path.splitext(filename)[1].lower()
        content = await f.read()

        matched_student: Student | None = None
        if student_id:
            matched_student = (
                db.query(Student)
                .filter(Student.id == student_id, Student.owner_user_id == current_teacher.id)
                .first()
            )
        if not matched_student:
            matched_student = _match_student_from_filename(db, current_teacher.id, filename)

        storage_path = storage_service.save_bytes(
            user_id=current_teacher.id,
            folder="submissions",
            filename=filename,
            content=content,
            content_type=f.content_type or "application/octet-stream",
        )
        local_path = storage_service.get_local_path(storage_path, current_teacher.id)

        sec_status = "safe"
        sec_note = None
        has_macros = False
        sha256_hash = ""
        file_size = len(content)

        try:
            report = validate_excel_file(
                local_path,
                max_file_size_mb=settings.EXCEL_MAX_FILE_SIZE_MB,
                allowed_extensions=set(assignment.allowed_extensions or [".xlsx", ".xls", ".xlsm"]),
            )
            sha256_hash = report.sha256_hash
            has_macros = report.has_macros
            file_size = report.file_size_bytes
            if report.warnings:
                sec_note = " | ".join(report.warnings)
        except ExcelEngineError as exc:
            sec_status = "corrupted"
            sec_note = exc.message
            import hashlib
            sha256_hash = hashlib.sha256(content).hexdigest()

        is_dup = sha256_hash in existing_hashes
        existing_hashes.add(sha256_hash)

        # Reuse submission if same student already uploaded for this assignment (multi-file support)
        submission: Submission | None = None
        if matched_student:
            submission = (
                db.query(Submission)
                .filter(
                    Submission.owner_user_id == current_teacher.id,
                    Submission.assignment_id == assignment.id,
                    Submission.student_id == matched_student.id,
                )
                .first()
            )

        if not submission:
            display_name = (
                f"{matched_student.first_name} {matched_student.last_name}"
                if matched_student
                else re.sub(r"\.[^.]+$", "", filename)
            )
            submission = Submission(
                owner_user_id=current_teacher.id,
                assignment_id=assignment.id,
                student_id=matched_student.id if matched_student else None,
                source="manual_upload",
                student_display_name=display_name,
                student_code_matched=matched_student.student_code if matched_student else None,
                submission_status="submitted" if sec_status == "safe" else "error",
                submitted_at=datetime.now(timezone.utc),
            )
            db.add(submission)
            db.flush()

        # Always make the latest valid uploaded file the primary file for grading
        if sec_status == "safe":
            db.query(SubmissionFile).filter(SubmissionFile.submission_id == submission.id).update(
                {"is_primary": False}
            )
            submission.submitted_at = datetime.now(timezone.utc)
            is_new_primary = True
        else:
            has_existing_files = (
                db.query(SubmissionFile)
                .filter(SubmissionFile.submission_id == submission.id)
                .count()
                > 0
            )
            is_new_primary = not has_existing_files

        sub_file = SubmissionFile(
            owner_user_id=current_teacher.id,
            submission_id=submission.id,
            original_filename=filename,
            storage_path=storage_path,
            file_extension=ext or ".xlsx",
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            is_primary=is_new_primary,
            is_duplicate=is_dup,
            has_macros=has_macros,
            security_status=sec_status,
            security_note=sec_note,
        )
        db.add(sub_file)
        db.flush()

        uploaded_summary.append({
            "submission_id": submission.id,
            "file_id": sub_file.id,
            "filename": filename,
            "matched_student": submission.student_display_name,
            "student_code": submission.student_code_matched,
            "is_duplicate": is_dup,
            "is_primary": sub_file.is_primary,
            "security_status": sec_status,
            "security_note": sec_note,
        })

    db.commit()
    return {"uploaded_count": len(uploaded_summary), "files": uploaded_summary}


@router.put("/{submission_id}/primary-file/{file_id}")
def set_primary_submission_file(
    submission_id: str,
    file_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    sub = (
        db.query(Submission)
        .filter(Submission.id == submission_id, Submission.owner_user_id == current_teacher.id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="ไม่พบรายการส่งงาน")

    target = (
        db.query(SubmissionFile)
        .filter(
            SubmissionFile.id == file_id,
            SubmissionFile.submission_id == sub.id,
            SubmissionFile.owner_user_id == current_teacher.id,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ที่ต้องการเลือก")

    db.query(SubmissionFile).filter(SubmissionFile.submission_id == sub.id).update({"is_primary": False})
    target.is_primary = True
    db.commit()
    return {"message": f"เลือกไฟล์ '{target.original_filename}' เป็นไฟล์หลักสำหรับตรวจแล้ว"}
