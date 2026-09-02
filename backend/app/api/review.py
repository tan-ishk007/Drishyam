"""Protected human-review decisions and dynamic report workflows."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Alert, AuditLog, Entity, Event, EvidenceFile, Report, Transaction, TrustifyReceipt
from app.schemas.reports import ReportResponse
from app.schemas.review import ReviewRequest, ReviewResponse
from app.services.audit import audit
from app.services.cases import require_case_access
from app.services.reporting import create_report_record, get_report_path
from app.services.trustify import verify_receipt
from app.services.review import apply_review
from app.workers.tasks import generate_report_task

router = APIRouter(prefix="/cases/{case_id}", tags=["review-and-reports"])


@router.get("/review-queue")
def review_queue(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    require_case_access(db, case_id, current_user)
    return {"events": [{"id": item.id, "type": item.event_type, "status": item.review_status.value} for item in db.scalars(select(Event).where(Event.case_id == case_id, Event.review_status == "unreviewed")).all()], "entities": [{"id": item.id, "type": item.entity_type, "value": item.value, "status": item.review_status.value} for item in db.scalars(select(Entity).where(Entity.case_id == case_id, Entity.review_status == "unreviewed")).all()], "transactions": [{"id": item.id, "amount": float(item.amount), "status": item.review_status.value} for item in db.scalars(select(Transaction).where(Transaction.case_id == case_id, Transaction.review_status == "unreviewed")).all()], "alerts": [{"id": item.id, "rule": item.rule_code, "severity": item.severity.value, "status": item.status.value} for item in db.scalars(select(Alert).where(Alert.case_id == case_id)).all()]}


@router.post("/review/{subject_type}/{subject_id}", response_model=ReviewResponse)
def review_subject(case_id: str, subject_type: str, subject_id: str, payload: ReviewRequest, current_user: CurrentUser, db: DbSession) -> ReviewResponse:
    require_case_access(db, case_id, current_user)
    decision = apply_review(db, case_id=case_id, subject_type=subject_type, subject_id=subject_id, decision=payload.decision, note=payload.note, reviewer_id=current_user.id)
    audit(db, action="review.apply", object_type=subject_type, object_id=subject_id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"decision": payload.decision.value})
    db.commit()
    return ReviewResponse(subject_type=subject_type, subject_id=subject_id, decision=payload.decision, review_id=decision.id)


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_202_ACCEPTED)
def create_report(case_id: str, current_user: CurrentUser, db: DbSession) -> ReportResponse:
    require_case_access(db, case_id, current_user)
    report = create_report_record(db, case_id=case_id, generated_by_id=current_user.id)
    audit(db, action="report.create", object_type="report", object_id=report.id, case_id=case_id, outcome="queued", actor_id=current_user.id)
    db.commit()
    generate_report_task.delay(report.id)
    return ReportResponse.model_validate(report, from_attributes=True)


@router.get("/reports", response_model=list[ReportResponse])
def list_reports(case_id: str, current_user: CurrentUser, db: DbSession) -> list[ReportResponse]:
    require_case_access(db, case_id, current_user)
    return [ReportResponse.model_validate(item, from_attributes=True) for item in db.scalars(select(Report).where(Report.case_id == case_id).order_by(Report.version.desc())).all()]


@router.get("/reports/{report_id}/download", response_class=FileResponse)
def download_report(case_id: str, report_id: str, current_user: CurrentUser, db: DbSession) -> FileResponse:
    require_case_access(db, case_id, current_user)
    report = db.scalar(select(Report).where(Report.id == report_id, Report.case_id == case_id))
    if not report or not report.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated report is not available")
    audit(db, action="report.download", object_type="report", object_id=report.id, case_id=case_id, outcome="success", actor_id=current_user.id)
    db.commit()
    return FileResponse(get_report_path(report.storage_key), media_type="application/pdf", filename=f"drishyam-report-v{report.version}.pdf")


@router.get("/trustify/reports/{report_id}/verify")
def verify_report(case_id: str, report_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    require_case_access(db, case_id, current_user)
    try:
        result = verify_receipt(db, case_id, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit(db, action="trustify.verify", object_type="report", object_id=report_id, case_id=case_id, outcome=result["status"], actor_id=current_user.id)
    db.commit()
    return result


@router.get("/trustify/summary")
def trustify_summary(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    require_case_access(db, case_id, current_user)
    evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()
    receipts = db.scalars(select(TrustifyReceipt).where(TrustifyReceipt.case_id == case_id).order_by(TrustifyReceipt.created_at.desc())).all()
    latest_audit_hash = db.scalar(select(AuditLog.event_hash).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc()))
    return {
        "case_id": case_id,
        "evidence_count": len(evidence),
        "evidence_hashes_present": sum(1 for item in evidence if item.sha256),
        "audit_event_count": db.scalar(select(func.count(AuditLog.id)).where(AuditLog.case_id == case_id)) or 0,
        "audit_chain_head": latest_audit_hash,
        "report_receipt_count": len(receipts),
        "latest_verification_id": receipts[0].verification_id if receipts else None,
        "caution": "Trustify records technical integrity and traceability signals; it does not decide truth, guilt, or legal admissibility.",
    }
