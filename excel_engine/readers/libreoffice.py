"""Isolated LibreOffice Headless recalculation wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from excel_engine.exceptions import RecalculationError


def find_libreoffice_binary(configured_bin: str = "soffice") -> str | None:
    """Locate LibreOffice executable across Linux/macOS/Windows."""
    found = shutil.which(configured_bin)
    if found:
        return found
    for candidate in ("libreoffice", "soffice", r"C:\Program Files\LibreOffice\program\soffice.exe"):
        if os.path.isfile(candidate):
            return candidate
        w = shutil.which(candidate)
        if w:
            return w
    return None


def recalculate_workbook(
    input_path: str | Path,
    output_dir: str | Path,
    libreoffice_bin: str = "soffice",
    timeout_seconds: int = 30,
) -> tuple[Path, bool, str | None]:
    """
    Recalculate all formulas in an Excel workbook using LibreOffice in an isolated profile.
    Macros are never executed (--norestore --headless).

    Returns:
        (path_to_workbook_for_values, recalculated_bool, warning_message_or_none)
    """
    src = Path(input_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    binary = find_libreoffice_binary(libreoffice_bin)
    if not binary:
        return (
            src,
            False,
            "ไม่พบ LibreOffice ในเครื่องเซิร์ฟเวอร์ ระบบใช้ค่าผลลัพธ์ที่บันทึกไว้ในไฟล์แทน (แนะนำให้รันผ่าน Docker เพื่อคำนวณสูตรจริง)",
        )

    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")
    try:
        profile_uri = Path(profile_dir).as_uri()
        cmd = [
            binary,
            f"-env:UserInstallation={profile_uri}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            "--nolockcheck",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(out_dir),
            str(src),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        converted = out_dir / f"{src.stem}.xlsx"
        if result.returncode != 0 or not converted.exists():
            stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
            raise RecalculationError(
                f"LibreOffice ไม่สามารถคำนวณสูตรใหม่ได้: {stderr_text or 'Unknown error'}"
            )
        return converted, True, None
    except subprocess.TimeoutExpired as exc:
        raise RecalculationError(
            f"การคำนวณสูตรผ่าน LibreOffice ใช้เวลาเกิน {timeout_seconds} วินาที"
        ) from exc
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
