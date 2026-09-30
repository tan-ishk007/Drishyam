"""Explainable, idempotent rules that surface reviewable leads rather than guilt assertions.

These read the transaction and event tables and are shaped for payment fraud; `network_rules.py`
reads the typed relationship graph. Both families end up on the same alerts page, so both carry a
sequence: an alerts list where some entries show their working and others hand the reader a count
teaches the reader to trust the count.
"""

from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import narrative
from app.alerts.narrative import Step
from app.models.entities import Alert, Entity, Event, EvidenceFile, Severity, Transaction


def _alert(db: Session, *, case_id: str, rule_code: str, key: str, severity: Severity, explanation: str, evidence_ids: list[str], event_id: str | None = None, sequence: list[dict] | None = None) -> None:
    """Record one lead, at most once per case, however many times the rule reaches it.

    The stored-row check alone is not enough. `db.add` only queues the row, so a second call in the
    same run -- the same recipient reached down two paths, or a file reprocessed after a retry --
    issues its SELECT against a table that does not hold the pending insert yet, decides the alert
    is new, and adds it again. Both rows then land in one batch and the unique index rejects the
    statement, which fails the whole file over a duplicate lead nobody needed.

    So the pending inserts are consulted too. Flushing here instead would work, but it would commit
    this session's partial work to the transaction on every rule, and a rule deciding when the
    pipeline's writes become visible is a worse trade than reading the session first.
    """
    idempotency_key = f"{case_id}:{rule_code}:{key}"
    if db.scalar(select(Alert).where(Alert.idempotency_key == idempotency_key)):
        return
    if any(isinstance(pending, Alert) and pending.idempotency_key == idempotency_key for pending in db.new):
        return
    db.add(Alert(case_id=case_id, rule_code=rule_code, severity=severity, explanation=explanation, affected_evidence_ids=evidence_ids, related_event_id=event_id, sequence=sequence, idempotency_key=idempotency_key))


def _transfer_step(transaction: Transaction) -> Step:
    """One documented transfer, as a line of the story it belongs to.

    A transaction row records the parties, the amount and the file it was read from, but not the
    page or row inside that file, so the line names its file and stops there. Naming a place it does
    not have would send a reader looking for something that is not written down.
    """
    sender = transaction.sender_value or "an unrecorded sender"
    receiver = transaction.receiver_value or "an unrecorded recipient"
    amount = f"{transaction.currency or 'INR'} {float(transaction.amount):,.2f}"
    reference = f" Reference {transaction.reference_id}." if transaction.reference_id else ""
    return Step(
        statement=f"{sender} is recorded transferring {amount} to {receiver}.{reference}",
        when=transaction.occurred_at,
        evidence_id=transaction.source_evidence_id,
    )


def _event_step(event: Event) -> Step:
    return Step(
        statement=f"{event.description.rstrip('.')}.",
        when=event.occurred_at,
        evidence_id=event.source_file_id,
    )


def evaluate_alerts(db: Session, case_id: str) -> int:
    transactions = db.scalars(select(Transaction).where(Transaction.case_id == case_id).order_by(Transaction.occurred_at)).all()
    events = db.scalars(select(Event).where(Event.case_id == case_id)).all()
    entities = db.scalars(select(Entity).where(Entity.case_id == case_id)).all()
    for transaction in transactions:
        if float(transaction.amount) >= 50_000:
            _alert(db, case_id=case_id, rule_code="HIGH_VALUE_TRANSFER", key=transaction.id, severity=Severity.HIGH, explanation=f"Review lead: a documented transfer of INR {float(transaction.amount):,.2f} exceeds the high-value threshold.", evidence_ids=[transaction.source_evidence_id], event_id=transaction.event_id, sequence=narrative.sequence([_transfer_step(transaction)], gaps=False))
    recipients = Counter(str(item.receiver_value).lower() for item in transactions if item.receiver_value)
    for receiver, count in recipients.items():
        if count >= 2:
            matching = [item for item in transactions if str(item.receiver_value).lower() == receiver]
            _alert(db, case_id=case_id, rule_code="REPEATED_RECIPIENT", key=receiver, severity=Severity.CRITICAL, explanation=f"Review lead: {count} documented transfers reference the same recipient identifier ({receiver}).", evidence_ids=[item.source_evidence_id for item in matching], event_id=matching[0].event_id, sequence=narrative.sequence(_transfer_step(item) for item in matching))
    indicators = Counter((item.entity_type, item.normalized_value) for item in entities)
    for (entity_type, value), count in indicators.items():
        if entity_type in {"upi", "upi_id", "phone", "email", "account"} and count >= 3:
            refs = [item for item in entities if (item.entity_type, item.normalized_value) == (entity_type, value)]
            _alert(db, case_id=case_id, rule_code="RECURRING_IDENTIFIER", key=f"{entity_type}:{value}", severity=Severity.HIGH, explanation=f"Review lead: the {entity_type} identifier '{value}' appears in {count} evidence-derived records.", evidence_ids=list({item.source_evidence_id for item in refs}), sequence=narrative.sequence(Step(statement=f"The identifier {item.value} is recorded here.", evidence_id=item.source_evidence_id) for item in refs))
    phishing = [event for event in events if event.event_type == "phishing_email"]
    if phishing and any(entity.entity_type == "url" for entity in entities):
        _alert(db, case_id=case_id, rule_code="PHISHING_LINK", key="case", severity=Severity.HIGH, explanation="Review lead: email evidence contains at least one extracted web link; verify the destination and sender independently.", evidence_ids=list({event.source_file_id for event in phishing}), event_id=phishing[0].id, sequence=narrative.sequence(_event_step(event) for event in phishing))
    dated = [item for item in transactions if item.occurred_at]
    for first, second in zip(dated, dated[1:]):
        if second.occurred_at - first.occurred_at <= timedelta(minutes=90):
            _alert(db, case_id=case_id, rule_code="RAPID_TRANSACTION_SEQUENCE", key=f"{first.id}:{second.id}", severity=Severity.MEDIUM, explanation="Review lead: two documented transfers are less than 90 minutes apart; verify whether their chronology forms a connected sequence.", evidence_ids=[first.source_evidence_id, second.source_evidence_id], event_id=second.event_id, sequence=narrative.sequence([_transfer_step(first), _transfer_step(second)], gaps=False))
            break
    return len(db.scalars(select(Alert).where(Alert.case_id == case_id)).all())
