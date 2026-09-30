"""Project source-grounded records onto the case surfaces the product already renders.

Timeline, transactions, graph, alerts and the PDF all read `Event` and `Transaction`. Rather than
rewrite every one of those readers, the grounded record is projected into them — so a screenshot
that the model actually understood stops showing up as "Not extracted".

Two rules hold this together:

* Projection is **idempotent**. Each grounded record owns exactly one projected event, addressed by
  `payload_json.grounded_record_id`, so reprocessing updates rather than duplicates.
* Projection **fills gaps, never overwrites**. A legacy row that already carries a reviewed value
  keeps it; only fields the deterministic pipeline left null are enriched.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Entity,
    Event,
    EventEntity,
    NormalizedRecord,
    ReviewStatus,
    Transaction,
)

logger = logging.getLogger(__name__)

PROJECTION_VERSION = "grounded-projection-v1"
PROJECTED_METHOD = "grounded_pipeline"

# Confidence bands the projection is willing to surface. A record the system could not validate at
# all stays in the review queue instead of appearing on the timeline as though it were established.
PROJECTABLE_BANDS = {"high", "medium", "low", "unknown"}

# The resolver decides what type each observed value belongs to, so projection and identity
# resolution mint the same node instead of one writing "upi_id" while the other writes "upi".
_ENTITY_FIELDS = ("phone_numbers", "email_addresses", "account_identifiers")

# How close two amounts must be to be the same payment. Amounts are stored as money, not floats,
# so this only absorbs rounding, never a different figure.
AMOUNT_TOLERANCE = 0.01

# A balance is a position, not a transfer. It belongs on the timeline — an investigator wants to see
# that an email quoted a figure of INR 29,500 — but putting it in the transaction trail asserts that
# somebody moved that money, and adds it into the case total as though they had.
NON_TRANSACTIONAL_AMOUNT_ROLES = {"balance"}


def _confidence_for(record: NormalizedRecord) -> float:
    if record.validation_confidence is not None:
        return float(record.validation_confidence)
    if record.model_confidence is not None:
        return float(record.model_confidence)
    return 0.5


def _description(record: NormalizedRecord) -> str:
    """What a reviewer reads on the timeline: the interpretation, then the source words."""
    parts: list[str] = []
    if record.normalized_summary:
        parts.append(record.normalized_summary.strip())
    if record.observed_text:
        observed = " ".join(record.observed_text.split())
        parts.append(f"Source text: {observed}")
    return ("\n\n".join(parts) or record.source_file_name)[:4000]


def _event_type(record: NormalizedRecord) -> str:
    if record.amount_value is not None and not _is_transactional(record):
        # Whatever the model called it, the source called it a balance.
        return "observed_balance"
    if record.event_type:
        return record.event_type[:80]
    return "observed_record" if record.amount_value is None else "financial_transaction"


def _existing_event(db: Session, record: NormalizedRecord) -> Event | None:
    for event in db.scalars(select(Event).where(Event.case_id == record.case_id, Event.source_file_id == record.evidence_id)).all():
        if (event.payload_json or {}).get("grounded_record_id") == record.id:
            return event
    return None


def _project_entities(db: Session, record: NormalizedRecord, event: Event) -> int:
    """Surface grounded identifiers in the entity graph, reusing any entity already present."""
    from app.services.entity_resolution import canonicalize

    linked = 0
    for field_name in _ENTITY_FIELDS:
        for raw in getattr(record, field_name, None) or []:
            identity = canonicalize(field_name, str(raw))
            if identity is None:
                continue
            entity = db.scalar(
                select(Entity).where(
                    Entity.case_id == record.case_id,
                    Entity.entity_type == identity.entity_type,
                    Entity.normalized_value == identity.canonical_value,
                )
            )
            if entity is None:
                entity = Entity(
                    case_id=record.case_id,
                    source_evidence_id=record.evidence_id,
                    entity_type=identity.entity_type,
                    value=identity.display_value[:512],
                    normalized_value=identity.canonical_value[:512],
                    source_reference=f"grounded:{record.record_key}"[:512],
                    extraction_method=PROJECTED_METHOD,
                    confidence=_confidence_for(record),
                )
                db.add(entity)
                db.flush()

            already = db.scalar(
                select(EventEntity).where(EventEntity.event_id == event.id, EventEntity.entity_id == entity.id)
            )
            if already is None:
                db.add(
                    EventEntity(
                        event_id=event.id,
                        entity_id=entity.id,
                        relationship_type="mentioned_in",
                        confidence=_confidence_for(record),
                    )
                )
                linked += 1
    return linked


def _is_transactional(record: NormalizedRecord) -> bool:
    """Does this figure describe money moving, or merely a position that was quoted?"""
    return (record.amount_role or "unknown") not in NON_TRANSACTIONAL_AMOUNT_ROLES


def _project_transaction(db: Session, record: NormalizedRecord, event: Event) -> bool:
    """Create, enrich, or withdraw the transaction row behind a grounded amount.

    Withdrawing matters as much as creating. When a figure is reclassified — a balance that had been
    projected as a payment — the row it produced has to go, or the correction never reaches the
    trail. A row a human has ruled on is left alone; retracting under a reviewer is not the
    projection's call.
    """
    if record.amount_value is None or not _is_transactional(record):
        stale = db.scalar(select(Transaction).where(Transaction.event_id == event.id))
        if stale is not None and stale.review_status is ReviewStatus.UNREVIEWED:
            logger.info("Withdrawing a projected transaction: the figure is a %s, not a transfer", record.amount_role)
            db.delete(stale)
            db.flush()
        return False

    transaction = db.scalar(select(Transaction).where(Transaction.event_id == event.id))
    if transaction is None:
        transaction = Transaction(
            case_id=record.case_id,
            event_id=event.id,
            source_evidence_id=record.evidence_id,
            amount=float(record.amount_value),
            currency=record.amount_currency or "INR",
            occurred_at=record.event_time,
            reference_id=record.transaction_reference,
            sender_value=record.sender,
            receiver_value=record.receiver,
            source_kind=record.source_type,
            confidence=_confidence_for(record),
        )
        db.add(transaction)
        return True

    if transaction.review_status is not ReviewStatus.UNREVIEWED:
        # A reviewer has ruled on this row; reprocessing must not move it underneath them.
        return False

    transaction.amount = float(record.amount_value)
    transaction.currency = record.amount_currency or transaction.currency
    transaction.occurred_at = transaction.occurred_at or record.event_time
    transaction.reference_id = transaction.reference_id or record.transaction_reference
    transaction.sender_value = transaction.sender_value or record.sender
    transaction.receiver_value = transaction.receiver_value or record.receiver
    transaction.confidence = _confidence_for(record)
    return False


def _enrich_sibling_transactions(db: Session, record: NormalizedRecord) -> int:
    """Fill blanks on the transaction the deterministic pipeline produced for the same payment.

    Those rows are what the report renders as "Not extracted". Only null fields are filled, only
    while the row is still unreviewed, and only on a row carrying the **same amount** — enriching
    every row from the file put "Namkar Jindal to Tanishk Gupta" onto figures that had nothing to
    do with either of them.
    """
    if record.amount_value is None or not _is_transactional(record):
        return 0

    filled = 0
    rows = db.scalars(
        select(Transaction).where(
            Transaction.case_id == record.case_id,
            Transaction.source_evidence_id == record.evidence_id,
            Transaction.review_status == ReviewStatus.UNREVIEWED,
        )
    ).all()
    for row in rows:
        if abs(float(row.amount) - float(record.amount_value)) > AMOUNT_TOLERANCE:
            continue
        changed = False
        if row.sender_value is None and record.sender:
            row.sender_value, changed = record.sender, True
        if row.receiver_value is None and record.receiver:
            row.receiver_value, changed = record.receiver, True
        if row.occurred_at is None and record.event_time:
            row.occurred_at, changed = record.event_time, True
        if row.reference_id is None and record.transaction_reference:
            row.reference_id, changed = record.transaction_reference, True
        filled += int(changed)
    return filled


def purge_orphan_projections(db: Session, case_id: str) -> dict[str, int]:
    """Drop projected rows whose grounded record no longer exists.

    When a record is superseded — reprocessing, or a cleanup of an earlier extraction shape — its
    event goes with it, but the transaction behind that event used to survive as a free-floating
    row. Those orphans are why a case built from three files reported fifteen payments, two of
    which (a phone number and an OCR-merged account line) were never amounts at all.
    """
    live_records = {record_id for record_id in db.scalars(select(NormalizedRecord.id).where(NormalizedRecord.case_id == case_id))}
    live_events = {event_id for event_id in db.scalars(select(Event.id).where(Event.case_id == case_id))}

    removed_events = 0
    for event in db.scalars(select(Event).where(Event.case_id == case_id)).all():
        grounded_id = (event.payload_json or {}).get("grounded_record_id")
        if grounded_id and grounded_id not in live_records:
            db.delete(event)
            live_events.discard(event.id)
            removed_events += 1

    removed_transactions = 0
    for transaction in db.scalars(select(Transaction).where(Transaction.case_id == case_id)).all():
        if transaction.event_id is not None and transaction.event_id not in live_events:
            db.delete(transaction)
            removed_transactions += 1

    if removed_events or removed_transactions:
        db.flush()
        logger.info("Removed %s orphaned events and %s orphaned transactions", removed_events, removed_transactions)
    return {"events_removed": removed_events, "transactions_removed": removed_transactions}


def project_record(db: Session, record: NormalizedRecord) -> dict[str, Any]:
    """Project one grounded record onto the legacy case surfaces."""
    if record.final_confidence_band not in PROJECTABLE_BANDS:
        return {"skipped": "band_not_projectable"}

    event = _existing_event(db, record)
    created = event is None
    if event is None:
        event = Event(
            case_id=record.case_id,
            source_file_id=record.evidence_id,
            event_type=_event_type(record),
            description=_description(record),
            raw_text_reference=f"grounded:{record.record_key}"[:512],
            confidence=_confidence_for(record),
        )
        db.add(event)
        db.flush()
    elif event.review_status is not ReviewStatus.UNREVIEWED:
        return {"skipped": "reviewed"}

    event.occurred_at = record.event_time
    event.original_time = record.event_time_raw
    event.time_precision = record.event_time_precision or "unknown"
    event.event_type = _event_type(record)
    event.description = _description(record)
    event.amount = float(record.amount_value) if record.amount_value is not None else None
    event.currency = record.amount_currency
    event.confidence = _confidence_for(record)
    event.payload_json = {
        "grounded_record_id": record.id,
        "grounded_record_key": record.record_key,
        "projection_version": PROJECTION_VERSION,
        "source_type": record.source_type,
        "observation_basis": record.observation_basis,
        "final_confidence_band": record.final_confidence_band,
        "validation_status": record.validation_status,
        "requires_human_review": record.requires_human_review,
        "review_reason": record.review_reason,
        "extraction_model_name": record.extraction_model_name,
        "sender": record.sender,
        "receiver": record.receiver,
        "chat_participant_identifier": record.chat_participant_identifier,
        "message_direction": record.message_direction,
        "field_provenance": record.field_provenance,
    }
    db.flush()

    return {
        "event_created": created,
        "entities_linked": _project_entities(db, record, event),
        "transaction_created": _project_transaction(db, record, event),
        "transactions_enriched": _enrich_sibling_transactions(db, record),
    }


def project_case(db: Session, case_id: str) -> dict[str, int]:
    """Project every grounded record in a case. Safe to run repeatedly."""
    from app.services.entity_resolution import resolve_case

    totals = {"records": 0, "events_created": 0, "entities_linked": 0, "transactions_created": 0, "transactions_enriched": 0}
    # Superseded projections are cleared before new ones are written, so a reprocess replaces the
    # previous reading of the evidence instead of accumulating alongside it.
    totals.update(purge_orphan_projections(db, case_id))
    records = db.scalars(
        select(NormalizedRecord).where(NormalizedRecord.case_id == case_id).order_by(NormalizedRecord.created_at)
    ).all()
    for record in records:
        outcome = project_record(db, record)
        if "skipped" in outcome:
            continue
        totals["records"] += 1
        totals["events_created"] += int(outcome["event_created"])
        totals["entities_linked"] += outcome["entities_linked"]
        totals["transactions_created"] += int(outcome["transaction_created"])
        totals["transactions_enriched"] += outcome["transactions_enriched"]

    # Identity resolution runs after projection so every sighting of a shared identifier is
    # registered against the evidence it was actually seen in.
    totals["identity_occurrences"] = resolve_case(db, case_id)["occurrences_added"]

    # Relationships are derived last, because both ends of an edge must already be resolved
    # entities. Building them earlier would mint nodes that no occurrence accounts for.
    from app.services.relationship_builder import build_relations_for_case

    totals["entity_relations"] = build_relations_for_case(db, case_id)["relations_added"]

    # Pattern rules read the relationships, so they run last. A failure here must not cost the
    # projection that already succeeded.
    from app.alerts.network_rules import evaluate_network_alerts

    try:
        totals["network_alerts"] = evaluate_network_alerts(db, case_id)["total_new"]
    except Exception:
        logger.exception("Network pattern rules failed; relationships and projections are unaffected")
        totals["network_alerts"] = 0
    return totals
