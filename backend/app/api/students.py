"""Students Management API: CRUD, CSV/Excel Roster Import, Class Transfer, Score History."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.models.models import Assignment, ClassStudent, GradingResult, Student, TeacherClass, User
from backend.app.schemas.schemas import StudentCreate, StudentTransferRequest, StudentUpdate

router = APIRouter(prefix="/students", tags=["Students"])


@router.get("")
def list_students(
    class_id: str | None = None,
    search: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    q = db.query(Student).filter(
        Student.owner_user_id == current_teacher.id,
        Student.deleted_at.is_(None),
    )
    if class_id:
        q = q.join(ClassStudent, ClassStudent.student_id == Student.id).filter(
            ClassStudent.class_id == class_id,
            ClassStudent.owner_user_id == current_teacher.id,
        )
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            (Student.student_code.ilike(like))
            | (Student.first_name.ilike(like))
            | (Student.last_name.ilike(like))
            | (Student.room.ilike(like))
        )
    students = q.order_by(Student.seat_number.asc().nullslast(), Student.student_code.asc()).all()

    out = []
    for s in students:
        enrollments = (
            db.query(TeacherClass.id, TeacherClass.name)
            .join(ClassStudent, ClassStudent.class_id == TeacherClass.id)
            .filter(ClassStudent.student_id == s.id, TeacherClass.deleted_at.is_(None))
            .all()
        )
        out.append({
            "id": s.id,
            "student_code": s.student_code,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "full_name": f"{s.first_name} {s.last_name}",
            "room": s.room,
            "seat_number": s.seat_number,
            "email": s.email,
            "notes": s.notes,
            "classes": [{"id": cid, "name": cname} for cid, cname in enrollments],
        })
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    dup = (
        db.query(Student)
        .filter(
            Student.owner_user_id == current_teacher.id,
            Student.student_code == payload.student_code.strip(),
            Student.deleted_at.is_(None),
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"รหัสนักเรียน '{payload.student_code}' มีอยู่ในระบบแล้ว")

    student = Student(
        owner_user_id=current_teacher.id,
        student_code=payload.student_code.strip(),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        room=payload.room,
        seat_number=payload.seat_number,
        email=payload.email,
        notes=payload.notes,
    )
    db.add(student)
    db.flush()

    if payload.class_id:
        cls = (
            db.query(TeacherClass)
            .filter(TeacherClass.id == payload.class_id, TeacherClass.owner_user_id == current_teacher.id)
            .first()
        )
        if not cls:
            raise HTTPException(status_code=404, detail="ไม่พบชั้นเรียนที่ระบุ")
        db.add(
            ClassStudent(
                owner_user_id=current_teacher.id,
                class_id=cls.id,
                student_id=student.id,
                seat_number=payload.seat_number,
            )
        )

    db.commit()
    db.refresh(student)
    return {
        "id": student.id,
        "student_code": student.student_code,
        "full_name": f"{student.first_name} {student.last_name}",
    }


@router.post("/import")
async def import_students_csv_or_excel(
    file: UploadFile = File(...),
    class_id: str | None = Form(default=None),
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Import students from CSV or Excel (.xlsx). Expected columns: student_code, first_name, last_name, room, seat_number, email."""
    content = await file.read()
    filename = (file.filename or "").lower()
    rows: list[dict[str, str]] = []

    if filename.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    elif filename.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        headers = [str(ws.cell(1, c).value or "").strip().lower() for c in range(1, (ws.max_column or 0) + 1)]
        for r_idx in range(2, (ws.max_row or 0) + 1):
            row_dict = {}
            for c_idx, h in enumerate(headers, start=1):
                val = ws.cell(r_idx, c_idx).value
                row_dict[h] = "" if val is None else str(val).strip()
            if any(row_dict.values()):
                rows.append(row_dict)
    else:
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ .csv หรือ .xlsx")

    imported = 0
    skipped = 0
    for r in rows:
        code = r.get("student_code") or r.get("รหัสนักเรียน") or r.get("id")
        fname = r.get("first_name") or r.get("ชื่อ")
        lname = r.get("last_name") or r.get("นามสกุล") or "-"
        if not code or not fname:
            skipped += 1
            continue

        existing = (
            db.query(Student)
            .filter(Student.owner_user_id == current_teacher.id, Student.student_code == code)
            .first()
        )
        if existing:
            student = existing
            student.deleted_at = None
        else:
            seat_raw = r.get("seat_number") or r.get("เลขที่")
            seat_num = int(seat_raw) if seat_raw and seat_raw.isdigit() else None
            student = Student(
                owner_user_id=current_teacher.id,
                student_code=code,
                first_name=fname,
                last_name=lname,
                room=r.get("room") or r.get("ห้อง"),
                seat_number=seat_num,
                email=r.get("email") or r.get("อีเมล"),
            )
            db.add(student)
            db.flush()
            imported += 1

        if class_id:
            already = (
                db.query(ClassStudent)
                .filter(ClassStudent.class_id == class_id, ClassStudent.student_id == student.id)
                .first()
            )
            if not already:
                db.add(
                    ClassStudent(
                        owner_user_id=current_teacher.id,
                        class_id=class_id,
                        student_id=student.id,
                        seat_number=student.seat_number,
                    )
                )

    db.commit()
    return {"imported": imported, "skipped": skipped, "total_rows": len(rows)}


