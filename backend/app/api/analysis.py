"""Read-only derived case surfaces backed by real normalized records rather than demo JSON."""

from fastapi import APIRouter, Query
from sqlalchemy import String, cast, or_, select

from app.api.deps import CurrentUser, DbSession
from app.graph import build_case_graph
from app.models.entities import Alert, AuditLog, Entity, Event, EventEntity, EvidenceFile, ProcessingRun, Transaction
from app.schemas.evidence import AlertResponse, AuditLogResponse, CrossCaseLinkResponse, ProcessingRunResponse, SearchResultResponse, TimelineEventResponse, TransactionResponse
from app.services.cases import require_case_access
from app.services.cross_case import find_cross_case_links

router = APIRouter(prefix="/cases/{case_id}", tags=["analysis"])


@router.get("/timeline", response_model=list[TimelineEventResponse])
def timeline(case_id: str, current_user: CurrentUser, db: DbSession) -> list[TimelineEventResponse]:
    require_case_access(db, case_id, current_user)
    events = db.scalars(select(Event).where(Event.case_id == case_id).order_by(Event.occurred_at.nulls_last(), Event.created_at)).all()
    return [TimelineEventResponse(id=item.id, source_file_id=item.source_file_id, occurred_at=item.occurred_at, original_time=item.original_time, time_precision=item.time_precision, event_type=item.event_type, description=item.description, amount=float(item.amount) if item.amount is not None else None, currency=item.currency, confidence=float(item.confidence), review_status=item.review_status, entities=[{"id": link.entity.id, "type": link.entity.entity_type, "value": link.entity.value} for link in db.scalars(select(EventEntity).where(EventEntity.event_id == item.id)).all()]) for item in events]


@router.get("/graph")
def graph(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    require_case_access(db, case_id, current_user)
    return build_case_graph(db, case_id)


@router.get("/transactions", response_model=list[TransactionResponse])
def transactions(case_id: str, current_user: CurrentUser, db: DbSession) -> list[TransactionResponse]:
    require_case_access(db, case_id, current_user)
    rows = db.scalars(select(Transaction).where(Transaction.case_id == case_id).order_by(Transaction.occurred_at.nulls_last())).all()
    return [TransactionResponse(id=item.id, event_id=item.event_id, source_evidence_id=item.source_evidence_id, amount=float(item.amount), currency=item.currency, occurred_at=item.occurred_at, reference_id=item.reference_id, sender_value=item.sender_value, receiver_value=item.receiver_value, source_kind=item.source_kind, confidence=float(item.confidence), review_status=item.review_status) for item in rows]


@router.get("/alerts", response_model=list[AlertResponse])
def alerts(case_id: str, current_user: CurrentUser, db: DbSession) -> list[AlertResponse]:
    require_case_access(db, case_id, current_user)
    return [AlertResponse.model_validate(item, from_attributes=True) for item in db.scalars(select(Alert).where(Alert.case_id == case_id).order_by(Alert.generated_at.desc())).all()]


@router.get("/processing-runs", response_model=list[ProcessingRunResponse])
def processing_runs(case_id: str, current_user: CurrentUser, db: DbSession) -> list[ProcessingRunResponse]:
    """Return the persisted processing lifecycle; this endpoint never queues or retries work."""
    require_case_access(db, case_id, current_user)
    rows = db.execute(
        select(ProcessingRun, EvidenceFile)
        .join(EvidenceFile, ProcessingRun.evidence_id == EvidenceFile.id)
        .where(EvidenceFile.case_id == case_id)
        .order_by(ProcessingRun.created_at.desc())
    ).all()
    return [
        ProcessingRunResponse(
            id=run.id,
            evidence_id=run.evidence_id,
            evidence_name=evidence.original_name,
            pipeline_stage=run.pipeline_stage,
            pipeline_version=run.pipeline_version,
            state=run.state,
            attempt=run.attempt,
            progress=run.progress,
            warning_messages=run.warning_messages,
            failure_reason=run.failure_reason,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )
        for run, evidence in rows
    ]


@router.get("/audit", response_model=list[AuditLogResponse])
def audit_log(case_id: str, current_user: CurrentUser, db: DbSession) -> list[AuditLogResponse]:
    """Return case-scoped, hash-linked audit metadata without recording a new audit event."""
    require_case_access(db, case_id, current_user)
    entries = db.scalars(
        select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc()).limit(500)
    ).all()
    return [AuditLogResponse.model_validate(entry, from_attributes=True) for entry in entries]


@router.get("/cross-case-links", response_model=list[CrossCaseLinkResponse])
def cross_case_links(case_id: str, current_user: CurrentUser, db: DbSession) -> list[dict]:
    """Return exact cross-case leads only from cases the caller is authorized to inspect.

    The response is read-only and source-backed. It deliberately returns candidate
    links rather than asserting a shared person, event, or culpability.
    """
    require_case_access(db, case_id, current_user)
    return find_cross_case_links(db, case_id, current_user)


