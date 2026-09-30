"""Source-grounded evidence surfaces: extraction, normalized records, relations and review.

Every route is case-scoped through `require_case_access`, paginated, and returns only derived data
— never a storage key, signed URL or credential.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import (
    Entity,
    EntityRelation,
    EvidenceFile,
    ModelInferenceRun,
    NormalizedRecord,
    ProcessingRun,
    RawExtractionArtifact,
    RecordRelation,
    RecordReview,
)
from app.schemas.grounded import (
    BridgeRelationshipResponse,
    CommunityResponse,
    EntityEndpointResponse,
    EntityRelationObservation,
    EntityRelationPage,
    EntityRelationReviewRequest,
    EntityRelationSummary,
    CaseAssistantRequest,
    CaseAssistantResponse,
    CaseChronologyResponse,
    EvidenceStagesResponse,
    ImportantEntityResponse,
    ModelRunResponse,
    NetworkEdgeResponse,
    NetworkNodeResponse,
    NetworkOverviewResponse,
    NetworkPathResponse,
    NetworkSubgraphResponse,
    NormalizedRecordPage,
    NormalizedRecordResponse,
    ProcessingStageResponse,
    RawArtifactResponse,
    TemporalFindingResponse,
    RecordReviewRequest,
    RecordReviewResponse,
    RelationPage,
    RelationResponse,
    RelationReviewRequest,
    ReviewQueueItem,
    ReviewQueuePage,
)
from app.core.security import utcnow
from app.graph import analytics
from app.services import case_assistant, entity_profile, entity_summary, ledger, prior_record, record_review, requisition, relationship_builder, temporal
from app.services.audit import audit
from app.services.cases import require_case_access
from app.services.grounded_pipeline import GROUNDED_PIPELINE_VERSION, UI_STAGE_ORDER

router = APIRouter(prefix="/cases/{case_id}/grounded", tags=["grounded-evidence"])

STAGE_LABELS = {
    "grounded.received": "File received",
    "grounded.type_detected": "Format detected",
    "grounded.extracting": "Parser extraction",
    "grounded.ocr_completed": "OCR completed",
    "grounded.local_model_completed": "Local model analysis",
    "grounded.groq_escalated": "Escalated for second opinion",
    "grounded.validated": "Validation completed",
    "grounded.review_required": "Review required",
    "grounded.ready": "Ready",
}


def _evidence(db: DbSession, case_id: str, evidence_id: str) -> EvidenceFile:
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id))
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence record not found")
    return evidence


def _record_response(record: NormalizedRecord) -> NormalizedRecordResponse:
    return NormalizedRecordResponse(
        id=record.id,
        evidence_id=record.evidence_id,
        case_id=record.case_id,
        workspace_id=record.workspace_id,
        record_key=record.record_key,
        source_file_name=record.source_file_name,
        source_type=record.source_type,
        observed_text=record.observed_text,
        normalized_summary=record.normalized_summary,
        event_type=record.event_type,
        event_time=record.event_time,
        event_time_raw=record.event_time_raw,
        event_time_precision=record.event_time_precision,
        participant_a=record.participant_a,
        participant_b=record.participant_b,
        sender=record.sender,
        receiver=record.receiver,
        message_direction=record.message_direction,
        chat_participant_identifier=record.chat_participant_identifier,
        phone_numbers=list(record.phone_numbers or []),
        email_addresses=list(record.email_addresses or []),
        account_identifiers=list(record.account_identifiers or []),
        vehicle_identifiers=list(record.vehicle_identifiers or []),
        organisation_names=list(record.organisation_names or []),
        person_names=list(record.person_names or []),
        location_names=list(record.location_names or []),
        transaction_reference=record.transaction_reference,
        amount={"value": float(record.amount_value) if record.amount_value is not None else None, "currency": record.amount_currency},
        location=record.location,
        device_identifier=record.device_identifier,
        event_attributes=dict(record.event_attributes or {}),
        observation_basis=record.observation_basis,
        field_provenance=dict(record.field_provenance or {}),
        model_confidence=float(record.model_confidence) if record.model_confidence is not None else None,
        validation_confidence=float(record.validation_confidence) if record.validation_confidence is not None else None,
        final_confidence_band=record.final_confidence_band,
        validation_status=record.validation_status,
        requires_human_review=record.requires_human_review,
        review_reason=record.review_reason,
        review_state=record.review_state,
        conflict_fields=list(record.conflict_fields or []),
        escalated=record.escalated,
        raw_extraction_version=record.raw_extraction_version,
        raw_model_output_version=record.raw_model_output_version,
        extraction_model_name=record.extraction_model_name,
        prompt_version=record.prompt_version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _relation_response(relation: RecordRelation) -> RelationResponse:
    return RelationResponse(
        id=relation.id,
        relation_type=relation.relation_type,
        status=relation.status,
        detection_method=relation.detection_method,
        evidence_ids=list(relation.evidence_ids or []),
        record_ids=list(relation.record_ids or []),
        matching_or_conflicting_fields=list(relation.matching_or_conflicting_fields or []),
        reason=relation.reason,
        source_references=list(relation.source_references or []),
        confidence=float(relation.confidence),
        requires_human_review=relation.requires_human_review,
        review_decision=relation.review_decision,
        reviewed_at=relation.reviewed_at,
        created_at=relation.created_at,
    )


def _review_response(review: RecordReview) -> RecordReviewResponse:
    return RecordReviewResponse(
        id=review.id,
        record_id=review.record_id,
        relation_id=review.relation_id,
        action=review.action,
        field_name=review.field_name,
        previous_value=review.previous_value,
        new_value=review.new_value,
        reason=review.reason,
        reviewer_id=review.reviewer_id,
        created_at=review.created_at,
    )


@router.get("/evidence/{evidence_id}/stages", response_model=EvidenceStagesResponse)
def evidence_stages(case_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> EvidenceStagesResponse:
    """Report the grounded processing lifecycle. This endpoint never queues or retries work."""
    require_case_access(db, case_id, current_user)
    _evidence(db, case_id, evidence_id)

    runs = {
        run.pipeline_stage: run
        for run in db.scalars(
            select(ProcessingRun).where(
                ProcessingRun.evidence_id == evidence_id,
                ProcessingRun.pipeline_version == GROUNDED_PIPELINE_VERSION,
            )
        ).all()
    }
    stages = [
        ProcessingStageResponse(
            stage=stage,
            label=STAGE_LABELS.get(stage, stage),
            state=runs[stage].state.value if stage in runs else "pending",
            attempt=runs[stage].attempt if stage in runs else 0,
            reached=stage in runs,
            failure_reason=runs[stage].failure_reason if stage in runs else None,
            started_at=runs[stage].started_at if stage in runs else None,
            completed_at=runs[stage].completed_at if stage in runs else None,
        )
        for stage in UI_STAGE_ORDER
    ]
    reached = [stage for stage in stages if stage.reached]
    return EvidenceStagesResponse(
        evidence_id=evidence_id,
        pipeline_version=GROUNDED_PIPELINE_VERSION,
        current_stage=reached[-1].stage if reached else None,
        stages=stages,
    )


@router.get("/evidence/{evidence_id}/extraction", response_model=list[RawArtifactResponse])
def raw_extraction(
    case_id: str,
    evidence_id: str,
    current_user: CurrentUser,
    db: DbSession,
    layer: str | None = Query(default=None, max_length=48),
) -> list[RawArtifactResponse]:
    """Return the immutable deterministic extraction layers, independent of any model output."""
    require_case_access(db, case_id, current_user)
    _evidence(db, case_id, evidence_id)

    query = select(RawExtractionArtifact).where(RawExtractionArtifact.evidence_id == evidence_id)
    if layer:
        query = query.where(RawExtractionArtifact.layer == layer)
    return [
        RawArtifactResponse(
            id=item.id,
            layer=item.layer,
            extractor_name=item.extractor_name,
            source_type=item.source_type,
            artifact_version=item.artifact_version,
            quality_flags=list(item.quality_flags or []),
            payload=dict(item.payload_json or {}),
            created_at=item.created_at,
        )
        for item in db.scalars(query.order_by(RawExtractionArtifact.layer)).all()
    ]


@router.get("/evidence/{evidence_id}/model-runs", response_model=list[ModelRunResponse])
def model_runs(case_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> list[ModelRunResponse]:
    """Every provider call for this evidence, including both outputs when models disagreed."""
    require_case_access(db, case_id, current_user)
    _evidence(db, case_id, evidence_id)
    return [
        ModelRunResponse(
            id=item.id,
            record_key=item.record_key,
            provider=item.provider,
            model_name=item.model_name,
            prompt_version=item.prompt_version,
            role=item.role,
            status=item.status,
            raw_output=item.raw_output,
            parsed_payload=item.parsed_payload,
            grounding_report=item.grounding_report,
            error=item.error_json,
            latency_ms=item.latency_ms,
            created_at=item.created_at,
        )
        for item in db.scalars(
            select(ModelInferenceRun)
            .where(ModelInferenceRun.evidence_id == evidence_id)
            .order_by(ModelInferenceRun.created_at)
        ).all()
    ]


@router.get("/records", response_model=NormalizedRecordPage)
def list_records(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    evidence_id: str | None = Query(default=None),
    band: str | None = Query(default=None, pattern="^(high|medium|low|unknown)$"),
    requires_review: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> NormalizedRecordPage:
    require_case_access(db, case_id, current_user)

    filters = [NormalizedRecord.case_id == case_id]
    if evidence_id:
        filters.append(NormalizedRecord.evidence_id == evidence_id)
    if band:
        filters.append(NormalizedRecord.final_confidence_band == band)
    if requires_review is not None:
        filters.append(NormalizedRecord.requires_human_review.is_(requires_review))

    total = db.scalar(select(func.count(NormalizedRecord.id)).where(*filters)) or 0
    rows = db.scalars(
        select(NormalizedRecord).where(*filters).order_by(NormalizedRecord.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return NormalizedRecordPage(items=[_record_response(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/review-queue", response_model=ReviewQueuePage)
def review_queue(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReviewQueuePage:
    """Records the system will not stand behind on its own."""
    require_case_access(db, case_id, current_user)

    filters = [NormalizedRecord.case_id == case_id, NormalizedRecord.requires_human_review.is_(True)]
    total = db.scalar(select(func.count(NormalizedRecord.id)).where(*filters)) or 0
    rows = db.scalars(
        select(NormalizedRecord)
        .where(*filters)
        .order_by(NormalizedRecord.final_confidence_band.desc(), NormalizedRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    names = dict(
        db.execute(select(EvidenceFile.id, EvidenceFile.original_name).where(EvidenceFile.case_id == case_id)).all()
    )
    relations = db.scalars(select(RecordRelation).where(RecordRelation.case_id == case_id)).all()

    items = [
        ReviewQueueItem(
            record=_record_response(row),
            evidence_name=names.get(row.evidence_id, "Unknown evidence"),
            relations=[_relation_response(relation) for relation in relations if row.id in (relation.record_ids or [])],
        )
        for row in rows
    ]
    return ReviewQueuePage(items=items, total=total, limit=limit, offset=offset)


@router.post("/records/{record_id}/review", response_model=RecordReviewResponse)
def review_record(
    case_id: str,
    record_id: str,
    payload: RecordReviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> RecordReviewResponse:
    require_case_access(db, case_id, current_user)
    review = record_review.review_record(
        db,
        case_id=case_id,
        record_id=record_id,
        action=payload.action,
        reviewer_id=current_user.id,
        field_name=payload.field_name,
        new_value=payload.new_value,
        reason=payload.reason,
    )
    audit(
        db,
        action="grounded.record_review",
        object_type="normalized_record",
        object_id=record_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"review_action": payload.action.value, "field": payload.field_name},
    )
    db.commit()
    return _review_response(review)


@router.get("/records/{record_id}/history", response_model=list[RecordReviewResponse])
def record_history(case_id: str, record_id: str, current_user: CurrentUser, db: DbSession) -> list[RecordReviewResponse]:
    require_case_access(db, case_id, current_user)
    return [_review_response(item) for item in record_review.history_for_record(db, case_id=case_id, record_id=record_id)]


@router.get("/relations", response_model=RelationPage)
def list_relations(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    relation_type: str | None = Query(default=None, pattern="^(corroboration|contradiction)$"),
    relation_status: str | None = Query(default=None, pattern="^(candidate|confirmed|rejected)$", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RelationPage:
    """Candidate corroborations and contradictions. Nothing here is a settled finding."""
    require_case_access(db, case_id, current_user)

    filters = [RecordRelation.case_id == case_id]
    if relation_type:
        filters.append(RecordRelation.relation_type == relation_type)
    if relation_status:
        filters.append(RecordRelation.status == relation_status)

    total = db.scalar(select(func.count(RecordRelation.id)).where(*filters)) or 0
    rows = db.scalars(
        select(RecordRelation).where(*filters).order_by(RecordRelation.confidence.desc()).limit(limit).offset(offset)
    ).all()
    return RelationPage(items=[_relation_response(row) for row in rows], total=total, limit=limit, offset=offset)


@router.post("/relations/{relation_id}/review", response_model=RecordReviewResponse)
def review_relation(
    case_id: str,
    relation_id: str,
    payload: RelationReviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> RecordReviewResponse:
    require_case_access(db, case_id, current_user)
    review = record_review.review_relation(
        db,
        case_id=case_id,
        relation_id=relation_id,
        action=payload.action,
        reviewer_id=current_user.id,
        reason=payload.reason,
    )
    audit(
        db,
        action="grounded.relation_review",
        object_type="record_relation",
        object_id=relation_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"review_action": payload.action.value},
    )
    db.commit()
    return _review_response(review)


@router.post("/evidence/{evidence_id}/reanalyze", status_code=status.HTTP_202_ACCEPTED)
def reanalyze(case_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Queue a reviewer-requested re-analysis, which forces escalation for this evidence."""
    require_case_access(db, case_id, current_user)
    evidence = _evidence(db, case_id, evidence_id)
    audit(
        db,
        action="grounded.reanalyze",
        object_type="evidence_file",
        object_id=evidence.id,
        case_id=case_id,
        outcome="queued",
        actor_id=current_user.id,
    )
    db.commit()

    from app.workers.tasks import reanalyze_evidence_task

    reanalyze_evidence_task.delay(evidence.id)
    return {"evidence_id": evidence.id, "status": "queued", "forced_escalation": True}


