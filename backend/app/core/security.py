"""Security utilities: Password hashing, JWT (Supabase + App), Fernet token encryption."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from backend.app.core.config import get_settings

settings = get_settings()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str, email: str, expires_minutes: int = 60 * 24) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "email": email,
        "role": "teacher",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "iss": "excel-auto-grader",
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=ALGORITHM)


def decode_auth_token(token: str) -> dict[str, Any]:
    """
    Verify JWT against Supabase JWT Secret (when configured) or App Secret Key.
    Never trusts client-supplied user IDs without cryptographic signature verification.
    """
    secrets_to_try: list[str] = []
    if settings.SUPABASE_JWT_SECRET:
        secrets_to_try.append(settings.SUPABASE_JWT_SECRET)
    secrets_to_try.append(settings.APP_SECRET_KEY)

    last_err: Exception | None = None
    for secret in secrets_to_try:
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=[ALGORITHM],
                options={"verify_aud": False},
            )
        except JWTError as exc:
            last_err = exc
    raise ValueError(f"Invalid or expired authentication token: {last_err}")


def _get_fernet() -> Fernet:
    key = settings.TOKEN_ENCRYPTION_KEY.strip()
    if key:
        return Fernet(key.encode("utf-8"))
    # Deterministic dev key derived from APP_SECRET_KEY when TOKEN_ENCRYPTION_KEY is not set
    digest = hashlib.sha256(settings.APP_SECRET_KEY.encode("utf-8")).digest()
    derived = base64.urlsafe_b64encode(digest)
    return Fernet(derived)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt Google OAuth access/refresh tokens before persisting to database."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt stored Google OAuth token."""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("ไม่สามารถถอดรหัส Token ได้ (TOKEN_ENCRYPTION_KEY อาจถูกเปลี่ยน)") from exc
