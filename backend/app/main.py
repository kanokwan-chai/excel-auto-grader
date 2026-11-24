"""FastAPI Main Application Entrypoint for Excel Auto Grader Multi-Teacher SaaS."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import (
    assignments,
    auth,
    classes,
    classroom,
    dashboard,
    google_accounts,
    grading,
    reports,
    rubrics,
    students,
    submissions,
)
from backend.app.core.config import get_settings
from backend.app.core.database import Base, engine

settings = get_settings()

# Ensure tables exist in dev/test SQLite or fresh Postgres environments
Base.metadata.create_all(bind=engine)


_REPAIR_STATS: dict[str, int] = {"repaired_rubrics": 0, "regraded_results": 0}


async def _auto_repair_stale_filter_rubrics_and_results() -> None:
    """Auto-repair any saved RubricItem/RubricVersion where numeric filter had column='ประเภท', and re-grade affected results."""
    from sqlalchemy.orm.attributes import flag_modified
    from backend.app.core.database import SessionLocal
    from backend.app.core.storage import storage_service
    from backend.app.integrations.google_classroom import download_drive_excel_file
    from backend.app.models.models import (
        Assignment,
        GoogleConnection,
        GradingDetail,
        GradingResult,
        RubricItem,
        RubricVersion,
        Submission,
        SubmissionFile,
    )
    from backend.app.services.grading_service import grade_single_submission

    bad_text_cols = {"ประเภท", "ประเภทสินค้า", "หมวดหมู่", "ยี่ห้อ", "ผู้จำหน่าย"}
    num_ops = {"gt", "gte", "lt", "lte", "between"}
    try:
        with SessionLocal() as db:
            changed = 0
            for ri in db.query(RubricItem).all():
                rc = ri.rule_config or {}
                fcs = rc.get("filter_conditions")
                if isinstance(fcs, list):
                    updated = False
                    for c in fcs:
                        if str(c.get("operator") or "").lower() in num_ops and str(c.get("column") or "").strip() in bad_text_cols:
                            c["column"] = "ยอดขาย (ชิ้น)"
                            updated = True
                    if updated:
                        ri.rule_config = dict(rc)
                        flag_modified(ri, "rule_config")
                        changed += 1

            for rv in db.query(RubricVersion).all():
                snap = rv.snapshot_json or {}
                items = snap.get("items")
                if isinstance(items, list):
                    rv_updated = False
                    for it in items:
                        rc = it.get("rule_config") or {}
                        fcs = rc.get("filter_conditions")
                        if isinstance(fcs, list):
                            for c in fcs:
                                if str(c.get("operator") or "").lower() in num_ops and str(c.get("column") or "").strip() in bad_text_cols:
                                    c["column"] = "ยอดขาย (ชิ้น)"
                                    rv_updated = True
                    if rv_updated:
                        rv.snapshot_json = dict(snap)
                        flag_modified(rv, "snapshot_json")
                        changed += 1

            if changed:
                db.commit()
            _REPAIR_STATS["repaired_rubrics"] = changed

            # Now find any existing GradingResult whose details still contain the old 'ประเภท > 50' error and re-grade them automatically!
            stale_details = (
                db.query(GradingDetail)
                .filter(
                    (GradingDetail.reason.like("%ประเภท >%"))
                    | (GradingDetail.suggestion.like("%ประเภท >%"))
                )
                .all()
            )
            affected_result_ids = list({d.grading_result_id for d in stale_details})
            regraded = 0
            for res_id in affected_result_ids:
                gr = db.query(GradingResult).filter(GradingResult.id == res_id).first()
                if not gr:
                    continue
                was_confirmed = bool(gr.is_confirmed)
                assign = db.query(Assignment).filter(Assignment.id == gr.assignment_id).first()
                sub = db.query(Submission).filter(Submission.id == gr.submission_id).first()
                rver = db.query(RubricVersion).filter(RubricVersion.id == gr.rubric_version_id).first()
                if not assign or not sub or not rver:
                    continue
                pf = (
                    db.query(SubmissionFile)
                    .filter(SubmissionFile.submission_id == sub.id)
                    .order_by(SubmissionFile.is_primary.desc(), SubmissionFile.created_at.desc())
                    .first()
                )
                if pf:
                    try:
                        storage_service.get_local_path(pf.storage_path, gr.owner_user_id)
                    except FileNotFoundError:
                        if pf.google_drive_file_id:
                            conn = (
                                db.query(GoogleConnection)
                                .filter(
                                    GoogleConnection.owner_user_id == gr.owner_user_id,
                                    GoogleConnection.status == "connected",
                                    GoogleConnection.deleted_at.is_(None),
                                )
                                .first()
                            )
                            if conn:
                                content, _ = await download_drive_excel_file(db, conn, pf.google_drive_file_id)
                                pf.storage_path = storage_service.save_bytes(
                                    user_id=gr.owner_user_id,
                                    folder="submissions",
                                    filename=pf.original_filename or "recovered.xlsx",
                                    content=content,
                                )
                                db.commit()
                try:
                    new_res = grade_single_submission(
                        db,
                        owner_user_id=gr.owner_user_id,
                        assignment=assign,
                        submission=sub,
                        rubric_version=rver,
                        enable_libreoffice=False,
                        force_regrade_confirmed=True,
                    )
                    if was_confirmed:
                        new_res.is_confirmed = True
                        new_res.status = "confirmed"
                        db.commit()
                    regraded += 1
                except Exception:
                    db.rollback()
            _REPAIR_STATS["regraded_results"] = regraded
    except Exception:
        pass

app = FastAPI(
    title="Excel Auto Grader API",
    description="Multi-Teacher SaaS Platform for Automatic Microsoft Excel Grading & Google Classroom Integration",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(classes.router, prefix=API_PREFIX)
app.include_router(students.router, prefix=API_PREFIX)
app.include_router(assignments.router, prefix=API_PREFIX)
app.include_router(rubrics.router, prefix=API_PREFIX)
app.include_router(submissions.router, prefix=API_PREFIX)
app.include_router(grading.router, prefix=API_PREFIX)
app.include_router(google_accounts.router, prefix=API_PREFIX)
app.include_router(classroom.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure unexpected 500 errors still pass through CORSMiddleware with a clear Thai message."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"เซิร์ฟเวอร์เกิดข้อผิดพลาดขณะประมวลผล: {type(exc).__name__}: {exc}"},
    )


@app.on_event("startup")
async def on_startup_repair():
    await _auto_repair_stale_filter_rubrics_and_results()


@app.get("/ping")
def lightweight_ping():
    return {"ok": True, "build": "fix-q5-live", **_REPAIR_STATS}


@app.get("/health")
def health_check():
    from sqlalchemy import text
    from backend.app.core.database import SessionLocal

    db_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "excel-auto-grader-backend",
        "version": "2.0.0",
        "database_connected": db_ok,
        "google_oauth_configured": settings.google_oauth_configured,
        "supabase_configured": settings.supabase_configured,
    }
