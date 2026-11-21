"""Per-Teacher Isolated Storage Service (Supabase Storage + Local Private Fallback).

Enforces strict tenant path isolation:
  /users/{user_id}/references/{filename}
  /users/{user_id}/submissions/{filename}
  /users/{user_id}/reports/{filename}
  /users/{user_id}/exports/{filename}
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Literal

import httpx

from backend.app.core.config import get_settings

StorageFolder = Literal["references", "submissions", "reports", "exports", "avatars"]

settings = get_settings()


def sanitize_filename(filename: str) -> str:
    """Produce a 100% ASCII-safe filename for Supabase Storage object keys (preserves extension)."""
    name = os.path.basename(filename).strip()
    _, ext = os.path.splitext(name)
    safe_ext = re.sub(r"[^a-zA-Z0-9.]", "", ext.lower())[:10] or ".xlsx"
    stem = re.sub(r"[^a-zA-Z0-9_-]", "", os.path.splitext(name)[0])[:40]
    return f"{stem}_{uuid.uuid4().hex[:10]}{safe_ext}" if stem else f"file_{uuid.uuid4().hex[:12]}{safe_ext}"


class StorageService:
    def __init__(self) -> None:
        self.base_dir = Path(settings.LOCAL_STORAGE_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def build_tenant_path(self, user_id: str, folder: StorageFolder, filename: str) -> str:
        safe_name = sanitize_filename(filename)
        return f"users/{user_id}/{folder}/{safe_name}"

    def assert_tenant_ownership(self, storage_path: str, user_id: str) -> None:
        expected_prefix = f"users/{user_id}/"
        normalized = storage_path.lstrip("/").replace("\\", "/")
        if not normalized.startswith(expected_prefix) or ".." in normalized:
            raise PermissionError("ไม่อนุญาตให้เข้าถึงไฟล์ของครูท่านอื่น")

    def save_bytes(
        self,
        user_id: str,
        folder: StorageFolder,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        rel_path = self.build_tenant_path(user_id, folder, filename)
        self.assert_tenant_ownership(rel_path, user_id)

        # Always keep local copy for Excel Grading Engine processing (cleaned up if needed)
        local_target = self.base_dir / rel_path
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_bytes(content)

        # If Supabase Storage is configured, upload to Private Bucket as well
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            upload_url = (
                f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/"
                f"{settings.SUPABASE_STORAGE_BUCKET}/{rel_path}"
            )
            try:
                httpx.post(
                    upload_url,
                    headers={
                        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                        "Content-Type": content_type,
                        "x-upsert": "true",
                    },
                    content=content,
                    timeout=30.0,
                )
            except Exception:
                # Local copy already persisted; log in production monitoring
                pass

        return rel_path

    def get_local_path(self, storage_path: str, user_id: str) -> Path:
        self.assert_tenant_ownership(storage_path, user_id)
        local_target = (self.base_dir / storage_path.lstrip("/")).resolve()
        if not str(local_target).startswith(str(self.base_dir)):
            raise PermissionError("Invalid storage path")
        if local_target.exists():
            return local_target

        # Download from Supabase Storage if not cached locally
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            download_url = (
                f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/"
                f"{settings.SUPABASE_STORAGE_BUCKET}/{storage_path.lstrip('/')}"
            )
            resp = httpx.get(
                download_url,
                headers={
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                },
                timeout=30.0,
            )
            if resp.status_code == 200:
                local_target.parent.mkdir(parents=True, exist_ok=True)
                local_target.write_bytes(resp.content)
                return local_target

        raise FileNotFoundError(f"ไม่พบไฟล์ในระบบจัดเก็บ: {storage_path}")

    def delete_file(self, storage_path: str, user_id: str) -> None:
        self.assert_tenant_ownership(storage_path, user_id)
        local_target = (self.base_dir / storage_path.lstrip("/")).resolve()
        if local_target.exists():
            local_target.unlink(missing_ok=True)


storage_service = StorageService()
