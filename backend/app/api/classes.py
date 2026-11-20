"""Teacher Classes Management API (Multi-Tenant Isolated)."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.models.models import ClassStudent, TeacherClass, User
from backend.app.schemas.schemas import ClassCreate, ClassUpdate

router = APIRouter(prefix="/classes", tags=["Classes"])


@router.get("")
def list_classes(
    search: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = db.query(TeacherClass).filter(
        TeacherClass.owner_user_id == current_teacher.id,
        TeacherClass.deleted_at.is_(None),
    )
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            (TeacherClass.name.ilike(like))
            | (TeacherClass.subject_code.ilike(like))
            | (TeacherClass.subject_name.ilike(like))
        )
    classes = q.order_by(TeacherClass.created_at.desc()).all()

    result = []
    for c in classes:
        student_count = (
            db.query(func.count(ClassStudent.id))
            .filter(ClassStudent.class_id == c.id, ClassStudent.owner_user_id == current_teacher.id)
            .scalar()
            or 0
        )
        result.append({
            "id": c.id,
            "name": c.name,
            "subject_code": c.subject_code,
            "subject_name": c.subject_name,
            "semester": c.semester,
            "academic_year": c.academic_year,
            "room": c.room,
            "description": c.description,
            "color_tag": c.color_tag,
            "is_archived": c.is_archived,
            "student_count": student_count,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_class(
    payload: ClassCreate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    cls = TeacherClass(
        owner_user_id=current_teacher.id,
        name=payload.name.strip(),
        subject_code=payload.subject_code,
        subject_name=payload.subject_name,
        semester=payload.semester,
        academic_year=payload.academic_year,
        room=payload.room,
        description=payload.description,
        color_tag=payload.color_tag,
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)
    return {
        "id": cls.id,
        "name": cls.name,
        "subject_code": cls.subject_code,
        "subject_name": cls.subject_name,
        "semester": cls.semester,
        "academic_year": cls.academic_year,
        "room": cls.room,
        "color_tag": cls.color_tag,
        "student_count": 0,
    }


@router.put("/{class_id}")
def update_class(
    class_id: str,
    payload: ClassUpdate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    cls = (
        db.query(TeacherClass)
        .filter(
            TeacherClass.id == class_id,
            TeacherClass.owner_user_id == current_teacher.id,
            TeacherClass.deleted_at.is_(None),
        )
        .first()
    )
    if not cls:
        raise HTTPException(status_code=404, detail="ไม่พบชั้นเรียนนี้")

    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(cls, k, v)
    db.commit()
    db.refresh(cls)
    return {"id": cls.id, "name": cls.name, "message": "อัปเดตข้อมูลชั้นเรียนเรียบร้อยแล้ว"}


@router.delete("/{class_id}")
def delete_class(
    class_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    cls = (
        db.query(TeacherClass)
        .filter(
            TeacherClass.id == class_id,
            TeacherClass.owner_user_id == current_teacher.id,
            TeacherClass.deleted_at.is_(None),
        )
        .first()
    )
    if not cls:
        raise HTTPException(status_code=404, detail="ไม่พบชั้นเรียนนี้")
    cls.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "ลบชั้นเรียนเรียบร้อยแล้ว"}
