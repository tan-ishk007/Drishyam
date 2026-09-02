"""Case numbering and object-level case authorization helpers."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Case, CaseMembership, Role, User


def create_case_number() -> str:
    return f"DRI-{datetime.now(timezone.utc):%Y%m%d}-{datetime.now(timezone.utc):%H%M%S%f}"[-29:]


def get_case_or_404(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def require_case_access(db: Session, case_id: str, user: User, *, owner_only: bool = False) -> Case:
    case = get_case_or_404(db, case_id)
    if user.role == Role.ADMIN:
        return case
    if case.owner_id == user.id:
        return case
    if owner_only:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case owner access is required")
    membership = db.scalar(select(CaseMembership).where(CaseMembership.case_id == case_id, CaseMembership.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this case")
    return case