# --------------------------------------------------------------------------- entity relations


def _entity_endpoint(entity: Entity | None, entity_id: str) -> EntityEndpointResponse:
    return EntityEndpointResponse(
        id=entity_id,
        label=entity.value if entity else None,
        type=entity.entity_type if entity else None,
    )


def _entity_relation_response(row: EntityRelation, entities: dict[str, Entity]) -> EntityRelationObservation:
    return EntityRelationObservation(
        id=row.id,
        relation_type=row.relation_type,
        directed=row.directed,
        basis=row.basis,
        subject=_entity_endpoint(entities.get(row.subject_entity_id), row.subject_entity_id),
        object=_entity_endpoint(entities.get(row.object_entity_id), row.object_entity_id),
        source_evidence_id=row.source_evidence_id,
        source_record_id=row.source_record_id,
        source_reference=dict(row.source_reference or {}),
        observed_at=row.observed_at,
        time_precision=row.time_precision,
        confidence=float(row.confidence),
        verification_status=row.verification_status,
        review_note=row.review_note,
        created_at=row.created_at,
    )


@router.get("/entity-relations", response_model=EntityRelationPage)
def list_entity_relations(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    relation_type: str | None = None,
    entity_id: str | None = None,
    verification_status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> EntityRelationPage:
    """Individual observations, each openable at the exact source region it came from."""
    require_case_access(db, case_id, current_user)

    conditions = [EntityRelation.case_id == case_id]
    if relation_type:
        conditions.append(EntityRelation.relation_type == relation_type)
    if verification_status:
        conditions.append(EntityRelation.verification_status == verification_status)
    if entity_id:
        conditions.append(
            or_(EntityRelation.subject_entity_id == entity_id, EntityRelation.object_entity_id == entity_id)
        )

    total = db.scalar(select(func.count()).select_from(EntityRelation).where(*conditions)) or 0
    rows = db.scalars(
        select(EntityRelation)
        .where(*conditions)
        .order_by(EntityRelation.confidence.desc(), EntityRelation.created_at)
        .limit(limit)
        .offset(offset)
    ).all()
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()}
    return EntityRelationPage(
        items=[_entity_relation_response(row, entities) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/entity-relations/summary", response_model=list[EntityRelationSummary])
def summarize_entity_relations(case_id: str, current_user: CurrentUser, db: DbSession) -> list[EntityRelationSummary]:
    """Distinct relationships, ranked by how many independent sources support each one.

    Ten mentions inside one file are one source. Two mentions across two files are corroboration,
    and that is what should drive review priority.
    """
    require_case_access(db, case_id, current_user)
    return [EntityRelationSummary(**entry) for entry in relationship_builder.relation_summary(db, case_id)]


@router.post("/entity-relations/{relation_id}/review", response_model=EntityRelationObservation)
def review_entity_relation(
    case_id: str,
    relation_id: str,
    payload: EntityRelationReviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> EntityRelationObservation:
    """Confirm or reject one observation. The row is never deleted; the decision is recorded on it."""
    require_case_access(db, case_id, current_user)
    row = db.scalar(select(EntityRelation).where(EntityRelation.id == relation_id, EntityRelation.case_id == case_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found in this case.")

    row.verification_status = "human_verified" if payload.action == "confirm_relationship" else "rejected"
    row.reviewed_by_id = current_user.id
    row.reviewed_at = utcnow()
    row.review_note = payload.reason

    audit(
        db,
        action="grounded.entity_relation_review",
        object_type="entity_relation",
        object_id=relation_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"review_action": payload.action, "relation_type": row.relation_type},
    )
    db.commit()
    db.refresh(row)
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()}
    return _entity_relation_response(row, entities)


# --------------------------------------------------------------------------- network analytics


@router.get("/network/overview", response_model=NetworkOverviewResponse)
def network_overview(case_id: str, current_user: CurrentUser, db: DbSession) -> NetworkOverviewResponse:
    require_case_access(db, case_id, current_user)
    return NetworkOverviewResponse(**analytics.network_overview(db, case_id))


@router.get("/network/important", response_model=list[ImportantEntityResponse])
def important_entities(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    metric: Literal["betweenness_centrality", "degree_centrality", "eigenvector_centrality"] = "betweenness_centrality",
    entity_type: str | None = None,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    verified_only: bool = False,
    limit: int = Query(default=10, ge=1, le=100),
) -> list[ImportantEntityResponse]:
    """Entities ranked by network position, each carrying the reason it ranked there.

    This answers the problem statement's "identify influential individuals". The answer is always a
    sentence plus a caveat, never a bare score: a number on its own invites the reading that the
    system is scoring people for criminality, which it is not doing and must not appear to do.
    """
    require_case_access(db, case_id, current_user)
    return [
        ImportantEntityResponse(**entry)
        for entry in analytics.important_entities(
            db,
            case_id,
            metric=metric,
            limit=limit,
            entity_type=entity_type,
            min_confidence=min_confidence,
            verified_only=verified_only,
        )
    ]


@router.get("/network/bridges", response_model=list[BridgeRelationshipResponse])
def bridge_relationships(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> list[BridgeRelationshipResponse]:
    """Relationships whose removal would disconnect part of the network -- verify these first."""
    require_case_access(db, case_id, current_user)
    return [BridgeRelationshipResponse(**entry) for entry in analytics.bridge_relationships(db, case_id, min_confidence=min_confidence)]


@router.get("/network/communities", response_model=list[CommunityResponse])
def network_communities(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> list[CommunityResponse]:
    require_case_access(db, case_id, current_user)
    return [CommunityResponse(**entry) for entry in analytics.communities(db, case_id, min_confidence=min_confidence)]


@router.get("/network/path", response_model=NetworkPathResponse)
def network_path(
    case_id: str,
    source_entity_id: str,
    target_entity_id: str,
    current_user: CurrentUser,
    db: DbSession,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> NetworkPathResponse:
    """The best-supported chain between two entities. "No path" is returned as a real answer."""
    require_case_access(db, case_id, current_user)
    return NetworkPathResponse(**analytics.shortest_path(db, case_id, source_entity_id, target_entity_id, min_confidence=min_confidence))


@router.get("/network/subgraph", response_model=NetworkSubgraphResponse)
def network_subgraph(
    case_id: str,
    entity_id: str,
    current_user: CurrentUser,
    db: DbSession,
    hops: int = Query(default=1, ge=1, le=3),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> NetworkSubgraphResponse:
    """One entity's neighbourhood. The browser expands outward rather than loading a whole case."""
    require_case_access(db, case_id, current_user)
    return NetworkSubgraphResponse(**analytics.subgraph(db, case_id, entity_id, hops=hops, min_confidence=min_confidence))


# --------------------------------------------------------------------------- temporal


def _temporal_finding(entry: dict, entities: dict[str, Entity], detail: str) -> TemporalFindingResponse:
    left, right = entry["pair"]
    return TemporalFindingResponse(
        subject=_entity_endpoint(entities.get(left), left),
        object=_entity_endpoint(entities.get(right), right),
        contacts=entry["contacts"],
        first=entry["first"],
        last=entry["last"],
        evidence_ids=entry["evidence_ids"],
        relation_ids=entry["relation_ids"],
        detail=detail,
        minutes=entry.get("minutes"),
        hours_before=entry.get("hours_before"),
    )


@router.get("/temporal/chronology", response_model=CaseChronologyResponse)
def case_chronology(case_id: str, current_user: CurrentUser, db: DbSession) -> CaseChronologyResponse:
    """Contact placed before, during and after the declared incident window.

    A case with no declared window says so rather than inventing one, and contact whose time was
    never established is reported rather than quietly folded into a bucket.
    """
    require_case_access(db, case_id, current_user)
    return CaseChronologyResponse(**temporal.case_chronology(db, case_id))


@router.get("/temporal/pre-incident", response_model=list[TemporalFindingResponse])
def pre_incident_contacts(case_id: str, current_user: CurrentUser, db: DbSession) -> list[TemporalFindingResponse]:
    """Pairs repeatedly in contact in the hours before the incident window opens."""
    require_case_access(db, case_id, current_user)
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()}
    return [
        _temporal_finding(
            entry,
            entities,
            f"{entry['contacts']} contacts, the last {entry['hours_before']} hours before the incident window opens.",
        )
        for entry in temporal.pre_incident_contacts(db, case_id)
    ]


@router.get("/temporal/bursts", response_model=list[TemporalFindingResponse])
def communication_bursts(case_id: str, current_user: CurrentUser, db: DbSession) -> list[TemporalFindingResponse]:
    """Contact between one pair repeated inside a short span."""
    require_case_access(db, case_id, current_user)
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()}
    return [
        _temporal_finding(entry, entities, f"{entry['contacts']} contacts within {entry['minutes']} minutes.")
        for entry in temporal.communication_bursts(db, case_id)
    ]


LEDGER_CAVEAT = (
    "The shared ledger holds only a keyed digest of each identifier, a case reference and a contact. It can say "
    "that another force holds this identity; it cannot say what their case is, what they found, or whether the two "
    "are related. That is a conversation to have with the officer named."
)


# --------------------------------------------------------------------------- case assistant


@router.get("/entities/{entity_id}/profile")
def read_entity_profile(case_id: str, entity_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Everything this case records about one identity, and whether another case knows it too.

    Only cases the reader can already open are named. An identifier appearing in two cases is a
    lead to follow with the officer holding the other one; nothing of that case's content is
    described here.
    """
    require_case_access(db, case_id, current_user)
    profile = entity_profile.build(db, case_id, entity_id, current_user)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found in this case")
    audit(
        db,
        action="grounded.entity_profile",
        object_type="entity",
        object_id=entity_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"other_cases": len(profile.other_cases)},
    )
    db.commit()
    return profile.to_dict()


@router.get("/requisition/draft")
def requisition_draft(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Draft what to request next, from what this case already records.

    The system drafts; it does not submit. What comes back is text an officer reads, edits and sends
    under their own name -- a requisition is a legal instrument and must carry a person's judgement,
    not a system's output. Nothing here is addressed, signed or transmitted.
    """
    case = require_case_access(db, case_id, current_user)
    draft = requisition.build(db, case_id, case.case_number)
    audit(
        db,
        action="requisition.draft",
        object_type="case",
        object_id=case_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"subjects": len(draft.subjects)},
    )
    db.commit()
    return draft.to_dict()


@router.get("/entities/{entity_id}/prior-record")
def read_entity_prior_record(case_id: str, entity_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """What the national record of registered cases already holds about this identity.

    A different source from the shared ledger and a different question. The ledger says another
    force is working a live case touching this identity and holds nothing else; this reads a store
    that is entitled to hold the details of cases already registered.

    Looking somebody up in a criminal record is an act worth recording, whatever it returns. An
    officer who ran the check has learned something about a person that the case in front of them
    did not contain.
    """
    require_case_access(db, case_id, current_user)
    entity = db.scalar(select(Entity).where(Entity.id == entity_id, Entity.case_id == case_id))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found in this case")

    found = prior_record.lookup(db, entity)
    audit(
        db,
        action="prior_record.lookup",
        object_type="entity",
        object_id=entity_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"entries": len(found.entries)},
    )
    db.commit()
    return found.to_dict()


@router.get("/entities/{entity_id}/elsewhere")
def read_entity_elsewhere(case_id: str, entity_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Whether a force this reader has no access to is already looking for the same identity.

    The profile's own "known to other cases" section lists cases the reader can already open. This
    is the other half, and the harder one: an identifier held by a district whose file this reader
    may never see. The ledger can answer it because it holds nothing but keyed digests -- the reply
    is a case reference and an officer to ring, and there is no field in it that could carry
    anything about what that case contains.

    Asking is itself an access event and is recorded as one. A reader who runs this check has
    learned that another force's case exists, which is not nothing, even when the answer is no.
    """
    case = require_case_access(db, case_id, current_user)
    entity = db.scalar(select(Entity).where(Entity.id == entity_id, Entity.case_id == case_id))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found in this case")

    try:
        found = ledger.matches_for_identity(db, case, entity)
    except ledger.LedgerClosed:
        # Not an error to the reader: the ledger being off is a deployment decision, and a profile
        # that failed to load because of it would be worse than one that says the check is unavailable.
        return {
            "available": False,
            "matches": [],
            "note": ledger.CLOSED_GATE,
            "caveat": LEDGER_CAVEAT,
        }

    audit(
        db,
        action="ledger.identity_check",
        object_type="entity",
        object_id=entity_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"matches": len(found)},
    )
    db.commit()
    return {
        "available": True,
        "matches": [item.to_dict() for item in found],
        "note": (
            f"{len(found)} other case(s) hold this identity."
            if found
            else "No case published to the shared ledger holds this identity. That is not a statement about cases "
            "whose force has not published to it."
        ),
        "caveat": LEDGER_CAVEAT,
    }


@router.get("/entities/{entity_id}/summary")
def read_entity_summary(case_id: str, entity_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Who this identity is, why it is in the case, and what it is not connected to.

    Assembled from stored rows rather than written, so every sentence carries the file and the
    place it was read from and the whole card can be checked line by line. No language model is
    involved, which is also why nothing about the case leaves this machine to produce it.
    """
    require_case_access(db, case_id, current_user)
    summary = entity_summary.build(db, case_id, entity_id)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found in this case")
    return summary.to_dict()


@router.post("/assistant/ask", response_model=CaseAssistantResponse)
def ask_case_assistant(
    case_id: str,
    payload: CaseAssistantRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> CaseAssistantResponse:
    """Answer a question about this case, from this case's own rows.

    Authorisation is checked before anything is read, so a question can never be used to discover
    whether an identifier appears in a case the asker cannot open.

    Distinct from the Trace Orb help assistant, which explains the product and is unable to reach
    case data at all. This one reaches only case data, and only for one authorised case.
    """
    require_case_access(db, case_id, current_user)
    answer = case_assistant.ask(db, case_id, payload.question)
    audit(
        db,
        action="grounded.assistant_question",
        object_type="case",
        object_id=case_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        # The question is recorded, the answer is not: what a user asked is an access record, and
        # storing the composed reply would duplicate case content into the audit log.
        details={"intent": answer.intent, "question_length": len(payload.question)},
    )
    db.commit()
    return CaseAssistantResponse(**answer.to_dict())
