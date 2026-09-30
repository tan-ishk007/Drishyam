"""Reviewer decisions on grounded records and candidate relations.

Decisions are an append-only layer. The original evidence, the raw model output and the machine's
own reading are never overwritten — an edit records the previous value beside the new one.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.evidence_intelligence.schema import (
    FieldProvenance,
    ObservationBasis,
    RelationReviewAction,
    ReviewAction,
    ValidationStatus,
)
from app.models.entities import NormalizedRecord, RecordRelation, RecordReview

EDITABLE_FIELDS = {
    "event_type",
    "sender",
    "receiver",
    "participant_a",
    "participant_b",
    "message_direction",
    "chat_participant_identifier",
    "transaction_reference",
    "location",
    "device_identifier",
    "normalized_summary",
}

REVIEW_STATE_FOR_ACTION = {
    ReviewAction.CONFIRM: "confirmed",
    ReviewAction.EDIT: "corrected",
    ReviewAction.REJECT: "rejected",
    ReviewAction.MARK_UNKNOWN: "marked_unknown",
}


def _record(db: Session, case_id: str, record_id: str) -> NormalizedRecord:
    record = db.scalar(select(NormalizedRecord).where(NormalizedRecord.id == record_id, NormalizedRecord.case_id == case_id))
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Normalized record not found in this case")
    return record


def _relation(db: Session, case_id: str, relation_id: str) -> RecordRelation:
    relation = db.scalar(select(RecordRelation).where(RecordRelation.id == relation_id, RecordRelation.case_id == case_id))
    if not relation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate relation not found in this case")
    return relation


def review_record(
    db: Session,
    *,
    case_id: str,
    record_id: str,
    action: ReviewAction,
    reviewer_id: str,
    field_name: str | None = None,
    new_value: Any = None,
    reason: str | None = None,
) -> RecordReview:
    record = _record(db, case_id, record_id)

    if action in {ReviewAction.EDIT, ReviewAction.MARK_UNKNOWN}:
        if not field_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A field name is required for this review action")
        if field_name not in EDITABLE_FIELDS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This field cannot be edited by review")

    previous_value = getattr(record, field_name) if field_name else None
    applied_value: Any = None

    if action is ReviewAction.EDIT:
        applied_value = new_value
        setattr(record, field_name, new_value)
        record.field_provenance = {
            **record.field_provenance,
            field_name: FieldProvenance(
                value=new_value,
                basis=ObservationBasis.DIRECT,
                reason=reason or "Set by a human reviewer.",
                validation_status=ValidationStatus.VALIDATED,
                confidence=1.0,
            ).model_dump(mode="json"),
        }
    elif action is ReviewAction.MARK_UNKNOWN:
        setattr(record, field_name, None)
        record.field_provenance = {
            **record.field_provenance,
            field_name: FieldProvenance(
                value=None,
                basis=ObservationBasis.UNKNOWN,
                reason=reason or "A reviewer determined the source does not establish this field.",
                validation_status=ValidationStatus.UNVALIDATED,
            ).model_dump(mode="json"),
        }

    record.review_state = REVIEW_STATE_FOR_ACTION[action]
    # A reviewed record leaves the queue, but its machine-generated reasoning stays on the row.
    record.requires_human_review = False
    record.updated_at = utcnow()

    review = RecordReview(
        case_id=case_id,
        record_id=record.id,
        action=action.value,
        field_name=field_name,
        previous_value={"value": previous_value} if field_name else None,
        new_value={"value": applied_value} if action is ReviewAction.EDIT else None,
        reason=reason,
        reviewer_id=reviewer_id,
    )
    db.add(review)
    db.flush()
    return review


def review_relation(
    db: Session,
    *,
    case_id: str,
    relation_id: str,
    action: RelationReviewAction,
    reviewer_id: str,
    reason: str | None = None,
) -> RecordReview:
    relation = _relation(db, case_id, relation_id)
    previous_status = relation.status

    relation.status = "confirmed" if action is RelationReviewAction.CONFIRM_RELATIONSHIP else "rejected"
    relation.review_decision = action.value
    relation.reviewed_by_id = reviewer_id
    relation.reviewed_at = utcnow()
    relation.requires_human_review = False

    review = RecordReview(
        case_id=case_id,
        relation_id=relation.id,
        action=action.value,
        previous_value={"status": previous_status},
        new_value={"status": relation.status},
        reason=reason,
        reviewer_id=reviewer_id,
    )
    db.add(review)
    db.flush()
    return review


def history_for_record(db: Session, *, case_id: str, record_id: str) -> list[RecordReview]:
    _record(db, case_id, record_id)
    return list(
        db.scalars(
            select(RecordReview)
            .where(RecordReview.case_id == case_id, RecordReview.record_id == record_id)
            .order_by(RecordReview.created_at.desc())
        ).all()
    )