@router.put("/{student_id}")
def update_student(
    student_id: str,
    payload: StudentUpdate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.owner_user_id == current_teacher.id, Student.deleted_at.is_(None))
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลนักเรียน")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(student, k, v)
    db.commit()
    return {"id": student.id, "message": "อัปเดตข้อมูลนักเรียนเรียบร้อยแล้ว"}


@router.post("/{student_id}/transfer")
def transfer_student(
    student_id: str,
    payload: StudentTransferRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.owner_user_id == current_teacher.id)
        .first()
    )
    target_class = (
        db.query(TeacherClass)
        .filter(TeacherClass.id == payload.to_class_id, TeacherClass.owner_user_id == current_teacher.id)
        .first()
    )
    if not student or not target_class:
        raise HTTPException(status_code=404, detail="ไม่พบนักเรียนหรือชั้นเรียนปลายทาง")

    if payload.from_class_id:
        db.query(ClassStudent).filter(
            ClassStudent.owner_user_id == current_teacher.id,
            ClassStudent.class_id == payload.from_class_id,
            ClassStudent.student_id == student.id,
        ).delete()

    exists = (
        db.query(ClassStudent)
        .filter(ClassStudent.class_id == target_class.id, ClassStudent.student_id == student.id)
        .first()
    )
    if not exists:
        db.add(
            ClassStudent(
                owner_user_id=current_teacher.id,
                class_id=target_class.id,
                student_id=student.id,
                seat_number=student.seat_number,
            )
        )
    db.commit()
    return {"message": f"ย้ายนักเรียนไปยังห้อง '{target_class.name}' เรียบร้อยแล้ว"}


@router.get("/{student_id}/scores")
def get_student_score_history(
    student_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.owner_user_id == current_teacher.id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลนักเรียน")

    results = (
        db.query(GradingResult, Assignment)
        .join(Assignment, GradingResult.assignment_id == Assignment.id)
        .filter(GradingResult.owner_user_id == current_teacher.id, GradingResult.student_id == student.id)
        .order_by(GradingResult.graded_at.desc())
        .all()
    )
    return {
        "student": {
            "id": student.id,
            "student_code": student.student_code,
            "full_name": f"{student.first_name} {student.last_name}",
        },
        "scores": [
            {
                "result_id": gr.id,
                "assignment_id": a.id,
                "assignment_title": a.title,
                "final_score": gr.final_score,
                "max_score": gr.max_score,
                "percentage": gr.percentage,
                "is_confirmed": gr.is_confirmed,
                "graded_at": gr.graded_at.isoformat() if gr.graded_at else None,
            }
            for gr, a in results
        ],
    }


@router.delete("/{student_id}")
def delete_student(
    student_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .filter(Student.id == student_id, Student.owner_user_id == current_teacher.id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลนักเรียน")
    student.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "ลบรายชื่อนักเรียนเรียบร้อยแล้ว"}
