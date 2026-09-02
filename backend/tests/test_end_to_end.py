"""End-to-end proof that generated files traverse the public backend workflow."""

from pathlib import Path

from scripts.generate_synthetic_evidence import generate


def test_synthetic_evidence_flows_to_graph_alerts_review_and_pdf(client, case_factory):
    case, headers = case_factory()
    artifacts = generate()
    categories = {"whatsapp": "whatsapp_chat", "phishing": "phishing_email", "bank": "bank_statement", "call": "call_log", "upi": "upi_receipt", "complaint": "complaint_fir"}
    receipts = []
    for artifact in artifacts:
        category = next(value for key, value in categories.items() if key in artifact.name)
        with artifact.open("rb") as stream:
            response = client.post(f"/api/v1/cases/{case['id']}/evidence", headers=headers, data={"source_category": category}, files={"file": (artifact.name, stream, "application/octet-stream")})
        assert response.status_code == 201, response.text
        receipts.append(response.json())
    assert len(receipts) == 6
    assert all(receipt["integrity_receipt"]["algorithm"] == "SHA-256" for receipt in receipts)
    evidence = client.get(f"/api/v1/cases/{case['id']}/evidence", headers=headers).json()
    assert len(evidence) == 6 and all(item["status"] == "completed" for item in evidence)
    timeline = client.get(f"/api/v1/cases/{case['id']}/timeline", headers=headers).json()
    transactions = client.get(f"/api/v1/cases/{case['id']}/transactions", headers=headers).json()
    alerts = client.get(f"/api/v1/cases/{case['id']}/alerts", headers=headers).json()
    graph = client.get(f"/api/v1/cases/{case['id']}/graph", headers=headers).json()
    assert len(timeline) >= 10
    assert len(transactions) >= 3
    assert len(alerts) >= 3
    assert graph["metrics"]["node_count"] >= 12
    review = client.post(f"/api/v1/cases/{case['id']}/review/event/{timeline[0]['id']}", headers=headers, json={"decision": "confirmed", "note": "Integration review"})
    assert review.status_code == 200, review.text
    report = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    assert report.status_code == 202, report.text
    pdf = client.get(f"/api/v1/cases/{case['id']}/reports/{report.json()['id']}/download", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    summary = client.get(f"/api/v1/cases/{case['id']}/trustify/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["evidence_hashes_present"] == 6
    verification = client.get(f"/api/v1/cases/{case['id']}/trustify/reports/{report.json()['id']}/verify", headers=headers)
    assert verification.status_code == 200, verification.text
    assert verification.json()["status"] == "verified"
