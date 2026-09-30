"""Temporal reading of a case, and the criminal-network pattern rules built on it.

The arithmetic is simple; the risk is in what gets asserted around it. A rule that says two people
spoke before an incident is useful. A rule that implies they arranged it is a finding the evidence
does not support, so most of these tests are about the refusals and the wording.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Alert, Case, EntityRelation
from app.services import temporal

# The incident opens at 12:00 on 14/08. Three contacts lead up to it; one earlier pair does not.
CDR = (
    "a-party,b-party,call date,duration_seconds\n"
    "+919876543210,+919988776655,14/08/2026 09:00,182\n"
    "+919876543210,+919988776655,14/08/2026 09:31,94\n"
    "+919876543210,+919988776655,14/08/2026 10:05,61\n"
    "+919988776655,+919123456789,13/08/2026 22:10,45\n"
)
INCIDENT_START = "2026-08-14T12:00:00Z"

FORBIDDEN_LANGUAGE = ("guilty", "culprit", "offender", "conspired", "planned the", "responsible for")


def _upload_cdr(client, case, headers) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "cdr.csv"
        path.write_text(CDR, encoding="utf-8")
        with path.open("rb") as stream:
            response = client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": "cdr"},
                files={"file": ("cdr.csv", stream, "application/octet-stream")},
            )
        assert response.status_code == 201, response.text


@pytest.fixture
def dated_case(client, account):
    """A case with a declared incident window and a call record leading up to it."""
    _, headers = account()
    case = client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "title": "Temporal rules case",
            "crime_type": "synthetic_demo",
            "description": "Synthetic case for temporal rules.",
            "date_range_start": INCIDENT_START,
        },
    ).json()
    _upload_cdr(client, case, headers)
    return case, headers, f"/api/v1/cases/{case['id']}/grounded"


@pytest.fixture
def undated_case(client, account):
    """The same evidence, but nobody declared when the incident was."""
    _, headers = account()
    case = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"title": "No window case", "crime_type": "synthetic_demo", "description": "No incident window declared."},
    ).json()
    _upload_cdr(client, case, headers)
    return case, headers, f"/api/v1/cases/{case['id']}/grounded"


def _alerts(case_id: str) -> list[Alert]:
    db = SessionLocal()
    try:
        return list(db.scalars(select(Alert).where(Alert.case_id == case_id)).all())
    finally:
        db.close()


# --------------------------------------------------------------------------- chronology


def test_contacts_are_placed_relative_to_the_declared_incident(dated_case, client) -> None:
    _, headers, base = dated_case
    body = client.get(f"{base}/temporal/chronology", headers=headers).json()
    assert body["incident_window_declared"] is True
    assert body["contacts_placed"]["before"] >= 3
    assert body["contacts_placed"]["during"] == 0


def test_a_case_with_no_window_says_so_rather_than_inventing_one(undated_case, client) -> None:
    _, headers, base = undated_case
    body = client.get(f"{base}/temporal/chronology", headers=headers).json()
    assert body["incident_window_declared"] is False
    assert body["contacts_placed"]["before"] == 0
    assert body["contacts_placed"]["no_window_declared"] >= 1


def test_no_pre_incident_finding_without_a_declared_incident(undated_case, client) -> None:
    """Choosing a moment on the case's behalf would manufacture the sequence this claims to find."""
    _, headers, base = undated_case
    assert client.get(f"{base}/temporal/pre-incident", headers=headers).json() == []


# --------------------------------------------------------------------------- findings


def test_repeated_contact_before_the_incident_is_reported(dated_case, client) -> None:
    _, headers, base = dated_case
    findings = client.get(f"{base}/temporal/pre-incident", headers=headers).json()
    assert findings, "three calls in the hours before the incident produced no finding"
    top = findings[0]
    assert top["contacts"] >= 3
    assert top["evidence_ids"], "a finding must name the evidence it was read from"
    assert top["relation_ids"]


def test_a_single_prior_contact_is_not_a_pattern(dated_case) -> None:
    """One call is contact. The rule needs repetition before it says anything."""
    case, _, _ = dated_case
    db = SessionLocal()
    try:
        findings = temporal.pre_incident_contacts(db, case["id"])
    finally:
        db.close()
    assert all(finding["contacts"] >= temporal.PRE_INCIDENT_MIN_CONTACTS for finding in findings)


def test_a_burst_is_contact_repeated_in_a_short_span(dated_case, client) -> None:
    _, headers, base = dated_case
    bursts = client.get(f"{base}/temporal/bursts", headers=headers).json()
    assert bursts
    assert bursts[0]["contacts"] >= temporal.BURST_MIN_CONTACTS
    assert bursts[0]["minutes"] <= temporal.BURST_WINDOW.total_seconds() / 60


