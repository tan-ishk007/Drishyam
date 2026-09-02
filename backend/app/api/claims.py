"""Structured claim and contradiction registers; mutation routes require explicit caller approval."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Alert, Claim, ClaimSourceLink, ClaimStatus, Contradiction, ContradictionSourceLink, ContradictionStatus, Entity, Event, EvidenceFile, Transaction
from app.schemas.claims import ClaimCreateRequest, ClaimResponse, ClaimStatusUpdateRequest, ContradictionCreateRequest, ContradictionResponse, ContradictionStatusUpdateRequest, SourceLinkResponse, SourceLinkWrite
from app.services.audit import audit
from app.services.cases import require_case_access


router = APIRouter(prefix="/cases/{case_id}", tags=["claims-and-contradictions"])
SOURCE_MODELS = {"evidence": EvidenceFile, "event": Event, "entity": Entity, "transaction": Transaction, "alert": Alert}


def _claim_sources(db: DbSession, claim_id: str) -> list[SourceLinkResponse]:
    return [SourceLinkResponse(source_type=item.source_type, source_id=item.source_id, relationship=item.relationship_type, note=item.note) for item in db.scalars(select(ClaimSourceLink).where(ClaimSourceLink.claim_id == claim_id).order_by(ClaimSourceLink.created_at)).all()]


def _contradiction_sources(db: DbSession, contradiction_id: str) -> list[SourceLinkResponse]:
    return [SourceLinkResponse(source_type=item.source_type, source_id=item.source_id, relationship=item.relationship_type, note=item.note) for item in db.scalars(select(ContradictionSourceLink).where(ContradictionSourceLink.contradiction_id == contradiction_id).order_by(ContradictionSourceLink.created_at)).all()]


def _validate_sources(db: DbSession, case_id: str, sources: list[SourceLinkWrite]) -> None:
    for source in sources:
        model = SOURCE_MODELS.get(source.source_type.lower())
        if not model:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported source type: {source.source_type}")
        exists = db.scalar(select(model.id).where(model.id == source.source_id, model.case_id == case_id))
        if not exists:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Source {source.source_type}:{source.source_id} is not available in this case")


def _claim_response(db: DbSession, item: Claim) -> ClaimResponse:
    return ClaimResponse(id=item.id, case_id=item.case_id, statement=item.statement, claim_type=item.claim_type, scope_note=item.scope_note, status=item.status, created_by_id=item.created_by_id, created_at=item.created_at, updated_at=item.updated_at, sources=_claim_sources(db, item.id))


def _contradiction_response(db: DbSession, item: Contradiction) -> ContradictionResponse:
    return ContradictionResponse(id=item.id, case_id=item.case_id, subject=item.subject, description=item.description, status=item.status, created_by_id=item.created_by_id, created_at=item.created_at, updated_at=item.updated_at, sources=_contradiction_sources(db, item.id))


@router.get("/claims", response_model=list[ClaimResponse])
def list_claims(case_id: str, current_user: CurrentUser, db: DbSession) -> list[ClaimResponse]:
    """Return existing case claims only; an empty list is a valid non-conclusive response."""
    require_case_access(db, case_id, current_user)
    return [_claim_response(db, item) for item in db.scalars(select(Claim).where(Claim.case_id == case_id).order_by(Claim.created_at.desc())).all()]


@router.post("/claims", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim(case_id: str, payload: ClaimCreateRequest, current_user: CurrentUser, db: DbSession) -> ClaimResponse:
    """Create a source-linked claim only when an explicitly approved caller invokes this route."""
    require_case_access(db, case_id, current_user)
    _validate_sources(db, case_id, payload.sources)
    claim = Claim(case_id=case_id, statement=payload.statement.strip(), claim_type=payload.claim_type.strip(), scope_note=payload.scope_note.strip() if payload.scope_note else None, status=ClaimStatus.DRAFT, created_by_id=current_user.id)
    db.add(claim)
    db.flush()
    for source in payload.sources:
        db.add(ClaimSourceLink(claim_id=claim.id, source_type=source.source_type.lower(), source_id=source.source_id, relationship_type=source.relationship, note=source.note.strip() if source.note else None))
    audit(db, action="claim.create", object_type="claim", object_id=claim.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"source_count": len(payload.sources), "claim_type": claim.claim_type})
    db.commit()
    db.refresh(claim)
    return _claim_response(db, claim)


@router.post("/claims/{claim_id}/status", response_model=ClaimResponse)
def update_claim_status(case_id: str, claim_id: str, payload: ClaimStatusUpdateRequest, current_user: CurrentUser, db: DbSession) -> ClaimResponse:
    require_case_access(db, case_id, current_user)
    claim = db.scalar(select(Claim).where(Claim.id == claim_id, Claim.case_id == case_id))
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found in this case")
    claim.status = payload.status
    audit(db, action="claim.status_update", object_type="claim", object_id=claim.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"status": payload.status.value})
    db.commit()
    db.refresh(claim)
    return _claim_response(db, claim)


@router.get("/contradictions", response_model=list[ContradictionResponse])
def list_contradictions(case_id: str, current_user: CurrentUser, db: DbSession) -> list[ContradictionResponse]:
    """Return existing case contradiction records only; an empty list never proves no conflict exists."""
    require_case_access(db, case_id, current_user)
    return [_contradiction_response(db, item) for item in db.scalars(select(Contradiction).where(Contradiction.case_id == case_id).order_by(Contradiction.created_at.desc())).all()]


@router.post("/contradictions", response_model=ContradictionResponse, status_code=status.HTTP_201_CREATED)
def create_contradiction(case_id: str, payload: ContradictionCreateRequest, current_user: CurrentUser, db: DbSession) -> ContradictionResponse:
    """Create a source-linked contradiction only when an explicitly approved caller invokes this route."""
    require_case_access(db, case_id, current_user)
    _validate_sources(db, case_id, payload.sources)
    contradiction = Contradiction(case_id=case_id, subject=payload.subject.strip(), description=payload.description.strip(), status=ContradictionStatus.OPEN, created_by_id=current_user.id)
    db.add(contradiction)
    db.flush()
    for source in payload.sources:
        db.add(ContradictionSourceLink(contradiction_id=contradiction.id, source_type=source.source_type.lower(), source_id=source.source_id, relationship_type=source.relationship, note=source.note.strip() if source.note else None))
    audit(db, action="contradiction.create", object_type="contradiction", object_id=contradiction.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"source_count": len(payload.sources)})
    db.commit()
    db.refresh(contradiction)
    return _contradiction_response(db, contradiction)


@router.post("/contradictions/{contradiction_id}/status", response_model=ContradictionResponse)
def update_contradiction_status(case_id: str, contradiction_id: str, payload: ContradictionStatusUpdateRequest, current_user: CurrentUser, db: DbSession) -> ContradictionResponse:
    require_case_access(db, case_id, current_user)
    contradiction = db.scalar(select(Contradiction).where(Contradiction.id == contradiction_id, Contradiction.case_id == case_id))
    if not contradiction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found in this case")
    contradiction.status = payload.status
    audit(db, action="contradiction.status_update", object_type="contradiction", object_id=contradiction.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"status": payload.status.value})
    db.commit()
    db.refresh(contradiction)
    return _contradiction_response(db, contradiction)
