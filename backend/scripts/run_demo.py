"""Exercise the public backend API with generated fictional files; no database fixture shortcuts are used."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["ENVIRONMENT"] = "development"
os.environ["STORAGE_ROOT"] = str(ROOT / "data" / "private_storage")
os.environ["GENERATED_REPORTS_ROOT"] = str(ROOT / "generated_reports")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from scripts.generate_synthetic_evidence import generate  # noqa: E402


def _latest_otp() -> str:
    mailbox = ROOT / "data" / "dev_mailbox"
    message = max(mailbox.glob("verification-*.json"), key=lambda path: path.stat().st_mtime)
    return json.loads(message.read_text(encoding="utf-8"))["verification_code"]


def run() -> dict:
    files = generate()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    email = f"synthetic.investigator.{stamp}@example.com"
    with TestClient(app) as client:
        signup = client.post("/api/v1/auth/signup", json={"name": "Synthetic Investigator", "email": email, "password": "SyntheticDemoPassword!2026", "role": "investigator"})
        signup.raise_for_status()
        verify = client.post("/api/v1/auth/verify", json={"email": email, "otp": _latest_otp()})
        verify.raise_for_status()
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
        case = client.post("/api/v1/cases", headers=headers, json={"title": "Synthetic job-offer fraud trail", "crime_type": "job_offer_fraud", "fir_number": "SYN-FIR-2026-001", "victim_alias": "Aarav Sharma", "priority": "high", "notes": "All input artifacts are fictional training evidence."})
        case.raise_for_status()
        case_id = case.json()["id"]
        uploads = []
        category = {"whatsapp": "whatsapp_chat", "phishing": "phishing_email", "bank": "bank_statement", "call": "call_log", "upi": "upi_receipt", "complaint": "complaint_fir"}
        for artifact in files:
            selected = next(value for key, value in category.items() if key in artifact.name)
            with artifact.open("rb") as stream:
                response = client.post(f"/api/v1/cases/{case_id}/evidence", headers=headers, data={"source_category": selected}, files={"file": (artifact.name, stream, "application/octet-stream")})
            response.raise_for_status()
            uploads.append(response.json())
        timeline = client.get(f"/api/v1/cases/{case_id}/timeline", headers=headers)
        transactions = client.get(f"/api/v1/cases/{case_id}/transactions", headers=headers)
        alerts = client.get(f"/api/v1/cases/{case_id}/alerts", headers=headers)
        graph = client.get(f"/api/v1/cases/{case_id}/graph", headers=headers)
        for response in [timeline, transactions, alerts, graph]:
            response.raise_for_status()
        if timeline.json():
            client.post(f"/api/v1/cases/{case_id}/review/event/{timeline.json()[0]['id']}", headers=headers, json={"decision": "confirmed", "note": "Synthetic validation review."}).raise_for_status()
        if alerts.json():
            client.post(f"/api/v1/cases/{case_id}/review/alert/{alerts.json()[0]['id']}", headers=headers, json={"decision": "confirmed", "note": "Synthetic validation review."}).raise_for_status()
        report = client.post(f"/api/v1/cases/{case_id}/reports", headers=headers)
        report.raise_for_status()
        report_id = report.json()["id"]
        reports = client.get(f"/api/v1/cases/{case_id}/reports", headers=headers)
        reports.raise_for_status()
        generated = next(item for item in reports.json() if item["id"] == report_id)
        pdf = client.get(f"/api/v1/cases/{case_id}/reports/{report_id}/download", headers=headers)
        pdf.raise_for_status()
        pdf_path = ROOT / "generated_reports" / "demo_report_latest.pdf"
        pdf_path.write_bytes(pdf.content)
        summary = client.get(f"/api/v1/preview/cases/{case_id}/summary", headers=headers)
        summary.raise_for_status()
    result = {"case_id": case_id, "email": email, "evidence_files": len(uploads), "timeline_events": len(timeline.json()), "transactions": len(transactions.json()), "alerts": len(alerts.json()), "graph_nodes": graph.json()["metrics"]["node_count"], "graph_edges": graph.json()["metrics"]["edge_count"], "report": generated, "report_copy": str(pdf_path), "preview_summary": summary.json()}
    (ROOT / "demo_run.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
