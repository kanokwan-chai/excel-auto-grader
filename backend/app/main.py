"""FastAPI Main Application Entrypoint for Excel Auto Grader Multi-Teacher SaaS."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "excel-auto-grader-backend",
        "version": "2.0.0",
        "google_oauth_configured": settings.google_oauth_configured,
        "supabase_configured": settings.supabase_configured,
    }
