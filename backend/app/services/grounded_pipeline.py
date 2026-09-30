"""Source-grounded evidence pipeline.

Runs beside the legacy `mvp-v1` pipeline and writes only to its own tables. Raw extraction is
committed before any model is contacted, so a provider outage can never cost us extraction that
already succeeded.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utcnow
from app.evidence_intelligence import correlation
from app.evidence_intelligence.detection import ContentFileTypeDetector
from app.evidence_intelligence.extraction import DeterministicExtractor, RawExtraction
from app.evidence_intelligence.ocr import OCRResult
from app.evidence_intelligence.providers.router import CachedResponse, ModelRouter, RoutingOutcome
from app.evidence_intelligence.schema import (
    RAW_EXTRACTION_VERSION,
    NormalizedRecordDraft,
    SourceType,
)
from app.models.entities import (
    EvidenceFile,
    ModelInferenceRun,
    NormalizedRecord,
    ProcessingRun,
    ProcessingState,
    RawExtractionArtifact,
    RecordRelation,
)
from app.services.grounded_projection import project_case
from app.services.storage import get_private_path

logger = logging.getLogger(__name__)

GROUNDED_PIPELINE_VERSION = RAW_EXTRACTION_VERSION

STAGE_RECEIVED = "grounded.received"
STAGE_TYPE_DETECTED = "grounded.type_detected"
STAGE_EXTRACTING = "grounded.extracting"
STAGE_OCR_COMPLETED = "grounded.ocr_completed"
STAGE_LOCAL_MODEL = "grounded.local_model_completed"
STAGE_ESCALATED = "grounded.groq_escalated"
STAGE_VALIDATED = "grounded.validated"
STAGE_REVIEW = "grounded.review_required"
STAGE_READY = "grounded.ready"

UI_STAGE_ORDER = (
    STAGE_RECEIVED,
    STAGE_TYPE_DETECTED,
    STAGE_EXTRACTING,
    STAGE_OCR_COMPLETED,
    STAGE_LOCAL_MODEL,
    STAGE_ESCALATED,
    STAGE_VALIDATED,
    STAGE_REVIEW,
    STAGE_READY,
)

VISUAL_TYPES = {SourceType.SCREENSHOT, SourceType.IMAGE}


def _stage(db: Session, evidence_id: str, stage: str, state: ProcessingState, *, failure: str | None = None) -> ProcessingRun:
    run = db.scalar(
        select(ProcessingRun).where(
            ProcessingRun.evidence_id == evidence_id,
            ProcessingRun.pipeline_stage == stage,
            ProcessingRun.pipeline_version == GROUNDED_PIPELINE_VERSION,
        )
    )
    if not run:
        run = ProcessingRun(evidence_id=evidence_id, pipeline_stage=stage, pipeline_version=GROUNDED_PIPELINE_VERSION)
        db.add(run)
        db.flush()
    else:
        run.attempt += 1
    run.state = state
    run.started_at = run.started_at or utcnow()
    if state in {ProcessingState.SUCCEEDED, ProcessingState.FAILED}:
        run.completed_at = utcnow()
        run.progress = 100 if state is ProcessingState.SUCCEEDED else run.progress
    if failure:
        run.failure_reason = failure[:1000]
    return run


def _persist_raw_artifacts(db: Session, evidence: EvidenceFile, extraction: RawExtraction) -> None:
    for layer in [*extraction.layers, _units_layer(extraction)]:
        existing = db.scalar(
            select(RawExtractionArtifact).where(
                RawExtractionArtifact.evidence_id == evidence.id,
                RawExtractionArtifact.artifact_version == extraction.version,
                RawExtractionArtifact.layer == layer.layer,
            )
        )
        if existing:
            continue
        db.add(
            RawExtractionArtifact(
                evidence_id=evidence.id,
                case_id=evidence.case_id,
                artifact_version=extraction.version,
                layer=layer.layer,
                extractor_name=layer.extractor,
                source_type=extraction.source_type.value,
                payload_json=layer.payload,
                quality_flags=extraction.quality_flags,
            )
        )


def _units_layer(extraction: RawExtraction) -> Any:
    from app.evidence_intelligence.extraction import ExtractionLayer

    return ExtractionLayer(
        layer="units",
        extractor=extraction.extractor,
        payload={"units": [unit.to_dict() for unit in extraction.units]},
    )


def _event_time(draft: NormalizedRecordDraft) -> tuple[datetime | None, str | None]:
    provenance = draft.field_provenance.get("event_time")
    raw_quote = provenance.quote if provenance else None
    if not draft.event_time:
        return None, raw_quote
    try:
        return datetime.fromisoformat(str(draft.event_time)), raw_quote
    except ValueError:
        return None, raw_quote


def _upsert_record(db: Session, evidence: EvidenceFile, outcome: RoutingOutcome) -> NormalizedRecord:
    draft = outcome.record
    event_time, event_time_raw = _event_time(draft)
    provenance = {name: value.model_dump(mode="json") for name, value in draft.field_provenance.items()}

    record = db.scalar(
        select(NormalizedRecord).where(
            NormalizedRecord.evidence_id == evidence.id,
            NormalizedRecord.record_key == draft.record_key,
            NormalizedRecord.raw_extraction_version == draft.raw_extraction_version,
        )
    )
    if record is None:
        record = NormalizedRecord(
            evidence_id=evidence.id,
            case_id=evidence.case_id,
            record_key=draft.record_key,
            raw_extraction_version=draft.raw_extraction_version,
        )
        db.add(record)
    elif record.review_state != "unreviewed":
        # A reviewer has already ruled on this record; reprocessing must not silently undo that.
        return record

    record.source_file_name = evidence.original_name
    record.source_type = draft.source_type.value
    record.observed_text = draft.observed_text
    record.normalized_summary = draft.normalized_summary
    record.event_type = draft.event_type
    record.event_time = event_time
    record.event_time_raw = event_time_raw
    record.event_time_precision = draft.event_time_precision.value
    record.participant_a = draft.participant_a
    record.participant_b = draft.participant_b
    record.sender = draft.sender
    record.receiver = draft.receiver
    record.message_direction = draft.message_direction.value if draft.message_direction else None
    record.chat_participant_identifier = draft.chat_participant_identifier
    record.phone_numbers = draft.phone_numbers
    record.email_addresses = draft.email_addresses
    record.account_identifiers = draft.account_identifiers
    record.vehicle_identifiers = draft.vehicle_identifiers
    record.organisation_names = draft.organisation_names
    record.person_names = draft.person_names
    record.person_roles = draft.person_roles
    record.location_names = draft.location_names
    record.transaction_reference = draft.transaction_reference
    record.amount_value = draft.amount.value
    record.amount_currency = draft.amount.currency
    record.amount_role = draft.amount.role.value
    record.location = draft.location
    record.device_identifier = draft.device_identifier
    record.event_attributes = draft.event_attributes
    record.observation_basis = draft.observation_basis.value
    record.field_provenance = provenance
    record.model_confidence = draft.model_confidence
    record.validation_confidence = draft.validation_confidence
    record.final_confidence_band = draft.final_confidence_band.value
    record.validation_status = draft.validation_status.value
    record.requires_human_review = draft.requires_human_review
    record.review_reason = draft.review_reason
    record.conflict_fields = sorted(set(outcome.conflicts))
    record.escalated = outcome.escalated
    record.raw_model_output_version = draft.raw_model_output_version
    record.extraction_model_name = draft.extraction_model_name
    record.prompt_version = draft.prompt_version
    return record


def _persist_attempts(db: Session, evidence: EvidenceFile, outcome: RoutingOutcome) -> None:
    for index, attempt in enumerate(outcome.attempts):
        existing = db.scalar(
            select(ModelInferenceRun).where(
                ModelInferenceRun.evidence_id == evidence.id,
                ModelInferenceRun.record_key == outcome.record.record_key,
                ModelInferenceRun.cache_key == attempt.cache_key,
            )
        )
        if existing:
            continue
        db.add(
            ModelInferenceRun(
                evidence_id=evidence.id,
                case_id=evidence.case_id,
                record_key=outcome.record.record_key,
                provider=attempt.provider,
                model_name=attempt.model,
                prompt_version=attempt.prompt_version,
                role="local" if index == 0 else "escalation",
                status=attempt.status,
                cache_key=attempt.cache_key,
                raw_output=attempt.raw_output,
                parsed_payload=attempt.payload,
                grounding_report=attempt.grounding_report,
                error_json=attempt.error,
                latency_ms=attempt.latency_ms,
            )
        )


def _persist_relations(db: Session, case_id: str) -> int:
    settings = get_settings()
    records = db.scalars(select(NormalizedRecord).where(NormalizedRecord.case_id == case_id)).all()
    if len(records) < 2:
        return 0

    created = 0
    for candidate in correlation.correlate(records, include_semantic=settings.semantic_correlation_enabled):
        if db.scalar(select(RecordRelation).where(RecordRelation.idempotency_key == candidate.idempotency_key)):
            continue
        db.add(
            RecordRelation(
                case_id=case_id,
                relation_type=candidate.relation_type.value,
                status=candidate.status.value,
                detection_method="semantic" if candidate.confidence <= correlation.SEMANTIC_CONFIDENCE else "exact_match",
                evidence_ids=candidate.evidence_ids,
                record_ids=candidate.record_ids,
                matching_or_conflicting_fields=candidate.matching_or_conflicting_fields,
                reason=candidate.reason,
                source_references=candidate.source_references,
                confidence=candidate.confidence,
                requires_human_review=candidate.requires_human_review,
                idempotency_key=candidate.idempotency_key,
            )
        )
        created += 1
    return created


def run_grounded_pipeline(db: Session, evidence: EvidenceFile, *, force_escalation: bool = False) -> dict[str, Any]:
    """Extract, normalize, score and correlate one evidence item.

    Returns a summary. Raises only on a genuinely unrecoverable extraction failure; provider
    problems are recorded and downgraded to a review requirement.
    """
    settings = get_settings()
    if not settings.evidence_intelligence_enabled:
        return {"skipped": "evidence_intelligence_disabled"}

    _stage(db, evidence.id, STAGE_RECEIVED, ProcessingState.SUCCEEDED)

    path = get_private_path(evidence.storage_key)
    detected = ContentFileTypeDetector().detect(
        path, declared_category=evidence.source_category, declared_mime=evidence.detected_mime
    )
    _stage(db, evidence.id, STAGE_TYPE_DETECTED, ProcessingState.SUCCEEDED)

    _stage(db, evidence.id, STAGE_EXTRACTING, ProcessingState.RUNNING)
    extractor = DeterministicExtractor()
    try:
        extraction = extractor.extract(path, evidence_id=evidence.id, detected=detected)
    except Exception as exc:
        _stage(db, evidence.id, STAGE_EXTRACTING, ProcessingState.FAILED, failure=str(exc))
        db.commit()
        raise

    _persist_raw_artifacts(db, evidence, extraction)
    _stage(db, evidence.id, STAGE_EXTRACTING, ProcessingState.SUCCEEDED)
    if extraction.layer("ocr"):
        _stage(db, evidence.id, STAGE_OCR_COMPLETED, ProcessingState.SUCCEEDED)
    # Raw extraction is durable from here on, whatever the model providers do next.
    db.commit()

    ocr_result = _ocr_result_from(extraction)
    image_path = path if detected.source_type in VISUAL_TYPES else None
    def _cached_answer(cache_key: str) -> CachedResponse | None:
        """A prior answer to an identical request, from any earlier run.

        The key already covers the evidence hash, parser version, provider, model, prompt version
        and the image bytes, so a hit means the exact same question was asked and answered. On a
        local vision model this turns a reprocess from tens of seconds per image into nothing.
        """
        prior = db.scalar(
            select(ModelInferenceRun)
            .where(ModelInferenceRun.cache_key == cache_key, ModelInferenceRun.status == "succeeded")
            .order_by(ModelInferenceRun.created_at.desc())
        )
        if prior is None or prior.parsed_payload is None:
            return None
        return CachedResponse(raw_output=prior.raw_output, payload=prior.parsed_payload)

    router = ModelRouter(cache_lookup=_cached_answer)

    # The model pass is the long part — minutes on a local vision model — and until now nothing
    # recorded that it had started. The processing view therefore showed every stage succeeded and
    # nothing running while the case sat empty, so the stage is opened before the first call and
    # committed immediately, where a reader can see it.
    _stage(db, evidence.id, STAGE_LOCAL_MODEL, ProcessingState.RUNNING)
    db.commit()

    outcomes: list[RoutingOutcome] = []
    for unit in extraction.units:
        outcome = router.normalize(
            unit,
            extraction,
            evidence_sha256=evidence.sha256,
            image_path=image_path,
            ocr_result=ocr_result,
            force_escalation=force_escalation,
        )
        outcomes.append(outcome)
        _upsert_record(db, evidence, outcome)
        _persist_attempts(db, evidence, outcome)

    local_ran = any(attempt.provider != "groq" and attempt.status == "succeeded" for outcome in outcomes for attempt in outcome.attempts)
    escalated = any(outcome.escalated for outcome in outcomes)
    _stage(
        db,
        evidence.id,
        STAGE_LOCAL_MODEL,
        ProcessingState.SUCCEEDED if local_ran else ProcessingState.FAILED,
        failure=None if local_ran else "The local model produced no usable reading for this evidence.",
    )
    if escalated:
        _stage(db, evidence.id, STAGE_ESCALATED, ProcessingState.SUCCEEDED)
    _stage(db, evidence.id, STAGE_VALIDATED, ProcessingState.SUCCEEDED)

    needs_review = any(outcome.record.requires_human_review for outcome in outcomes)
    _stage(db, evidence.id, STAGE_REVIEW if needs_review else STAGE_READY, ProcessingState.SUCCEEDED)
    db.commit()

    relations = _persist_relations(db, evidence.case_id)
    db.commit()

    # Surface the grounded reading on the timeline, transactions, graph and report. Projection is
    # idempotent and never overwrites a reviewed row, so a failure here costs presentation only —
    # the grounded records themselves are already committed above.
    projected: dict[str, int] = {}
    try:
        projected = project_case(db, evidence.case_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Grounded projection failed; normalized records are unaffected")

    return {
        "evidence_id": evidence.id,
        "source_type": detected.source_type.value,
        "raw_extraction_version": extraction.version,
        "units": len(extraction.units),
        "records": len(outcomes),
        "escalated": escalated,
        "requires_human_review": needs_review,
        "relations_created": relations,
        "projected": projected,
        "quality_flags": extraction.quality_flags,
    }


def _ocr_result_from(extraction: RawExtraction) -> OCRResult | None:
    """Rebuild the OCR view the model should be allowed to cite."""
    from app.evidence_intelligence.ocr import OCRBlock

    layer = extraction.layer("ocr")
    if not layer:
        return None
    payload = layer.payload
    raw_blocks = payload.get("blocks")
    if raw_blocks is None:
        raw_blocks = [block for page in payload.get("pages", []) for block in page.get("blocks", [])]
    blocks = [
        OCRBlock(
            block_id=str(item["block_id"]),
            text=str(item.get("text", "")),
            confidence=float(item.get("confidence") or 0.0),
            bbox=tuple(float(value) for value in item.get("bbox", (0, 0, 0, 0))),
            page=int(item.get("page") or 1),
        )
        for item in raw_blocks
        if item.get("block_id")
    ]
    return OCRResult(
        blocks=blocks,
        width=int(payload.get("width") or 0),
        height=int(payload.get("height") or 0),
        mean_confidence=payload.get("mean_confidence"),
        quality_flags=list(payload.get("quality_flags") or extraction.quality_flags),
    )
