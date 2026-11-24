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


_REPAIR_STATS: dict[str, object] = {
    "repaired_rubrics": 0,
    "stale_details_found": 0,
    "regraded_results": 0,
    "patched_comments": 0,
    "last_error": None,
}


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
        GradingError,
        GradingResult,
        RubricItem,
        RubricVersion,
        Submission,
        SubmissionFile,
    )
    from backend.app.services.grading_service import grade_single_submission

    num_ops = {"gt", "gte", "lt", "lte", "between"}

    def _is_wrong_text_col(col_val: object) -> bool:
        s = str(col_val or "").strip()
        return any(k in s for k in ("ประเภท", "หมวดหมู่", "ยี่ห้อ", "ผู้จำหน่าย", "ชื่อสินค้า"))

    # Phase 1: Repair RubricItem & RubricVersion in their own isolated commit
    try:
        with SessionLocal() as db:
            changed = 0
            for ri in db.query(RubricItem).all():
                rc = dict(ri.rule_config or {})
                fcs = rc.get("filter_conditions")
                if isinstance(fcs, list):
                    updated = False
                    new_fcs = []
                    for c in fcs:
                        c2 = dict(c)
                        if str(c2.get("operator") or "").lower() in num_ops and _is_wrong_text_col(c2.get("column")):
                            c2["column"] = "ยอดขาย (ชิ้น)"
                            updated = True
                        new_fcs.append(c2)
                    if updated:
                        rc["filter_conditions"] = new_fcs
                        ri.rule_config = rc
                        flag_modified(ri, "rule_config")
                        changed += 1

            for rv in db.query(RubricVersion).all():
                snap = dict(rv.snapshot_json or {})
                items = snap.get("items")
                if isinstance(items, list):
                    rv_updated = False
                    new_items = []
                    for it in items:
                        it2 = dict(it)
                        rc = dict(it2.get("rule_config") or {})
                        fcs = rc.get("filter_conditions")
                        if isinstance(fcs, list):
                            new_fcs = []
                            for c in fcs:
                                c2 = dict(c)
                                if str(c2.get("operator") or "").lower() in num_ops and _is_wrong_text_col(c2.get("column")):
                                    c2["column"] = "ยอดขาย (ชิ้น)"
                                    rv_updated = True
                                new_fcs.append(c2)
                            rc["filter_conditions"] = new_fcs
                            it2["rule_config"] = rc
                        new_items.append(it2)
                    if rv_updated:
                        snap["items"] = new_items
                        rv.snapshot_json = snap
                        flag_modified(rv, "snapshot_json")
                        changed += 1

            if changed:
                db.commit()
            _REPAIR_STATS["repaired_rubrics"] = changed
    except Exception as exc1:
        _REPAIR_STATS["last_error"] = f"phase1: {exc1}"

    # Phase 2: Re-grade every GradingResult that still has 'ประเภท >' in GradingDetail / GradingError / teacher_comment
    try:
        with SessionLocal() as db:
            stale_details = (
                db.query(GradingDetail)
                .filter(
                    (GradingDetail.reason.like("%ประเภท >%"))
                    | (GradingDetail.suggestion.like("%ประเภท >%"))
                )
                .all()
            )
            stale_errors = (
                db.query(GradingError)
                .filter(
                    (GradingError.message_th.like("%ประเภท >%"))
                    | (GradingError.fix_suggestion_th.like("%ประเภท >%"))
                )
                .all()
            )
            affected_ids = list(
                {d.grading_result_id for d in stale_details}
                | {e.grading_result_id for e in stale_errors}
            )
            _REPAIR_STATS["stale_details_found"] = len(affected_ids)

        regraded = 0
        for res_id in affected_ids:
            try:
                with SessionLocal() as db:
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
                    file_ready = False
                    if pf:
                        try:
                            storage_service.get_local_path(pf.storage_path, gr.owner_user_id)
                            file_ready = True
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
                                    file_ready = True

                    if file_ready:
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
                    else:
                        # Fallback if old local test upload has no Drive file: clean stale 'ประเภท > 50' text directly
                        for d in gr.details:
                            if d.reason and "ประเภท >" in d.reason:
                                d.reason = d.reason.replace("ประเภท >", "ยอดขาย (ชิ้น) >")
                            if d.suggestion and "ประเภท >" in d.suggestion:
                                d.suggestion = d.suggestion.replace("ประเภท >", "ยอดขาย (ชิ้น) >")
                        for e in gr.errors:
                            if e.message_th and "ประเภท >" in e.message_th:
                                e.message_th = e.message_th.replace("ประเภท >", "ยอดขาย (ชิ้น) >")
                            if e.fix_suggestion_th and "ประเภท >" in e.fix_suggestion_th:
                                e.fix_suggestion_th = e.fix_suggestion_th.replace("ประเภท >", "ยอดขาย (ชิ้น) >")
                        if gr.teacher_comment and "ประเภท >" in gr.teacher_comment:
                            gr.teacher_comment = gr.teacher_comment.replace("ประเภท >", "ยอดขาย (ชิ้น) >")
                        db.commit()
            except Exception as exc_item:
                _REPAIR_STATS["last_error"] = f"item {res_id[:8]}: {exc_item}"

        # Phase 3: Clean any remaining teacher_comment strings that still say 'ประเภท >'
        with SessionLocal() as db:
            patched_c = 0
            for gr in db.query(GradingResult).filter(GradingResult.teacher_comment.like("%ประเภท >%")).all():
                gr.teacher_comment = gr.teacher_comment.replace("ประเภท >", "ยอดขาย (ชิ้น) >")
                patched_c += 1
            if patched_c:
                db.commit()
            _REPAIR_STATS["patched_comments"] = patched_c
        _REPAIR_STATS["regraded_results"] = regraded
    except Exception as exc2:
        _REPAIR_STATS["last_error"] = f"phase2: {exc2}"

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


@app.middleware("http")
async def no_cache_api_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure unexpected 500 errors still pass through CORSMiddleware with a clear Thai message."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"เซิร์ฟเวอร์เกิดข้อผิดพลาดขณะประมวลผล: {type(exc).__name__}: {exc}"},
    )


@app.on_event("startup")
async def on_startup_repair():
    import asyncio
    asyncio.create_task(_auto_repair_stale_filter_rubrics_and_results())


@app.get("/ping")
def lightweight_ping():
    return {"ok": True, "build": "fast-live-v5", **_REPAIR_STATS}


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