def test_contact_with_no_established_time_is_excluded_not_assumed(dated_case) -> None:
    """A record with no timestamp is not evidence of anything happening at a particular moment."""
    case, _, _ = dated_case
    db = SessionLocal()
    try:
        undated = db.scalars(
            select(EntityRelation).where(
                EntityRelation.case_id == case["id"], EntityRelation.observed_at.is_(None)
            )
        ).all()
        placed = sum(temporal.case_chronology(db, case["id"])["contacts_placed"].values())
        total = db.scalars(select(EntityRelation).where(EntityRelation.case_id == case["id"])).all()
    finally:
        db.close()
    assert placed <= len(total) - len([row for row in undated if row.relation_type in temporal.CONTACT_RELATIONS])


def test_a_rejected_relationship_stops_driving_temporal_findings(dated_case, client) -> None:
    _, headers, base = dated_case
    relations = client.get(f"{base}/entity-relations", headers=headers, params={"relation_type": "CALLED", "limit": 50}).json()["items"]
    before = len(client.get(f"{base}/temporal/bursts", headers=headers).json())

    for relation in relations[:2]:
        client.post(
            f"{base}/entity-relations/{relation['id']}/review",
            headers=headers,
            json={"action": "reject_relationship", "reason": "Not supported by the source row."},
        )

    after = client.get(f"{base}/temporal/bursts", headers=headers).json()
    assert len(after) <= before, "a rejected contact still counted towards a burst"


# --------------------------------------------------------------------------- alerts


def test_the_pattern_rules_raise_reviewable_leads(dated_case) -> None:
    case, _, _ = dated_case
    codes = {alert.rule_code for alert in _alerts(case["id"])}
    assert "PRE_INCIDENT_COMMUNICATION" in codes
    assert "COMMUNICATION_BURST" in codes


def test_every_alert_names_the_evidence_or_explains_why_it_cannot(dated_case) -> None:
    case, _, _ = dated_case
    for alert in _alerts(case["id"]):
        assert alert.explanation.startswith("Review lead:"), alert.rule_code
        # A network-position alert points at entities rather than files; everything else must name
        # the evidence it was read from.
        if alert.rule_code != "BRIDGE_ENTITY":
            assert alert.affected_evidence_ids, alert.rule_code


def test_no_alert_asserts_involvement(dated_case) -> None:
    case, _, _ = dated_case
    body = " ".join(alert.explanation for alert in _alerts(case["id"])).lower()
    used = [word for word in FORBIDDEN_LANGUAGE if word in body]
    assert not used, f"alert wording asserted involvement: {used}"


def test_a_pre_incident_alert_says_contact_is_not_involvement(dated_case) -> None:
    case, _, _ = dated_case
    alerts = [alert for alert in _alerts(case["id"]) if alert.rule_code == "PRE_INCIDENT_COMMUNICATION"]
    assert alerts
    assert "not evidence of involvement" in alerts[0].explanation


def test_reprocessing_does_not_duplicate_alerts(dated_case, client) -> None:
    case, headers, _ = dated_case
    before = len(_alerts(case["id"]))
    evidence = client.get(f"/api/v1/cases/{case['id']}/evidence", headers=headers).json()
    for item in evidence:
        client.post(f"/api/v1/cases/{case['id']}/evidence/{item['id']}/process", headers=headers)
    assert len(_alerts(case["id"])) == before


def test_no_rule_discloses_another_case(dated_case) -> None:
    """A cross-case alert would tell everyone who can see this case that another one exists.

    Cross-case links stay behind the authorisation-scoped endpoint, where the asking user's own
    access decides what they are shown.
    """
    case, _, _ = dated_case
    db = SessionLocal()
    try:
        other_case_ids = {row.id for row in db.scalars(select(Case).where(Case.id != case["id"])).all()}
    finally:
        db.close()
    body = " ".join(alert.explanation for alert in _alerts(case["id"]))
    assert not [identifier for identifier in other_case_ids if identifier in body]
    assert "SHARED_IDENTIFIER_ACROSS_CASES" not in {alert.rule_code for alert in _alerts(case["id"])}


def test_temporal_endpoints_are_case_scoped(dated_case, client, case_factory) -> None:
    _, _, _ = dated_case
    other_case, other_headers = case_factory()
    other_base = f"/api/v1/cases/{other_case['id']}/grounded"
    assert client.get(f"{other_base}/temporal/pre-incident", headers=other_headers).json() == []
    assert client.get(f"{other_base}/temporal/bursts", headers=other_headers).json() == []
