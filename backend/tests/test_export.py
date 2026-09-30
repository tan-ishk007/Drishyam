"""Handing a case to another system, and what must travel with it.

An export is a disclosure: the rows leave this system's authorisation, its audit trail and its
redaction rules behind, and land somewhere none of those apply. So the tests here are about what
goes with them -- the source of every row, the protected identity still protected, and a line in
the record saying it happened.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from scripts import benchmark_case

PROTECTED = "Priya Sharma"


@pytest.fixture
def worked_case(client, account):
    """A case that declares a protected identity, with the benchmark evidence behind it."""
    _, headers = account()
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "title": "Synthetic export investigation",
            "crime_type": "job_offer_fraud",
            "description": "SYNTHETIC TEST DESCRIPTION ONLY.",
            "victim_alias": PROTECTED,
        },
    )
    assert created.status_code == 201, created.text
    case = created.json()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
    return case, headers


def _export(client, case, headers, subject: str, **params):
    return client.get(f"/api/v1/cases/{case['id']}/export/{subject}", headers=headers, params=params)


def _rows(response) -> list[dict]:
    return list(csv.DictReader(io.StringIO(response.text)))


@pytest.mark.parametrize("subject", ["entities", "relationships"])
def test_every_row_carries_the_source_it_was_read_from(client, worked_case, subject: str) -> None:
    """A spreadsheet of assertions with no provenance is something somebody will later have to
    justify with nothing to justify it from."""
    case, headers = worked_case
    response = _export(client, case, headers, subject)

    assert response.status_code == 200, response.text
    rows = _rows(response)
    assert rows, f"the benchmark case has {subject}"
    for row in rows:
        assert row["source_evidence"], "a row with no evidence file cannot be checked"
        assert "source_reference" in row


def test_json_carries_the_same_rows_and_says_what_they_are(client, worked_case) -> None:
    case, headers = worked_case
    body = json.loads(_export(client, case, headers, "relationships", format="json").text)

    assert body["rows"]
    assert "not findings of fact" in body["carried"]


def test_the_protected_identity_is_protected_in_the_export(client, worked_case) -> None:
    """The export is likelier than a screen to be forwarded to somebody the case team never chose."""
    case, headers = worked_case
    text = _export(client, case, headers, "entities").text

    assert PROTECTED not in text, "the declared protected identity reached an exported file"


def test_redaction_is_on_unless_it_is_turned_off_deliberately(client, worked_case) -> None:
    case, headers = worked_case
    default = _export(client, case, headers, "entities").text
    identified = _export(client, case, headers, "entities", redaction_profile="identified").text

    assert PROTECTED not in default
    assert PROTECTED in identified, "an explicit identified export should carry the name"


def test_turning_redaction_off_is_recorded_with_the_export(client, worked_case) -> None:
    case, headers = worked_case
    _export(client, case, headers, "entities", redaction_profile="identified")

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    exports = [item for item in entries if item["action"] == "case.export"]
    assert exports and exports[0]["details"]["redaction_profile"] == "identified"


def test_exporting_is_audited(client, worked_case) -> None:
    case, headers = worked_case
    _export(client, case, headers, "relationships")

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "case.export" in [item["action"] for item in entries]


def test_findings_are_exported_as_the_report_printed_them(client, worked_case) -> None:
    case, headers = worked_case
    created = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    assert created.status_code in {200, 201, 202}, created.text

    rows = _rows(_export(client, case, headers, "findings"))
    assert rows, "a generated report produces numbered findings"
    for row in rows:
        assert row["finding"].startswith("F-")
        assert row["source_evidence"]


def test_a_case_with_no_report_exports_no_findings_rather_than_guessing(client, case_factory) -> None:
    case, headers = case_factory()
    response = _export(client, case, headers, "findings")
    assert response.status_code == 200
    assert "No findings are recorded" in response.text


def test_an_unknown_subject_is_refused(client, worked_case) -> None:
    case, headers = worked_case
    assert _export(client, case, headers, "everything").status_code == 404


def test_an_outsider_cannot_export(client, worked_case, account) -> None:
    case, _ = worked_case
    _, outsider = account()
    assert _export(client, case, outsider, "entities").status_code in {403, 404}
