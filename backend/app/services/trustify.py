from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AuditLog, EvidenceFile, Report, TrustifyReceipt
from app.services.storage import get_report_artifact_path, report_storage_key

settings = get_settings()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_chain_hash(db: Session, case_id: str) -> str | None:
    row = db.scalar(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at.desc()))
    return row.event_hash if row else None


def create_receipt(db: Session, report: Report, output: Path) -> TrustifyReceipt:
    evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == report.case_id).order_by(EvidenceFile.id)).all()
    report_hash = _sha256(output)
    audit_chain_hash = _audit_chain_hash(db, report.case_id)
    verification_id = f"TRU-{report.case_id[:8].upper()}-R{report.version}"
    manifest = {
        "schema": "drishyam-trustify-v1",
        "verification_id": verification_id,
        "case_id": report.case_id,
        "report_id": report.id,
        "report_version": report.version,
        "report_hash": report_hash,
        "review_snapshot_hash": report.review_snapshot_hash,
        "audit_chain_hash": audit_chain_hash,
        "evidence": [{"evidence_id": item.id, "sha256": item.sha256, "version": item.version} for item in evidence],
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_hash = hashlib.sha256(encoded).hexdigest()
    directory = output.parent / "trustify"
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / f"report-v{report.version}-manifest.json"
    manifest_path.write_bytes(encoded)
    receipt = db.scalar(select(TrustifyReceipt).where(TrustifyReceipt.report_id == report.id))
    if receipt is None:
        receipt = TrustifyReceipt(
            case_id=report.case_id,
            report_id=report.id,
            verification_id=verification_id,
            report_hash=report_hash,
            manifest_hash=manifest_hash,
            audit_chain_hash=audit_chain_hash,
            review_snapshot_hash=report.review_snapshot_hash,
            manifest_storage_key=report_storage_key(str(manifest_path.relative_to(settings.generated_reports_root))),
        )
        db.add(receipt)
    else:
        receipt.report_hash, receipt.manifest_hash, receipt.audit_chain_hash = report_hash, manifest_hash, audit_chain_hash
    return receipt


def verify_receipt(db: Session, case_id: str, report_id: str) -> dict:
    receipt = db.scalar(select(TrustifyReceipt).where(TrustifyReceipt.case_id == case_id, TrustifyReceipt.report_id == report_id))
    if receipt is None:
        raise ValueError("Trustify receipt not available")
    report = db.get(Report, report_id)
    if not report or not report.storage_key:
        raise ValueError("Report object is not available")
    report_path = get_report_artifact_path(report.storage_key)
    report_valid = _sha256(report_path) == receipt.report_hash
    manifest_path = get_report_artifact_path(receipt.manifest_storage_key)
    manifest_valid = hashlib.sha256(manifest_path.read_bytes()).hexdigest() == receipt.manifest_hash
    return {"verification_id": receipt.verification_id, "report_id": report_id, "report_hash_valid": report_valid, "manifest_hash_valid": manifest_valid, "audit_chain_hash": receipt.audit_chain_hash, "status": "verified" if report_valid and manifest_valid else "attention_required"}
