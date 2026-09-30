"""Declaring when the incident happened, and what that switches on.

The case record has always had `date_range_start` / `date_range_end`, and a whole temporal reading
was built on them: contact placed before, during and after the incident, and pairs repeatedly in
touch in the hours leading up to it. None of it could ever run, because nothing returned the window
and nothing could set it after the case was opened. A feature that cannot be switched on is not a
feature.

The other half of this file is the case that stays silent. A case with no declared window must keep
saying so. An investigator who does not yet know when something happened must not be made to guess,
and a window invented on their behalf would manufacture the very sequence the temporal reading is
supposed to find.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import AuditLog
from scripts import benchmark_case

INCIDENT = datetime(2026, 5, 12, 21, 0, tzinfo=timezone.utc)


def _window(client, case_id: str, headers: dict, start, end) -> dict:
    return client.patch(
        f"/api/v1/cases/{case_id}/incident-window",
        headers=headers,
        json={
            "date_range_start": start.isoformat() if start else None,
            "date_range_end": end.isoformat() if end else None,
        },
    )


def _chronology(client, case_id: str, headers: dict) -> dict:
    response = client.get(f"/api/v1/cases/{case_id}/grounded/temporal/chronology", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- declaring it


def test_a_case_is_created_with_the_window_it_declared(client, account) -> None:
    _, headers = account()
    response = client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "title": "Synthetic test investigation",
            "crime_type": "job_offer_fraud",
            "description": "SYNTHETIC TEST DESCRIPTION ONLY.",
            "date_range_start": INCIDENT.isoformat(),
            "date_range_end": (INCIDENT + timedelta(hours=3)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["date_range_start"] is not None, "a window the server keeps but never returns cannot be corrected"
    assert body["date_range_end"] is not None


def test_a_case_created_without_one_says_so(case_factory, client) -> None:
    case, headers = case_factory()
    assert case["date_range_start"] is None
    assert _chronology(client, case["id"], headers)["incident_window_declared"] is False


def test_the_window_can_be_declared_after_the_case_is_open(client, case_factory) -> None:
    """A case is usually opened before anybody knows when the incident happened."""
    case, headers = case_factory()
    response = _window(client, case["id"], headers, INCIDENT, INCIDENT + timedelta(hours=3))

    assert response.status_code == 200, response.text
    assert _chronology(client, case["id"], headers)["incident_window_declared"] is True


def test_a_declared_window_can_be_cleared(client, case_factory) -> None:
    """A window nobody stands behind must be removable, not merely replaceable."""
    case, headers = case_factory()
    _window(client, case["id"], headers, INCIDENT, None)
    assert _chronology(client, case["id"], headers)["incident_window_declared"] is True

    assert _window(client, case["id"], headers, None, None).status_code == 200
    assert _chronology(client, case["id"], headers)["incident_window_declared"] is False


# --------------------------------------------------------------------------- what it refuses


def test_a_window_that_ends_before_it_starts_is_refused(client, case_factory) -> None:
    """Far likelier a typo than an intention. Silently swapping the ends would put records on the
    wrong side of the incident with nothing on screen to show it happened."""
    case, headers = case_factory()
    response = _window(client, case["id"], headers, INCIDENT, INCIDENT - timedelta(hours=2))
    assert response.status_code == 422, response.text
    assert _chronology(client, case["id"], headers)["incident_window_declared"] is False


def test_the_same_refusal_applies_at_creation(client, account) -> None:
    _, headers = account()
    response = client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "title": "Synthetic test investigation",
            "crime_type": "job_offer_fraud",
            "description": "SYNTHETIC TEST DESCRIPTION ONLY.",
            "date_range_start": INCIDENT.isoformat(),
            "date_range_end": (INCIDENT - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 422, response.text


def test_an_outsider_cannot_declare_a_window(client, case_factory, account) -> None:
    case, _ = case_factory()
    _, outsider = account()
    assert _window(client, case["id"], outsider, INCIDENT, None).status_code in {403, 404}


# --------------------------------------------------------------------------- accountability


def test_changing_the_window_records_what_it_was(client, case_factory) -> None:
    """The window decides which side of the incident every record falls on. A reader who finds a
    finding surprising needs to be able to see whether the window moved under it."""
    case, headers = case_factory()
    _window(client, case["id"], headers, INCIDENT, None)
    _window(client, case["id"], headers, INCIDENT + timedelta(days=1), None)

    db = SessionLocal()
    try:
        entries = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.case_id == case["id"], AuditLog.action == "case.incident_window_set")
                .order_by(AuditLog.created_at)
            )
        )
        assert len(entries) == 2
        assert entries[0].details["previous"]["date_range_start"] is None
        assert entries[1].details["previous"]["date_range_start"] is not None, "the span it replaced must be recorded"
        assert entries[1].details["declared"]["date_range_start"] is not None
    finally:
        db.close()


# --------------------------------------------------------------------------- what it switches on


@pytest.fixture
def benchmark(client, case_factory):
    case, headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
    return case, headers


# The benchmark FIR puts the incident on the evening of 12 July 2026, with the complainant asked to
# travel that night. Twenty-one hundred is the moment the case treats as the incident opening.
BENCHMARK_INCIDENT = datetime(2026, 7, 12, 21, 0, tzinfo=timezone.utc)


def test_the_benchmark_case_places_its_contact_once_a_window_is_declared(client, benchmark) -> None:
    """The done-when for this step: the same case that reported nothing now reports a chronology,
    and the only thing that changed is one declared field."""
    case, headers = benchmark

    silent = _chronology(client, case["id"], headers)
    assert silent["incident_window_declared"] is False
    assert silent["contacts_placed"].get("before", 0) == 0, "nothing can be before an incident nobody declared"

    assert _window(client, case["id"], headers, BENCHMARK_INCIDENT, BENCHMARK_INCIDENT.replace(hour=23, minute=59)).status_code == 200

    placed = _chronology(client, case["id"], headers)
    assert placed["incident_window_declared"] is True
    assert placed["contacts_placed"]["before"] > 0, "the calls in the hours beforehand must land somewhere"
    assert sum(placed["contacts_placed"].values()) == sum(silent["contacts_placed"].values()), (
        "declaring a window places the same contacts differently; it must not create or lose any"
    )


def test_pre_incident_contact_becomes_answerable(client, benchmark) -> None:
    """A whole analysis was written and could never run: it returns nothing without a window."""
    case, headers = benchmark
    route = f"/api/v1/cases/{case['id']}/grounded/temporal/pre-incident"

    assert client.get(route, headers=headers).json() == [], "without a declared incident there is no 'before'"

    _window(client, case["id"], headers, BENCHMARK_INCIDENT, None)
    findings = client.get(route, headers=headers).json()

    assert findings, "the benchmark has repeated contact in the hours before the incident"
    for finding in findings:
        assert finding["evidence_ids"], "a temporal finding that names no source cannot be checked"
        assert finding["contacts"] >= 2
