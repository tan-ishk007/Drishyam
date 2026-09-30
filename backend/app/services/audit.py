"""Compact audit trail service that stores metadata only, never credentials or original evidence content.

Each entry carries the hash of the one before it, so an entry that is altered or removed breaks
every hash after it. That is the whole of what a chain gives, and it is worth nothing until somebody
walks it -- which `app.services.integrity` does.

The payload a hash is taken over is built in exactly one place below, and both writing and
verifying call it. Two copies of that dictionary would be two definitions of what the chain
protects, and the day they drifted apart every chain in the system would read as broken while
nothing had actually been tampered with.
"""

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog
from app.core.security import utcnow


def chain_payload(
    *,
    actor_id: str | None,
    case_id: str | None,
    action: str,
    object_type: str,
    object_id: str | None,
    outcome: str,
    details: dict | None,
    previous_hash: str | None,
    created_at: datetime | str,
) -> dict:
    """The exact record a chain hash is taken over.

    Changing a field here changes every hash the system will compute from now on, and every entry
    written before the change will fail verification. That is the correct behaviour -- the old
    entries genuinely are hashes of a different record -- but it means this shape is a stored
    format, not an implementation detail.
    """
    return {
        "actor_id": actor_id,
        "case_id": case_id,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "outcome": outcome,
        "details": details or {},
        "previous_hash": previous_hash,
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
    }


def chain_hash(payload: dict) -> str:
    """Stable across processes and machines: sorted keys, no incidental whitespace."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _previous_hash(db: Session, case_id: str | None) -> str | None:
    """The hash this entry must follow: the latest recorded action against the same case.

    The session does not autoflush, so an entry added earlier in the same transaction is still
    only in memory and a plain query cannot see it. Two actions recorded before a single commit
    would then both claim to follow the same predecessor, and the chain would read as broken with
    nothing having been tampered with. Pending entries are therefore considered alongside stored
    ones rather than flushing here, which would push out whatever else the caller is midway
    through building.
    """
    if not case_id:
        return None
    candidates = [
        entry
        for entry in db.new
        if isinstance(entry, AuditLog) and entry.case_id == case_id and entry.created_at
    ]
    stored = db.scalar(
        select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc())
    )
    if stored is not None:
        candidates.append(stored)
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry.created_at).event_hash


def audit(
    db: Session,
    *,
    action: str,
    object_type: str,
    outcome: str,
    actor_id: str | None = None,
    case_id: str | None = None,
    object_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    created_at = utcnow()
    previous = _previous_hash(db, case_id)
    payload = chain_payload(
        actor_id=actor_id,
        case_id=case_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=outcome,
        details=details,
        previous_hash=previous,
        created_at=created_at,
    )
    entry = AuditLog(
        actor_id=actor_id,
        case_id=case_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=outcome,
        details=details or {},
        previous_hash=previous,
        event_hash=chain_hash(payload),
        created_at=created_at,
    )
    db.add(entry)
    return entry
