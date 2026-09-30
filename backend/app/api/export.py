"""Handing a case to another system without anybody retyping it.

An export is a disclosure. The rows leave this system's authorisation, its audit trail and its
redaction rules behind, and land somewhere none of those apply. So three things hold here that do
not hold for an on-screen table: the same protected-identity rule the reports use is applied, every
row carries the source it was read from, and the act is recorded.

The source columns are not decoration. A spreadsheet of relationships with no provenance is a set
of assertions somebody will later have to justify with nothing to justify them from -- and the
whole point of this system is that every line can be traced back to the page it came from.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Entity, EntityRelation, EvidenceFile, Report
from app.services.audit import audit
from app.services.cases import require_case_access
from app.services.reporting import redaction_context

router = APIRouter(prefix="/cases/{case_id}/export", tags=["export"])

SUBJECTS = {"entities", "relationships", "findings"}
FORMATS = {"csv", "json"}

CARRIED = (
    "Exported from DRISHYAM. Every row carries the evidence file and place it was read from. Rows state what a "
    "source records; they are not findings of fact, and nothing here establishes identity, intent or culpability."
)


def _entities(db, case_id: str, hide) -> list[dict[str, Any]]:
    files = {item.id: item.original_name for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))}
    return [
        {
            "entity_id": item.id,
            "type": item.entity_type,
            "value": hide(item.value),
            "canonical_value": hide(item.normalized_value),
            "confidence": float(item.confidence or 0),
            "review_status": item.review_status.value,
            "source_evidence": files.get(item.source_evidence_id, "not in this case"),
            "source_reference": item.source_reference,
        }
        for item in db.scalars(select(Entity).where(Entity.case_id == case_id).order_by(Entity.value))
    ]


def _relationships(db, case_id: str, hide) -> list[dict[str, Any]]:
    labels = {item.id: item.value for item in db.scalars(select(Entity).where(Entity.case_id == case_id))}
    files = {item.id: item.original_name for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))}
    return [
        {
            "relation_id": item.id,
            "subject": hide(labels.get(item.subject_entity_id, "unresolved")),
            "relation": item.relation_type,
            "object": hide(labels.get(item.object_entity_id, "unresolved")),
            "directed": bool(item.directed),
            "observed_at": item.observed_at.isoformat() if item.observed_at else None,
            "confidence": float(item.confidence or 0),
            "verification_status": item.verification_status,
            "source_evidence": files.get(item.source_evidence_id, "not in this case"),
            "source_reference": item.source_reference,
        }
        for item in db.scalars(select(EntityRelation).where(EntityRelation.case_id == case_id))
    ]


def _findings(db, case_id: str) -> list[dict[str, Any]]:
    """The numbered findings as the latest generated report printed them.

    Read back from the report rather than recomputed, for the same reason the report viewer does:
    a number cited outside this system has to keep meaning the statement that was filed.
    """
    report = db.scalar(
        select(Report)
        .where(Report.case_id == case_id, Report.findings.isnot(None))
        .order_by(Report.version.desc())
    )
    if report is None:
        return []
    return [
        {
            "finding": item.get("id"),
            "statement": item.get("statement"),
            "source_evidence": item.get("file"),
            "source_reference": item.get("place"),
            "confidence": item.get("confidence"),
            "verification": item.get("verification"),
            "load_bearing": item.get("load_bearing"),
            "report_version": report.version,
        }
        for item in report.findings or []
    ]


def _csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return buffer.getvalue()


@router.get("/{subject}")
def export_case(
    case_id: str,
    subject: str,
    current_user: CurrentUser,
    db: DbSession,
    format: str = Query(default="csv"),
    redaction_profile: str = Query(default="protected"),
) -> Response:
    """Export one kind of case record, with its sources, under the report redaction rules.

    Redaction defaults to the protected profile rather than to none. An export is more likely than
    a screen to be forwarded to somebody the case team never chose, so the safer default is the one
    that has to be turned off deliberately -- and turning it off is recorded alongside the export.
    """
    require_case_access(db, case_id, current_user)
    if subject not in SUBJECTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Nothing exportable is called {subject!r}.")
    if format not in FORMATS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Format must be csv or json.")

    with redaction_context(db, case_id, redaction_profile) as hide:
        if subject == "entities":
            rows = _entities(db, case_id, hide)
        elif subject == "relationships":
            rows = _relationships(db, case_id, hide)
        else:
            rows = _findings(db, case_id)

    audit(
        db,
        action="case.export",
        object_type="case",
        object_id=case_id,
        case_id=case_id,
        outcome="success",
        actor_id=current_user.id,
        details={"subject": subject, "format": format, "rows": len(rows), "redaction_profile": redaction_profile},
    )
    db.commit()

    filename = f"drishyam-{subject}.{format}"
    if format == "json":
        body = json.dumps({"case_id": case_id, "subject": subject, "carried": CARRIED, "rows": rows}, default=str, indent=2)
        media = "application/json"
    else:
        body = _csv(rows) or f"# {CARRIED}\n# No {subject} are recorded in this case.\n"
        media = "text/csv"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Drishyam-Note": CARRIED[:180]},
    )
