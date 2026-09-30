"""Protected multipart evidence intake and controlled original-download endpoints."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import EvidenceFile, EvidenceStatus
from app.schemas.evidence import EvidenceReceiptResponse, EvidenceResponse
from app.services.audit import audit
from app.services.cases import require_case_access
from app.services import source_view
from app.services.storage import delete_private_object, get_private_path, persist_upload, source_category
from app.workers.tasks import process_evidence_task

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])


def _response(item: EvidenceFile) -> EvidenceResponse:
    return EvidenceResponse.model_validate(item, from_attributes=True)


@router.post("", response_model=EvidenceReceiptResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(case_id: str, current_user: CurrentUser, db: DbSession, file: UploadFile = File(...), source_category_value: str = Form(..., alias="source_category")) -> EvidenceReceiptResponse:
    case = require_case_access(db, case_id, current_user)
    evidence = EvidenceFile(id=str(uuid4()), case_id=case.id, original_name=Path(file.filename or "").name, stored_name="pending", storage_key="pending", source_category=source_category(source_category_value), extension=Path(file.filename or "").suffix.lower(), declared_mime=file.content_type, detected_mime="pending", byte_size=0, sha256="pending", status=EvidenceStatus.VALIDATING, uploader_id=current_user.id)
    stored = await persist_upload(file, case_id=case.id, evidence_id=evidence.id)
    duplicate = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case.id, EvidenceFile.sha256 == stored.sha256))
    if duplicate:
        delete_private_object(stored.storage_key)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate evidence hash already exists in this case")
    evidence.stored_name, evidence.storage_key, evidence.extension = stored.stored_name, stored.storage_key, stored.extension
    evidence.detected_mime, evidence.byte_size, evidence.sha256, evidence.status = stored.detected_mime, stored.byte_size, stored.sha256, EvidenceStatus.QUEUED
    db.add(evidence)
    db.flush()
    audit(db, action="evidence.upload", object_type="evidence_file", object_id=evidence.id, case_id=case.id, outcome="success", actor_id=current_user.id, details={"sha256": evidence.sha256, "bytes": evidence.byte_size})
    db.commit()
    process_evidence_task.delay(evidence.id)
    return EvidenceReceiptResponse(evidence=_response(evidence), integrity_receipt={"algorithm": "SHA-256", "digest": evidence.sha256, "bytes": evidence.byte_size, "storage": "private_case_scoped"})


@router.get("", response_model=list[EvidenceResponse])
def list_evidence(case_id: str, current_user: CurrentUser, db: DbSession) -> list[EvidenceResponse]:
    require_case_access(db, case_id, current_user)
    return [_response(item) for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id).order_by(EvidenceFile.uploaded_at)).all()]


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(case_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> EvidenceResponse:
    require_case_access(db, case_id, current_user)
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id))
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence record not found")
    return _response(evidence)


@router.get("/{evidence_id}/original", response_class=FileResponse)
def download_original(case_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> FileResponse:
    require_case_access(db, case_id, current_user)
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id))
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence record not found")
    audit(db, action="evidence.download_original", object_type="evidence_file", object_id=evidence.id, case_id=case_id, outcome="success", actor_id=current_user.id)
    db.commit()
    return FileResponse(get_private_path(evidence.storage_key), media_type=evidence.detected_mime, filename=evidence.original_name)


@router.get("/{evidence_id}/source-view")
def read_source_view(
    case_id: str,
    evidence_id: str,
    current_user: CurrentUser,
    db: DbSession,
    value: str | None = Query(None, max_length=320, description="The value to find, when the reference alone does not place it."),
    row: int | None = Query(None, ge=1),
    column: str | None = Query(None, max_length=160),
    page: int | None = Query(None, ge=1),
    line_start: int | None = Query(None, ge=1),
    line_end: int | None = Query(None, ge=1),
    block_id: str | None = Query(None, max_length=64),
) -> dict:
    """Show one evidence file with the place a stored reference points at marked on it.

    The parameters are the fields of a source reference as it is already stored on a relationship,
    an entity occurrence or an assistant finding, so a caller passes back what it was given rather
    than deriving anything of its own.

    Reading a file's contents is a disclosure of evidence and is recorded as one. The response
    reports whether the place was actually found: a viewer must be able to say "this is the source,
    but the exact spot could not be located" instead of marking somewhere plausible.
    """
    require_case_access(db, case_id, current_user)
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id))
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence record not found")

    target = source_view.Target(
        value=value,
        row=row,
        column=column,
        page=page,
        line_start=line_start,
        line_end=line_end,
        block_id=block_id,
    )
    view = source_view.build(db, evidence, target=target)
    audit(
        db,
        action="evidence.source_view",
        object_type="evidence_file",
        object_id=evidence.id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"kind": view.kind, "located": view.located},
    )
    db.commit()
    return view.to_dict()


@router.get("/{evidence_id}/page/{page_number}")
def read_rendered_page(
    case_id: str,
    evidence_id: str,
    page_number: int,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    """One page of a document, rendered as an image so marks can be drawn on it.

    A PDF is a picture of a record. Citing "page 1, line 6" makes a reviewer count lines; showing
    the page with the line boxed makes them look. The image is rendered at the same scale the
    marks were measured against, so a client can place them without knowing any PDF geometry.
    """
    require_case_access(db, case_id, current_user)
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id))
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence record not found")
    if (evidence.detected_mime or "") != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This evidence is not a document with pages")

    try:
        image = source_view.render_page(get_private_path(evidence.storage_key), page_number)
    except Exception as error:  # noqa: BLE001 - a page that will not render is a 404, not a crash
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That page could not be rendered") from error

    audit(
        db,
        action="evidence.page_render",
        object_type="evidence_file",
        object_id=evidence.id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"page": page_number},
    )
    db.commit()
    return Response(content=image, media_type="image/png")


@router.post("/{evidence_id}/process", response_model=EvidenceResponse)
def requeue_evidence(case_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> EvidenceResponse:
    require_case_access(db, case_id, current_user)
    evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id))
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence record not found")
    evidence.status, evidence.failure_reason = EvidenceStatus.QUEUED, None
    db.commit()
    process_evidence_task.delay(evidence.id)
    return _response(evidence)
