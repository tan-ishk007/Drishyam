"""Backend-only developer preview and debug surfaces with no dependency on the existing frontend."""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Alert, Entity, Event, EvidenceFile, Report, Transaction
from app.services.cases import require_case_access

router = APIRouter(prefix="/preview", tags=["backend-preview"])


@router.get("/cases/{case_id}/summary")
def summary(case_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    case = require_case_access(db, case_id, current_user)
    count = lambda model: db.scalar(select(func.count()).select_from(model).where(model.case_id == case_id))
    evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id).order_by(EvidenceFile.uploaded_at)).all()
    return {"case": {"id": case.id, "number": case.case_number, "title": case.title, "status": case.status.value}, "counts": {"evidence": count(EvidenceFile), "entities": count(Entity), "events": count(Event), "transactions": count(Transaction), "alerts": count(Alert), "reports": count(Report)}, "evidence": [{"id": item.id, "name": item.original_name, "sha256": item.sha256, "status": item.status.value} for item in evidence]}


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def preview_case(case_id: str, current_user: CurrentUser, db: DbSession) -> HTMLResponse:
    payload = summary(case_id, current_user, db)
    evidence_rows = "".join(f"<tr><td>{escape(item['name'])}</td><td><code>{escape(item['sha256'])}</code></td><td>{escape(item['status'])}</td></tr>" for item in payload["evidence"])
    metrics = "".join(f"<li><strong>{escape(key)}</strong>: {value}</li>" for key, value in payload["counts"].items())
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>DRISHYAM backend preview</title><style>body{{font-family:system-ui;margin:3rem;background:#f7f3ee;color:#1f2022}} main{{max-width:1000px;margin:auto}} h1{{color:#7b1e2b}} table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:.7rem;border:1px solid #ddd;text-align:left}}code{{font-size:.75rem;word-break:break-all}}</style></head><body><main><p>Standalone backend developer preview</p><h1>{escape(payload['case']['number'])} — {escape(payload['case']['title'])}</h1><p>Case state: <strong>{escape(payload['case']['status'])}</strong>. This view is generated from the backend database and requires authenticated case access.</p><h2>Derived record counts</h2><ul>{metrics}</ul><h2>Evidence integrity register</h2><table><thead><tr><th>Original file</th><th>SHA-256 receipt</th><th>Pipeline state</th></tr></thead><tbody>{evidence_rows}</tbody></table><p>All derived outputs are reviewable leads, not findings of guilt.</p></main></body></html>")

