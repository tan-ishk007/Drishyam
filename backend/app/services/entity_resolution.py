"""Turn grounded records into shared identity nodes.

Two ideas do the work here.

**Identity vs attribute.** Only things that identify a party — a phone, an address, an account, a
reference — become graph nodes. An amount does not identify anyone: making `25,000` a node linked
eleven unrelated files together purely because they mention the same figure.

**One identifier, one node, many sightings.** The same handle read out of a chat, a receipt and a
bank statement is one node with three occurrences, not three nodes. That is what makes a link
between two files visible at all.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence_intelligence import patterns
from app.models.entities import Entity, EntityOccurrence, NormalizedRecord

logger = logging.getLogger(__name__)

RESOLVER_VERSION = "entity-resolution-v1"

# Identity-bearing fields only. `amount`, `event_time` and free text are attributes of an event, not
# identities, and are deliberately excluded — see the module docstring.
IDENTITY_FIELDS: dict[str, str] = {
    "phone_numbers": "phone",
    "email_addresses": "email",
    "account_identifiers": "account",
    "transaction_reference": "reference",
    "device_identifier": "device",
    "sender": "party",
    "receiver": "party",
    "chat_participant_identifier": "party",
    # SIH26189 entity classes. A vehicle is an identifier and behaves like one.
    # A person and an organisation are named things whose identity the source
    # rarely proves, and a place identifies nobody at all -- so all three stay
    # weak and are never merged on similarity alone.
    "vehicle_identifiers": "vehicle",
    "organisation_names": "organisation",
    "person_names": "person",
    "location_names": "location",
}

# A name read off a screen is a label, not a proof of identity, so party nodes stay weak.
PARTY_FIELDS = {"sender", "receiver", "chat_participant_identifier", "person_names", "organisation_names", "location_names"}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ResolvedIdentity:
    entity_type: str
    display_value: str
    canonical_value: str


def _classify_account(value: str) -> str:
    """UPI handles and email addresses look alike; the same string must not become two nodes."""
    if patterns.EMAIL_PATTERN.fullmatch(value):
        return "email"
    if "@" in value:
        return "upi"
    if patterns.IFSC_PATTERN.fullmatch(value.upper()):
        return "ifsc"
    return "account"


# A personal name is a short run of alphabetic words. This does not decide whether the name is
# real, or whose it is -- only whether the string is shaped like one at all.
_MAX_NAME_WORDS = 4


def _reads_as_a_name(folded: str) -> bool:
    words = folded.split()
    return 1 <= len(words) <= _MAX_NAME_WORDS and all(word.isalpha() and len(word) > 1 for word in words)


def canonicalize(field_name: str, raw: str) -> ResolvedIdentity | None:
    """Reduce one observed value to the node it belongs to, or None if it identifies nothing."""
    value = str(raw).strip()
    if not value or len(value) > 320:
        return None

    kind = IDENTITY_FIELDS.get(field_name)
    if kind is None:
        return None

    if kind == "phone":
        canonical = patterns.normalize_phone(value)
        digits = re.sub(r"\D", "", canonical)
        return ResolvedIdentity("phone", canonical, digits[-10:]) if len(digits) >= 10 else None

    if kind in {"email", "account"}:
        resolved = _classify_account(value)
        # An account number is written with spaces or dashes as often as without, and a bank code
        # is quoted in either case. Neither separator nor case identifies a different account, so
        # both are dropped. A UPI handle and an email keep their shape; only case is folded.
        if resolved in {"account", "ifsc"}:
            return ResolvedIdentity(resolved, value, _NON_ALNUM.sub("", value.casefold()))
        return ResolvedIdentity(resolved, value, value.casefold())

    if kind == "reference":
        # OCR reads O/0 and I/1/l interchangeably, so references are folded before comparison.
        folded = _NON_ALNUM.sub("", value.casefold()).translate(str.maketrans("oil", "011"))
        return ResolvedIdentity("reference", value, folded) if len(folded) >= 6 else None

    if kind == "device":
        return ResolvedIdentity("device", value, _NON_ALNUM.sub("", value.casefold()))

    if kind == "vehicle":
        canonical = patterns.normalize_vehicle(value)
        # A plate is at least a state code, an RTO code and a serial. Anything
        # shorter is a fragment, and a fragment links files that share nothing.
        return ResolvedIdentity("vehicle", value.upper(), canonical) if len(canonical) >= 8 else None

    if kind == "organisation":
        folded = patterns.normalize_organisation(value)
        return ResolvedIdentity("organisation", value, folded) if len(folded) >= 3 else None

    if kind == "person":
        folded = patterns.normalize_person(value)
        # Two people share a name far more often than they share an account.
        # This node records that the same name was written down twice; whether
        # it is the same person is a review decision, never an extraction one.
        return ResolvedIdentity("person", value, folded) if len(folded) >= 3 else None

    if kind == "location":
        folded = patterns.normalize_location(value)
        return ResolvedIdentity("location", value, folded) if len(folded) >= 3 else None

    if kind == "party":
        # A stated sender or receiver is whatever it turns out to be. Reading it as an opaque
        # "party" put the complainant named in an FIR and the same complainant named in the payer
        # column of a statement into two nodes, and a UPI handle in a receiver column into a second
        # node beside the one the handle already had. Both halves were weak in exactly the same
        # way, so the split bought nothing and cost the link.
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 10:
            return ResolvedIdentity("phone", patterns.normalize_phone(value), digits[-10:])
        if "@" in value:
            resolved = _classify_account(value)
            return ResolvedIdentity(resolved, value, value.casefold())
        folded = patterns.normalize_person(value)
        if len(folded) < 3:
            return None
        # Still a name read off a document, and a name is not proof of identity. `person` carries
        # that caveat already; the confidence this is stored with says the rest.
        #
        # But only where the value reads as a name at all. A sender column in real mail and ledger
        # data carries things like "withdrawal approval pending inbox ww" and "synthetic account
        # 8233", and calling those people states something the source does not. They stay `party`:
        # a stated counterparty of unknown kind, which is exactly what they are.
        return ResolvedIdentity("person" if _reads_as_a_name(folded) else "party", value, folded)

    return None


def _values_for(record: NormalizedRecord, field_name: str) -> list[str]:
    value = getattr(record, field_name, None)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _confidence_for(record: NormalizedRecord, field_name: str) -> float:
    provenance = (record.field_provenance or {}).get(field_name) or {}
    raw = provenance.get("confidence")
    if isinstance(raw, (int, float)):
        return float(raw)
    if record.validation_confidence is not None:
        return float(record.validation_confidence)
    return 0.6 if field_name in PARTY_FIELDS else 0.75


def _stated_role(record: NormalizedRecord, field_name: str, raw: object) -> str | None:
    """What this record called this person, where it called them anything.

    Only person names carry a role. A phone number has no role, and inventing one for it would be
    the system asserting something no source stated. Recorded against the occurrence rather than
    the entity because a role is what one source said in one place: the same individual can be a
    witness in one file and a suspect in another, and the entity must not have to choose.
    """
    if field_name != "person_names":
        return None
    roles = record.person_roles or {}
    return roles.get(str(raw)) or roles.get(str(raw).strip())


def _source_reference(record: NormalizedRecord, field_name: str) -> dict:
    provenance = (record.field_provenance or {}).get(field_name) or {}
    reference = provenance.get("source_reference")
    return reference if isinstance(reference, dict) else {}


def _entity_for(db: Session, record: NormalizedRecord, identity: ResolvedIdentity) -> Entity:
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
            extraction_method=RESOLVER_VERSION,
            confidence=0.8,
        )
        db.add(entity)
        db.flush()
    return entity


def resolve_record(db: Session, record: NormalizedRecord, seen: set[tuple[str, str, str]] | None = None) -> int:
    """Register every identity this record observed. Returns how many new sightings were stored.

    `seen` carries the occurrences already queued in this transaction. The session runs with
    autoflush disabled, so a SELECT cannot see a row that an earlier record in the same pass has
    added but not yet flushed. Without this set the duplicate survived all the way to the flush and
    raised a UniqueViolation on uq_entity_occurrence -- which aborted the whole projection, so
    events, transactions and every identity sighting were rolled back together and the connection
    graph stayed empty.
    """
    if seen is None:
        seen = set()
    stored = 0
    for field_name in IDENTITY_FIELDS:
        for raw in _values_for(record, field_name):
            identity = canonicalize(field_name, raw)
            if identity is None:
                continue

            entity = _entity_for(db, record, identity)
            key = (entity.id, record.evidence_id, field_name)
            if key in seen:
                # Two spellings in one field can resolve to the same node -- a number written both
                # grouped and unbroken is one phone, seen once.
                continue

            existing = db.scalar(
                select(EntityOccurrence).where(
                    EntityOccurrence.entity_id == entity.id,
                    EntityOccurrence.evidence_id == record.evidence_id,
                    EntityOccurrence.field_name == field_name,
                )
            )
            if existing is not None:
                seen.add(key)
                continue

            seen.add(key)
            db.add(
                EntityOccurrence(
                    case_id=record.case_id,
                    entity_id=entity.id,
                    evidence_id=record.evidence_id,
                    record_id=record.id,
                    field_name=field_name,
                    observed_value=str(raw)[:512],
                    source_reference=_source_reference(record, field_name),
                    detection_method=RESOLVER_VERSION,
                    stated_role=_stated_role(record, field_name, raw),
                    confidence=_confidence_for(record, field_name),
                )
            )
            stored += 1
    return stored


def resolve_case(db: Session, case_id: str) -> dict[str, int]:
    """Rebuild identity sightings for a whole case. Safe to run repeatedly."""
    records = db.scalars(
        select(NormalizedRecord).where(NormalizedRecord.case_id == case_id).order_by(NormalizedRecord.created_at)
    ).all()
    # One set for the whole pass: several records from one evidence item routinely observe the same
    # identifier, and each of those is one sighting of that file, not one per record.
    seen: set[tuple[str, str, str]] = set()
    stored = sum(resolve_record(db, record, seen) for record in records)
    return {"records": len(records), "occurrences_added": stored}


# The deterministic regex extractor speaks an older vocabulary than the grounded pipeline: it
# writes "upi_id" where the resolver writes "upi", "utr" where the resolver writes "reference",
# and it canonicalizes a phone as "+919876543210" where the resolver keys on the last ten digits.
# Both write into the same `entities` table, so one phone number became two nodes -- one carrying
# the relationships, the other carrying none -- and a value seen in a chat export never joined the
# same value seen in a bank statement. Mapping the old names onto identity fields sends both
# generations through the single function above, so they mint one node.
INDICATOR_FIELDS: dict[str, str] = {
    # The regex extractor's vocabulary.
    "phone": "phone_numbers",
    "email": "email_addresses",
    "upi_id": "account_identifiers",
    "ifsc": "account_identifiers",
    "account_number": "account_identifiers",
    "utr": "transaction_reference",
    # The resolver's own node types, so a row already minted by this module re-resolves to
    # itself rather than falling through to a weaker normalization.
    "upi": "account_identifiers",
    "account": "account_identifiers",
    "reference": "transaction_reference",
    "device": "device_identifier",
    "party": "sender",
    "person": "person_names",
    "organisation": "organisation_names",
    "location": "location_names",
    "vehicle": "vehicle_identifiers",
}


def canonicalize_indicator(entity_type: str, value: str) -> ResolvedIdentity | None:
    """Resolve a deterministic-extractor indicator to the same node the grounded pipeline mints.

    Returns None for a type the resolver has no identity field for -- a URL, an IP address, or a
    legacy `amount` row that was never an identity at all. The caller keeps whatever key such a row
    already has, because these are types the two pipelines never disagreed about and re-deriving
    them from the display value only loses information: an amount stored as "59000" came back as
    "59,000".

    Passing a value this module minted returns that same node, so the function is safe to run over
    rows already on record.
    """
    field_name = INDICATOR_FIELDS.get(entity_type)
    return canonicalize(field_name, value) if field_name is not None else None
