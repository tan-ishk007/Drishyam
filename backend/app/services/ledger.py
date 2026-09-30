"""The shared identifier ledger: the one place in this product where a ledger earns its cost.

Two districts hold cases that involve the same phone number and neither knows it. Today the only
way to find that out is for one officer to describe their case to another, which is exactly what
case-level authorisation exists to prevent. So the question has to be answerable without either
side seeing the other's file.

**What is published.** A keyed digest of the identifier, the case reference, and a contact. Nothing
else: not the identifier, not a name, not a fact about what the case contains, not even how many
identifiers the case holds beyond what is published. The receiving district learns "an identifier
you also hold appears in case DRI-2026-1024, ring this officer" and not one thing more.

The one exception is the contact, and it is worth naming rather than glossing. It is free text a
person types, so nothing here can stop an officer writing case detail into it. Every other field is
machine-written and carries only what this module put there; that one is only as careful as whoever
filled it in, and the interface asks for a name and a station for exactly that reason.

**Why keyed and not merely hashed.** A plain SHA-256 of a phone number is the phone number with
extra steps: there are about ten billion of them and a laptop enumerates that space in an
afternoon. The same is true of vehicle registrations and UPI handles. So the digest is an HMAC
under a key the participating districts share, which a stolen copy of the ledger does not include.
Without that key there is no ledger at all -- publishing is refused rather than falling back to
something that looks like protection and is not.

**Why a chain rather than a table.** Everywhere else in DRISHYAM there is one party and it is
trusted, and a local hash chain is the honest answer. Here the parties are different forces, and
the property that matters is that whoever holds the store cannot quietly remove an entry, backdate
one, or reorder them. Each entry carries the hash of the one before it, so any of those breaks
every hash after it -- and `verify()` walks it exactly as the case audit chain is walked.

**What this is not.** There is no consensus, no mining, and no distributed agreement here, and this
module does not pretend otherwise. It is an append-only chained store with a shared key. Calling
that a blockchain would be a claim about Byzantine fault tolerance that nothing here provides.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utcnow
from app.models.entities import Case, Entity, LedgerEntry, User
from app.services.cross_case import MATCHABLE_ENTITY_TYPES
from app.services.entity_resolution import canonicalize_indicator

settings = get_settings()

__all__ = ["canonicalize_indicator", "digest", "publish_case", "withdraw_case", "matches_for_case", "verify"]

LEDGER_VERSION = "ledger-v1"

INTACT = "intact"
BROKEN = "broken"
EMPTY = "empty"

CLOSED_GATE = (
    "The shared ledger is switched off. Nothing derived from this case has been published. It requires both "
    "settings to be on and a key shared with the other participating districts; any one of the three missing "
    "means publishing is refused rather than done weakly."
)


class LedgerClosed(RuntimeError):
    """Raised rather than degrading. A gate that half-opens is not a gate."""


@dataclass
class Published:
    case_reference: str
    published: int
    already_present: int
    skipped_unmatchable: int
    head: str | None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_reference": self.case_reference,
            "published": self.published,
            "already_present": self.already_present,
            "skipped_unmatchable": self.skipped_unmatchable,
            "head": self.head,
            "note": self.note,
            "ledger_version": LEDGER_VERSION,
        }


@dataclass
class Match:
    """A shared identifier, told in the only terms the other district may hear."""

    case_reference: str
    contact: str
    published_at: str
    # Which of this case's identities matched, so the reader knows what to ring about. This is the
    # reader's own data being named back to them, not anything learned from the other case.
    your_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_reference": self.case_reference,
            "contact": self.contact,
            "published_at": self.published_at,
            "your_identity": self.your_identity,
        }


@dataclass
class LedgerVerification:
    status: str
    entries: int
    verified: int
    head: str | None
    broken_at: int | None = None
    statement: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "entries": self.entries,
            "verified": self.verified,
            "head": self.head,
            "broken_at": self.broken_at,
            "statement": self.statement,
            "ledger_version": LEDGER_VERSION,
        }


# --------------------------------------------------------------------------- the digest


def digest(entity_type: str, canonical_value: str) -> str:
    """The published form of one identifier.

    The type is inside the digest rather than stored beside it. Folding it in stops an account
    number matching a phone number that happens to read the same, and keeping it out of the row
    means the ledger does not even disclose what kind of identifier somebody published.
    """
    key = settings.ledger_key
    if not key:
        raise LedgerClosed(CLOSED_GATE)
    return hmac.new(
        key.get_secret_value().encode("utf-8"),
        f"{entity_type}:{canonical_value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _chain_payload(entry: LedgerEntry) -> dict[str, Any]:
    """Exactly what an entry's hash is taken over. A stored format, not an implementation detail."""
    return {
        "identifier_digest": entry.identifier_digest,
        "case_reference": entry.case_reference,
        "contact": entry.contact,
        "previous_hash": entry.previous_hash,
        "published_at": entry.published_at.isoformat()
        if isinstance(entry.published_at, datetime)
        else entry.published_at,
    }


