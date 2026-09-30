"""Celery task entry points; evidence work is never executed in the API request handler."""

import logging

from app.core.db import SessionLocal
from app.models.entities import EvidenceFile
from app.services.pipeline import process_evidence
from app.services.reporting import generate_report
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=2, name="app.workers.tasks.process_evidence_task")
def process_evidence_task(self, evidence_id: str) -> dict:
    return process_evidence(evidence_id)


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=2, name="app.workers.tasks.generate_report_task")
def generate_report_task(self, report_id: str) -> dict:
    return generate_report(report_id)


@celery_app.task(bind=True, max_retries=1, name="app.workers.tasks.reanalyze_evidence_task")
def reanalyze_evidence_task(self, evidence_id: str) -> dict:
    """Reviewer-requested re-analysis. Forces escalation and never touches the legacy pipeline."""
    from app.services.grounded_pipeline import run_grounded_pipeline

    db = SessionLocal()
    try:
        evidence = db.get(EvidenceFile, evidence_id)
        if not evidence:
            return {"status": "skipped", "reason": "evidence_missing"}
        return {"status": "completed", **run_grounded_pipeline(db, evidence, force_escalation=True)}
    except Exception as exc:
        db.rollback()
        logger.exception("Reviewer-requested re-analysis failed; existing records are unchanged")
        return {"status": "failed", "reason": type(exc).__name__}
    finally:
        db.close()

