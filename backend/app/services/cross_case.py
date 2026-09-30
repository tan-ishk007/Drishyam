"""Read-only, authorization-scoped exact identifier matching across accessible cases."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Case, CaseMembership, Entity, EvidenceFile, ReviewStatus, Role, Transaction, User


# Both extraction generations now mint nodes through one resolver, so this lists the resolver's
# vocabulary. The older spellings stay listed because cases processed before that change still
# carry them, and dropping them would silently stop matching on evidence already on record.
MATCHABLE_ENTITY_TYPES = {
    "phone", "email", "upi", "account", "ifsc", "reference", "url", "vehicle", "device",
    "upi_id", "account_number", "utr",
}
RELIABLE_REVIEW_STATUSES = {ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED}


def _authorized_case_ids(db: Session, user: User) -> set[str]:
    if user.role == Role.ADMIN:
        return set(db.scalars(select(Case.id)).all())
    owned = set(db.scalars(select(Case.id).where(Case.owner_id == user.id)).all())
    member = set(db.scalars(select(CaseMembership.case_id).where(CaseMembership.user_id == user.id)).all())
    return owned | member


def _review_posture(*statuses: ReviewStatus) -> str:
    return "reviewed" if all(status in RELIABLE_REVIEW_STATUSES for status in statuses) else "needs_review"


def _confidence(*statuses: ReviewStatus) -> str:
    return "high" if all(status in RELIABLE_REVIEW_STATUSES for status in statuses) else "medium"


def _case_map(db: Session, case_ids: set[str]) -> dict[str, Case]:
    if not case_ids:
        return {}
    return {row.id: row for row in db.scalars(select(Case).where(Case.id.in_(case_ids))).all()}


def _evidence_map(db: Session, evidence_ids: set[str]) -> dict[str, EvidenceFile]:
    if not evidence_ids:
        return {}
    return {row.id: row for row in db.scalars(select(EvidenceFile).where(EvidenceFile.id.in_(evidence_ids))).all()}


def _source(record_type: str, record_id: str, evidence: EvidenceFile | None, label: str, review_status: str) -> dict:
    return {
        "record_type": record_type,
        "record_id": record_id,
        "source_evidence_id": evidence.id if evidence else None,
        "source_label": evidence.original_name if evidence else label,
        "review_status": review_status,
    }


def _linked_case(case: Case) -> dict:
    return {"id": case.id, "case_number": case.case_number, "title": case.title, "status": case.status.value}


def find_cross_case_links(db: Session, case_id: str, user: User, *, limit: int = 80) -> list[dict]:
    """Return exact, explainable candidates only within the caller's authorized case scope.

    A returned candidate indicates a shared identifier or matching evidence hash. It does
    not identify a person, prove a connection, or establish legal responsibility.
    """
    visible_case_ids = _authorized_case_ids(db, user)
    comparison_case_ids = visible_case_ids - {case_id}
    if not comparison_case_ids:
        return []

    linked_cases = _case_map(db, comparison_case_ids)
    candidates: list[dict] = []

    current_entities = db.scalars(
        select(Entity).where(
            Entity.case_id == case_id,
            Entity.entity_type.in_(MATCHABLE_ENTITY_TYPES),
            Entity.review_status != ReviewStatus.REJECTED,
        )
    ).all()
    current_by_key = {(row.entity_type, row.normalized_value): row for row in current_entities if row.normalized_value}
    if current_by_key:
        other_entities = db.scalars(
            select(Entity).where(
                Entity.case_id.in_(comparison_case_ids),
                Entity.entity_type.in_(MATCHABLE_ENTITY_TYPES),
                Entity.review_status != ReviewStatus.REJECTED,
            )
        ).all()
        evidence = _evidence_map(db, {row.source_evidence_id for row in [*current_entities, *other_entities]})
        for linked in other_entities:
            current = current_by_key.get((linked.entity_type, linked.normalized_value))
            linked_case = linked_cases.get(linked.case_id)
            if not current or not linked_case:
                continue
            posture = _review_posture(current.review_status, linked.review_status)
            entity_label = linked.entity_type.replace("_", " ").upper()
            candidates.append(
                {
                    "id": f"entity:{current.id}:{linked.id}",
                    "signal_type": linked.entity_type,
                    "signal_label": entity_label,
                    "normalized_value": current.normalized_value,
                    "confidence": _confidence(current.review_status, linked.review_status),
                    "review_posture": posture,
                    "current_source": _source("entity", current.id, evidence.get(current.source_evidence_id), current.source_reference, current.review_status.value),
                    "linked_case": _linked_case(linked_case),
                    "linked_source": _source("entity", linked.id, evidence.get(linked.source_evidence_id), linked.source_reference, linked.review_status.value),
                    "explanation": f"Exact {entity_label} value occurs in two cases you are authorized to inspect. This is a reviewable lead, not an identity or culpability finding.",
                }
            )

    current_evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()
    current_by_hash = {row.sha256: row for row in current_evidence if row.sha256}
    if current_by_hash:
        other_evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id.in_(comparison_case_ids))).all()
        for linked in other_evidence:
            current = current_by_hash.get(linked.sha256)
            linked_case = linked_cases.get(linked.case_id)
            if not current or not linked_case:
                continue
            candidates.append(
                {
                    "id": f"evidence_sha256:{current.id}:{linked.id}",
                    "signal_type": "evidence_sha256",
                    "signal_label": "EVIDENCE SHA-256",
                    "normalized_value": current.sha256,
                    "confidence": "high",
                    "review_posture": "technical_match",
                    "current_source": _source("evidence", current.id, current, current.original_name, current.status.value),
                    "linked_case": _linked_case(linked_case),
                    "linked_source": _source("evidence", linked.id, linked, linked.original_name, linked.status.value),
                    "explanation": "The preserved files have the same SHA-256 hash. This is an exact binary match, not a conclusion about the people or events in either case.",
                }
            )

    current_transactions = db.scalars(
        select(Transaction).where(Transaction.case_id == case_id, Transaction.reference_id.is_not(None), Transaction.review_status != ReviewStatus.REJECTED)
    ).all()
    current_by_reference = {row.reference_id.strip().lower(): row for row in current_transactions if row.reference_id and row.reference_id.strip()}
    if current_by_reference:
        other_transactions = db.scalars(
            select(Transaction).where(
                Transaction.case_id.in_(comparison_case_ids),
                Transaction.reference_id.is_not(None),
                Transaction.review_status != ReviewStatus.REJECTED,
            )
        ).all()
        evidence = _evidence_map(db, {row.source_evidence_id for row in [*current_transactions, *other_transactions]})
        for linked in other_transactions:
            key = linked.reference_id.strip().lower() if linked.reference_id else ""
            current = current_by_reference.get(key)
            linked_case = linked_cases.get(linked.case_id)
            if not current or not linked_case:
                continue
            candidates.append(
                {
                    "id": f"transaction_reference:{current.id}:{linked.id}",
                    "signal_type": "transaction_reference",
                    "signal_label": "TRANSACTION REFERENCE",
                    "normalized_value": current.reference_id,
                    "confidence": _confidence(current.review_status, linked.review_status),
                    "review_posture": _review_posture(current.review_status, linked.review_status),
                    "current_source": _source("transaction", current.id, evidence.get(current.source_evidence_id), current.reference_id or "Transaction reference", current.review_status.value),
                    "linked_case": _linked_case(linked_case),
                    "linked_source": _source("transaction", linked.id, evidence.get(linked.source_evidence_id), linked.reference_id or "Transaction reference", linked.review_status.value),
                    "explanation": "An exact transaction reference occurs in two cases you are authorized to inspect. Confirm its documentary context before drawing any case-level conclusion.",
                }
            )

    unique: dict[str, dict] = {}
    for candidate in candidates:
        key = f"{candidate['signal_type']}:{candidate['normalized_value']}:{candidate['linked_case']['id']}:{candidate['linked_source']['record_id']}"
        unique.setdefault(key, candidate)
    confidence_rank = {"high": 0, "medium": 1}
    return sorted(unique.values(), key=lambda item: (confidence_rank.get(item["confidence"], 2), item["signal_label"], item["linked_case"]["case_number"]))[:limit]
