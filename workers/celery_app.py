"""Celery Background Worker Application (Redis Broker)."""

from __future__ import annotations

from celery import Celery
from backend.app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "excel_auto_grader_workers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["workers.tasks.grading_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Bangkok",
    enable_utc=True,
    task_time_limit=180,
    task_soft_time_limit=150,
    worker_prefetch_multiplier=1,
)
