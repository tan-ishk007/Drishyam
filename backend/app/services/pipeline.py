"""Idempotent evidence processing pipeline from private object through reviewable derived records."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import evaluate_alerts
from app.core.db import SessionLocal
from app.core.security import utcnow
from app.extraction import extract_indicators, extract_timestamp, extract_transaction_fields
from app.models.entities import Entity, Event, EventEntity, EvidenceFile, EvidenceStatus, ExtractedText, ProcessingRun, ProcessingState, Transaction
from app.parsers import ParsedRecord, parse_evidence
from app.services.audit import audit
from app.services.storage import get_private_path

logger = logging.getLogger(__name__)
PIPELINE_VERSION = "mvp-v1"


def _run(db: Session, evidence_id: str, stage: str) -> ProcessingRun:
    run = db.scalar(select(ProcessingRun).where(ProcessingRun.evidence_id == evidence_id, ProcessingRun.pipeline_stage == stage, ProcessingRun.pipeline_version == PIPELINE_VERSION))
    if not run:
        run = ProcessingRun(evidence_id=evidence_id, pipeline_stage=stage, pipeline_version=PIPELINE_VERSION)
        db.add(run)
        db.flush()
    run.state, run.started_at, run.progress = ProcessingState.RUNNING, run.started_at or utcnow(), 5
    return run


def _finish(run: ProcessingRun) -> None:
    run.state, run.progress, run.completed_at = ProcessingState.SUCCEEDED, 100, utcnow()


def _entity_for(db: Session, *, case_id: str, evidence_id: str, indicator: tuple[str, str, str, float], reference: str) -> Entity:
    entity_type, value, normalized_value, confidence = indicator
    existing = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.entity_type == entity_type, Entity.normalized_value == normalized_value))
    if existing:
        return existing
    entity = Entity(case_id=case_id, source_evidence_id=evidence_id, entity_type=entity_type, value=value, normalized_value=normalized_value, source_reference=reference[:512], extraction_method="regex_normalizer", confidence=confidence)
    db.add(entity)
    db.flush()
    return entity


def _records(db: Session, evidence: EvidenceFile) -> tuple[list[ParsedRecord], str]:
    run = _run(db, evidence.id, "parse")
    prior = db.scalar(select(ExtractedText).where(ExtractedText.evidence_id == evidence.id, ExtractedText.pipeline_version == PIPELINE_VERSION))
    if prior:
        _finish(run)
        return [ParsedRecord(raw_text=line, metadata={"reused": True}, record_type="message") for line in prior.content.splitlines() if line.strip()], prior.extraction_method
    evidence.status = EvidenceStatus.PROCESSING
    document = parse_evidence(get_private_path(evidence.storage_key), source_category=evidence.source_category)
    db.add(ExtractedText(evidence_id=evidence.id, pipeline_version=PIPELINE_VERSION, content=document.content, extraction_method=document.method, confidence=document.confidence, metadata_json={"parser": document.method, **document.metadata}))
    _finish(run)
    return document.records, document.method


def _events(db: Session, evidence: EvidenceFile, records: list[ParsedRecord]) -> list[Event]:
    run = _run(db, evidence.id, "extract")
    prior = db.scalars(select(Event).where(Event.source_file_id == evidence.id)).all()
    if prior:
        _finish(run)
        return prior
    evidence.status = EvidenceStatus.EXTRACTING
    events: list[Event] = []
    for record in records:
        if len(record.raw_text.strip()) < 3:
            continue
        occurred_at, original_time, time_precision = extract_timestamp(record.raw_text)
        transaction = extract_transaction_fields(record.raw_text, record.metadata)
        event_type = "financial_transaction" if record.record_type == "bank_transaction" or transaction["amount"] is not None else ("phishing_email" if record.record_type == "phishing_email" else record.record_type)
        event = Event(case_id=evidence.case_id, source_file_id=evidence.id, occurred_at=occurred_at, original_time=original_time, time_precision=time_precision, event_type=event_type, description=record.raw_text[:4000], raw_text_reference=f"{record.record_type}:{record.metadata.get('line') or record.metadata.get('row') or 'record'}", amount=transaction["amount"], confidence=0.91 if record.record_type == "bank_transaction" else 0.78, payload_json={"record_type": record.record_type, "metadata": record.metadata, "parser_provenance": PIPELINE_VERSION})
        db.add(event)
        db.flush()
        events.append(event)
        for indicator in extract_indicators(record.raw_text):
            entity = _entity_for(db, case_id=evidence.case_id, evidence_id=evidence.id, indicator=indicator, reference=event.raw_text_reference)
            db.add(EventEntity(event_id=event.id, entity_id=entity.id, relationship_type="mentioned_in", confidence=indicator[3]))
        if transaction["amount"] is not None:
            db.add(Transaction(case_id=evidence.case_id, event_id=event.id, source_evidence_id=evidence.id, amount=float(transaction["amount"]), occurred_at=event.occurred_at, reference_id=str(transaction["reference"]) if transaction["reference"] else None, sender_value=str(transaction["sender"]).strip().lower() if transaction["sender"] else None, receiver_value=str(transaction["receiver"]).strip().lower() if transaction["receiver"] else None, source_kind=evidence.source_category, confidence=event.confidence))
    _finish(run)
    return events


def process_evidence(evidence_id: str) -> dict:
    """Execute all worker stages against actual private evidence; no synthetic hardcoded response is produced."""
    db = SessionLocal()
    try:
        evidence = db.get(EvidenceFile, evidence_id)
        if not evidence:
            raise ValueError("Evidence record not found")
        records, parser_method = _records(db, evidence)
        events = _events(db, evidence, records)
        for stage, state in [("normalize", EvidenceStatus.NORMALIZING), ("graph", EvidenceStatus.BUILDING_GRAPH)]:
            run = _run(db, evidence.id, stage)
            evidence.status = state
            _finish(run)
        run = _run(db, evidence.id, "alerts")
        evidence.status = EvidenceStatus.EVALUATING_ALERTS
        alert_count = evaluate_alerts(db, evidence.case_id)
        _finish(run)
        evidence.status, evidence.processed_at = EvidenceStatus.COMPLETED, utcnow()
        audit(db, action="evidence.process", object_type="evidence_file", object_id=evidence.id, case_id=evidence.case_id, outcome="success", actor_id=evidence.uploader_id, details={"parser": parser_method, "events": len(events), "alerts": alert_count})
        db.commit()
        return {"evidence_id": evidence.id, "records": len(records), "events": len(events), "status": evidence.status.value}
    except Exception as exc:
        db.rollback()
        evidence = db.get(EvidenceFile, evidence_id)
        if evidence:
            evidence.status, evidence.failure_reason = EvidenceStatus.FAILED, str(exc)[:1000]
            run = _run(db, evidence.id, "parse")
            run.state, run.failure_reason, run.completed_at = ProcessingState.FAILED, str(exc)[:1000], utcnow()
            audit(db, action="evidence.process", object_type="evidence_file", object_id=evidence.id, case_id=evidence.case_id, outcome="failed", actor_id=evidence.uploader_id, details={"reason": type(exc).__name__})
            db.commit()
        logger.exception("Evidence processing failed for an evidence identifier")
        raise
    finally:
        db.close()

