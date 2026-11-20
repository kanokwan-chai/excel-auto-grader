"""Strict Multi-Teacher Authentication Dependencies.

NEVER trusts teacher_id passed in request body/query/header.
Always verifies the cryptographic Bearer JWT and resolves the authenticated User from DB.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import decode_auth_token
from backend.app.models.models import TeacherPreference, TeacherProfile, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_teacher(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="กรุณาเข้าสู่ระบบก่อนใช้งาน",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_auth_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session หมดอายุหรือไม่ถูกต้อง กรุณาเข้าสู่ระบบใหม่",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Resolve internal user by id or Supabase auth_uid
    user = (
        db.query(User)
        .filter(((User.id == sub) | (User.auth_uid == sub)), User.deleted_at.is_(None))
        .first()
    )

    # Auto-provision teacher record if authenticated via Supabase Auth for the first time
    if not user and email:
        user = User(
            auth_uid=sub,
            email=email.lower(),
            full_name=payload.get("user_metadata", {}).get("full_name") or email.split("@")[0],
            role="teacher",
        )
        db.add(user)
        db.flush()
        db.add(TeacherProfile(user_id=user.id, display_name=user.full_name))
        db.add(TeacherPreference(owner_user_id=user.id))
        db.commit()
        db.refresh(user)

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ไม่พบบัญชีผู้ใช้งานหรือบัญชีถูกระงับ")

    return user