@router.get("/search", response_model=list[SearchResultResponse])
def search_case(
    case_id: str,
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=36, ge=1, le=60),
) -> list[SearchResultResponse]:
    """Search existing authorized case metadata without reading originals or creating audit activity."""
    require_case_access(db, case_id, current_user)
    term = q.strip()
    if not term:
        return []
    like = f"%{term}%"
    category_limit = min(10, limit)
    matches: list[SearchResultResponse] = []

    evidence_rows = db.scalars(
        select(EvidenceFile)
        .where(EvidenceFile.case_id == case_id, or_(EvidenceFile.original_name.ilike(like), EvidenceFile.sha256.ilike(like), EvidenceFile.source_category.ilike(like)))
        .order_by(EvidenceFile.uploaded_at.desc())
        .limit(category_limit)
    ).all()
    matches.extend(
        SearchResultResponse(
            kind="Evidence",
            id=item.id,
            target="Evidence Vault",
            title=item.original_name,
            excerpt=f"{item.source_category} · {item.status.value} · SHA-256 {item.sha256[:14]}…",
            details={"evidence_id": item.id, "source_category": item.source_category, "sha256": item.sha256, "status": item.status.value, "uploaded_at": item.uploaded_at.isoformat()},
        )
        for item in evidence_rows
    )

    entity_rows = db.scalars(
        select(Entity)
        .where(Entity.case_id == case_id, or_(Entity.value.ilike(like), Entity.normalized_value.ilike(like), Entity.entity_type.ilike(like)))
        .order_by(Entity.created_at.desc())
        .limit(category_limit)
    ).all()
    matches.extend(
        SearchResultResponse(
            kind="Entity",
            id=item.id,
            target="Entities & Graph",
            title=item.value,
            excerpt=f"{item.entity_type} · source evidence {item.source_evidence_id} · {item.review_status.value}",
            details={"entity_id": item.id, "entity_type": item.entity_type, "normalized_value": item.normalized_value, "source_evidence_id": item.source_evidence_id, "review_status": item.review_status.value},
        )
        for item in entity_rows
    )

    event_rows = db.scalars(
        select(Event)
        .where(Event.case_id == case_id, or_(Event.description.ilike(like), Event.event_type.ilike(like), Event.raw_text_reference.ilike(like)))
        .order_by(Event.created_at.desc())
        .limit(category_limit)
    ).all()
    matches.extend(
        SearchResultResponse(
            kind="Event",
            id=item.id,
            target="Timeline",
            title=item.event_type,
            excerpt=item.description[:240],
            details={"event_id": item.id, "source_evidence_id": item.source_file_id, "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None, "original_time": item.original_time, "time_precision": item.time_precision, "review_status": item.review_status.value},
        )
        for item in event_rows
    )

    transaction_rows = db.scalars(
        select(Transaction)
        .where(Transaction.case_id == case_id, or_(Transaction.reference_id.ilike(like), Transaction.sender_value.ilike(like), Transaction.receiver_value.ilike(like), Transaction.source_kind.ilike(like)))
        .order_by(Transaction.created_at.desc())
        .limit(category_limit)
    ).all()
    matches.extend(
        SearchResultResponse(
            kind="Transaction",
            id=item.id,
            target="Transactions",
            title=f"{item.currency} {float(item.amount):,.2f}",
            excerpt=f"{item.sender_value or 'Sender not supplied'} → {item.receiver_value or item.reference_id or 'Receiver/reference not supplied'}",
            details={"transaction_id": item.id, "reference_id": item.reference_id, "source_evidence_id": item.source_evidence_id, "event_id": item.event_id, "review_status": item.review_status.value},
        )
        for item in transaction_rows
    )

    alert_rows = db.scalars(
        select(Alert)
        .where(Alert.case_id == case_id, or_(Alert.rule_code.ilike(like), Alert.explanation.ilike(like), cast(Alert.status, String).ilike(like)))
        .order_by(Alert.generated_at.desc())
        .limit(category_limit)
    ).all()
    matches.extend(
        SearchResultResponse(
            kind="Alert",
            id=item.id,
            target="Alerts",
            title=item.rule_code,
            excerpt=item.explanation[:240],
            details={"alert_id": item.id, "severity": item.severity.value, "status": item.status.value, "affected_evidence_ids": item.affected_evidence_ids, "related_event_id": item.related_event_id},
        )
        for item in alert_rows
    )

    audit_rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.case_id == case_id, or_(AuditLog.action.ilike(like), AuditLog.object_type.ilike(like), AuditLog.object_id.ilike(like), AuditLog.outcome.ilike(like)))
        .order_by(AuditLog.created_at.desc())
        .limit(category_limit)
    ).all()
    matches.extend(
        SearchResultResponse(
            kind="Audit",
            id=item.id,
            target="Custody / Audit",
            title=item.action,
            excerpt=f"{item.object_type}{f' · {item.object_id}' if item.object_id else ''} · {item.outcome}",
            details={"audit_id": item.id, "object_type": item.object_type, "object_id": item.object_id, "outcome": item.outcome, "created_at": item.created_at.isoformat(), "event_hash": item.event_hash},
        )
        for item in audit_rows
    )

    return matches[:limit]
