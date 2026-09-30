from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AuditLog, EvidenceFile, Report, TrustifyReceipt
from app.services import merkle
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
    # One value over the whole set. The manifest already lists every hash, which lets a reader check
    # any file they hold; it does not fix which files were in the case, because a file quietly
    # dropped leaves the remaining hashes all still correct. Leaves are ordered by evidence id, the
    # same order the manifest lists them in, so the root can be rebuilt from the manifest alone.
    leaves = [item.sha256 for item in evidence if item.sha256]
    merkle_root = merkle.root(leaves)
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
        "merkle_root": merkle_root,
        "merkle_version": merkle.MERKLE_VERSION,
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
            merkle_root=merkle_root,
            merkle_leaves=leaves,
            manifest_storage_key=report_storage_key(str(manifest_path.relative_to(settings.generated_reports_root))),
        )
        db.add(receipt)
    else:
        receipt.report_hash, receipt.manifest_hash, receipt.audit_chain_hash = report_hash, manifest_hash, audit_chain_hash
        receipt.merkle_root, receipt.merkle_leaves = merkle_root, leaves
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


def inclusion_proof(db: Session, case_id: str, report_id: str, evidence_id: str) -> dict:
    """Show that one file was in this case when the report was generated.

    Built from the leaves stored with the receipt, not from the case as it stands now. The point of
    the proof is what was true at that moment; rebuilding it from a case that has since gained or
    lost a file would answer a different question and look like the same one.

    The path is the sibling hashes on the way to the root -- a handful of values, not the whole
    manifest. That is what lets a court be shown one file's membership without being handed the
    hashes of everyone else's material in the case.
    """
    receipt = db.scalar(
        select(TrustifyReceipt).where(TrustifyReceipt.report_id == report_id, TrustifyReceipt.case_id == case_id)
    )
    if receipt is None or not receipt.merkle_root:
        return {"available": False, "reason": "This report has no root recorded against it."}

    evidence = db.scalar(
        select(EvidenceFile).where(EvidenceFile.id == evidence_id, EvidenceFile.case_id == case_id)
    )
    if evidence is None or not evidence.sha256:
        return {"available": False, "reason": "That evidence file is not in this case, or carries no hash."}

    leaves = list(receipt.merkle_leaves or [])
    if evidence.sha256 not in leaves:
        return {
            "available": False,
            "reason": (
                "This file is in the case now but was not in the set this report covered. That is a true answer, not "
                "a failure: the root fixes what was there at the time."
            ),
        }

    found = merkle.proof(leaves, leaves.index(evidence.sha256))
    if found is None:
        return {"available": False, "reason": "The stored set could not produce a proof."}

    body = found.to_dict()
    body["available"] = True
    body["evidence_id"] = evidence.id
    body["evidence_name"] = evidence.original_name
    body["verification_id"] = receipt.verification_id
    body["set_size"] = len(leaves)
    body["verified"] = merkle.verify(found.leaf, found.path, receipt.merkle_root)
    return body
