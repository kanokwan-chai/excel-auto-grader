"""Assignments Management API: CRUD, Draft/Duplicate, Reference Excel File Upload & Inspection."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.storage import storage_service
from backend.app.models.models import (
    Assignment,
    GradingResult,
    ReferenceFile,
    Submission,
    TeacherClass,
    User,
)
from backend.app.schemas.schemas import AssignmentCreate, AssignmentUpdate
from excel_engine.exceptions import ExcelEngineError
from excel_engine.readers import extract_workbook_metadata, validate_excel_file

router = APIRouter(prefix="/assignments", tags=["Assignments"])
settings = get_settings()


@router.get("")
def list_assignments(
    class_id: str | None = None,
    status_filter: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = db.query(Assignment).filter(
        Assignment.owner_user_id == current_teacher.id,
        Assignment.deleted_at.is_(None),
    )
    if class_id:
        q = q.filter(Assignment.class_id == class_id)
    if status_filter:
        q = q.filter(Assignment.status == status_filter)

    items = q.order_by(Assignment.created_at.desc()).all()
    out = []
    for a in items:
        sub_count = db.query(func.count(Submission.id)).filter(
            Submission.owner_user_id == current_teacher.id, Submission.assignment_id == a.id
        ).scalar() or 0
        graded_count = db.query(func.count(GradingResult.id)).filter(
            GradingResult.owner_user_id == current_teacher.id, GradingResult.assignment_id == a.id
        ).scalar() or 0
        ref = (
            db.query(ReferenceFile)
            .filter(ReferenceFile.assignment_id == a.id, ReferenceFile.is_active.is_(True))
            .order_by(ReferenceFile.created_at.desc())
            .first()
        )
        cls_name = None
        if a.class_id:
            cls = db.query(TeacherClass).filter(TeacherClass.id == a.class_id).first()
            cls_name = cls.name if cls else None

        out.append({
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "subject_name": a.subject_name,
            "class_id": a.class_id,
            "class_name": cls_name,
            "start_at": a.start_at.isoformat() if a.start_at else None,
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "max_score": a.max_score,
            "pass_score": a.pass_score,
            "max_files_allowed": a.max_files_allowed,
            "allowed_extensions": a.allowed_extensions,
            "status": a.status,
            "submission_count": sub_count,
            "graded_count": graded_count,
            "reference_file": (
                {
                    "id": ref.id,
                    "filename": ref.original_filename,
                    "has_macros": ref.has_macros,
                    "sheet_metadata": ref.sheet_metadata,
                }
                if ref
                else None
            ),
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    if payload.class_id:
        cls = (
            db.query(TeacherClass)
            .filter(TeacherClass.id == payload.class_id, TeacherClass.owner_user_id == current_teacher.id)
            .first()
        )
        if not cls:
            raise HTTPException(status_code=404, detail="ไม่พบชั้นเรียนที่เลือก")

    assignment = Assignment(
        owner_user_id=current_teacher.id,
        class_id=payload.class_id,
        title=payload.title.strip(),
        description=payload.description,
        subject_name=payload.subject_name,
        start_at=payload.start_at,
        due_at=payload.due_at,
        max_score=payload.max_score,
        pass_score=payload.pass_score,
        max_files_allowed=payload.max_files_allowed,
        allowed_extensions=payload.allowed_extensions,
        status=payload.status,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id, "title": assignment.title, "status": assignment.status}


@router.put("/{assignment_id}")
def update_assignment(
    assignment_id: str,
    payload: AssignmentUpdate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    a = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id,
            Assignment.owner_user_id == current_teacher.id,
            Assignment.deleted_at.is_(None),
        )
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="ไม่พบงานที่ระบุ")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(a, k, v)
    db.commit()
    return {"id": a.id, "message": "อัปเดตงานเรียบร้อยแล้ว"}


@router.post("/{assignment_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_assignment(
    assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    orig = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id,
            Assignment.owner_user_id == current_teacher.id,
            Assignment.deleted_at.is_(None),
        )
        .first()
    )
    if not orig:
        raise HTTPException(status_code=404, detail="ไม่พบงานต้นฉบับ")
    copy_a = Assignment(
        owner_user_id=current_teacher.id,
        class_id=orig.class_id,
        title=f"{orig.title} (สำเนา)",
        description=orig.description,
        subject_name=orig.subject_name,
        max_score=orig.max_score,
        pass_score=orig.pass_score,
        max_files_allowed=orig.max_files_allowed,
        allowed_extensions=list(orig.allowed_extensions or [".xlsx", ".xls", ".xlsm"]),
        status="draft",
    )
    db.add(copy_a)
    db.commit()
    db.refresh(copy_a)
    return {"id": copy_a.id, "title": copy_a.title}


@router.post("/{assignment_id}/reference-file")
async def upload_reference_file(
    assignment_id: str,
    file: UploadFile = File(...),
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    a = (
        db.query(Assignment)
        .filter(
            Assignment.id == assignment_id,
            Assignment.owner_user_id == current_teacher.id,
            Assignment.deleted_at.is_(None),
        )
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="ไม่พบงานที่ระบุ")

    content = await file.read()
    filename = file.filename or "reference.xlsx"
    storage_path = storage_service.save_bytes(
        user_id=current_teacher.id,
        folder="references",
        filename=filename,
        content=content,
        content_type=file.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    local_path = storage_service.get_local_path(storage_path, current_teacher.id)

    try:
        sec_report = validate_excel_file(local_path, max_file_size_mb=settings.EXCEL_MAX_FILE_SIZE_MB)
        metadata = extract_workbook_metadata(local_path)
    except ExcelEngineError as exc:
        storage_service.delete_file(storage_path, current_teacher.id)
        raise HTTPException(status_code=400, detail=exc.message)

    # Mark previous references inactive
    db.query(ReferenceFile).filter(
        ReferenceFile.assignment_id == a.id, ReferenceFile.owner_user_id == current_teacher.id
    ).update({"is_active": False})

    ref = ReferenceFile(
        owner_user_id=current_teacher.id,
        assignment_id=a.id,
        original_filename=filename,
        storage_path=storage_path,
        file_size_bytes=sec_report.file_size_bytes,
        sha256_hash=sec_report.sha256_hash,
        sheet_metadata=metadata,
        has_macros=sec_report.has_macros,
        is_active=True,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)

    return {
        "id": ref.id,
        "filename": ref.original_filename,
        "has_macros": ref.has_macros,
        "warnings": sec_report.warnings,
        "sheet_metadata": metadata,
    }


@router.delete("/{assignment_id}")
def delete_assignment(
    assignment_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    a = (
        db.query(Assignment)
        .filter(Assignment.id == assignment_id, Assignment.owner_user_id == current_teacher.id)
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="ไม่พบงานที่ระบุ")
    a.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "ลบงานเรียบร้อยแล้ว"}
