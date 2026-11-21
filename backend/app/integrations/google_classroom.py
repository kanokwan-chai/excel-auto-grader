"""Real Google OAuth 2.0, Google Classroom API, and Google Drive API Integration.

Security & Multi-Account Guarantees:
- Never mocks Classroom data in production.
- Encrypts access_token & refresh_token with Fernet before storing in DB.
- Handles OAuth 2.0 Authorization Code Flow with state JWT bound to teacher_id.
- Automatically refreshes expired access tokens using stored encrypted refresh_token.
- Handles revoked permissions (invalid_grant) and marks connection status = 'revoked'.
- Supports full API pagination (nextPageToken) and 429 rate-limit backoff.
- Requests minimal read-only scopes needed for courses, coursework, rosters, submissions, and Drive attachments.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import decrypt_secret, encrypt_secret
from backend.app.models.models import GoogleConnection

settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CLASSROOM_API_BASE = "https://classroom.googleapis.com/v1"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

# Minimal necessary scopes for Excel Auto Grader (includes coursework.students for pushing approved grades)
REQUIRED_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/drive.readonly",
]

SUPPORTED_EXCEL_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.google-apps.spreadsheet",
}
SUPPORTED_EXCEL_EXTS = (".xlsx", ".xls", ".xlsm")


class GoogleAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502, code: str = "GOOGLE_API_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def build_oauth_authorization_url(state_token: str, login_hint: str | None = None) -> str:
    if not settings.google_oauth_configured:
        raise GoogleAPIError(
            "ยังไม่ได้ตั้งค่า GOOGLE_CLIENT_ID และ GOOGLE_CLIENT_SECRET ในไฟล์ .env",
            status_code=503,
            code="GOOGLE_OAUTH_NOT_CONFIGURED",
        )
    params: dict[str, str] = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(REQUIRED_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent select_account",
        "state": state_token,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    if not settings.google_oauth_configured:
        raise GoogleAPIError(
            "ยังไม่ได้ตั้งค่า GOOGLE_CLIENT_ID และ GOOGLE_CLIENT_SECRET",
            status_code=503,
            code="GOOGLE_OAUTH_NOT_CONFIGURED",
        )
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise GoogleAPIError(
                f"ไม่สามารถแลก OAuth Code เป็น Token ได้: {resp.text}",
                status_code=400,
                code="OAUTH_TOKEN_EXCHANGE_FAILED",
            )
        token_data = resp.json()

        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if user_resp.status_code != 200:
            raise GoogleAPIError("ไม่สามารถดึงข้อมูลโปรไฟล์บัญชี Google ได้", status_code=400)
        profile = user_resp.json()

    return {"tokens": token_data, "profile": profile}


async def ensure_valid_access_token(db: Session, conn: GoogleConnection) -> str:
    """Decrypt and return valid access token; refresh automatically if expiring within 2 minutes."""
    now = datetime.now(timezone.utc)
    if conn.status == "revoked":
        raise GoogleAPIError(
            f"บัญชี {conn.google_email} ถูกยกเลิกสิทธิ์ กรุณาเชื่อมต่อใหม่",
            status_code=401,
            code="GOOGLE_TOKEN_REVOKED",
        )

    expires_at = conn.token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at is None or expires_at > now + timedelta(minutes=2):
        return decrypt_secret(conn.encrypted_access_token)

    if not conn.encrypted_refresh_token:
        conn.status = "expired"
        conn.last_error = "Access Token หมดอายุและไม่มี Refresh Token กรุณาเชื่อมต่อบัญชีใหม่"
        db.commit()
        raise GoogleAPIError(conn.last_error, status_code=401, code="GOOGLE_TOKEN_EXPIRED")

    refresh_token = decrypt_secret(conn.encrypted_refresh_token)
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            body = resp.text
            conn.status = "revoked" if "invalid_grant" in body else "error"
            conn.last_error = f"ไม่สามารถต่ออายุ Token ได้: {body}"
            db.commit()
            raise GoogleAPIError(
                f"สิทธิ์การเข้าถึงของบัญชี {conn.google_email} หมดอายุหรือถูกยกเลิก กรุณาเชื่อมต่อใหม่",
                status_code=401,
                code="GOOGLE_TOKEN_REFRESH_FAILED",
            )
        data = resp.json()
        new_access = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        conn.encrypted_access_token = encrypt_secret(new_access)
        conn.token_expires_at = now + timedelta(seconds=expires_in)
        conn.status = "connected"
        conn.last_error = None
        db.commit()
        return new_access


async def _google_get_paginated(
    access_token: str,
    url: str,
    items_key: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Call Google REST API with automatic pagination and 429 rate-limit retry."""
    all_items: list[dict[str, Any]] = []
    query = dict(params or {})
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=25.0) as client:
        while True:
            if page_token:
                query["pageToken"] = page_token
            for attempt in range(3):
                resp = await client.get(
                    url,
                    params=query,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code == 429:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                break

            if resp.status_code == 401:
                raise GoogleAPIError("Google Access Token ไม่ถูกต้องหรือหมดอายุ", status_code=401, code="GOOGLE_UNAUTHORIZED")
            if resp.status_code == 403:
                raise GoogleAPIError(
                    "บัญชี Google นี้ไม่มีสิทธิ์เข้าถึงข้อมูลดังกล่าว (ตรวจสอบ Scope หรือสิทธิ์ครูในห้องเรียน)",
                    status_code=403,
                    code="GOOGLE_FORBIDDEN",
                )
            if resp.status_code != 200:
                raise GoogleAPIError(f"Google API error ({resp.status_code}): {resp.text}", status_code=resp.status_code)

            payload = resp.json()
            all_items.extend(payload.get(items_key, []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

    return all_items


async def fetch_classroom_courses(db: Session, conn: GoogleConnection) -> list[dict[str, Any]]:
    token = await ensure_valid_access_token(db, conn)
    return await _google_get_paginated(
        token,
        f"{CLASSROOM_API_BASE}/courses",
        items_key="courses",
        params={"teacherId": "me", "pageSize": 100},
    )


async def fetch_course_students(db: Session, conn: GoogleConnection, course_id: str) -> list[dict[str, Any]]:
    token = await ensure_valid_access_token(db, conn)
    return await _google_get_paginated(
        token,
        f"{CLASSROOM_API_BASE}/courses/{course_id}/students",
        items_key="students",
        params={"pageSize": 100},
    )


async def fetch_course_work(db: Session, conn: GoogleConnection, course_id: str) -> list[dict[str, Any]]:
    token = await ensure_valid_access_token(db, conn)
    return await _google_get_paginated(
        token,
        f"{CLASSROOM_API_BASE}/courses/{course_id}/courseWork",
        items_key="courseWork",
        params={"pageSize": 100},
    )


async def fetch_student_submissions(
    db: Session,
    conn: GoogleConnection,
    course_id: str,
    coursework_id: str,
) -> list[dict[str, Any]]:
    token = await ensure_valid_access_token(db, conn)
    return await _google_get_paginated(
        token,
        f"{CLASSROOM_API_BASE}/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions",
        items_key="studentSubmissions",
        params={"pageSize": 100},
    )


def is_supported_excel_attachment(title: str, mime_type: str | None = None) -> bool:
    lower_title = (title or "").lower()
    if any(lower_title.endswith(ext) for ext in SUPPORTED_EXCEL_EXTS):
        return True
    if mime_type and mime_type in SUPPORTED_EXCEL_MIMES:
        return True
    return False


async def fetch_drive_file_metadata(
    db: Session,
    conn: GoogleConnection,
    drive_file_id: str,
) -> dict[str, Any] | None:
    """Fetch modifiedTime, createdTime, and size of a Google Drive file."""
    try:
        token = await ensure_valid_access_token(db, conn)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files/{drive_file_id}",
                params={"fields": "id,name,mimeType,modifiedTime,createdTime,size"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


async def download_drive_excel_file(
    db: Session,
    conn: GoogleConnection,
    drive_file_id: str,
    mime_type: str | None = None,
) -> tuple[bytes, str]:
    """
    Download an Excel file from Google Drive.
    If the attachment is a Google Sheet, exports it as .xlsx via Drive Export API.
    """
    token = await ensure_valid_access_token(db, conn)
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        if mime_type == "application/vnd.google-apps.spreadsheet":
            url = f"{DRIVE_API_BASE}/files/{drive_file_id}/export"
            resp = await client.get(
                url,
                params={"mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                headers={"Authorization": f"Bearer {token}"},
            )
            ext = ".xlsx"
        else:
            url = f"{DRIVE_API_BASE}/files/{drive_file_id}"
            resp = await client.get(
                url,
                params={"alt": "media"},
                headers={"Authorization": f"Bearer {token}"},
            )
            ext = ".xlsx"

        if resp.status_code != 200:
            raise GoogleAPIError(
                f"ไม่สามารถดาวน์โหลดไฟล์จาก Google Drive ({drive_file_id}): HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.content, ext


async def push_grade_to_classroom(
    db: Session,
    conn: GoogleConnection,
    course_id: str,
    coursework_id: str,
    submission_id: str,
    score: float,
    return_to_student: bool = False,
) -> dict[str, Any]:
    """
    Push an approved score (draftGrade & assignedGrade) to Google Classroom API.
    Note: Google Classroom API only allows modifying grades for coursework created by the same OAuth project;
    if Google returns 403 ProjectPermissionDenied, raises GoogleAPIError with a clear Thai explanation.
    """
    token = await ensure_valid_access_token(db, conn)
    url = f"{CLASSROOM_API_BASE}/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions/{submission_id}"
    payload: dict[str, Any] = {"draftGrade": score}
    update_mask = "draftGrade"
    if return_to_student:
        payload["assignedGrade"] = score
        update_mask = "draftGrade,assignedGrade"

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.patch(
            url,
            params={"updateMask": update_mask},
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if resp.status_code == 403:
            body = resp.text
            if "ProjectPermissionDenied" in body or "not owned by" in body:
                raise GoogleAPIError(
                    "Google Classroom ไม่อนุญาตให้แอปภายนอกเขียนคะแนนทับงานที่ครูสร้างเองในหน้า Classroom (ข้อจำกัดของ Google API) — แต่ระบบอนุมัติคะแนนและสร้างคอมเมนต์กระชับให้คัดลอกวางเรียบร้อยแล้ว",
                    status_code=403,
                    code="CLASSROOM_PROJECT_PERMISSION_DENIED",
                )
            raise GoogleAPIError(
                "บัญชี Google ยังไม่มีสิทธิ์ส่งคะแนน (กรุณาเพิ่ม Scope classroom.coursework.students ใน Google Cloud แล้วเชื่อมต่อบัญชี Google ใหม่ 1 ครั้ง)",
                status_code=403,
                code="CLASSROOM_WRITE_SCOPE_MISSING",
            )
        if resp.status_code != 200:
            raise GoogleAPIError(
                f"ส่งคะแนนเข้า Google Classroom ไม่สำเร็จ (HTTP {resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )

        if return_to_student:
            await client.post(
                f"{url}:return",
                headers={"Authorization": f"Bearer {token}"},
            )

        return resp.json()


async def create_classroom_coursework(
    db: Session,
    conn: GoogleConnection,
    course_id: str,
    title: str,
    description: str | None = None,
    max_points: float = 20.0,
    due_at: datetime | None = None,
    state: str = "PUBLISHED",
) -> dict[str, Any]:
    """Create a real Assignment (courseWork) in Google Classroom via official API.
    Assignments created via this app allow 100% automatic grade pushing (draftGrade / assignedGrade / return).
    """
    token = await ensure_valid_access_token(db, conn)
    body: dict[str, Any] = {
        "title": title.strip(),
        "workType": "ASSIGNMENT",
        "maxPoints": float(max_points),
        "state": state if state in ("PUBLISHED", "DRAFT") else "PUBLISHED",
    }
    if description:
        body["description"] = description.strip()
    if due_at:
        utc_dt = due_at.astimezone(timezone.utc) if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
        body["dueDate"] = {"year": utc_dt.year, "month": utc_dt.month, "day": utc_dt.day}
        body["dueTime"] = {"hours": utc_dt.hour, "minutes": utc_dt.minute}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{CLASSROOM_API_BASE}/courses/{course_id}/courseWork",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if resp.status_code == 403:
            raise GoogleAPIError(
                "บัญชี Google นี้ยังไม่มีสิทธิ์สร้างงาน (กรุณาเพิ่ม Scope classroom.coursework.students ใน Google Cloud แล้วเชื่อมต่อบัญชี Google ใหม่ 1 ครั้ง)",
                status_code=403,
                code="CLASSROOM_WRITE_SCOPE_MISSING",
            )
        if resp.status_code != 200:
            raise GoogleAPIError(
                f"สร้างงานใน Google Classroom ไม่สำเร็จ (HTTP {resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()
