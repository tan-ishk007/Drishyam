"""End-to-end proof that a case of mixed synthetic evidence produces a downloadable report.

This began as a one-off visual check and wrote its PDF to an absolute path on the machine it was
authored on, so it failed everywhere else. The pipeline assertions are worth keeping, so the
artifact now goes to the test's own temporary directory. Set DRISHYAM_REPORT_PREVIEW_DIR to keep a
copy somewhere you can open it.
"""

import os
from pathlib import Path

from scripts.generate_synthetic_evidence import generate


def test_write_upgraded_report_preview(client, case_factory, tmp_path):
    case, headers = case_factory()
    categories = {
        "whatsapp": "whatsapp_chat",
        "phishing": "phishing_email",
        "bank": "bank_statement",
        "call": "call_log",
        "upi": "upi_receipt",
        "complaint": "complaint_fir",
    }
    for artifact in generate():
        category = next(value for key, value in categories.items() if key in artifact.name)
        with artifact.open("rb") as stream:
            response = client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": category},
                files={"file": (artifact.name, stream, "application/octet-stream")},
            )
        assert response.status_code == 201, response.text
    timeline = client.get(f"/api/v1/cases/{case['id']}/timeline", headers=headers).json()
    assert timeline
    review = client.post(
        f"/api/v1/cases/{case['id']}/review/event/{timeline[0]['id']}",
        headers=headers,
        json={"decision": "confirmed", "note": "Preview report review"},
    )
    assert review.status_code == 200, review.text
    report = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    assert report.status_code == 202, report.text
    pdf = client.get(f"/api/v1/cases/{case['id']}/reports/{report.json()['id']}/download", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    preview = tmp_path / "validated_report_preview.pdf"
    preview.write_bytes(pdf.content)
    assert preview.stat().st_size > 0

    if keep := os.environ.get("DRISHYAM_REPORT_PREVIEW_DIR"):
        destination = Path(keep)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "validated_report_preview.pdf").write_bytes(pdf.content)