def _chain_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _head(db: Session) -> LedgerEntry | None:
    """The last entry, counting anything pending in this session.

    The session does not autoflush, so a run that appends several entries before committing would
    otherwise have every one of them claim the same predecessor -- and the chain would read as
    broken with nothing having been tampered with.
    """
    pending = [item for item in db.new if isinstance(item, LedgerEntry) and item.published_at]
    stored = db.scalar(select(LedgerEntry).order_by(LedgerEntry.published_at.desc(), LedgerEntry.id.desc()))
    candidates = pending + ([stored] if stored is not None else [])
    return max(candidates, key=lambda item: item.published_at) if candidates else None


# --------------------------------------------------------------------------- publishing


def _identities(db: Session, case_id: str) -> list[tuple[str, str, str]]:
    """This case's identifiers, in the canonical form both districts will compute the same way.

    Canonicalising is what makes matching work at all: a number written +91 98765 43210 in one file
    and 09876543210 in another is one identifier, and a ledger that published the written form
    would match neither against the other.
    """
    found: dict[str, tuple[str, str, str]] = {}
    for entity in db.scalars(select(Entity).where(Entity.case_id == case_id)).all():
        if entity.entity_type not in MATCHABLE_ENTITY_TYPES:
            continue
        resolved = canonicalize_indicator(entity.entity_type, entity.value)
        if resolved is None:
            continue
        found.setdefault(
            f"{resolved.entity_type}:{resolved.canonical_value}",
            (resolved.entity_type, resolved.canonical_value, entity.value),
        )
    return list(found.values())


def publish_case(db: Session, case: Case, user: User, contact: str) -> Published:
    """Put this case's identifiers on the shared ledger, as digests and a way to be reached.

    Raises rather than returning an empty result when the gate is shut. A caller that received
    "published: 0" from a closed gate would reasonably read it as "this case has no identifiers".
    """
    if not settings.ledger_publication_allowed:
        raise LedgerClosed(CLOSED_GATE)

    identities = _identities(db, case.id)
    all_entities = db.scalars(select(Entity).where(Entity.case_id == case.id)).all()

    published = 0
    already = 0
    for entity_type, canonical, _ in identities:
        value = digest(entity_type, canonical)
        exists = db.scalar(
            select(LedgerEntry).where(
                LedgerEntry.identifier_digest == value, LedgerEntry.case_reference == case.case_number
            )
        )
        if exists is not None:
            already += 1
            continue
        previous = _head(db)
        entry = LedgerEntry(
            identifier_digest=value,
            case_reference=case.case_number,
            contact=contact,
            published_by_id=user.id,
            source_case_id=case.id,
            previous_hash=previous.entry_hash if previous else None,
            published_at=utcnow(),
        )
        entry.entry_hash = _chain_hash(_chain_payload(entry))
        db.add(entry)
        published += 1

    head = _head(db)
    return Published(
        case_reference=case.case_number,
        published=published,
        already_present=already,
        skipped_unmatchable=len(all_entities) - len(identities),
        head=head.entry_hash if head else None,
        note=(
            "Only a keyed digest of each identifier, this case's reference and a contact were written. No "
            "identifier, name, or fact about this case left it."
        ),
    )


