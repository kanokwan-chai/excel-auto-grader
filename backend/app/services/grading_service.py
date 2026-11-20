"""Grading Service: Bridges Database Models (Multi-Teacher) with ExcelGradingEngine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.storage import storage_service
from backend.app.models.models import (
    ActivityLog,
    Assignment,
    GradingDetail,
    GradingError,
    GradingJob,
    GradingResult,
    GradingRubric,
    ReferenceFile,
    RubricVersion,
    Submission,
    SubmissionFile,
)
from excel_engine.exceptions import ExcelEngineError
from excel_engine.models import RubricConfig, RubricItemConfig
from excel_engine.scoring.engine import ExcelGradingEngine

settings = get_settings()


def build_rubric_config_from_version(version: RubricVersion) -> RubricConfig:
    snap: dict[str, Any] = version.snapshot_json
    items = [RubricItemConfig(**item) for item in snap.get("items", [])]
    return RubricConfig(
        id=str(version.rubric_id),
        name=snap.get("name", "Rubric"),
        version=version.version_number,
        total_points=float(version.total_points),
        enabled_categories=snap.get(
            "enabled_categories",
            ["formula", "value", "position", "style", "structure", "chart", "completeness"],
        ),
        items=items,
    )


def get_or_create_latest_rubric_version(db: Session, owner_user_id: str, rubric: GradingRubric) -> RubricVersion:
    existing = (
        db.query(RubricVersion)
        .filter(
            RubricVersion.owner_user_id == owner_user_id,
            RubricVersion.rubric_id == rubric.id,
            RubricVersion.version_number == rubric.current_version,
        )
        .first()
    )
    if existing:
        return existing

    snapshot = {
        "name": rubric.name,
        "description": rubric.description,
        "total_points": rubric.total_points,
        "enabled_categories": rubric.enabled_categories,
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "sheet_name": item.sheet_name,
                "target_cell": item.target_cell,
                "rule_config": item.rule_config or {},
                "max_points": float(item.max_points),
                "min_points": float(item.min_points),
                "allow_partial_credit": bool(item.allow_partial_credit),
                "weight_importance": item.weight_importance,
                "zero_on_error": bool(item.zero_on_error),
                "is_enabled": bool(item.is_enabled),
            }
            for item in rubric.items
        ],
    }
    ver = RubricVersion(
        owner_user_id=owner_user_id,
        rubric_id=rubric.id,
        version_number=rubric.current_version,
        total_points=rubric.total_points,
        snapshot_json=snapshot,
        change_note="Auto-snapshot before grading",
    )
    db.add(ver)
    db.flush()
    return ver


def grade_single_submission(
    db: Session,
    *,
    owner_user_id: str,
    assignment: Assignment,
    submission: Submission,
    rubric_version: RubricVersion,
    grading_job: GradingJob | None = None,
    enable_libreoffice: bool = True,
) -> GradingResult:
    """
    Grade a single submission's primary Excel file.
    CRITICAL RULE: Never overwrite a result that the teacher has already confirmed (`is_confirmed=True`).
    """
    existing_confirmed = (
        db.query(GradingResult)
        .filter(
            GradingResult.owner_user_id == owner_user_id,
            GradingResult.submission_id == submission.id,
            GradingResult.is_confirmed.is_(True),
        )
        .first()
    )
    if existing_confirmed:
        return existing_confirmed

    primary_file = (
        db.query(SubmissionFile)
        .filter(
            SubmissionFile.owner_user_id == owner_user_id,
            SubmissionFile.submission_id == submission.id,
        )
        .order_by(SubmissionFile.is_primary.desc(), SubmissionFile.created_at.desc())
        .first()
    )

    # Remove previous unconfirmed result for clean re-grade
    db.query(GradingResult).filter(
        GradingResult.owner_user_id == owner_user_id,
        GradingResult.submission_id == submission.id,
        GradingResult.is_confirmed.is_(False),
    ).delete()
    db.flush()

    if not primary_file:
        res = GradingResult(
            owner_user_id=owner_user_id,
            grading_job_id=grading_job.id if grading_job else None,
            assignment_id=assignment.id,
            submission_id=submission.id,
            student_id=submission.student_id,
            rubric_version_id=rubric_version.id,
            auto_score=0.0,
            final_score=0.0,
            max_score=float(rubric_version.total_points),
            percentage=0.0,
            status="error",
            teacher_comment="ไม่พบไฟล์ Excel ที่รองรับในการส่งงานนี้",
        )
        db.add(res)
        db.flush()
        db.add(
            GradingError(
                owner_user_id=owner_user_id,
                grading_result_id=res.id,
                error_code="NO_SUBMISSION_FILE",
                severity="critical",
                message_th="นักเรียนไม่ได้แนบไฟล์ Excel ที่รองรับ",
                fix_suggestion_th="ขอให้นักเรียนอัปโหลดไฟล์นามสกุล .xlsx หรือ .xls",
            )
        )
        db.commit()
        db.refresh(res)
        return res

    ref_file = (
        db.query(ReferenceFile)
        .filter(
            ReferenceFile.owner_user_id == owner_user_id,
            ReferenceFile.assignment_id == assignment.id,
            ReferenceFile.is_active.is_(True),
        )
        .order_by(ReferenceFile.created_at.desc())
        .first()
    )

    student_path: Path = storage_service.get_local_path(primary_file.storage_path, owner_user_id)
    ref_path: Path | None = (
        storage_service.get_local_path(ref_file.storage_path, owner_user_id) if ref_file else None
    )

    rubric_cfg = build_rubric_config_from_version(rubric_version)
    engine = ExcelGradingEngine(
        libreoffice_bin=settings.LIBREOFFICE_BIN,
        max_file_size_mb=settings.EXCEL_MAX_FILE_SIZE_MB,
        recalc_timeout_seconds=settings.EXCEL_RECALC_TIMEOUT_SECONDS,
        enable_libreoffice=enable_libreoffice,
    )

    try:
        output = engine.grade(
            student_file_path=student_path,
            rubric=rubric_cfg,
            reference_file_path=ref_path,
        )
        primary_file.security_status = "safe"
        primary_file.has_macros = output.security_report.has_macros
    except ExcelEngineError as exc:
        primary_file.security_status = "corrupted"
        primary_file.security_note = exc.message
        res = GradingResult(
            owner_user_id=owner_user_id,
            grading_job_id=grading_job.id if grading_job else None,
            assignment_id=assignment.id,
            submission_id=submission.id,
            submission_file_id=primary_file.id,
            student_id=submission.student_id,
            rubric_version_id=rubric_version.id,
            auto_score=0.0,
            final_score=0.0,
            max_score=float(rubric_version.total_points),
            percentage=0.0,
            status="error",
        )
        db.add(res)
        db.flush()
        db.add(
            GradingError(
                owner_user_id=owner_user_id,
                grading_result_id=res.id,
                error_code=exc.code,
                severity="critical",
                message_th=exc.message,
                fix_suggestion_th="ตรวจสอบไฟล์ Excel ของนักเรียนว่าไม่เสียหายและไม่ได้ใส่รหัสผ่าน",
            )
        )
        db.commit()
        db.refresh(res)
        return res

    result = GradingResult(
        owner_user_id=owner_user_id,
        grading_job_id=grading_job.id if grading_job else None,
        assignment_id=assignment.id,
        submission_id=submission.id,
        submission_file_id=primary_file.id,
        student_id=submission.student_id,
        rubric_version_id=rubric_version.id,
        auto_score=output.auto_score,
        final_score=output.auto_score,
        max_score=output.max_score,
        percentage=output.percentage,
        status="graded",
        recalculated_with_libreoffice=output.recalculated_with_libreoffice,
        graded_at=datetime.now(timezone.utc),
    )
    db.add(result)
    db.flush()

    for det in output.details:
        gd = GradingDetail(
            owner_user_id=owner_user_id,
            grading_result_id=result.id,
            rubric_item_id=det.rubric_item_id if len(det.rubric_item_id) == 36 else None,
            item_title=det.item_title,
            category=det.category,
            target_cell=det.target_cell,
            earned_points=det.earned_points,
            deducted_points=det.deducted_points,
            max_points=det.max_points,
            passed=det.passed,
            expected_value=det.expected_value,
            actual_value=det.actual_value,
            expected_formula=det.expected_formula,
            actual_formula=det.actual_formula,
            reason=det.reason,
            suggestion=det.suggestion,
            evidence_json=det.evidence,
        )
        db.add(gd)
        db.flush()
        for err in det.errors:
            db.add(
                GradingError(
                    owner_user_id=owner_user_id,
                    grading_result_id=result.id,
                    grading_detail_id=gd.id,
                    error_code=err.error_code,
                    severity=err.severity,
                    sheet_name=err.sheet_name,
                    cell_reference=err.cell_reference,
                    message_th=err.message_th,
                    expected_detail=err.expected_detail,
                    actual_detail=err.actual_detail,
                    fix_suggestion_th=err.fix_suggestion_th,
                )
            )

    db.add(
        ActivityLog(
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="grade_submission",
            entity_type="grading_result",
            entity_id=result.id,
            metadata_json={"score": result.final_score, "max_score": result.max_score},
        )
    )
    db.commit()
    db.refresh(result)
    return result
