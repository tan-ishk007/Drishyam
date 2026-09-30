"""Idempotent evidence processing pipeline from private object through reviewable derived records."""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import evaluate_alerts
from app.core.db import SessionLocal
from app.core.security import utcnow
from app.extraction import extract_indicators, extract_timestamp, extract_transaction_fields
from app.models.entities import Entity, Event, EventEntity, EvidenceFile, EvidenceStatus, ExtractedText, ProcessingRun, ProcessingState, Transaction
from app.parsers import ParsedRecord, parse_evidence
from app.services import entity_resolution
from app.services.audit import audit
from app.services.storage import get_private_path

logger = logging.getLogger(__name__)
PIPELINE_VERSION = "mvp-v1"
OCR_RECORD_TYPE = "ocr_document"
OCR_PARSER_METHODS = {"tesseract_ocr"}


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


def _entity_for(db: Session, *, case_id: str, evidence_id: str, indicator: tuple[str, str, str, float], reference: str) -> Entity | None:
    """Mint or reuse the one node this indicator belongs to.

    The regex extractor's own normalization is deliberately ignored here. It disagreed with the
    grounded pipeline's resolver on both the type name and the canonical key, so the same phone
    number arrived as two rows -- one holding every relationship, the other holding none.
    """
    entity_type, value, own_normalization, confidence = indicator
    identity = entity_resolution.canonicalize_indicator(entity_type, value)
    if identity is not None:
        entity_type, value, normalized_value = identity.entity_type, identity.display_value, identity.canonical_value
    else:
        # A type the resolver holds no identity field for, such as a URL. Its own normalization is
        # the only one there is, and the two pipelines never disagreed about it.
        normalized_value = own_normalization
    if not normalized_value:
        return None
    existing = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.entity_type == entity_type, Entity.normalized_value == normalized_value))
    if existing:
        return existing
    entity = Entity(case_id=case_id, source_evidence_id=evidence_id, entity_type=entity_type, value=value[:512], normalized_value=normalized_value[:512], source_reference=reference[:512], extraction_method="regex_normalizer", confidence=confidence)
    db.add(entity)
    db.flush()
    return entity


def _records(db: Session, evidence: EvidenceFile) -> tuple[list[ParsedRecord], str]:
    run = _run(db, evidence.id, "parse")
    prior = db.scalar(select(ExtractedText).where(ExtractedText.evidence_id == evidence.id, ExtractedText.pipeline_version == PIPELINE_VERSION))
    if prior:
        _finish(run)
        # Replaying stored text has to replay what kind of text it was. Labelling every reused line
        # "message" made an OCR'd screenshot look like a chat transcript on the second pass, which
        # is how one image kept expanding back into an event per line.
        reused_type = OCR_RECORD_TYPE if prior.extraction_method in OCR_PARSER_METHODS else "message"
        return [ParsedRecord(raw_text=line, metadata={"reused": True}, record_type=reused_type) for line in prior.content.splitlines() if line.strip()], prior.extraction_method
    evidence.status = EvidenceStatus.PROCESSING
    document = parse_evidence(get_private_path(evidence.storage_key), source_category=evidence.source_category)
    db.add(ExtractedText(evidence_id=evidence.id, pipeline_version=PIPELINE_VERSION, content=document.content, extraction_method=document.method, confidence=document.confidence, metadata_json={"parser": document.method, **document.metadata}))
    _finish(run)
    return document.records, document.method



