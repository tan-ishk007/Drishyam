"""Compact audit trail service that stores metadata only, never credentials or original evidence content."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog
from app.core.security import utcnow


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
    previous = None
    if case_id:
        previous_entry = db.scalar(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc()))
        previous = previous_entry.event_hash if previous_entry else None
    payload = {"actor_id": actor_id, "case_id": case_id, "action": action, "object_type": object_type, "object_id": object_id, "outcome": outcome, "details": details or {}, "previous_hash": previous, "created_at": created_at.isoformat()}
    entry = AuditLog(
        actor_id=actor_id,
        case_id=case_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=outcome,
        details=details or {},
        previous_hash=previous,
        event_hash=hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest(),
        created_at=created_at,
    )
    db.add(entry)
    return entry
