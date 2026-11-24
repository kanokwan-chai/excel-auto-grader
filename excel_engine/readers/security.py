"""File security validation: extension, magic bytes, zip-bomb defense, macro detection."""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

from excel_engine.exceptions import FileSecurityError
from excel_engine.models import FileSecurityReport

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}
ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

MAX_UNCOMPRESSED_BYTES = 350 * 1024 * 1024  # 350 MB uncompressed limit
MAX_COMPRESSION_RATIO = 500.0
MAX_ZIP_ENTRIES = 10000


def compute_sha256(file_path: str | Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_excel_file(
    file_path: str | Path,
    max_file_size_mb: int = 50,
    allowed_extensions: set[str] | None = None,
) -> FileSecurityReport:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileSecurityError("ไม่พบไฟล์ Excel ที่ระบุ", code="FILE_NOT_FOUND")

    ext = path.suffix.lower()
    allowed = allowed_extensions or ALLOWED_EXTENSIONS
    if ext not in allowed:
        raise FileSecurityError(
            f"นามสกุลไฟล์ '{ext}' ไม่ได้รับอนุญาต (รองรับเฉพาะ {', '.join(sorted(allowed))})",
            code="UNSUPPORTED_EXTENSION",
        )

    file_size = path.stat().st_size
    if file_size == 0:
        raise FileSecurityError("ไฟล์มีขนาด 0 ไบต์ ไม่สามารถตรวจได้", code="EMPTY_FILE")

    max_bytes = max_file_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise FileSecurityError(
            f"ขนาดไฟล์เกินกำหนด ({file_size / (1024 * 1024):.2f} MB > {max_file_size_mb} MB)",
            code="FILE_TOO_LARGE",
        )

    with open(path, "rb") as f:
        header = f.read(8)

    warnings: list[str] = []
    has_macros = False
    uncompressed_size = file_size

    if ext in {".xlsx", ".xlsm"}:
        if not header.startswith(ZIP_MAGIC):
            raise FileSecurityError(
                "โครงสร้างไฟล์ไม่ถูกต้อง ไม่ใช่ไฟล์ Excel (.xlsx/.xlsm) ที่สมบูรณ์",
                code="INVALID_MAGIC_BYTES",
            )
        try:
            with zipfile.ZipFile(path, "r") as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ZIP_ENTRIES:
                    raise FileSecurityError(
                        "ตรวจพบจำนวนไฟล์ย่อยภายในผิดปกติ (อาจเป็น Zip Bomb)",
                        code="ZIP_BOMB_ENTRIES",
                    )

                total_uncompressed = 0
                has_workbook_xml = False
                for info in infos:
                    if ".." in info.filename or info.filename.startswith("/"):
                        raise FileSecurityError(
                            "ตรวจพบเส้นทางไฟล์อันตรายภายในแพ็กเกจ Excel (Path Traversal)",
                            code="ZIP_PATH_TRAVERSAL",
                        )
                    total_uncompressed += info.file_size
                    if info.compress_size > 0:
                        ratio = info.file_size / info.compress_size
                        if ratio > MAX_COMPRESSION_RATIO and info.file_size > 30 * 1024 * 1024:
                            raise FileSecurityError(
                                "ตรวจพบอัตราการบีบอัดผิดปกติ (สงสัย Zip Bomb)",
                                code="ZIP_BOMB_RATIO",
                            )
                    lower_name = info.filename.lower()
                    if lower_name.endswith("vbaproject.bin"):
                        has_macros = True
                    if lower_name == "xl/workbook.xml":
                        has_workbook_xml = True

                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise FileSecurityError(
                        "ขนาดข้อมูลหลังแตกไฟล์เกินขีดจำกัดความปลอดภัย",
                        code="ZIP_BOMB_SIZE",
                    )
                if not has_workbook_xml:
                    raise FileSecurityError(
                        "ไฟล์ไม่ใช่เอกสาร Excel ที่สมบูรณ์ (ไม่พบ xl/workbook.xml)",
                        code="INVALID_EXCEL_STRUCTURE",
                    )
                uncompressed_size = total_uncompressed
        except zipfile.BadZipFile as exc:
            raise FileSecurityError(
                "ไฟล์ Excel เสียหายหรือไม่สามารถเปิดอ่านโครงสร้าง ZIP ได้",
                code="CORRUPTED_ZIP",
            ) from exc

        if has_macros:
            warnings.append(
                "ตรวจพบ Macro (VBA) ภายในไฟล์ ระบบจะไม่อนุญาตให้รัน Macro และจะตรวจสอบเฉพาะสูตรและข้อมูลอย่างปลอดภัย"
            )
    elif ext == ".xls":
        if not header.startswith(OLE2_MAGIC):
            raise FileSecurityError(
                "โครงสร้างไฟล์ .xls ไม่ถูกต้อง (ไม่ตรงตามมาตรฐาน OLE2)",
                code="INVALID_XLS_HEADER",
            )
        warnings.append("ไฟล์รูปแบบเก่า (.xls) แนะนำให้แปลงผ่าน LibreOffice ก่อนตรวจสูตร")

    file_hash = compute_sha256(path)
    return FileSecurityReport(
        is_safe=True,
        file_extension=ext,
        file_size_bytes=file_size,
        sha256_hash=file_hash,
        has_macros=has_macros,
        uncompressed_size_bytes=uncompressed_size,
        warnings=warnings,
    )
