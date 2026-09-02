"""Celery task entry points; evidence work is never executed in the API request handler."""

from app.services.pipeline import process_evidence
from app.services.reporting import generate_report
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=2, name="app.workers.tasks.process_evidence_task")
def process_evidence_task(self, evidence_id: str) -> dict:
    return process_evidence(evidence_id)


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=2, name="app.workers.tasks.generate_report_task")
def generate_report_task(self, report_id: str) -> dict:
    return generate_report(report_id)

