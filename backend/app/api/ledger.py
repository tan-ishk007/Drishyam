"""Publishing to and reading the shared identifier ledger.

Every route here is gated twice over and audited. Publishing is the one action in this product that
puts anything derived from a case outside it, and asking whether an identifier appears elsewhere is
itself an access event -- an officer who runs that check has learned something about another force's
case file, even if all they learned is that it exists.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.services import ledger
from app.services.audit import audit
from app.services.cases import require_case_access

settings = get_settings()

router = APIRouter(tags=["shared-ledger"])


class PublishRequest(BaseModel):
    """A contact is required, not optional.

    The ledger's entire purpose is that another force can pick up a phone. An entry with no way to
    be reached tells them an identifier is shared and gives them nothing to do about it.
    """

    contact: str = Field(min_length=3, max_length=320)


@router.get("/ledger/status")
def ledger_status(current_user: CurrentUser, db: DbSession) -> dict:
    """Whether the ledger is open, and what it would publish if it were.

    Readable with the gate shut, deliberately: somebody has to be able to see that it is off, and
    the answer discloses nothing about any case.
    """
    verification = ledger.verify(db)
    return {
        "open": settings.ledger_publication_allowed,
        "switches": {
            "ledger_enabled": settings.ledger_enabled,
            "ledger_publication": settings.ledger_publication,
            "shared_key_present": bool(settings.ledger_key),
        },
        "closed_reason": None if settings.ledger_publication_allowed else ledger.CLOSED_GATE,
        "chain": verification.to_dict(),
        "publishes": (
            "A keyed digest of each identifier, the case reference, and a contact. No identifier, no name, and "
            "nothing about what a case contains."
        ),
    }


@router.post("/cases/{case_id}/ledger/publish")
def publish(case_id: str, payload: PublishRequest, current_user: CurrentUser, db: DbSession) -> dict:
    """Put this case's identifiers on the shared ledger."""
    case = require_case_access(db, case_id, current_user, owner_only=True)
    try:
        result = ledger.publish_case(db, case, current_user, payload.contact.strip())
    except ledger.LedgerClosed as closed:
        # Recorded even though nothing was published: an attempt to send identifiers outside the
        # case is worth a line in the record whether or not the gate let it through.
        audit(db, action="ledger.publish", object_type="case", object_id=case.id, case_id=case.id, outcome="refused", actor_id=current_user.id, details={"reason": "gate_closed"})
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(closed)) from closed

    audit(db, action="ledger.publish", object_type="case", object_id=case.id, case_id=case.id, outcome="success", actor_id=current_user.id, details={"published": result.published, "already_present": result.already_present})
    db.commit()
    return result.to_dict()


@router.delete("/cases/{case_id}/ledger/publish")
def withdraw(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Take back what this case published.

    This leaves a hole in an append-only chain and the ledger will report itself broken from that
    point. That is the honest trade: a withdrawal nobody could see would make the chain worthless,
    and an identifier that can never be withdrawn however wrongly it was published is worse.
    """
    case = require_case_access(db, case_id, current_user, owner_only=True)
    removed = ledger.withdraw_case(db, case)
    audit(db, action="ledger.withdraw", object_type="case", object_id=case.id, case_id=case.id, outcome="success", actor_id=current_user.id, details={"removed": removed})
    db.commit()
    return {
        "withdrawn": removed,
        "note": (
            "These entries have been removed. The ledger chain will now report a break where they were, which is "
            "visible to every district reading it -- a withdrawal that could not be seen would make the chain "
            "worth nothing."
        ),
    }


@router.get("/cases/{case_id}/ledger/matches")
def matches(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Which other cases hold an identifier this case also holds.

    The answer names a case reference and an officer. It cannot name what that case contains,
    because the ledger does not hold that and never did.
    """
    case = require_case_access(db, case_id, current_user)
    try:
        found = ledger.matches_for_case(db, case)
    except ledger.LedgerClosed as closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(closed)) from closed

    audit(db, action="ledger.match", object_type="case", object_id=case.id, case_id=case.id, outcome="success", actor_id=current_user.id, details={"matches": len(found)})
    db.commit()
    return {
        "matches": [item.to_dict() for item in found],
        "note": (
            "Each match means another case holds an identifier this one also holds. It says nothing about what that "
            "case is, what it found, or whether the two are related. Contact the officer named."
        ),
    }
