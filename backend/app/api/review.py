"""Protected human-review decisions and dynamic report workflows."""

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Alert, AuditLog, Entity, Event, EvidenceFile, Report, Transaction, TrustifyReceipt
from app.schemas.reports import ReportRequest, ReportResponse
from app.schemas.review import ReviewRequest, ReviewResponse
from app.services.audit import audit
from app.services.cases import require_case_access
from app.services.integrity import verify_chain
from app.services import report_questions, report_view
from app.services.reporting import create_report_record, get_report_path
from app.services.trustify import inclusion_proof, verify_receipt
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
def create_report(case_id: str, current_user: CurrentUser, db: DbSession, payload: ReportRequest | None = None) -> ReportResponse:
    """Generate a report for this case.

    The body is optional so that callers written before profiles existed keep getting the full case
    file, which is what they were always getting.
    """
    require_case_access(db, case_id, current_user)
    request = payload or ReportRequest()
    report = create_report_record(
        db,
        case_id=case_id,
        generated_by_id=current_user.id,
        redaction_profile=request.redaction_profile,
        profile=request.profile,
    )
    audit(db, action="report.create", object_type="report", object_id=report.id, case_id=case_id, outcome="queued", actor_id=current_user.id, details={"profile": request.profile, "redaction_profile": request.redaction_profile})
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


def _readable_report(case_id: str, report_id: str, current_user, db):
    """The report file, once the reader has been shown to be allowed to open it.

    Reading a report is an access event in exactly the way downloading one is. The difference
    between the two is where the copy ends up, not who is entitled to see it, so the same
    authorisation applies and the same audit trail records it.
    """
    require_case_access(db, case_id, current_user)
    report = db.scalar(select(Report).where(Report.id == report_id, Report.case_id == case_id))
    if not report or not report.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated report is not available")
    path = get_report_path(report.storage_key)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The report record exists but its file is not on this server.",
        )
    return report, path


@router.get("/reports/{report_id}/pages")
def report_pages(case_id: str, report_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """How long the report is and what size its pages render at.

    Opening a report to read it is recorded. A reviewer who reads a report and a reviewer who
    downloads one have both accessed the case's formal record.
    """
    report, path = _readable_report(case_id, report_id, current_user, db)
    try:
        described = report_view.describe(path)
    except Exception as failure:  # a corrupt or half-written PDF must say so, not return a blank viewer
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This report could not be opened for reading: {failure}",
        ) from failure
    audit(db, action="report.read", object_type="report", object_id=report.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"pages": described.pages})
    db.commit()
    return described.to_dict()


@router.get("/reports/{report_id}/pages/{page_number}", response_class=Response)
def report_page(case_id: str, report_id: str, page_number: int, current_user: CurrentUser, db: DbSession) -> Response:
    """One page of the report, rendered the same way an evidence page is.

    Not audited per page: the read was recorded when the report was opened, and one entry per page
    turned would bury that record under scrolling.
    """
    _, path = _readable_report(case_id, report_id, current_user, db)
    return Response(content=report_view.page_png(path, page_number), media_type="image/png")


@router.get("/reports/{report_id}/search")
def report_search(case_id: str, report_id: str, current_user: CurrentUser, db: DbSession, q: str = Query(default="")) -> dict:
    """Where the text appears in the report, as rectangles rather than a count."""
    report, path = _readable_report(case_id, report_id, current_user, db)
    result = report_view.search(path, q)
    audit(db, action="report.search", object_type="report", object_id=report.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"query": result.query, "total": result.total})
    db.commit()
    return result.to_dict()


class ReportQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/reports/{report_id}/ask")
def ask_report(case_id: str, report_id: str, payload: ReportQuestion, current_user: CurrentUser, db: DbSession) -> dict:
    """Ask about this report, answered from this report and this case and nowhere else.

    There is no outbound call in this path to configure or forget to disable. Questions of fact go
    to the case assistant, which reads the case's own rows; questions about the document return the
    report's own words; anything else is declined in a sentence that says why.
    """
    report, path = _readable_report(case_id, report_id, current_user, db)
    result = report_questions.answer(db, report, path, payload.question)
    audit(db, action="report.question", object_type="report", object_id=report.id, case_id=case_id, outcome="success", actor_id=current_user.id, details={"kind": result.kind})
    db.commit()
    return result.to_dict()


@router.get("/reports/{report_id}/findings")
def report_findings(case_id: str, report_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """The numbered findings this report printed, each with the place it was read from.

    Returned from what was stored when the report was generated, not recomputed. A finding is cited
    by number in documents outside this system, so F-07 has to keep meaning the statement the
    printed report carries even after the case has moved on around it.

    A finding whose evidence has since left the case keeps its number and says so, rather than
    disappearing and silently renumbering everything after it.
    """
    report, _ = _readable_report(case_id, report_id, current_user, db)
    live = {item.id for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))}
    findings = []
    for item in report.findings or []:
        entry = dict(item)
        entry["openable"] = bool(entry.get("evidence_id")) and entry.get("evidence_id") in live
        if not entry["openable"]:
            entry["unopenable_reason"] = (
                "The evidence file this was read from is no longer held in this case, so it cannot be opened here. "
                "The finding is kept as printed."
            )
        findings.append(entry)
    return {
        "report_id": report.id,
        "version": report.version,
        "findings": findings,
        "note": (
            "These are the findings as this version printed them. They are not recomputed, so their numbers stay "
            "valid for anything that cites them."
        ),
    }


@router.get("/trustify/reports/{report_id}/evidence/{evidence_id}/proof")
def evidence_inclusion_proof(case_id: str, report_id: str, evidence_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Prove one evidence file was in the set this report covered, without revealing the rest.

    A court can be shown that this file was in the case at report time using a handful of sibling
    hashes. The other files' hashes stay out of it -- they are not the court's to see, and may
    belong to people who are not on trial.
    """
    require_case_access(db, case_id, current_user)
    result = inclusion_proof(db, case_id, report_id, evidence_id)
    audit(db, action="trustify.inclusion_proof", object_type="evidence", object_id=evidence_id, case_id=case_id, outcome="success" if result.get("available") else "unavailable", actor_id=current_user.id, details={"report_id": report_id})
    db.commit()
    return result


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


@router.get("/trustify/chain")
def verify_audit_chain(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    """Walk this case's audit chain and report whether it holds.

    Every hash is recomputed from the entry's stored fields and compared with the value sealed
    against it, and each entry is checked to follow the one before. Where it breaks, the exact
    entry is named: "something is wrong somewhere" is not evidence anybody can act on.

    Verifying is itself an action against the case, so it is recorded — which means the next
    verification has one more entry to check than this one did.
    """
    require_case_access(db, case_id, current_user)
    result = verify_chain(db, case_id)
    audit(
        db,
        action="integrity.verify_chain",
        object_type="case",
        object_id=case_id,
        case_id=case_id,
        outcome=result.status,
        actor_id=current_user.id,
        details={"entries": result.entries, "verified": result.verified},
    )
    db.commit()
    return result.to_dict()


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
