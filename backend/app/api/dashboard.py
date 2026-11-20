"""Dashboard Summary API - 100% Real Database Aggregations Scoped by Teacher ID."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_teacher
from backend.app.core.database import get_db
from backend.app.models.models import (
    Assignment,
    GoogleConnection,
    GradingJob,
    GradingResult,
    Student,
    Submission,
    TeacherClass,
    User,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    current_teacher: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    tid = current_teacher.id

    total_classes = db.query(func.count(TeacherClass.id)).filter(
        TeacherClass.owner_user_id == tid, TeacherClass.deleted_at.is_(None)
    ).scalar() or 0

    total_students = db.query(func.count(Student.id)).filter(
        Student.owner_user_id == tid, Student.deleted_at.is_(None)
    ).scalar() or 0

    total_assignments = db.query(func.count(Assignment.id)).filter(
        Assignment.owner_user_id == tid, Assignment.deleted_at.is_(None)
    ).scalar() or 0

    grading_in_progress = db.query(func.count(GradingJob.id)).filter(
        GradingJob.owner_user_id == tid, GradingJob.status.in_(["queued", "processing"])
    ).scalar() or 0

    completed_assignments = db.query(func.count(Assignment.id)).filter(
        Assignment.owner_user_id == tid, Assignment.status == "completed", Assignment.deleted_at.is_(None)
    ).scalar() or 0

    total_submissions = db.query(func.count(Submission.id)).filter(Submission.owner_user_id == tid).scalar() or 0
    graded_submission_count = db.query(func.count(GradingResult.id)).filter(GradingResult.owner_user_id == tid).scalar() or 0
    pending_files = max(0, total_submissions - graded_submission_count)

    avg_percentage = db.query(func.avg(GradingResult.percentage)).filter(
        GradingResult.owner_user_id == tid
    ).scalar()
    average_score_pct = round(float(avg_percentage or 0.0), 2)

    connected_google_accounts = db.query(func.count(GoogleConnection.id)).filter(
        GoogleConnection.owner_user_id == tid,
        GoogleConnection.deleted_at.is_(None),
        GoogleConnection.status == "connected",
    ).scalar() or 0

    # Chart 1: Average score per assignment
    assignments = (
        db.query(Assignment)
        .filter(Assignment.owner_user_id == tid, Assignment.deleted_at.is_(None))
        .order_by(Assignment.created_at.desc())
        .limit(8)
        .all()
    )

    assignment_score_chart = []
    submission_progress_chart = []
    for a in reversed(assignments):
        avg_s = db.query(func.avg(GradingResult.final_score)).filter(
            GradingResult.owner_user_id == tid, GradingResult.assignment_id == a.id
        ).scalar()
        sub_cnt = db.query(func.count(Submission.id)).filter(
            Submission.owner_user_id == tid, Submission.assignment_id == a.id
        ).scalar() or 0
        graded_cnt = db.query(func.count(GradingResult.id)).filter(
            GradingResult.owner_user_id == tid, GradingResult.assignment_id == a.id
        ).scalar() or 0

        short_title = a.title[:22] + ("…" if len(a.title) > 22 else "")
        assignment_score_chart.append({
            "assignment_id": a.id,
            "name": short_title,
            "average_score": round(float(avg_s or 0.0), 2),
            "max_score": float(a.max_score),
        })
        submission_progress_chart.append({
            "assignment_id": a.id,
            "name": short_title,
            "submitted": sub_cnt,
            "graded": graded_cnt,
        })

    recent_assignments = [
        {
            "id": a.id,
            "title": a.title,
            "subject_name": a.subject_name,
            "status": a.status,
            "max_score": a.max_score,
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assignments[:5]
    ]

    recent_results_q = (
        db.query(GradingResult, Assignment, Submission)
        .join(Assignment, GradingResult.assignment_id == Assignment.id)
        .join(Submission, GradingResult.submission_id == Submission.id)
        .filter(GradingResult.owner_user_id == tid)
        .order_by(GradingResult.graded_at.desc())
        .limit(6)
        .all()
    )
    recent_gradings = [
        {
            "result_id": gr.id,
            "assignment_title": a.title,
            "student_name": sub.student_display_name or "ไม่ระบุชื่อ",
            "final_score": gr.final_score,
            "max_score": gr.max_score,
            "percentage": gr.percentage,
            "status": gr.status,
            "is_confirmed": gr.is_confirmed,
            "graded_at": gr.graded_at.isoformat() if gr.graded_at else None,
        }
        for gr, a, sub in recent_results_q
    ]

    return {
        "kpis": {
            "total_classes": total_classes,
            "total_students": total_students,
            "total_assignments": total_assignments,
            "grading_in_progress": grading_in_progress,
            "completed_assignments": completed_assignments,
            "pending_files": pending_files,
            "average_score_percentage": average_score_pct,
            "connected_google_accounts": connected_google_accounts,
        },
        "assignment_score_chart": assignment_score_chart,
        "submission_progress_chart": submission_progress_chart,
        "recent_assignments": recent_assignments,
        "recent_gradings": recent_gradings,
    }
