"""The report has to describe the product this became, not the one it started as.

For a long time it did not. The PDF was written for a cyber-fraud case and never mentioned network
position, connected groups, the entity classes SIH26189 names, or the incident window -- so the
document an evaluator or a court would actually read said nothing about the work the system does.

These hold the report to two things: that it reports the network, and that it reports it under the
same restraint the screen does. A ranking printed on paper is read by somebody deciding whether to
act on it, and a score beside a person's name with no explanation beside it is the one output this
system must never produce.
"""

from __future__ import annotations

import re

import fitz
import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Report, User
from app.services import reporting
from scripts import benchmark_case


@pytest.fixture
def report_text(client, case_factory) -> str:
    """One benchmark case, taken all the way to a rendered PDF and read back as text."""
    case, headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )

    db = SessionLocal()
    try:
        author = db.scalar(select(User).limit(1))
        record = reporting.create_report_record(db, case_id=case["id"], generated_by_id=author.id)
        db.commit()
        report_id = record.id
    finally:
        db.close()

    outcome = reporting.generate_report(report_id)
    assert outcome["status"] == "succeeded", outcome

    db = SessionLocal()
    try:
        stored = db.get(Report, report_id)
        path = reporting.get_report_path(stored.storage_key)
    finally:
        db.close()

    with fitz.open(path) as document:
        assert document.page_count > 1
        text = "\n".join(page.get_text() for page in document)

    # A PDF breaks a sentence wherever the line ends, so extracted text carries newlines in the
    # middle of phrases. Comparing against the words rather than the layout is the only comparison
    # that means anything here.
    return re.sub(r"\s+", " ", text)


# --------------------------------------------------------------------------- what it says it is


def test_the_report_is_titled_for_the_problem_it_solves(report_text: str) -> None:
    assert "Criminal Network Analysis Report" in report_text
    assert "Digital Evidence Investigation Report" not in report_text


# --------------------------------------------------------------------------- what it now reports


@pytest.mark.parametrize(
    "section",
    [
        "Criminal network analysis",
        "Entities recorded, by class",
        "Identities appearing in more than one source",
        "Network position",
        "Relationships to verify first",
        "Connected groups",
        "Contact around the declared incident",
        "Traceability of this network",
    ],
)
def test_the_network_sections_are_present(report_text: str, section: str) -> None:
    assert section in report_text


def test_the_entity_classes_the_problem_statement_names_are_reported(report_text: str) -> None:
    """People, vehicles, places and organisations are the classes SIH26189 asks for by name."""
    for label in ("Person", "Vehicle", "Place"):
        assert label in report_text, f"the report never names the {label} class"


def test_an_identity_read_from_several_files_is_reported_as_one(report_text: str) -> None:
    """Resolving one identity across sources is what the product exists to do, so it is a figure."""
    assert "resolved to a single identity" in report_text


def test_traceability_is_stated_as_a_measured_figure(report_text: str) -> None:
    assert "% of the" in report_text
    assert "a relationship with no source cannot be stored" in report_text


# --------------------------------------------------------------------------- under what restraint


def test_no_ranking_is_printed_without_its_reason_and_its_caveat(report_text: str) -> None:
    """A number beside a name, alone on a page, is the one output this system must not produce."""
    assert "review priority, not guilt" in report_text
    assert "It is not an indication of guilt" in report_text


def test_a_group_is_not_reported_as_an_organisation(report_text: str) -> None:
    assert "a pattern, not an organisation" in report_text
    assert "It is not a finding that an organisation exists" in report_text


def test_contact_before_an_incident_is_not_reported_as_involvement(report_text: str) -> None:
    assert "not evidence of involvement" in report_text or "No incident window is declared" in report_text


def test_a_recorded_name_is_not_reported_as_an_established_identity(report_text: str) -> None:
    assert "does not establish that the person, place or body behind the name is the one named elsewhere" in report_text


def test_the_report_never_asserts_criminality(report_text: str) -> None:
    """The caveats name guilt in order to disclaim it. Nothing may assert it."""
    lowered = report_text.lower()
    for claim in ("is guilty", "is the culprit", "is a criminal", "committed the offence", "is responsible for the"):
        assert claim not in lowered, f"the report asserts: {claim}"
