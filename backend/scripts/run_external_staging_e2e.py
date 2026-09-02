"""Exercise the live localhost API against approved Supabase, Upstash, and private Storage with fiction-only evidence."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_synthetic_evidence import generate


BASE_URL = "http://127.0.0.1:8000/api/v1"
TIMEOUT_SECONDS = 180


def _raise(response: httpx.Response, step: str) -> httpx.Response:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"{step} failed with HTTP {response.status_code}: {response.text[:600]}") from exc
    return response


def _wait_for_otp(email: str) -> str:
    mailbox = ROOT / "data" / "dev_mailbox"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        for path in sorted(mailbox.glob("verification-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("to") == email:
                return str(payload["verification_code"])
        time.sleep(0.5)
    raise TimeoutError("Synthetic account OTP did not reach the explicitly enabled local console mailbox")


def _wait_for_evidence(client: httpx.Client, case_id: str, headers: dict[str, str], expected: int) -> list[dict]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        evidence = _raise(client.get(f"/cases/{case_id}/evidence", headers=headers), "list evidence").json()
        states = {item["status"] for item in evidence}
        if len(evidence) == expected and states == {"completed"}:
            return evidence
        if "failed" in states:
            failures = [item.get("failure_reason", "unknown") for item in evidence if item["status"] == "failed"]
            raise RuntimeError(f"Evidence processing failed: {failures}")
        time.sleep(2)
    raise TimeoutError("Evidence processing did not reach completed state before the deadline")


def _wait_for_report(client: httpx.Client, case_id: str, report_id: str, headers: dict[str, str]) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        reports = _raise(client.get(f"/cases/{case_id}/reports", headers=headers), "list reports").json()
        report = next((item for item in reports if item["id"] == report_id), None)
        if report and report["status"] == "succeeded":
            return report
        if report and report["status"] == "failed":
            raise RuntimeError(f"Report generation failed: {report.get('failure_reason', 'unknown')}")
        time.sleep(2)
    raise TimeoutError("Report generation did not reach succeeded state before the deadline")


def run() -> dict:
    files = generate()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    email = f"synthetic.e2e.{stamp}@example.com"
    categories = {
        "whatsapp": "whatsapp_chat",
        "phishing": "phishing_email",
        "bank": "bank_statement",
        "call": "call_log",
        "upi": "upi_receipt",
        "complaint": "complaint_fir",
    }

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        signup = _raise(
            client.post("/auth/signup", json={"name": "Synthetic E2E Investigator", "email": email, "password": "SyntheticE2EPassword!2026", "role": "investigator"}),
            "synthetic signup",
        )
        otp = _wait_for_otp(email)
        verified = _raise(client.post("/auth/verify", json={"email": email, "otp": otp}), "synthetic verification").json()
        headers = {"Authorization": f"Bearer {verified['access_token']}"}
        case = _raise(
            client.post(
                "/cases",
                headers=headers,
                json={
                    "title": f"SYNTHETIC E2E · Fictional job-offer fraud trail · {stamp}",
                    "crime_type": "job_offer_fraud",
                    "fir_number": f"SYN-E2E-{stamp}",
                    "victim_alias": "Fictional Investigator",
                    "priority": "high",
                    "notes": "Fiction-only staging validation. No real person, account, transaction, or allegation.",
                },
            ),
            "create synthetic case",
        ).json()
        case_id = case["id"]

        uploaded: list[dict] = []
        first_file_bytes: bytes | None = None
        for artifact in files:
            category = next(value for key, value in categories.items() if key in artifact.name)
            payload = artifact.read_bytes()
            if first_file_bytes is None:
                first_file_bytes = payload
            response = _raise(
                client.post(
                    f"/cases/{case_id}/evidence",
                    headers=headers,
                    data={"source_category": category},
                    files={"file": (artifact.name, payload, "application/octet-stream")},
                ),
                f"upload {artifact.name}",
            )
            uploaded.append(response.json()["evidence"])

        completed = _wait_for_evidence(client, case_id, headers, expected=len(uploaded))
        original = _raise(client.get(f"/cases/{case_id}/evidence/{uploaded[0]['id']}/original", headers=headers), "download private original")
        if first_file_bytes is None or hashlib.sha256(original.content).hexdigest() != hashlib.sha256(first_file_bytes).hexdigest():
            raise RuntimeError("Private original download checksum did not match the uploaded synthetic evidence")

        timeline = _raise(client.get(f"/cases/{case_id}/timeline", headers=headers), "timeline").json()
        transactions = _raise(client.get(f"/cases/{case_id}/transactions", headers=headers), "transactions").json()
        alerts = _raise(client.get(f"/cases/{case_id}/alerts", headers=headers), "alerts").json()
        graph = _raise(client.get(f"/cases/{case_id}/graph", headers=headers), "graph").json()
        if not timeline or not transactions or not alerts or graph["metrics"]["node_count"] < 1:
            raise RuntimeError("Derived evidence outputs did not meet the synthetic validation minimums")

        _raise(client.post(f"/cases/{case_id}/review/event/{timeline[0]['id']}", headers=headers, json={"decision": "confirmed", "note": "Synthetic E2E validation review."}), "review event")
        _raise(client.post(f"/cases/{case_id}/review/alert/{alerts[0]['id']}", headers=headers, json={"decision": "confirmed", "note": "Synthetic E2E validation review."}), "review alert")

        queued_report = _raise(client.post(f"/cases/{case_id}/reports", headers=headers), "queue report").json()
        report = _wait_for_report(client, case_id, queued_report["id"], headers)
        pdf = _raise(client.get(f"/cases/{case_id}/reports/{report['id']}/download", headers=headers), "download report")
        if not pdf.content.startswith(b"%PDF-"):
            raise RuntimeError("Downloaded synthetic report was not a PDF")
        trustify = _raise(client.get(f"/cases/{case_id}/trustify/reports/{report['id']}/verify", headers=headers), "verify Trustify receipt").json()
        if trustify.get("status") != "verified":
            raise RuntimeError(f"Trustify verification returned {trustify.get('status')}")
        summary = _raise(client.get(f"/cases/{case_id}/trustify/summary", headers=headers), "Trustify summary").json()

    result = {
        "case_id": case_id,
        "synthetic_account": email,
        "evidence_files": len(completed),
        "timeline_events": len(timeline),
        "transactions": len(transactions),
        "alerts": len(alerts),
        "graph_nodes": graph["metrics"]["node_count"],
        "graph_edges": graph["metrics"]["edge_count"],
        "private_original_checksum_verified": True,
        "report_id": report["id"],
        "report_bytes": len(pdf.content),
        "trustify_status": trustify["status"],
        "trustify_receipts": summary["report_receipt_count"],
        "audit_events": summary["audit_event_count"],
    }
    (ROOT / "data" / "external_staging_e2e_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    run()