def _ocr_document_event(db: Session, evidence: EvidenceFile, records: list[ParsedRecord]) -> Event:
    """One screenshot is one document, so it gets one event.

    Emitting an event per OCR line turned a three-file case into sixty timeline rows reading
    "Learn more" and "@ Message 0", and let stray digits on a line — a phone number, an account
    row — become standalone transactions. An image has no line-level record structure to preserve;
    what it has is a picture, and the grounded pipeline is what reads meaning out of it.
    """
    text = "\n".join(record.raw_text.strip() for record in records if record.raw_text.strip())
    event = Event(
        case_id=evidence.case_id,
        source_file_id=evidence.id,
        event_type=OCR_RECORD_TYPE,
        description=text[:4000],
        raw_text_reference=f"{OCR_RECORD_TYPE}:{evidence.id}",
        confidence=0.78,
        payload_json={"record_type": OCR_RECORD_TYPE, "lines": len(records), "parser_provenance": PIPELINE_VERSION},
    )
    db.add(event)
    db.flush()
    linked: set[str] = set()
    for indicator in extract_indicators(text):
        entity = _entity_for(db, case_id=evidence.case_id, evidence_id=evidence.id, indicator=indicator, reference=event.raw_text_reference)
        if entity is None or entity.id in linked:
            continue
        linked.add(entity.id)
        db.add(EventEntity(event_id=event.id, entity_id=entity.id, relationship_type="mentioned_in", confidence=indicator[3]))
    return event


def _events(db: Session, evidence: EvidenceFile, records: list[ParsedRecord]) -> list[Event]:
    run = _run(db, evidence.id, "extract")
    prior = db.scalars(select(Event).where(Event.source_file_id == evidence.id)).all()
    if prior:
        _finish(run)
        return prior
    evidence.status = EvidenceStatus.EXTRACTING
    if records and all(record.record_type == OCR_RECORD_TYPE for record in records):
        _finish(run)
        return [_ocr_document_event(db, evidence, records)]
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
        linked: set[str] = set()
        for indicator in extract_indicators(record.raw_text):
            entity = _entity_for(db, case_id=evidence.case_id, evidence_id=evidence.id, indicator=indicator, reference=event.raw_text_reference)
            if entity is None or entity.id in linked:
                continue
            linked.add(entity.id)
            db.add(EventEntity(event_id=event.id, entity_id=entity.id, relationship_type="mentioned_in", confidence=indicator[3]))
        if transaction["amount"] is not None:
            db.add(Transaction(case_id=evidence.case_id, event_id=event.id, source_evidence_id=evidence.id, amount=float(transaction["amount"]), occurred_at=event.occurred_at, reference_id=str(transaction["reference"]) if transaction["reference"] else None, sender_value=str(transaction["sender"]).strip().lower() if transaction["sender"] else None, receiver_value=str(transaction["receiver"]).strip().lower() if transaction["receiver"] else None, source_kind=evidence.source_category, confidence=event.confidence))
    _finish(run)
    return events


# The model pass reaches out to a local daemon and, on escalation, across the network. Those calls
# fail transiently — a busy GPU, a rate-limited provider, a dropped database socket — and a single
# lost attempt cost the whole file its timeline, transactions and graph edges with nothing but a
# log line to show for it. Three attempts have covered every transient failure seen so far.
GROUNDED_MAX_ATTEMPTS = 3
GROUNDED_RETRY_BACKOFF_SECONDS = (15.0, 45.0)


def _extraction_is_durable(db: Session, evidence_id: str) -> bool:
    """Did deterministic extraction get far enough to be worth retrying the model pass?

    Raw artifacts are committed before any provider is contacted. If none exist, the failure was in
    reading the file itself — an unsupported format, an unreadable image — and retrying only burns
    minutes to reach the same answer.
    """
    from app.models.entities import RawExtractionArtifact

    return db.scalar(select(RawExtractionArtifact.id).where(RawExtractionArtifact.evidence_id == evidence_id)) is not None