def withdraw_case(db: Session, case: Case) -> int:
    """Remove what this case published.

    A withdrawal is a hole in a chain that is supposed to be append-only, and it will make
    `verify()` report the chain as broken from that point. That is correct and is left visible: a
    ledger that let entries be removed silently would give the other districts nothing worth
    trusting. The alternative -- a published identifier that can never be taken back, however
    wrongly it was published -- is worse.
    """
    rows = db.scalars(select(LedgerEntry).where(LedgerEntry.source_case_id == case.id)).all()
    for row in rows:
        db.delete(row)
    return len(rows)


# --------------------------------------------------------------------------- matching


def matches_for_case(db: Session, case: Case) -> list[Match]:
    """Which other cases on the ledger hold an identifier this case also holds.

    Entries this case published are excluded: telling an officer that their own case shares an
    identifier with their own case is noise, and would also be the one way this endpoint could
    confirm to a reader what they themselves published.
    """
    if not settings.ledger_publication_allowed:
        raise LedgerClosed(CLOSED_GATE)

    wanted = {digest(entity_type, canonical): written for entity_type, canonical, written in _identities(db, case.id)}
    if not wanted:
        return []

    rows = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.identifier_digest.in_(wanted.keys()), LedgerEntry.case_reference != case.case_number
        )
    ).all()
    return [
        Match(
            case_reference=row.case_reference,
            contact=row.contact,
            published_at=row.published_at.isoformat(),
            your_identity=wanted[row.identifier_digest],
        )
        for row in sorted(rows, key=lambda item: item.published_at)
    ]


def matches_for_identity(db: Session, case: Case, entity: Entity) -> list[Match]:
    """Which other cases on the ledger hold this one identity.

    The per-case check answers "does this case overlap with anyone". This answers the question an
    investigator actually asks, which is about one number in front of them: is this the same person
    another district is already looking for.

    An identity the resolver cannot canonicalise returns nothing rather than being digested from
    whatever string happened to be typed. Two districts must compute the same digest from the same
    identifier written differently, and a raw string does not have that property.
    """
    if not settings.ledger_publication_allowed:
        raise LedgerClosed(CLOSED_GATE)

    resolved = canonicalize_indicator(entity.entity_type, entity.value)
    if resolved is None or entity.entity_type not in MATCHABLE_ENTITY_TYPES:
        return []

    rows = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.identifier_digest == digest(resolved.entity_type, resolved.canonical_value),
            LedgerEntry.case_reference != case.case_number,
        )
    ).all()
    return [
        Match(
            case_reference=row.case_reference,
            contact=row.contact,
            published_at=row.published_at.isoformat(),
            your_identity=entity.value,
        )
        for row in sorted(rows, key=lambda item: item.published_at)
    ]


# --------------------------------------------------------------------------- verifying


def verify(db: Session) -> LedgerVerification:
    """Walk the ledger and say whether it holds.

    The whole reason this store is chained is that the districts reading it do not have to trust
    whoever hosts it. That is worth nothing until somebody recomputes it, which is what this does.
    """
    entries = list(db.scalars(select(LedgerEntry).order_by(LedgerEntry.published_at, LedgerEntry.id)))
    if not entries:
        return LedgerVerification(
            status=EMPTY,
            entries=0,
            verified=0,
            head=None,
            statement="Nothing has been published to the shared ledger. That is an empty record, not a failure.",
        )

    previous: str | None = None
    verified = 0
    broken_at: int | None = None
    for position, entry in enumerate(entries, start=1):
        recomputed = _chain_hash(_chain_payload(entry))
        if recomputed != entry.entry_hash or entry.previous_hash != previous:
            broken_at = position
            break
        verified += 1
        previous = entry.entry_hash

    if broken_at is not None:
        return LedgerVerification(
            status=BROKEN,
            entries=len(entries),
            verified=verified,
            head=entries[-1].entry_hash,
            broken_at=broken_at,
            statement=(
                f"The ledger holds for its first {verified} entries and breaks at entry {broken_at} of {len(entries)}. "
                "An entry has been altered, removed or reordered since it was written. Entries after a break cannot "
                "be relied on, whatever they say."
            ),
        )

    return LedgerVerification(
        status=INTACT,
        entries=len(entries),
        verified=verified,
        head=entries[-1].entry_hash,
        statement=(
            f"All {len(entries)} published entries verify. Each hashes to the value sealed with it and follows the "
            "entry before it, so none has been altered, removed or reordered by whoever holds this store."
        ),
    )
