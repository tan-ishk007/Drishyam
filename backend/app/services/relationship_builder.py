"""Derive typed entity-to-entity edges from grounded records.

This is the layer that turns "these files share an identifier" into "this party paid that party",
which is the relationship map SIH26189 asks for.

Three rules govern everything here.

**A relation is only as strong as what the source states.** A bank row that names a payer column
and a payee column states a transfer. A CDR that names an A-party and a B-party states who dialled;
a call log that lists both numbers in one column does not, and produces a symmetric edge instead.
An FIR sentence carrying a verb -- "was driving MH12DE1433" -- states that the person used the
vehicle; the same two names sitting in different sentences on one page state only that the source
mentioned them together, and that edge says exactly that and nothing more.

**Every edge carries its source.** `source_evidence_id` and `source_reference` are mandatory at the
column level. An edge whose evidence a reviewer cannot open is not intelligence.

**Nothing here confirms anything.** Every edge is written as `machine_extracted` and waits for a
reviewer. The confidence attached is about how firmly the source states the relation, never about
whether the relation is criminal.
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Iterable, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Entity, EntityRelation, NormalizedRecord
from app.services.entity_resolution import canonicalize

logger = logging.getLogger(__name__)

BUILDER_VERSION = "relationship-builder-v1"

# --- relation vocabulary ----------------------------------------------------
# Only relations the current adapters can actually establish are listed. USED_VEHICLE and
# LOCATED_AT arrived with the report adapters, and they are read one sentence at a time from a
# stated verb -- never from two names appearing on the same page.
TRANSFERRED_TO = "TRANSFERRED_TO"
REQUESTED_PAYMENT_FROM = "REQUESTED_PAYMENT_FROM"
CALLED = "CALLED"
USED_VEHICLE = "USED_VEHICLE"
LOCATED_AT = "LOCATED_AT"
MESSAGED = "MESSAGED"
COMMUNICATED_WITH = "COMMUNICATED_WITH"
ASSOCIATED_WITH = "ASSOCIATED_WITH"
MENTIONED_WITH = "MENTIONED_WITH"

RELATION_TYPES = (TRANSFERRED_TO, REQUESTED_PAYMENT_FROM, CALLED, USED_VEHICLE, LOCATED_AT, MESSAGED, COMMUNICATED_WITH, ASSOCIATED_WITH, MENTIONED_WITH)

# What each relation means in a sentence, for the reviewer and the report.
#
# ASSOCIATED_WITH exists because "the source stated the roles" and "the source stated what passed
# between them" are different facts. A statement row that names a payer and a payee but quotes a
# closing balance has named the counterparties without recording a transfer. Filing that as
# MENTIONED_WITH would throw away the roles the source did state; filing it as TRANSFERRED_TO would
# invent a payment. It is its own thing.
RELATION_MEANING = {
    TRANSFERRED_TO: "The source states that the first party sent money to the second.",
    REQUESTED_PAYMENT_FROM: "The source states that the first party asked the second for money. It does not record that any money moved.",
    CALLED: "The call record names the first number as the calling party and the second as the called party.",
    USED_VEHICLE: "One sentence in the source states that the person was driving, riding or using the vehicle.",
    LOCATED_AT: "One sentence in the source places it at this location. It does not establish when.",
    MESSAGED: "The source states that the first party sent a message to the second.",
    COMMUNICATED_WITH: "The source records contact between the two parties but does not state who initiated it.",
    ASSOCIATED_WITH: "The source names these two as the parties to the same record, without stating what passed between them.",
    MENTIONED_WITH: "The source names both in the same record. It does not state any relationship between them.",
}

# How firmly the source states each relation. These are not probabilities that the relation is
# real-world true; they rank how much interpretation was needed to read it off the page.
RELATION_CONFIDENCE = {
    TRANSFERRED_TO: 0.90,
    REQUESTED_PAYMENT_FROM: 0.85,
    CALLED: 0.92,
    USED_VEHICLE: 0.82,
    LOCATED_AT: 0.72,
    MESSAGED: 0.88,
    COMMUNICATED_WITH: 0.75,
    ASSOCIATED_WITH: 0.60,
    MENTIONED_WITH: 0.35,
}

# Money that actually moved. A balance is a position, not a transfer, so a row quoting one must
# never produce a TRANSFERRED_TO edge.
MOVED_AMOUNT_ROLES = {"payment", "fee"}

# Money that was asked for. A demand is not a transfer: a phishing mail demanding a release fee
# records that the money was requested, never that it was paid. Folding the two together let an
# extortion attempt appear in the graph as a completed payment, which is the strongest claim the
# evidence does not support.
REQUESTED_AMOUNT_ROLES = {"request"}

COMMUNICATION_SOURCES = {"email", "chat_export", "screenshot"}

# Sources whose rows are call records. A stated A-party and B-party is what makes CALLED
# directed; without those columns the pair is only known to have been in contact.
CALL_SOURCES = {"call_log", "cdr"}

# A ledger row states a completed transaction by its structure: a declared amount column between a
# payer column and a payee column is what a statement *is*. Its narration is a label, not the
# evidence -- and reading the narration instead gets it wrong, because "Synthetic UPI transfer"
# classifies as a request while "transferred" classifies as a payment. Here the structure decides
# and the wording does not, the same way a column header already settles that digits are money.
STRUCTURED_TRANSFER_SOURCES = {"bank_record"}

# Except for a balance. A statement quoting a position has still not recorded a movement, and no
# amount of structure turns one into the other.
BALANCE_ROLE = "balance"

# Fields whose values are named things that can co-occur meaningfully. Amounts, times and free text
# are attributes of an event, not parties to a relationship.
CO_OCCURRENCE_FIELDS = (
    "person_names",
    "organisation_names",
    "vehicle_identifiers",
    "location_names",
    "phone_numbers",
    "email_addresses",
    "account_identifiers",
)

# A dense record would otherwise produce a quadratic blast of weak edges that buries every strong
# one. A page naming more entities than this says little about any particular pair.
MAX_CO_OCCURRENCE_ENTITIES = 8

# Co-occurrence between two places, or between a place and anything else, is close to meaningless:
# every party in a case file shares the district it was filed in.
CO_OCCURRENCE_EXCLUDED_TYPES = {"location"}


class Endpoint(NamedTuple):
    """One end of a relation: the entity, and the record field it was read from."""

    entity: Entity
    field_name: str


def _entity_for_value(db: Session, record: NormalizedRecord, field_name: str, raw: str) -> Entity | None:
    """The already-resolved entity for one observed value, or None if it identifies nothing.

    Resolution has run by the time this is called, so the entity is looked up rather than created.
    Creating one here would mint a node that no `EntityOccurrence` accounts for.
    """
    identity = canonicalize(field_name, raw)
    if identity is None:
        return None
    return db.scalar(
        select(Entity).where(
            Entity.case_id == record.case_id,
            Entity.entity_type == identity.entity_type,
            Entity.normalized_value == identity.canonical_value,
        )
    )


def _values(record: NormalizedRecord, field_name: str) -> list[str]:
    value = getattr(record, field_name, None)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _field_reference(record: NormalizedRecord, *field_names: str) -> dict:
    """The narrowest source reference available for the fields that produced this edge.

    A reviewer opening the edge should land on the cell or region the relation was read from, not
    on the whole file.
    """
    provenance = record.field_provenance or {}
    for name in field_names:
        reference = (provenance.get(name) or {}).get("source_reference")
        if isinstance(reference, dict) and reference:
            return reference
    return {"evidence_id": record.evidence_id, "kind": "record", "record_key": record.record_key}


def _add(
    db: Session,
    record: NormalizedRecord,
    *,
    subject: Entity,
    object_: Entity,
    relation_type: str,
    directed: bool,
    basis: str,
    reference: dict,
) -> EntityRelation | None:
    """Write one observation, unless this record already produced it.

    Self-edges are refused. An account that appears in both the payer and payee column of one row
    is a parsing artefact, and an edge from a node to itself is never a finding.
    """
    if subject.id == object_.id:
        return None

    left, right = (subject, object_) if directed else tuple(sorted((subject, object_), key=lambda item: item.id))
    key = f"{record.case_id}:{relation_type}:{left.id}:{right.id}:{record.id}"

    if db.scalar(select(EntityRelation).where(EntityRelation.idempotency_key == key)) is not None:
        return None

    relation = EntityRelation(
        case_id=record.case_id,
        subject_entity_id=left.id,
        object_entity_id=right.id,
        relation_type=relation_type,
        directed=directed,
        source_evidence_id=record.evidence_id,
        source_record_id=record.id,
        source_reference=reference,
        basis=basis,
        observed_at=record.event_time,
        time_precision=record.event_time_precision or "unknown",
        extraction_method=BUILDER_VERSION,
        confidence=RELATION_CONFIDENCE.get(relation_type, 0.3),
        verification_status="machine_extracted",
        idempotency_key=key,
    )
    db.add(relation)
    db.flush()
    return relation


def _stated_party_edges(db: Session, record: NormalizedRecord) -> list[EntityRelation]:
    """Edges from a source that names both roles: a payer and a payee, a From and a To.

    This is the strongest evidence the pipeline produces, because the roles were not inferred --
    a column header or a mail header stated them.
    """
    sender_values = _values(record, "sender")
    receiver_values = _values(record, "receiver")
    if not sender_values or not receiver_values:
        return []

    amount_role = (record.amount_role or "unknown").lower()
    has_amount = record.amount_value is not None
    source_type = (record.source_type or "").lower()
    is_ledger_row = source_type in STRUCTURED_TRANSFER_SOURCES

    if source_type in CALL_SOURCES:
        # The record names an A-party column and a B-party column, so the direction is stated
        # rather than inferred. A log that prints one bare number column never reaches here and
        # produces the symmetric COMMUNICATED_WITH edge instead.
        relation_type = CALLED
    elif has_amount and amount_role == BALANCE_ROLE:
        # A position, not a movement. The parties are named; nothing passed between them here.
        relation_type = ASSOCIATED_WITH
    elif has_amount and (amount_role in MOVED_AMOUNT_ROLES or is_ledger_row):
        relation_type = TRANSFERRED_TO
    elif has_amount and amount_role in REQUESTED_AMOUNT_ROLES:
        relation_type = REQUESTED_PAYMENT_FROM
    elif source_type in COMMUNICATION_SOURCES:
        relation_type = MESSAGED
    else:
        # Roles are stated but the record describes neither money moving nor a message -- a
        # statement line quoting a balance, say. The roles are real and are kept; what passed
        # between the parties is not established and is not guessed.
        relation_type = ASSOCIATED_WITH

    reference = _field_reference(record, "sender", "receiver", "amount")
    created: list[EntityRelation] = []
    for sender_raw in sender_values:
        subject = _entity_for_value(db, record, "sender", sender_raw)
        if subject is None:
            continue
        for receiver_raw in receiver_values:
            object_ = _entity_for_value(db, record, "receiver", receiver_raw)
            if object_ is None:
                continue
            relation = _add(
                db,
                record,
                subject=subject,
                object_=object_,
                relation_type=relation_type,
                directed=True,
                basis="stated_roles",
                reference=reference,
            )
            if relation is not None:
                created.append(relation)
    return created


def _call_log_edges(db: Session, record: NormalizedRecord) -> list[EntityRelation]:
    """Contact between the two numbers on one call-log row.

    The row proves the two numbers were in contact. It does not say who dialled: the parser maps
    every number column into one list, so caller and callee are indistinguishable here. The edge is
    therefore symmetric. A dedicated CDR adapter that reads A-party and B-party separately can
    upgrade these to a directed CALLED.
    """
    if (record.source_type or "").lower() not in CALL_SOURCES:
        return []
    if _values(record, "sender") and _values(record, "receiver"):
        # The row named its A-party and B-party, so a directed CALLED has already been recorded.
        # Adding the symmetric edge as well would put two edges on one fact and make the pair look
        # twice as supported as it is.
        return []
    numbers = _values(record, "phone_numbers")
    if len(numbers) != 2:
        # One number is a row about a single party; three or more is a parse that lost the row
        # boundary. Neither states a specific pair.
        return []

    entities = [_entity_for_value(db, record, "phone_numbers", number) for number in numbers]
    if any(entity is None for entity in entities):
        return []

    relation = _add(
        db,
        record,
        subject=entities[0],
        object_=entities[1],
        relation_type=COMMUNICATED_WITH,
        directed=False,
        basis="table_row",
        reference=_field_reference(record, "phone_numbers"),
    )
    return [relation] if relation is not None else []


def _stated_role_edges(db: Session, record: NormalizedRecord) -> list[EntityRelation]:
    """Edges a report narrative states in so many words.

    The extractor has already done the reading: it kept only sentences carrying an explicit verb,
    and only pairs found inside one sentence. What is left here is looking the two ends up as
    resolved entities and recording the edge against the sentence that stated it.
    """
    attributes = record.event_attributes or {}
    created: list[EntityRelation] = []

    for attribute, relation_type, subject_field, object_field in (
        ("stated_vehicle_use", USED_VEHICLE, "person_names", "vehicle_identifiers"),
        ("stated_presence", LOCATED_AT, "person_names", "location_names"),
        ("stated_vehicle_presence", LOCATED_AT, "vehicle_identifiers", "location_names"),
    ):
        pairs = attributes.get(attribute) or []
        if not isinstance(pairs, list):
            continue
        reference = _field_reference(record, attribute, subject_field, object_field)
        for pair in pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            subject = _entity_for_value(db, record, subject_field, str(pair[0]))
            object_ = _entity_for_value(db, record, object_field, str(pair[1]))
            if subject is None or object_ is None:
                continue
            relation = _add(
                db,
                record,
                subject=subject,
                object_=object_,
                relation_type=relation_type,
                directed=True,
                basis="stated_in_sentence",
                reference=reference,
            )
            if relation is not None:
                created.append(relation)
    return created


def _co_occurrence_edges(db: Session, record: NormalizedRecord) -> list[EntityRelation]:
    """The weakest edge in the system: the source named both of these in one record.

    It is worth storing because it is how an FIR links a person to a vehicle at all. It is capped,
    excluded for places, and labelled so it can never be mistaken for a stated relationship.
    """
    endpoints: list[Endpoint] = []
    seen: set[str] = set()
    for field_name in CO_OCCURRENCE_FIELDS:
        for raw in _values(record, field_name):
            entity = _entity_for_value(db, record, field_name, raw)
            if entity is None or entity.id in seen:
                continue
            if entity.entity_type in CO_OCCURRENCE_EXCLUDED_TYPES:
                continue
            seen.add(entity.id)
            endpoints.append(Endpoint(entity, field_name))

    if len(endpoints) < 2 or len(endpoints) > MAX_CO_OCCURRENCE_ENTITIES:
        return []

    created: list[EntityRelation] = []
    for left, right in combinations(endpoints, 2):
        relation = _add(
            db,
            record,
            subject=left.entity,
            object_=right.entity,
            relation_type=MENTIONED_WITH,
            directed=False,
            basis="co_occurrence",
            reference=_field_reference(record, left.field_name, right.field_name),
        )
        if relation is not None:
            created.append(relation)
    return created


def _states_a_stronger_relation(record: NormalizedRecord) -> bool:
    """Whether this record says something more specific than "these were named together".

    Asked of the record rather than of how many rows the current pass inserted. `_add` returns None
    for an edge that already exists, so on a second pass -- and the builder runs over the whole case
    every time any evidence is processed -- the stronger edges looked like nothing at all, and the
    weak co-occurrence duplicates they exist to suppress were written after all.
    """
    if _values(record, "sender") and _values(record, "receiver"):
        return True
    attributes = record.event_attributes or {}
    if attributes.get("stated_vehicle_use") or attributes.get("stated_presence"):
        return True
    if (record.source_type or "").lower() in CALL_SOURCES and len(_values(record, "phone_numbers")) == 2:
        return True
    return False


def build_relations_for_record(db: Session, record: NormalizedRecord) -> int:
    """Every relation this one record states. Returns how many new observations were written."""
    created = _stated_party_edges(db, record)
    created += _call_log_edges(db, record)
    created += _stated_role_edges(db, record)

    # Co-occurrence adds nothing where the source already stated the roles; a weak duplicate of a
    # strong edge only makes the graph noisier and the pair look better supported than it is.
    if not _states_a_stronger_relation(record):
        created += _co_occurrence_edges(db, record)

    return len(created)


def build_relations_for_case(db: Session, case_id: str) -> dict[str, int]:
    """Rebuild relations for a whole case. Safe to run repeatedly."""
    records = db.scalars(
        select(NormalizedRecord).where(NormalizedRecord.case_id == case_id).order_by(NormalizedRecord.created_at)
    ).all()
    created = sum(build_relations_for_record(db, record) for record in records)
    return {"records": len(records), "relations_added": created}


def relation_summary(db: Session, case_id: str) -> list[dict]:
    """Distinct relationships in a case, each with the observations that support it.

    The write side stores one row per observation so provenance stays exact. Investigators think in
    relationships, so the read side groups them and reports how many independent records back each
    one -- which is the number that should drive review priority.
    """
    rows = db.scalars(
        select(EntityRelation).where(EntityRelation.case_id == case_id).order_by(EntityRelation.created_at)
    ).all()
    if not rows:
        return []

    entities = {
        entity.id: entity
        for entity in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()
    }

    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row.relation_type, row.subject_entity_id, row.object_entity_id)
        subject, object_ = entities.get(row.subject_entity_id), entities.get(row.object_entity_id)
        entry = grouped.setdefault(
            key,
            {
                "relation_type": row.relation_type,
                "meaning": RELATION_MEANING.get(row.relation_type, ""),
                "directed": row.directed,
                "subject": {"id": row.subject_entity_id, "label": subject.value if subject else None, "type": subject.entity_type if subject else None},
                "object": {"id": row.object_entity_id, "label": object_.value if object_ else None, "type": object_.entity_type if object_ else None},
                "observation_ids": [],
                "evidence_ids": [],
                "bases": set(),
                "confidence": 0.0,
                "verification_status": "machine_extracted",
                "first_observed_at": None,
                "last_observed_at": None,
            },
        )
        entry["observation_ids"].append(row.id)
        if row.source_evidence_id not in entry["evidence_ids"]:
            entry["evidence_ids"].append(row.source_evidence_id)
        entry["bases"].add(row.basis)
        entry["confidence"] = max(entry["confidence"], float(row.confidence))
        if row.verification_status == "human_verified":
            entry["verification_status"] = "human_verified"
        elif row.verification_status == "rejected" and entry["verification_status"] != "human_verified":
            entry["verification_status"] = "rejected"
        if row.observed_at is not None:
            first, last = entry["first_observed_at"], entry["last_observed_at"]
            entry["first_observed_at"] = row.observed_at if first is None or row.observed_at < first else first
            entry["last_observed_at"] = row.observed_at if last is None or row.observed_at > last else last

    summary = []
    for entry in grouped.values():
        entry["bases"] = sorted(entry["bases"])
        entry["observation_count"] = len(entry["observation_ids"])
        # Independent sources are what make a relationship worth acting on. Ten mentions inside one
        # file are one source; two mentions across two files are corroboration.
        entry["supporting_evidence_count"] = len(entry["evidence_ids"])
        summary.append(entry)

    summary.sort(key=lambda item: (-item["supporting_evidence_count"], -item["confidence"], item["relation_type"]))
    return summary


def relation_types_in_use() -> Iterable[str]:
    return RELATION_TYPES