def _record_grounded_failure(db: Session, evidence_id: str, exc: Exception, attempts: int) -> None:
    """Leave the failure where a reviewer will see it, not only in the worker log."""
    from app.services.grounded_pipeline import STAGE_VALIDATED, _stage

    try:
        _stage(
            db,
            evidence_id,
            STAGE_VALIDATED,
            ProcessingState.FAILED,
            failure=f"{type(exc).__name__}: {exc} (after {attempts} attempts)"[:1000],
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record the grounded failure stage")


def _run_grounded(db: Session, evidence_id: str) -> dict:
    """Run the source-grounded pipeline as a strictly additive second pass.

    The legacy result is already committed by this point. A failure here degrades the evidence to
    'grounded analysis unavailable' — it must never undo a successful legacy run.

    Re-running is safe: artifacts, records and projections are all keyed on the evidence, so a
    second attempt replaces the first attempt's partial work rather than duplicating it.
    """
    from app.services.grounded_pipeline import run_grounded_pipeline

    if db.get(EvidenceFile, evidence_id) is None:
        return {"status": "skipped", "reason": "evidence_missing"}

    for attempt in range(1, GROUNDED_MAX_ATTEMPTS + 1):
        evidence = db.get(EvidenceFile, evidence_id)
        if evidence is None:
            return {"status": "skipped", "reason": "evidence_missing"}
        try:
            return {"status": "completed", "attempts": attempt, **run_grounded_pipeline(db, evidence)}
        except Exception as exc:
            db.rollback()
            retryable = attempt < GROUNDED_MAX_ATTEMPTS and _extraction_is_durable(db, evidence_id)
            if not retryable:
                logger.exception("Grounded evidence analysis failed; legacy extraction is unaffected")
                _record_grounded_failure(db, evidence_id, exc, attempt)
                return {"status": "failed", "reason": type(exc).__name__, "attempts": attempt}
            delay = GROUNDED_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(GROUNDED_RETRY_BACKOFF_SECONDS) - 1)]
            logger.warning(
                "Grounded evidence analysis attempt %d failed (%s); retrying in %.0fs",
                attempt,
                type(exc).__name__,
                delay,
            )
            time.sleep(delay)
    return {"status": "failed", "reason": "exhausted", "attempts": GROUNDED_MAX_ATTEMPTS}


def process_evidence(evidence_id: str) -> dict:
    """Execute all worker stages against actual private evidence; no synthetic hardcoded response is produced."""
    db = SessionLocal()
    try:
        evidence = db.get(EvidenceFile, evidence_id)
        if not evidence:
            raise ValueError("Evidence record not found")
        records, parser_method = _records(db, evidence)
        # Raw extraction is made durable before enrichment starts. Without this commit, a failure
        # during event extraction rolls back parser output that had already succeeded.
        db.commit()
        events = _events(db, evidence, records)
        for stage, state in [("normalize", EvidenceStatus.NORMALIZING), ("graph", EvidenceStatus.BUILDING_GRAPH)]:
            run = _run(db, evidence.id, stage)
            evidence.status = state
            _finish(run)
        run = _run(db, evidence.id, "alerts")
        evidence.status = EvidenceStatus.EVALUATING_ALERTS
        alert_count = evaluate_alerts(db, evidence.case_id)
        _finish(run)
        # The grounded pass is where the timeline, transactions and graph actually come from, and on
        # a local vision model it takes minutes. Reporting COMPLETED before it runs told the
        # investigator the file was done while the case was still empty, so the file stays in a
        # working state until the model pass has had its turn.
        evidence.status = EvidenceStatus.NORMALIZING
        audit(db, action="evidence.process", object_type="evidence_file", object_id=evidence.id, case_id=evidence.case_id, outcome="success", actor_id=evidence.uploader_id, details={"parser": parser_method, "events": len(events), "alerts": alert_count})
        db.commit()

        grounded = _run_grounded(db, evidence_id)

        # Whatever the model pass did, the deterministic result is already durable, so the file is
        # finished either way; a grounded failure is reported through the stage records, not by
        # leaving the evidence stuck.
        evidence = db.get(EvidenceFile, evidence_id)
        status = EvidenceStatus.COMPLETED
        if evidence and evidence.status is not EvidenceStatus.FAILED:
            evidence.status, evidence.processed_at = status, utcnow()
            db.commit()
        return {"evidence_id": evidence_id, "records": len(records), "events": len(events), "status": status.value, "grounded": grounded}
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

