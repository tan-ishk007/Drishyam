"""What arrived in a case since this reader last opened it.

Coming back to a case after a week means reading everything again to find the three things that
changed. This answers that before anything else on the page does.

Per reader, and only about things that reader could already see. The digest is assembled from rows
in the case they have access to; it reports counts and names of things inside their own case, never
anything from elsewhere, and it makes no claim about what any of it means. New evidence arriving is
a fact about the case file. Whether it matters is the investigator's read.

An unchanged case says so plainly. A digest that padded a quiet week with restated old facts would
teach the reader to skip it, which costs more than showing nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.entities import (
    Alert,
    CaseNote,
    CaseVisit,
    EntityRelation,
    EvidenceFile,
    ReviewDecision,
    User,
)

WHATS_NEW_VERSION = "whats-new-v1"

FIRST_VISIT = (
    "This is the first time you have opened this case, so there is nothing to compare against. What is here is "
    "everything the case holds."
)
NOTHING_NEW = "Nothing has been added to this case since you last opened it."


@dataclass
class Change:
    kind: str
    count: int
    detail: str
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "count": self.count, "detail": self.detail, "examples": self.examples}


@dataclass
class Digest:
    since: str | None
    first_visit: bool
    changes: list[Change] = field(default_factory=list)
    statement: str = ""
    version: str = WHATS_NEW_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "since": self.since,
            "first_visit": self.first_visit,
            "changes": [item.to_dict() for item in self.changes],
            "statement": self.statement,
            "version": self.version,
        }


def _since(db: Session, case_id: str, user: User) -> datetime | None:
    visit = db.scalar(select(CaseVisit).where(CaseVisit.case_id == case_id, CaseVisit.user_id == user.id))
    return visit.last_opened_at if visit else None


def build(db: Session, case_id: str, user: User) -> Digest:
    """What has arrived since this reader's previous visit. Reading does not update the mark."""
    since = _since(db, case_id, user)
    if since is None:
        return Digest(since=None, first_visit=True, statement=FIRST_VISIT)

    digest = Digest(since=since.isoformat(), first_visit=False)

    files = list(
        db.scalars(
            select(EvidenceFile)
            .where(EvidenceFile.case_id == case_id, EvidenceFile.uploaded_at > since)
            .order_by(EvidenceFile.uploaded_at)
        )
    )
    if files:
        digest.changes.append(Change(
            kind="evidence",
            count=len(files),
            detail="New evidence has been added to this case. Whether it changes anything is your read of it.",
            examples=[item.original_name for item in files[:4]],
        ))

    relations = db.scalar(
        select(func.count())
        .select_from(EntityRelation)
        .where(EntityRelation.case_id == case_id, EntityRelation.created_at > since)
    )
    if relations:
        digest.changes.append(Change(
            kind="relationships",
            count=int(relations),
            detail=(
                "Relationships have been read out of the evidence since your last visit. Each one states what a "
                "source records, not that anything was established."
            ),
        ))

    alerts = list(
        db.scalars(
            select(Alert).where(Alert.case_id == case_id, Alert.generated_at > since).order_by(Alert.generated_at)
        )
    )
    if alerts:
        digest.changes.append(Change(
            kind="patterns",
            count=len(alerts),
            detail="Rules have found patterns since your last visit. A pattern is a reason to look, not a finding.",
            examples=sorted({item.rule_code for item in alerts})[:4],
        ))

    reviews = db.scalar(
        select(func.count())
        .select_from(ReviewDecision)
        .where(ReviewDecision.case_id == case_id, ReviewDecision.created_at > since)
    )
    if reviews:
        digest.changes.append(Change(
            kind="review decisions",
            count=int(reviews),
            detail="Somebody on this case has confirmed, corrected or rejected records since you were last here.",
        ))

    notes = list(
        db.scalars(
            select(CaseNote)
            .where(CaseNote.case_id == case_id, CaseNote.created_at > since, CaseNote.deleted_at.is_(None))
            .order_by(CaseNote.created_at)
        )
    )
    if notes:
        digest.changes.append(Change(
            kind="investigator notes",
            count=len(notes),
            detail="Colleagues have written down what they know. Notes are commentary, not evidence.",
        ))

    if not digest.changes:
        digest.statement = NOTHING_NEW
    else:
        parts = ", ".join(f"{item.count} {item.kind}" for item in digest.changes)
        digest.statement = f"Since you last opened this case: {parts}."
    return digest


def record_visit(db: Session, case_id: str, user: User) -> None:
    """Mark this reader as having seen the case as it now stands.

    Separate from building the digest on purpose. If reading the digest also moved the mark, a
    reader who glanced at it and got called away would never see those changes again.
    """
    visit = db.scalar(select(CaseVisit).where(CaseVisit.case_id == case_id, CaseVisit.user_id == user.id))
    if visit is None:
        db.add(CaseVisit(case_id=case_id, user_id=user.id, last_opened_at=utcnow()))
    else:
        visit.last_opened_at = utcnow()
