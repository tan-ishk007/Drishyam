"""Explainable, idempotent rules that surface reviewable leads rather than guilt assertions."""

from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Alert, Entity, Event, EvidenceFile, Severity, Transaction


def _alert(db: Session, *, case_id: str, rule_code: str, key: str, severity: Severity, explanation: str, evidence_ids: list[str], event_id: str | None = None) -> None:
    idempotency_key = f"{case_id}:{rule_code}:{key}"
    if not db.scalar(select(Alert).where(Alert.idempotency_key == idempotency_key)):
        db.add(Alert(case_id=case_id, rule_code=rule_code, severity=severity, explanation=explanation, affected_evidence_ids=evidence_ids, related_event_id=event_id, idempotency_key=idempotency_key))


def evaluate_alerts(db: Session, case_id: str) -> int:
    transactions = db.scalars(select(Transaction).where(Transaction.case_id == case_id).order_by(Transaction.occurred_at)).all()
    events = db.scalars(select(Event).where(Event.case_id == case_id)).all()
    entities = db.scalars(select(Entity).where(Entity.case_id == case_id)).all()
    for transaction in transactions:
        if float(transaction.amount) >= 50_000:
            _alert(db, case_id=case_id, rule_code="HIGH_VALUE_TRANSFER", key=transaction.id, severity=Severity.HIGH, explanation=f"Review lead: a documented transfer of INR {float(transaction.amount):,.2f} exceeds the high-value threshold.", evidence_ids=[transaction.source_evidence_id], event_id=transaction.event_id)
    recipients = Counter(str(item.receiver_value).lower() for item in transactions if item.receiver_value)
    for receiver, count in recipients.items():
        if count >= 2:
            matching = [item for item in transactions if str(item.receiver_value).lower() == receiver]
            _alert(db, case_id=case_id, rule_code="REPEATED_RECIPIENT", key=receiver, severity=Severity.CRITICAL, explanation=f"Review lead: {count} documented transfers reference the same recipient identifier ({receiver}).", evidence_ids=[item.source_evidence_id for item in matching], event_id=matching[0].event_id)
    indicators = Counter((item.entity_type, item.normalized_value) for item in entities)
    for (entity_type, value), count in indicators.items():
        if entity_type in {"upi_id", "phone", "email"} and count >= 3:
            refs = [item for item in entities if (item.entity_type, item.normalized_value) == (entity_type, value)]
            _alert(db, case_id=case_id, rule_code="RECURRING_IDENTIFIER", key=f"{entity_type}:{value}", severity=Severity.HIGH, explanation=f"Review lead: the {entity_type} identifier '{value}' appears in {count} evidence-derived records.", evidence_ids=list({item.source_evidence_id for item in refs}))
    phishing = [event for event in events if event.event_type == "phishing_email"]
    if phishing and any(entity.entity_type == "url" for entity in entities):
        _alert(db, case_id=case_id, rule_code="PHISHING_LINK", key="case", severity=Severity.HIGH, explanation="Review lead: email evidence contains at least one extracted web link; verify the destination and sender independently.", evidence_ids=list({event.source_file_id for event in phishing}), event_id=phishing[0].id)
    dated = [item for item in transactions if item.occurred_at]
    for first, second in zip(dated, dated[1:]):
        if second.occurred_at - first.occurred_at <= timedelta(minutes=90):
            _alert(db, case_id=case_id, rule_code="RAPID_TRANSACTION_SEQUENCE", key=f"{first.id}:{second.id}", severity=Severity.MEDIUM, explanation="Review lead: two documented transfers are less than 90 minutes apart; verify whether their chronology forms a connected sequence.", evidence_ids=[first.source_evidence_id, second.source_evidence_id], event_id=second.event_id)
            break
    return len(db.scalars(select(Alert).where(Alert.case_id == case_id)).all())
