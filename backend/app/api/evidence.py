"""Protected multipart evidence intake and controlled original-download endpoints."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import EvidenceFile, EvidenceStatus
from app.schemas.evidence import EvidenceReceiptResponse, EvidenceResponse
from app.services.audit import audit
from app.services.cases import require_case_access
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
