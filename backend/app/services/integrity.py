"""Walk the audit chain and say whether it holds.

Every action against a case is written with the hash of the action before it, so altering or
removing one breaks every hash after it. That has been true since the chain was written. What was
missing is anybody checking: the receipt reported the chain head and never recomputed it, so the
system had a tamper-evident structure and no way to answer "prove it".

An unverified hash chain is not tamper-evidence. It is a table that looks like one.

Two things are checked for each entry, and they catch different failures:

    the entry's own hash    recomputed from its stored fields. A mismatch means the entry's
                            content is not what was hashed -- somebody edited a row.
    the link to the one     compared against the previous entry's hash. A mismatch means an entry
    before it               was removed, inserted or reordered, even though every row still hashes
                            correctly on its own.

Where a chain breaks, the exact entry is named. "Something is wrong somewhere" is not evidence a
reviewer can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog
from app.services.audit import chain_hash, chain_payload

VERIFICATION_VERSION = "chain-verify-v1"

INTACT = "intact"
BROKEN = "broken"
EMPTY = "empty"
UNCHAINED = "unchained"


@dataclass
class Break:
    """One entry that does not verify, and what specifically is wrong with it."""

    position: int
    entry_id: str
    action: str
    recorded_at: str
    fault: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "entry_id": self.entry_id,
            "action": self.action,
            "recorded_at": self.recorded_at,
            "fault": self.fault,
            "detail": self.detail,
        }


@dataclass
class ChainVerification:
    case_id: str
    status: str
    entries: int
    verified: int
    head: str | None
    first_recorded_at: str | None
    last_recorded_at: str | None
    breaks: list[Break] = field(default_factory=list)
    statement: str = ""
    verification_version: str = VERIFICATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "entries": self.entries,
            "verified": self.verified,
            "head": self.head,
            "first_recorded_at": self.first_recorded_at,
            "last_recorded_at": self.last_recorded_at,
            "breaks": [item.to_dict() for item in self.breaks],
            "statement": self.statement,
            "verification_version": self.verification_version,
        }


def verify_chain(db: Session, case_id: str) -> ChainVerification:
    """Recompute every hash in this case's audit chain and report what holds."""
    entries = list(
        db.scalars(
            select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at, AuditLog.id)
        )
    )

    result = ChainVerification(
        case_id=case_id,
        status=EMPTY,
        entries=len(entries),
        verified=0,
        head=entries[-1].event_hash if entries else None,
        first_recorded_at=entries[0].created_at.isoformat() if entries else None,
        last_recorded_at=entries[-1].created_at.isoformat() if entries else None,
    )

    if not entries:
        result.statement = (
            "No action has been recorded against this case, so there is no chain to verify. That is not a "
            "failure; it is an empty record."
        )
        return result

    # An entry written before the chain existed carries no hash. It is reported rather than
    # treated as tampering: nothing was altered, the guarantee simply does not reach back that far.
    unhashed = [item for item in entries if not item.event_hash]

    previous_hash: str | None = None
    for position, entry in enumerate(entries, start=1):
        if not entry.event_hash:
            previous_hash = None
            continue

        expected = chain_hash(
            chain_payload(
                actor_id=entry.actor_id,
                case_id=entry.case_id,
                action=entry.action,
                object_type=entry.object_type,
                object_id=entry.object_id,
                outcome=entry.outcome,
                details=entry.details,
                previous_hash=entry.previous_hash,
                created_at=entry.created_at,
            )
        )

        if expected != entry.event_hash:
            result.breaks.append(Break(
                position=position,
                entry_id=entry.id,
                action=entry.action,
                recorded_at=entry.created_at.isoformat(),
                fault="content_altered",
                detail=(
                    "This entry does not hash to the value recorded against it, so its content is not what was "
                    "sealed. Every entry after it inherits a hash computed from this one."
                ),
            ))
        elif previous_hash is not None and entry.previous_hash != previous_hash:
            result.breaks.append(Break(
                position=position,
                entry_id=entry.id,
                action=entry.action,
                recorded_at=entry.created_at.isoformat(),
                fault="link_broken",
                detail=(
                    "This entry hashes correctly but does not follow the entry before it. An entry has been "
                    "removed, inserted or reordered between them."
                ),
            ))
        else:
            result.verified += 1

        previous_hash = entry.event_hash

    if result.breaks:
        first = result.breaks[0]
        result.status = BROKEN
        result.statement = (
            f"The chain breaks at entry {first.position} of {result.entries} "
            f"({first.action}, recorded {first.recorded_at}). {first.detail}"
        )
    elif unhashed:
        result.status = UNCHAINED
        result.statement = (
            f"{result.verified} of {result.entries} entries verify. The remaining {len(unhashed)} were written "
            "before this case kept a chain and carry no hash, so the guarantee does not reach them. Nothing "
            "indicates they were altered; nothing proves they were not."
        )
    else:
        result.status = INTACT
        result.statement = (
            f"All {result.entries} recorded actions verify. Each hashes to the value sealed with it and follows "
            "the entry before it, so no entry has been altered, removed or reordered since it was written."
        )

    return result
