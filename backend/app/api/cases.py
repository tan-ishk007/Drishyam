"""Case CRUD and membership endpoints protected by object-level authorization."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Case, CaseMembership, Role, User
from app.schemas.cases import (
    CaseCreateRequest,
    CaseMemberRequest,
    CaseMemberResponse,
    CaseResponse,
    IncidentWindowRequest,
)
from app.services.audit import audit
from app.services import whats_new as whats_new_service
from app.services.cases import create_case_number, require_case_access

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreateRequest, current_user: CurrentUser, db: DbSession) -> CaseResponse:
    if payload.description is None or not payload.description.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Case description is required.")
    case = Case(
        case_number=create_case_number(),
        title=payload.title.strip(),
        crime_type=payload.crime_type.strip(),
        description=payload.description,
        fir_number=payload.fir_number,
        victim_alias=payload.victim_alias,
        date_range_start=payload.date_range_start,
        date_range_end=payload.date_range_end,
        notes=payload.notes,
        priority=payload.priority,
        owner_id=current_user.id,
    )
    db.add(case)
    db.flush()
    db.add(CaseMembership(case_id=case.id, user_id=current_user.id, case_role=current_user.role))
    audit(db, action="case.create", object_type="case", object_id=case.id, case_id=case.id, outcome="success", actor_id=current_user.id)
    db.commit()
    db.refresh(case)
    return CaseResponse.model_validate(case, from_attributes=True)


@router.get("", response_model=list[CaseResponse])
def list_cases(current_user: CurrentUser, db: DbSession) -> list[CaseResponse]:
    if current_user.role == Role.ADMIN:
        cases = db.scalars(select(Case).order_by(Case.updated_at.desc())).all()
    else:
        cases = db.scalars(
            select(Case)
            .outerjoin(CaseMembership, CaseMembership.case_id == Case.id)
            .where((Case.owner_id == current_user.id) | (CaseMembership.user_id == current_user.id))
            .distinct()
            .order_by(Case.updated_at.desc())
        ).all()
    return [CaseResponse.model_validate(case, from_attributes=True) for case in cases]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, current_user: CurrentUser, db: DbSession) -> CaseResponse:
    case = require_case_access(db, case_id, current_user)
    return CaseResponse.model_validate(case, from_attributes=True)


@router.patch("/{case_id}/incident-window", response_model=CaseResponse)
def set_incident_window(
    case_id: str, payload: IncidentWindowRequest, current_user: CurrentUser, db: DbSession
) -> CaseResponse:
    """Declare, change or clear the span this case treats as the incident.

    A case is usually opened before anybody knows when the incident happened, so this cannot be a
    creation-only field. Until it is declared the case reports that no window exists and every
    temporal reading stays silent; declaring it is what turns a list of timestamps into contact
    placed before, during and after something.

    Because it decides which side of the incident every record falls on, the change is audited with
    both the old span and the new one. A reader who finds a finding surprising can see whether the
    window moved under it.
    """
    case = require_case_access(db, case_id, current_user)
    before = {
        "date_range_start": case.date_range_start.isoformat() if case.date_range_start else None,
        "date_range_end": case.date_range_end.isoformat() if case.date_range_end else None,
    }
    case.date_range_start = payload.date_range_start
    case.date_range_end = payload.date_range_end
    audit(
        db,
        action="case.incident_window_set",
        object_type="case",
        object_id=case.id,
        case_id=case.id,
        outcome="success",
        actor_id=current_user.id,
        details={
            "previous": before,
            "declared": {
                "date_range_start": payload.date_range_start.isoformat() if payload.date_range_start else None,
                "date_range_end": payload.date_range_end.isoformat() if payload.date_range_end else None,
            },
        },
    )
    db.commit()
    db.refresh(case)
    return CaseResponse.model_validate(case, from_attributes=True)


@router.get("/{case_id}/whats-new")
def whats_new(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """What has arrived in this case since this reader last opened it.

    Reading it does not move the mark. A reader who glanced at the digest and was called away would
    otherwise never see those changes again, which is the one way this feature could actively lose
    somebody information.
    """
    require_case_access(db, case_id, current_user)
    return whats_new_service.build(db, case_id, current_user).to_dict()


@router.post("/{case_id}/whats-new/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(case_id: str, current_user: CurrentUser, db: DbSession) -> None:
    """Mark this case as seen as it now stands. Explicit, because it is what clears the digest."""
    require_case_access(db, case_id, current_user)
    whats_new_service.record_visit(db, case_id, current_user)
    db.commit()


@router.post("/{case_id}/members", response_model=CaseMemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(case_id: str, payload: CaseMemberRequest, current_user: CurrentUser, db: DbSession) -> CaseMemberResponse:
    case = require_case_access(db, case_id, current_user, owner_only=True)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership = db.scalar(select(CaseMembership).where(CaseMembership.case_id == case.id, CaseMembership.user_id == user.id))
    if membership:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already has access to this case")
    membership = CaseMembership(case_id=case.id, user_id=user.id, case_role=payload.case_role)
    db.add(membership)
    audit(db, action="case.member_add", object_type="case_membership", object_id=membership.id, case_id=case.id, outcome="success", actor_id=current_user.id, details={"member_id": user.id})
    db.commit()
    return CaseMemberResponse(user_id=user.id, case_id=case.id, case_role=membership.case_role)

