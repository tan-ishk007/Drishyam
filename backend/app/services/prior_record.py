"""What the national record already holds about an identity, and what that is worth.

An investigator looking at a number in a live case wants to know whether it has been seen before.
Today that means ringing round, and the answer depends on who happens to remember. This reads the
national record of registered cases -- an NCRB or CCTNS extract in a real deployment, a synthetic
dataset here -- and returns what it holds.

**This is not the shared ledger and must never be confused with it.** The ledger says another force
is working a *live* case touching this identity, and deliberately holds nothing beyond a case
reference and a contact, because that force's file is not this reader's to see. The national record
is a different store with different authority: it is entitled to hold the details, and it describes
cases that have already been registered and usually disposed of.

**The rule that makes this safe to show at all.** Under section 46 of the Bharatiya Sakshya
Adhiniyam a person's previous bad character is generally not relevant, and "he has done this
before" is exactly the reasoning the rest of this product refuses to make. So three things hold
here and are not negotiable:

    every disposal is shown        A store that surfaced convictions and quietly dropped
                                   acquittals, closures and quashed cases would be a lie told by
                                   arithmetic -- and it is that omission, not the lookup, that
                                   turns a record into an accusation.

    nothing is scored or ranked    No "risk from history", no count presented as a trend. Four
                                   registered cases is four registered cases; what it means is the
                                   reader's judgement and the court's, not a number this module
                                   invents.

    the caveat travels with it     Wherever a prior record appears, so does the sentence saying it
                                   is not evidence in this case.

Matching is on the canonical value the resolver produces, so a number written four ways still finds
the same record. An identity the resolver cannot canonicalise returns nothing rather than being
matched on whatever string happened to be typed -- a near-miss here attaches somebody else's
criminal history to the person in front of you.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Entity, PriorRecord
from app.services.entity_resolution import canonicalize_indicator

PRIOR_RECORD_VERSION = "prior-record-v1"

CAVEAT = (
    "A registered case is a record that something was reported and what became of it. It is not evidence in this "
    "case, and it does not make anything in this case more likely. Under section 46 of the Bharatiya Sakshya "
    "Adhiniyam previous bad character is generally not relevant; this is here so you can reach the officer who "
    "dealt with it, not so this case can lean on it."
)

# How each disposal reads to somebody who is not a lawyer, and whether the case is still open.
DISPOSALS: dict[str, tuple[str, str]] = {
    "under_investigation": ("Still under investigation", "open"),
    "chargesheeted": ("Chargesheeted; before a court", "open"),
    "convicted": ("Convicted", "closed"),
    "acquitted": ("Acquitted — the court did not find it proved", "closed"),
    "closed": ("Closed without a chargesheet", "closed"),
    "quashed": ("Quashed by a court", "closed"),
}


@dataclass
class Entry:
    """One registered case, as the national record holds it."""

    record_reference: str
    police_station: str
    district: str | None
    sections: list[str]
    registered_on: str
    disposal: str
    disposal_reading: str
    disposal_state: str
    disposal_on: str | None
    subject_name: str | None
    contact_officer: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_reference": self.record_reference,
            "police_station": self.police_station,
            "district": self.district,
            "sections": self.sections,
            "registered_on": self.registered_on,
            "disposal": self.disposal,
            "disposal_reading": self.disposal_reading,
            "disposal_state": self.disposal_state,
            "disposal_on": self.disposal_on,
            "subject_name": self.subject_name,
            "contact_officer": self.contact_officer,
            "source": self.source,
        }


@dataclass
class Lookup:
    identity: str
    matched_on: str | None
    entries: list[Entry] = field(default_factory=list)
    statement: str = ""
    caveat: str = CAVEAT
    version: str = PRIOR_RECORD_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "matched_on": self.matched_on,
            "entries": [item.to_dict() for item in self.entries],
            "statement": self.statement,
            "caveat": self.caveat,
            "version": self.version,
        }


def _reading(disposal: str) -> tuple[str, str]:
    return DISPOSALS.get(disposal, (disposal.replace("_", " "), "unknown"))


def _statement(entries: list[Entry], identity: str) -> str:
    """What the record holds, counted honestly.

    The open and closed counts are given separately because they mean different things to an
    investigator, and the sentence never adds them into a verdict about the person.
    """
    if not entries:
        return (
            f"The national record holds no registered case against {identity}. That is a statement about this "
            "record, not about the person: a case registered elsewhere, under another identifier, or not yet "
            "extracted into this dataset would not appear here."
        )

    open_count = sum(1 for item in entries if item.disposal_state == "open")
    closed = [item for item in entries if item.disposal_state == "closed"]
    convicted = sum(1 for item in closed if item.disposal == "convicted")
    not_proved = len(closed) - convicted

    parts = [f"{len(entries)} registered case{'' if len(entries) == 1 else 's'} name{'s' if len(entries) == 1 else ''} {identity}"]
    if open_count:
        parts.append(f"{open_count} still open")
    if convicted:
        parts.append(f"{convicted} ended in conviction")
    if not_proved:
        parts.append(f"{not_proved} closed without one")
    return ". ".join([", ".join(parts)]) + "."


def lookup(db: Session, entity: Entity) -> Lookup:
    """What the national record holds about one identity in this case."""
    resolved = canonicalize_indicator(entity.entity_type, entity.value)
    if resolved is None:
        return Lookup(
            identity=entity.value,
            matched_on=None,
            statement=(
                "This identity could not be reduced to a canonical form, so the national record was not searched. "
                "Matching on the raw text would risk attaching somebody else's record to this person."
            ),
        )

    rows = db.scalars(
        select(PriorRecord)
        .where(
            PriorRecord.identifier_type == resolved.entity_type,
            PriorRecord.identifier_value == resolved.canonical_value,
        )
        .order_by(PriorRecord.registered_on.desc())
    ).all()

    entries = []
    for row in rows:
        reading, state = _reading(row.disposal)
        entries.append(Entry(
            record_reference=row.record_reference,
            police_station=row.police_station,
            district=row.district,
            sections=list(row.sections or []),
            registered_on=row.registered_on.date().isoformat(),
            disposal=row.disposal,
            disposal_reading=reading,
            disposal_state=state,
            disposal_on=row.disposal_on.date().isoformat() if row.disposal_on else None,
            subject_name=row.subject_name,
            contact_officer=row.contact_officer,
            source=row.source,
        ))

    return Lookup(
        identity=entity.value,
        matched_on=resolved.canonical_value,
        entries=entries,
        statement=_statement(entries, entity.value),
    )
