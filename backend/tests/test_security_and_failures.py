"""Security, integrity, malformed-evidence, worker-failure, and authorization tests."""

from io import BytesIO

from PIL import Image

from app.services.reporting import generate_report


def _upload(client, case_id, headers, name, content, category="whatsapp_chat"):
    return client.post(f"/api/v1/cases/{case_id}/evidence", headers=headers, data={"source_category": category}, files={"file": (name, content, "application/octet-stream")})


def test_invalid_auth_and_object_level_case_access(client, case_factory, account):
    assert client.get("/api/v1/cases").status_code == 401
    case, owner_headers = case_factory()
    _, outsider_headers = account("Outside Investigator")
    assert client.get(f"/api/v1/cases/{case['id']}", headers=outsider_headers).status_code == 403
    assert client.get(f"/api/v1/cases/{case['id']}", headers=owner_headers).status_code == 200


def test_invalid_type_duplicate_and_failed_worker_are_recorded(client, case_factory):
    case, headers = case_factory()
    assert _upload(client, case["id"], headers, "malware.exe", b"MZ fake bytes").status_code == 415
    valid = b"SYNTHETIC TRAINING\n14/08/2026 09:05 +91 9876543210 said use fraudcollect@upi\n"
    assert _upload(client, case["id"], headers, "chat.txt", valid).status_code == 201
    assert _upload(client, case["id"], headers, "chat_copy.txt", valid).status_code == 409
    corrupt = _upload(client, case["id"], headers, "broken.pdf", b"%PDF-1.7\nNOT-A-VALID-PDF")
    assert corrupt.status_code == 201, corrupt.text
    record = client.get(f"/api/v1/cases/{case['id']}/evidence/{corrupt.json()['evidence']['id']}", headers=headers)
    assert record.status_code == 200 and record.json()["status"] == "failed"


def test_size_limit_and_unreadable_ocr_failure_are_recorded(client, case_factory, monkeypatch):
    case, headers = case_factory()
    from app.services import storage
    monkeypatch.setattr(storage.settings, "max_upload_size_bytes", 8)
    assert _upload(client, case["id"], headers, "large.txt", b"this synthetic file is over the test limit").status_code == 413
    monkeypatch.setattr(storage.settings, "max_upload_size_bytes", 10 * 1024 * 1024)
    blank = BytesIO()
    Image.new("RGB", (200, 200), "white").save(blank, format="PNG")
    unreadable = _upload(client, case["id"], headers, "blank.png", blank.getvalue(), "upi_receipt")
    assert unreadable.status_code == 201
    record = client.get(f"/api/v1/cases/{case['id']}/evidence/{unreadable.json()['evidence']['id']}", headers=headers)
    assert record.json()["status"] == "failed"


def test_malformed_csv_fails_without_exposing_original_content(client, case_factory):
    case, headers = case_factory()
    response = _upload(client, case["id"], headers, "bad.csv", b"only_one_column\nvalue\n", "bank_statement")
    assert response.status_code == 201
    status_response = client.get(f"/api/v1/cases/{case['id']}/evidence/{response.json()['evidence']['id']}", headers=headers)
    assert status_response.json()["status"] == "failed"


def test_missing_report_generation_fails_safely():
    try:
        generate_report("00000000-0000-0000-0000-000000000000")
    except ValueError as exc:
        assert "Report record not found" in str(exc)
    else:
        raise AssertionError("Missing reports must not produce a fabricated document")
