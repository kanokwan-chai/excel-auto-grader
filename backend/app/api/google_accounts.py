"""Multiple Google Accounts Manager API (OAuth 2.0 Authorization Code Flow).

Allows each teacher to connect, monitor, refresh, and disconnect multiple independent Google accounts.
Tokens are ALWAYS encrypted at rest and NEVER sent to browser Local Storage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.security import ALGORITHM, encrypt_secret
from backend.app.integrations.google_classroom import (
    GoogleAPIError,
    build_oauth_authorization_url,
    ensure_valid_access_token,
    exchange_code_for_tokens,
)
from backend.app.models.models import GoogleConnection, User

router = APIRouter(prefix="/google-accounts", tags=["Google Accounts Manager"])
settings = get_settings()


def _create_oauth_state(teacher_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "teacher_id": teacher_id,
            "purpose": "google_oauth",
            "exp": int((now + timedelta(minutes=15)).timestamp()),
        },
        settings.APP_SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _decode_oauth_state(state: str) -> str:
    try:
        data = jwt.decode(state, settings.APP_SECRET_KEY, algorithms=[ALGORITHM])
        if data.get("purpose") != "google_oauth" or not data.get("teacher_id"):
            raise ValueError("Invalid OAuth state")
        return str(data["teacher_id"])
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="OAuth state ไม่ถูกต้องหรือหมดอายุ") from exc


@router.get("")
def list_google_accounts(
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    accounts = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.owner_user_id == current_teacher.id,
            GoogleConnection.deleted_at.is_(None),
        )
        .order_by(GoogleConnection.is_default.desc(), GoogleConnection.created_at.desc())
        .all()
    )
    return {
        "oauth_configured": settings.google_oauth_configured,
        "accounts": [
            {
                "id": a.id,
                "google_user_id": a.google_user_id,
                "google_email": a.google_email,
                "display_name": a.display_name,
                "avatar_url": a.avatar_url,
                "status": a.status,
                "scopes": a.scopes,
                "token_expires_at": a.token_expires_at.isoformat() if a.token_expires_at else None,
                "has_refresh_token": bool(a.encrypted_refresh_token),
                "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
                "last_error": a.last_error,
                "is_default": a.is_default,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in accounts
        ],
    }


@router.get("/connect-url")
def get_google_connect_url(
    login_hint: str | None = None,
    current_teacher: User = Depends(get_current_teacher),
):
    state = _create_oauth_state(current_teacher.id)
    try:
        auth_url = build_oauth_authorization_url(state_token=state, login_hint=login_hint)
        return {"authorization_url": auth_url, "oauth_configured": True}
    except GoogleAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/callback")
async def google_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    redirect_base = f"{settings.FRONTEND_URL.rstrip('/')}/google-accounts"
    if error or not code or not state:
        return RedirectResponse(url=f"{redirect_base}?error={error or 'oauth_cancelled'}")

    teacher_id = _decode_oauth_state(state)
    try:
        result = await exchange_code_for_tokens(code)
    except GoogleAPIError as exc:
        return RedirectResponse(url=f"{redirect_base}?error={exc.code}")

    tokens = result["tokens"]
    profile = result["profile"]
    google_uid = str(profile["id"])
    google_email = profile["email"].lower()
    expires_in = int(tokens.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    existing = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.owner_user_id == teacher_id,
            GoogleConnection.google_user_id == google_uid,
        )
        .first()
    )
    if existing:
        existing.google_email = google_email
        existing.display_name = profile.get("name")
        existing.avatar_url = profile.get("picture")
        existing.encrypted_access_token = encrypt_secret(tokens["access_token"])
        if tokens.get("refresh_token"):
            existing.encrypted_refresh_token = encrypt_secret(tokens["refresh_token"])
        existing.token_expires_at = expires_at
        existing.scopes = tokens.get("scope", "").split()
        existing.status = "connected"
        existing.last_error = None
        existing.deleted_at = None
    else:
        has_any = (
            db.query(GoogleConnection)
            .filter(GoogleConnection.owner_user_id == teacher_id, GoogleConnection.deleted_at.is_(None))
            .count()
            > 0
        )
        db.add(
            GoogleConnection(
                owner_user_id=teacher_id,
                google_user_id=google_uid,
                google_email=google_email,
                display_name=profile.get("name"),
                avatar_url=profile.get("picture"),
                encrypted_access_token=encrypt_secret(tokens["access_token"]),
                encrypted_refresh_token=encrypt_secret(tokens["refresh_token"]) if tokens.get("refresh_token") else None,
                token_expires_at=expires_at,
                scopes=tokens.get("scope", "").split(),
                status="connected",
                is_default=not has_any,
            )
        )
    db.commit()
    return RedirectResponse(url=f"{redirect_base}?connected={google_email}")


@router.post("/{connection_id}/refresh")
async def refresh_google_account_token(
    connection_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
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
        raise HTTPException(status_code=404, detail="ไม่พบบัญชี Google นี้")
    try:
        # Force refresh check
        conn.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await ensure_valid_access_token(db, conn)
        return {"message": f"ต่ออายุ Token ของบัญชี {conn.google_email} สำเร็จ", "status": conn.status}
    except GoogleAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.put("/{connection_id}/default")
def set_default_google_account(
    connection_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
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
        raise HTTPException(status_code=404, detail="ไม่พบบัญชี Google นี้")
    db.query(GoogleConnection).filter(GoogleConnection.owner_user_id == current_teacher.id).update({"is_default": False})
    conn.is_default = True
    db.commit()
    return {"message": f"ตั้งบัญชี {conn.google_email} เป็นบัญชีหลักแล้ว"}


@router.delete("/{connection_id}")
def disconnect_google_account(
    connection_id: str,
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
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
        raise HTTPException(status_code=404, detail="ไม่พบบัญชี Google นี้")
    conn.deleted_at = datetime.now(timezone.utc)
    conn.status = "revoked"
    db.commit()
    return {"message": f"ยกเลิกการเชื่อมต่อบัญชี {conn.google_email} เรียบร้อยแล้ว"}
