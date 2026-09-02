"""Celery configuration for isolated evidence and reporting work queues."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("drishyam", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    imports=("app.workers.tasks",),
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=False,
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_routes={
        "app.workers.tasks.process_evidence_task": {"queue": "evidence_parse"},
        "app.workers.tasks.generate_report_task": {"queue": "reports"},
    },
)
