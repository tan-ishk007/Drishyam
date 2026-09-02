"""Human review service: derived records remain leads until a reviewer decides otherwise."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Alert, AlertStatus, Entity, Event, ReviewDecision, ReviewStatus, Transaction

SUBJECT_MODELS = {"event": Event, "entity": Entity, "transaction": Transaction, "alert": Alert}


def apply_review(db: Session, *, case_id: str, subject_type: str, subject_id: str, decision: ReviewStatus, note: str | None, reviewer_id: str) -> ReviewDecision:
    model = SUBJECT_MODELS.get(subject_type)
    if not model:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported review subject type")
    subject = db.scalar(select(model).where(model.id == subject_id, model.case_id == case_id))
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review subject not found in this case")
    if subject_type == "alert":
        subject.status = AlertStatus.DISMISSED if decision == ReviewStatus.REJECTED else AlertStatus.REVIEWED
    else:
        subject.review_status = decision
    review = ReviewDecision(case_id=case_id, subject_type=subject_type, subject_id=subject_id, decision=decision, note=note, reviewer_id=reviewer_id)
    db.add(review)
    return review

