"""Criminal-network pattern rules, over the grounded relationship graph.

`rules.py` reads the legacy transaction and event tables and its rules are shaped for payment
fraud. These read the typed relationships instead, which is where a call, a vehicle and a place
actually live, and they are the patterns SIH26189 names.

Every rule here is transparent arithmetic with a stated threshold. None of them predicts anything.
An alert is a reason to look at named evidence, and its wording has to survive being read out in a
courtroom -- so each one says what was counted, over what span, and from which sources.

One rule is deliberately absent. A cross-case alert ("this phone also appears in case B") would
tell everyone who can see case A that case B exists, which is a disclosure the case-level
authorisation model exists to prevent. Cross-case links stay behind the authorisation-scoped
endpoint in `services/cross_case.py`, where the asking user's own access decides what they see.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import narrative
from app.alerts.narrative import Step
from app.models.entities import (
    Alert,
    Case,
    Entity,
    EntityOccurrence,
    EntityRelation,
    EvidenceFile,
    NormalizedRecord,
    Severity,
)
from app.services import temporal
from app.services.entity_resolution import canonicalize_indicator

logger = logging.getLogger(__name__)

NETWORK_RULES_VERSION = "network-rules-v1"

# A vehicle recorded at the same place this many times is worth a look. Twice is a coincidence
# often enough; three times is a pattern the investigator should see.
RECURRING_SIGHTING_MIN = 3


def _label(entities: dict[str, Entity], entity_id: str) -> str:
    entity = entities.get(entity_id)
    return entity.value if entity else entity_id


def _raise(
    db: Session,
    *,
    case_id: str,
    rule_code: str,
    key: str,
    severity: Severity,
    explanation: str,
    evidence_ids: list[str],
    sequence: list[dict] | None = None,
) -> bool:
    """Record one alert, once. Returns whether it was new.

    "Once" has to include the inserts this session is already holding. `db.add` does not write, so
    a second call in the same run reads a table without the pending row, adds a duplicate, and the
    unique index then rejects the whole batch -- failing the file over a repeated lead.
    """
    idempotency_key = f"{case_id}:{rule_code}:{NETWORK_RULES_VERSION}:{key}"
    if db.scalar(select(Alert).where(Alert.idempotency_key == idempotency_key)):
        return False
    if any(isinstance(pending, Alert) and pending.idempotency_key == idempotency_key for pending in db.new):
        return False
    db.add(
        Alert(
            case_id=case_id,
            rule_code=rule_code,
            severity=severity,
            explanation=explanation,
            affected_evidence_ids=evidence_ids,
            sequence=sequence,
            idempotency_key=idempotency_key,
        )
    )
    return True


def _record_places(db: Session, case_id: str) -> dict[str, dict]:
    """Where each normalized record sits inside its file.

    A record does not carry its own page or row; the occurrences read out of it do. Reading them
    back here is what lets a record-based line of a story be opened at the place it came from,
    rather than merely naming the file and leaving the reader to search it.
    """
    places: dict[str, dict] = {}
    rows = db.scalars(
        select(EntityOccurrence).where(EntityOccurrence.case_id == case_id, EntityOccurrence.record_id.isnot(None))
    ).all()
    for row in rows:
        places.setdefault(str(row.record_id), dict(row.source_reference or {}))
    return places


def _record_step(record: NormalizedRecord, statement: str, places: dict[str, dict]) -> Step:
    reference = places.get(record.id, {})
    return Step(
        statement=statement,
        when=record.event_time,
        evidence_id=record.evidence_id,
        place=narrative._place(reference),
        source_reference=reference,
    )


def _relations(db: Session, relation_ids: list[str]) -> list[EntityRelation]:
    """The relationship rows a finding was built from, so the alert can retell them.

    A finding carries ids rather than rows; reading them back here keeps the arithmetic in
    `temporal` free of presentation and means the story is assembled from the same records the
    threshold was counted over, not a second query that might disagree with it.
    """
    if not relation_ids:
        return []
    rows = db.scalars(select(EntityRelation).where(EntityRelation.id.in_(relation_ids))).all()
    return list(rows)


def _story(db: Session, relation_ids: list[str], entities: dict[str, Entity], *, gaps: bool = True) -> list[dict]:
    return narrative.sequence(
        (narrative.step_from_relation(item, entities) for item in _relations(db, relation_ids)),
        gaps=gaps,
    )


def _pre_incident_communication(db: Session, case_id: str, entities: dict[str, Entity]) -> int:
    raised = 0
    for finding in temporal.pre_incident_contacts(db, case_id):
        left, right = finding["pair"]
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="PRE_INCIDENT_COMMUNICATION",
            key=f"{left}:{right}",
            severity=Severity.HIGH,
            explanation=(
                f"Review lead: {_label(entities, left)} and {_label(entities, right)} are recorded in contact "
                f"{finding['contacts']} times in the {int(temporal.PRE_INCIDENT_LOOKBACK.total_seconds() // 3600)} hours "
                f"before the declared incident window, the last of them {finding['hours_before']} hours before it opens. "
                "Contact before an incident is not evidence of involvement in it; open the call records and read them."
            ),
            evidence_ids=finding["evidence_ids"],
            sequence=_story(db, finding["relation_ids"], entities),
        )
    return raised


def _communication_burst(db: Session, case_id: str, entities: dict[str, Entity]) -> int:
    raised = 0
    for finding in temporal.communication_bursts(db, case_id):
        left, right = finding["pair"]
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="COMMUNICATION_BURST",
            key=f"{left}:{right}",
            severity=Severity.MEDIUM,
            explanation=(
                f"Review lead: {_label(entities, left)} and {_label(entities, right)} are recorded in contact "
                f"{finding['contacts']} times within {finding['minutes']} minutes. "
                "A burst of contact can have an ordinary explanation; the records themselves are the evidence."
            ),
            evidence_ids=finding["evidence_ids"],
            # A burst is dense by definition, so stating the silences inside it would be noise.
            sequence=_story(db, finding["relation_ids"], entities, gaps=False),
        )
    return raised


def _recurring_vehicle_at_location(db: Session, case_id: str) -> int:
    """The same registration and the same place recorded together, repeatedly.

    Read from records that name both, which states that the source recorded them together -- not
    that the vehicle was at the place at any particular time. The wording keeps that distinction.
    """
    sightings: dict[tuple[str, str], list[NormalizedRecord]] = defaultdict(list)
    records = db.scalars(select(NormalizedRecord).where(NormalizedRecord.case_id == case_id)).all()
    for record in records:
        for vehicle in record.vehicle_identifiers or []:
            for place in record.location_names or []:
                sightings[(str(vehicle), str(place))].append(record)

    places = _record_places(db, case_id)
    raised = 0
    for (vehicle, place), matches in sightings.items():
        if len(matches) < RECURRING_SIGHTING_MIN:
            continue
        evidence_ids = sorted({item.evidence_id for item in matches})
        story = narrative.sequence(
            _record_step(item, f"{vehicle} and {place} are recorded together in this record.", places)
            for item in matches
        )
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="RECURRING_VEHICLE_AT_LOCATION",
            key=f"{vehicle}:{place}",
            severity=Severity.MEDIUM,
            explanation=(
                f"Review lead: vehicle {vehicle} and the location {place} are recorded together in "
                f"{len(matches)} records across {len(evidence_ids)} evidence files. "
                "The sources record them together; they do not establish that the vehicle was there at a stated time."
            ),
            evidence_ids=evidence_ids,
            sequence=story,
        )
    return raised


def _bridge_entity(db: Session, case_id: str, entities: dict[str, Entity]) -> int:
    """Entities whose removal would disconnect the network.

    These are where the case is most fragile: if the relationship through such an entity is wrong,
    the connection between two parts of the network does not exist. That makes them the first thing
    worth verifying, which is what the alert says -- not that they are important people.
    """
    from app.graph import analytics  # imported here; analytics reads relations this module writes about

    raised = 0
    for entry in analytics.important_entities(db, case_id, limit=20):
        if not entry["is_bridge"] or entry["supporting_evidence_count"] < 2:
            continue
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="BRIDGE_ENTITY",
            key=entry["entity_id"],
            severity=Severity.MEDIUM,
            explanation=(
                f"Review lead: {entry['label']} holds two parts of this network together. {entry['why']} "
                "Verify the relationships through it first: if one of them is wrong, the connection between "
                "those groups does not exist. Network position is review priority, not an indication of guilt."
            ),
            # The lead says how many evidence files support this position, so it must name them.
            # Raised with an empty list, it told a reviewer to verify relationships it gave them no
            # way to open.
            evidence_ids=list(entry.get("supporting_evidence_ids") or []),
            # A bridge is not a chronology, so the sequence is the relationships running through it
            # -- the exact ones a reviewer is being asked to verify first, each openable.
            sequence=narrative.sequence(
                (
                    narrative.step_from_relation(item, entities)
                    for item in db.scalars(
                        select(EntityRelation).where(
                            EntityRelation.case_id == case_id,
                            (EntityRelation.subject_entity_id == entry["entity_id"])
                            | (EntityRelation.object_entity_id == entry["entity_id"]),
                        )
                    ).all()
                ),
                gaps=False,
            ),
        )
    return raised


# --------------------------------------------------------------------------- C2: five more patterns

# Several distinct parties named at one location inside this span is a convergence worth a look.
CONVERGENCE_WINDOW = timedelta(hours=6)
CONVERGENCE_MIN_PARTIES = 3

# An identity that enters the case this long after it was opened did not come from the evidence
# originally filed. That is a fact about the case file, and the wording says so.
LATE_ARRIVAL_AFTER = timedelta(hours=24)

# A vehicle recorded at this many distinct places, in time order, is a route rather than a sighting.
CORRIDOR_MIN_PLACES = 3


def _relay(db: Session, case_id: str, entities: dict[str, Entity]) -> int:
    """A contacts B, then B contacts C, close enough together to read as one movement."""
    raised = 0
    for finding in temporal.relays(db, case_id):
        start, middle, end = finding["path"]
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="RELAY_CONTACT",
            key=":".join(finding["path"]),
            severity=Severity.MEDIUM,
            explanation=(
                f"Review lead: {_label(entities, start)} is recorded in contact with {_label(entities, middle)}, and "
                f"{finding['minutes']} minutes later {_label(entities, middle)} is recorded in contact with "
                f"{_label(entities, end)}. The records show this shape; they do not establish that anything was passed "
                "on, or that the two contacts are related at all. Read both records."
            ),
            evidence_ids=finding["evidence_ids"],
            sequence=_story(db, finding["relation_ids"], entities, gaps=False),
        )
    return raised


def _converging_location(db: Session, case_id: str) -> int:
    """Several distinct parties named at one place inside a short span."""
    records = db.scalars(
        select(NormalizedRecord).where(NormalizedRecord.case_id == case_id, NormalizedRecord.event_time.isnot(None))
    ).all()
    at_place: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        for place in record.location_names or []:
            at_place[str(place)].append(record)

    places = _record_places(db, case_id)
    raised = 0
    for place, matches in at_place.items():
        matches.sort(key=lambda item: item.event_time)
        for index, anchor in enumerate(matches):
            window = [item for item in matches[index:] if item.event_time - anchor.event_time <= CONVERGENCE_WINDOW]
            parties = {
                str(name)
                for item in window
                for name in (item.person_names or []) + (item.vehicle_identifiers or []) + (item.phone_numbers or [])
            }
            if len(parties) < CONVERGENCE_MIN_PARTIES:
                continue
            evidence_ids = sorted({item.evidence_id for item in window})
            raised += _raise(
                db,
                case_id=case_id,
                rule_code="CONVERGING_LOCATION",
                key=f"{place}:{anchor.event_time.isoformat()}",
                severity=Severity.MEDIUM,
                explanation=(
                    f"Review lead: {len(parties)} distinct parties are recorded in connection with {place} within "
                    f"{int(CONVERGENCE_WINDOW.total_seconds() // 3600)} hours of each other, across "
                    f"{len(evidence_ids)} evidence files. Being named against the same place in the same window is "
                    "not a record of anyone meeting anyone. Read the records and see what each one actually states."
                ),
                evidence_ids=evidence_ids,
                sequence=narrative.sequence(
                    _record_step(item, f"This record names {place}.", places) for item in window
                ),
            )
            break  # one convergence per place is enough to prompt a look
    return raised


def _late_arriving_identity(db: Session, case_id: str, entities: dict[str, Entity]) -> int:
    """An identity that entered the case well after it was opened.

    This is a fact about the case file, not about the world: it says the identity was not in the
    evidence originally filed and came in with something added later. An investigator reads that
    differently from an identity that was there from the start, and nothing else reports it.
    """
    case = db.get(Case, case_id)
    if case is None:
        return 0

    arrivals: dict[str, EntityOccurrence] = {}
    rows = db.scalars(
        select(EntityOccurrence).where(EntityOccurrence.case_id == case_id).order_by(EntityOccurrence.created_at)
    ).all()
    for row in rows:
        arrivals.setdefault(row.entity_id, row)

    files = {item.id: item for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()}
    raised = 0
    for entity_id, first in arrivals.items():
        delay = first.created_at - case.created_at
        if delay < LATE_ARRIVAL_AFTER:
            continue
        source = files.get(first.evidence_id)
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="LATE_ARRIVING_IDENTITY",
            key=entity_id,
            severity=Severity.LOW,
            explanation=(
                f"Review lead: {_label(entities, entity_id)} was not present in the evidence this case opened with. "
                f"It first appears {round(delay.total_seconds() / 86400, 1)} days later, in "
                f"{source.original_name if source else 'an evidence file added afterwards'}. "
                "That is a fact about when the file arrived, not about when the identity became involved."
            ),
            evidence_ids=[first.evidence_id],
            sequence=narrative.sequence(
                [
                    Step(
                        statement=(
                            f"{_label(entities, entity_id)} is first recorded in this case here, "
                            f"written as {first.observed_value}."
                        ),
                        when=first.created_at,
                        evidence_id=first.evidence_id,
                        place=narrative._place(first.source_reference),
                        source_reference=dict(first.source_reference or {}),
                    )
                ],
                gaps=False,
            ),
        )
    return raised


def _vehicle_corridor(db: Session, case_id: str) -> int:
    """One vehicle recorded at several distinct places, in the order the sources time them."""
    records = db.scalars(
        select(NormalizedRecord).where(NormalizedRecord.case_id == case_id, NormalizedRecord.event_time.isnot(None))
    ).all()
    journeys: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        if not record.location_names:
            continue
        for vehicle in record.vehicle_identifiers or []:
            journeys[str(vehicle)].append(record)

    places = _record_places(db, case_id)
    raised = 0
    for vehicle, matches in journeys.items():
        matches.sort(key=lambda item: item.event_time)
        route = [str(name) for item in matches for name in (item.location_names or [])]
        distinct = list(dict.fromkeys(route))
        if len(distinct) < CORRIDOR_MIN_PLACES:
            continue
        evidence_ids = sorted({item.evidence_id for item in matches})
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="VEHICLE_CORRIDOR",
            key=f"{vehicle}:{len(distinct)}",
            severity=Severity.MEDIUM,
            explanation=(
                f"Review lead: {vehicle} is recorded in connection with {len(distinct)} distinct places, across "
                f"{len(evidence_ids)} evidence files, which the sources time in this order: "
                f"{' then '.join(distinct)}. The order is the order of the records. It does not establish that the "
                "vehicle travelled between them, or that the same driver was involved throughout."
            ),
            evidence_ids=evidence_ids,
            sequence=narrative.sequence(
                _record_step(
                    item,
                    f"{vehicle} is recorded with {', '.join(str(name) for name in item.location_names or [])}.",
                    places,
                )
                for item in matches
            ),
        )
    return raised


def _sudden_silence(db: Session, case_id: str, entities: dict[str, Entity]) -> int:
    """A pair in regular recorded contact whose contact stops while the case keeps recording."""
    raised = 0
    for finding in temporal.sudden_silence(db, case_id):
        left, right = finding["pair"]
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="SUDDEN_SILENCE",
            key=f"{left}:{right}",
            severity=Severity.MEDIUM,
            explanation=(
                f"Review lead: {_label(entities, left)} and {_label(entities, right)} are recorded in contact "
                f"{finding['contacts']} times, roughly every {finding['usual_gap_hours']} hours, and then not again. "
                f"The record continues for a further {finding['silent_hours']} hours with no contact between them. "
                "Numbers change and people fall out; the record shows the pattern stopping and says nothing about why."
            ),
            evidence_ids=finding["evidence_ids"],
            sequence=_story(db, finding["relation_ids"], entities),
        )
    return raised


def _shared_device(db: Session, case_id: str) -> int:
    """Two or more identifiers recorded against the same handset.

    This is the strongest thing a call detail record carries beyond the calls themselves, and no
    amount of analysing who rang whom will find it: one person running two numbers leaves exactly
    this trace and nothing else does. It is also why a CDR's IMEI column is worth reading at all.

    What it does not say is which of two explanations applies. One person using two numbers, a
    handset sold on, a phone borrowed for an evening, a SIM moved after a number was blocked -- the
    record shows the numbers and the handset, and is silent on the rest. The wording keeps it that
    way, because "these belong to the same person" is the conclusion an investigator reaches after
    checking, not one this rule is entitled to hand them.
    """
    records = db.scalars(
        select(NormalizedRecord).where(
            NormalizedRecord.case_id == case_id, NormalizedRecord.device_identifier.isnot(None)
        )
    ).all()

    on_handset: dict[str, dict[str, list[NormalizedRecord]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        device = str(record.device_identifier).strip()
        if not device:
            continue

        # Whose handset this is. A call record's IMEI belongs to the subscriber whose record it is
        # -- the calling party -- and not to the number they rang. Attributing it to every number on
        # the row would have this rule announce that two people share a handset on the evidence of a
        # single call between them, which is exactly the false accusation it exists to avoid.
        owner = record.sender
        if not owner:
            numbers = list(record.phone_numbers or [])
            # One number and one handset on a record is unambiguous. Several numbers and no stated
            # owner is not, and a guess here is a guess about whose phone it is.
            owner = numbers[0] if len(numbers) == 1 else None
        if not owner:
            continue

        resolved = canonicalize_indicator("phone", str(owner))
        if resolved is None:
            continue
        on_handset[device][resolved.canonical_value].append(record)

    places = _record_places(db, case_id)
    raised = 0
    for device, numbers in on_handset.items():
        if len(numbers) < 2:
            continue
        evidence_ids = sorted({item.evidence_id for rows in numbers.values() for item in rows})
        written = sorted(numbers)
        raised += _raise(
            db,
            case_id=case_id,
            rule_code="SHARED_DEVICE",
            key=device,
            severity=Severity.HIGH,
            explanation=(
                f"Review lead: {len(numbers)} different numbers are recorded against the same handset "
                f"({device}) across {len(evidence_ids)} evidence file(s): {', '.join(written)}. "
                "A handset shared between numbers can mean one person using both, a phone passed on, or a "
                "SIM moved after a number stopped working. The record shows which numbers and which handset; "
                "it does not say which of those it was."
            ),
            evidence_ids=evidence_ids,
            sequence=narrative.sequence(
                _record_step(
                    item,
                    f"{number} is recorded on handset {device}.",
                    places,
                )
                for number, rows in sorted(numbers.items())
                for item in rows
            ),
        )
    return raised


def evaluate_network_alerts(db: Session, case_id: str) -> dict[str, int]:
    """Run every criminal-network rule for one case. Safe to run repeatedly."""
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id)).all()}
    counts = {
        "pre_incident_communication": _pre_incident_communication(db, case_id, entities),
        "communication_burst": _communication_burst(db, case_id, entities),
        "recurring_vehicle_at_location": _recurring_vehicle_at_location(db, case_id),
        "bridge_entity": _bridge_entity(db, case_id, entities),
        "relay": _relay(db, case_id, entities),
        "converging_location": _converging_location(db, case_id),
        "late_arriving_identity": _late_arriving_identity(db, case_id, entities),
        "vehicle_corridor": _vehicle_corridor(db, case_id),
        "sudden_silence": _sudden_silence(db, case_id, entities),
        "shared_device": _shared_device(db, case_id),
    }
    counts["total_new"] = sum(counts.values())
    counts["rules_version"] = NETWORK_RULES_VERSION  # type: ignore[assignment]
    return counts
