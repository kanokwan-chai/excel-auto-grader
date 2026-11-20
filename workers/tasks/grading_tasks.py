"""Celery Asynchronous Tasks for Batch Excel Grading (Isolated from Web Server)."""

from __future__ import annotations

from datetime import datetime, timezone

from workers.celery_app import celery_app
from backend.app.core.database import SessionLocal
from backend.app.models.models import Assignment, GradingJob, RubricVersion, Submission
from backend.app.services.grading_service import grade_single_submission


@celery_app.task(name="workers.grade_assignment_batch", bind=True, max_retries=2)
def grade_assignment_batch(
    self,
    job_id: str,
    owner_user_id: str,
    assignment_id: str,
    rubric_version_id: str,
    submission_ids: list[str] | None = None,
) -> dict:
    db = SessionLocal()
    try:
        job = db.query(GradingJob).filter(GradingJob.id == job_id, GradingJob.owner_user_id == owner_user_id).first()
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.owner_user_id == owner_user_id).first()
        rubric_ver = db.query(RubricVersion).filter(RubricVersion.id == rubric_version_id).first()
        if not job or not assignment or not rubric_ver:
            return {"status": "failed", "reason": "Missing job/assignment/rubric"}

        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        q = db.query(Submission).filter(
            Submission.owner_user_id == owner_user_id,
            Submission.assignment_id == assignment_id,
        )
        if submission_ids:
            q = q.filter(Submission.id.in_(submission_ids))
        submissions = q.all()

        job.total_files = len(submissions)
        processed = 0
        failed = 0

        for sub in submissions:
            res = grade_single_submission(
                db,
                owner_user_id=owner_user_id,
                assignment=assignment,
                submission=sub,
                rubric_version=rubric_ver,
                grading_job=job,
            )
            processed += 1
            if res.status == "error":
                failed += 1
            job.processed_files = processed
            job.failed_files = failed
            db.commit()

        job.status = "completed" if failed == 0 else "partial_failed"
        job.completed_at = datetime.now(timezone.utc)
        assignment.status = "completed"
        db.commit()

        return {"job_id": job.id, "processed": processed, "failed": failed}
    finally:
        db.close()
