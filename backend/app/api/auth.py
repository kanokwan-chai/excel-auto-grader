"""Multi-Teacher Authentication, Profile, Avatar & Preferences Endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.core.storage import storage_service
from backend.app.models.models import ActivityLog, TeacherPreference, TeacherProfile, User
from backend.app.schemas.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TeacherMeResponse,
    TeacherPreferenceUpdate,
    TeacherProfileUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Profile"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register_teacher(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="อีเมลนี้ถูกใช้งานในระบบแล้ว")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role="teacher",
    )
    db.add(user)
    db.flush()

    db.add(
        TeacherProfile(
            user_id=user.id,
            display_name=user.full_name,
            school_name=payload.school_name,
            department=payload.department,
        )
    )
    db.add(TeacherPreference(owner_user_id=user.id))
    db.add(
        ActivityLog(
            owner_user_id=user.id,
            actor_user_id=user.id,
            action="register_teacher",
            entity_type="user",
            entity_id=user.id,
        )
    )
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id, email=user.email)
    return AuthResponse(
        access_token=token,
        teacher_id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
    )


@router.post("/login", response_model=AuthResponse)
def login_teacher(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")

    token = create_access_token(subject=user.id, email=user.email)
    return AuthResponse(
        access_token=token,
        teacher_id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
    )


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    # Always return generic message to prevent email enumeration
    return {
        "message": f"หากอีเมล {payload.email} มีอยู่ในระบบ เราได้ส่งลิงก์รีเซ็ตรหัสผ่านให้เรียบร้อยแล้ว (ผ่าน Supabase Auth เมื่อเปิดใช้งาน)"
    }


@router.get("/me", response_model=TeacherMeResponse)
def get_me(current_teacher: User = Depends(get_current_teacher), db: Session = Depends(get_db)):
    profile = db.query(TeacherProfile).filter(TeacherProfile.user_id == current_teacher.id).first()
    prefs = db.query(TeacherPreference).filter(TeacherPreference.owner_user_id == current_teacher.id).first()
    return TeacherMeResponse(
        teacher_id=current_teacher.id,
        email=current_teacher.email,
        full_name=current_teacher.full_name,
        role=current_teacher.role,
        avatar_url=current_teacher.avatar_url,
        school_name=profile.school_name if profile else None,
        department=profile.department if profile else None,
        phone=profile.phone if profile else None,
        bio=profile.bio if profile else None,
        preferences={
            "language": prefs.language if prefs else "th",
            "default_pass_percentage": prefs.default_pass_percentage if prefs else 50.0,
            "default_numeric_tolerance": prefs.default_numeric_tolerance if prefs else 0.01,
            "email_notifications": prefs.email_notifications if prefs else True,
            "auto_recalculate_libreoffice": prefs.auto_recalculate_libreoffice if prefs else True,
            "theme_accent": prefs.theme_accent if prefs else "lavender",
        },
    )


@router.put("/profile", response_model=TeacherMeResponse)
def update_profile(
    payload: TeacherProfileUpdate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    profile = db.query(TeacherProfile).filter(TeacherProfile.user_id == current_teacher.id).first()
    if not profile:
        profile = TeacherProfile(user_id=current_teacher.id, display_name=current_teacher.full_name)
        db.add(profile)

    if payload.email:
        new_email = payload.email.lower().strip()
        if new_email != current_teacher.email:
            dup = db.query(User).filter(User.email == new_email, User.id != current_teacher.id).first()
            if dup:
                raise HTTPException(status_code=409, detail="อีเมลนี้ถูกใช้งานโดยบัญชีอื่นแล้ว")
            current_teacher.email = new_email

    if payload.full_name:
        current_teacher.full_name = payload.full_name.strip()
        profile.display_name = payload.full_name.strip()
    if payload.display_name:
        profile.display_name = payload.display_name.strip()
    if payload.school_name is not None:
        profile.school_name = payload.school_name
    if payload.department is not None:
        profile.department = payload.department
    if payload.phone is not None:
        profile.phone = payload.phone
    if payload.bio is not None:
        profile.bio = payload.bio
    if payload.avatar_url is not None:
        current_teacher.avatar_url = payload.avatar_url

    db.commit()
    return get_me(current_teacher=current_teacher, db=db)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    import base64
    import io
    from PIL import Image

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์รูปภาพเท่านั้น")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ขนาดรูปโปรไฟล์ต้องไม่เกิน 5 MB")

    path = storage_service.save_bytes(
        user_id=current_teacher.id,
        folder="avatars",
        filename=file.filename or "avatar.png",
        content=content,
        content_type=file.content_type,
    )

    # Compress avatar to a crisp 256x256 JPEG data URL so it always renders reliably on Vercel/Render
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.thumbnail((256, 256))
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85)
        b64 = base64.b64encode(out_buf.getvalue()).decode("ascii")
        avatar_data_url = f"data:image/jpeg;base64,{b64}"
    except Exception:
        b64 = base64.b64encode(content).decode("ascii")
        avatar_data_url = f"data:{file.content_type};base64,{b64}"

    profile = db.query(TeacherProfile).filter(TeacherProfile.user_id == current_teacher.id).first()
    if profile:
        profile.avatar_storage_path = path
    current_teacher.avatar_url = avatar_data_url
    db.commit()
    return {"avatar_url": current_teacher.avatar_url, "storage_path": path}


@router.put("/password")
def change_password(
    payload: PasswordChangeRequest,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    if not current_teacher.password_hash or not verify_password(payload.current_password, current_teacher.password_hash):
        raise HTTPException(status_code=400, detail="รหัสผ่านปัจจุบันไม่ถูกต้อง")
    current_teacher.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "เปลี่ยนรหัสผ่านสำเร็จ"}


@router.put("/preferences")
def update_preferences(
    payload: TeacherPreferenceUpdate,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    prefs = db.query(TeacherPreference).filter(TeacherPreference.owner_user_id == current_teacher.id).first()
    if not prefs:
        prefs = TeacherPreference(owner_user_id=current_teacher.id)
        db.add(prefs)
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(prefs, field, val)
    db.commit()
    return {"message": "บันทึกการตั้งค่าเรียบร้อยแล้ว"}
