"""Four readers, four documents, and the line between them.

One report was being asked to serve a station officer, an investigator, a court and the next
officer on the case at once. It served none of them well: the briefing was buried on page nine, and
a court was handed network rankings interleaved with the evidence register as though a centrality
score and a SHA-256 were the same kind of statement.

The line that matters most here is the court annexure's. It carries what can be attested to -- what
files exist, what they hash to, what was run over them, who touched them -- and none of what this
system inferred. A ranking printed beside a hash borrows the hash's authority, and no caveat
printed underneath undoes that.
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


@pytest.fixture(scope="function")
def case_with_evidence(client, case_factory):
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


def _render(case_id: str, profile: str) -> tuple[str, int]:
    db = SessionLocal()
    try:
        author = db.scalar(select(User).limit(1))
        record = reporting.create_report_record(db, case_id=case_id, generated_by_id=author.id, profile=profile)
        db.commit()
        report_id = record.id
    finally:
        db.close()

    assert reporting.generate_report(report_id)["status"] == "succeeded"

    db = SessionLocal()
    try:
        stored = db.get(Report, report_id)
        assert stored.profile == profile, "the report did not keep the profile it was asked for"
        path = reporting.get_report_path(stored.storage_key)
    finally:
        db.close()

    with fitz.open(path) as document:
        return re.sub(r"\s+", " ", "\n".join(page.get_text() for page in document)), document.page_count


# --------------------------------------------------------------------------- each is its own document


def test_a_briefing_is_short_and_says_where_to_look(case_with_evidence) -> None:
    case, _ = case_with_evidence
    text, pages = _render(case["id"], "briefing")

    assert pages <= 4, f"a briefing that runs to {pages} pages is not a briefing"
    assert "Investigation Briefing" in text
    assert "Where to look first" in text
    assert "Verify these before acting on anything" in text
    assert "What this case does not establish" in text


def test_a_handover_says_what_has_not_been_checked(case_with_evidence) -> None:
    case, _ = case_with_evidence
    text, _ = _render(case["id"], "handover")

    assert "Case Handover Pack" in text
    assert "State of this case" in text
    assert "Not yet checked by a person" in text
    assert "What is missing" in text


def test_the_full_case_file_is_still_the_full_case_file(case_with_evidence) -> None:
    case, _ = case_with_evidence
    text, pages = _render(case["id"], "case_file")

    assert pages > 10
    assert "Criminal Network Analysis Report" in text
    assert "Criminal network analysis" in text
    assert "Evidence register" in text


# --------------------------------------------------------------------------- the court's line


def test_a_court_annexure_carries_the_record_and_not_the_reading(case_with_evidence) -> None:
    """The whole point of this profile. Everything here can be attested to."""
    case, _ = case_with_evidence
    text, _ = _render(case["id"], "court_annexure")

    assert "Evidence Annexure and Integrity Record" in text
    assert "Evidence register" in text
    assert "SHA-256" in text
    assert "Access and handling record" in text
    assert "contains no analysis, no ranking and no finding" in text


@pytest.mark.parametrize(
    "interpretation",
    ["review priority", "Network position", "sits at the centre", "Connected groups", "Verify these"],
)
def test_a_court_annexure_states_nothing_the_system_inferred(case_with_evidence, interpretation: str) -> None:
    case, _ = case_with_evidence
    text, _ = _render(case["id"], "court_annexure")
    assert interpretation not in text, f"the annexure carries an inference: {interpretation}"


def test_a_court_annexure_carries_no_numbered_finding(case_with_evidence) -> None:
    case, _ = case_with_evidence
    text, _ = _render(case["id"], "court_annexure")
    assert not re.search(r"\bF-\d\d\b", text), "a finding is a reading, and readings are not attested to here"


# --------------------------------------------------------------------------- numbered findings


def test_a_finding_can_be_cited_by_number_and_opened_at_its_source(case_with_evidence) -> None:
    """An FIR or a case diary needs to be able to say "finding F-07" and have that mean one thing."""
    case, _ = case_with_evidence

    db = SessionLocal()
    try:
        findings = reporting._numbered_findings(db, case["id"], {})
    finally:
        db.close()

    assert findings, "the benchmark case states relationships and should produce findings"
    assert [item["id"] for item in findings] == [f"F-{index:02d}" for index in range(1, len(findings) + 1)]

    for item in findings:
        assert item["statement"].endswith("."), "a finding is a sentence"
        assert item["file"], f"{item['id']} names no evidence file"
        assert 0.0 <= item["confidence"] <= 1.0


def test_the_findings_that_hold_the_network_together_come_first(case_with_evidence) -> None:
    """Ordered by how much of the case rests on each, because that is the order of consequence."""
    case, _ = case_with_evidence

    db = SessionLocal()
    try:
        findings = reporting._numbered_findings(db, case["id"], {})
    finally:
        db.close()

    flags = [item["load_bearing"] for item in findings]
    if any(flags) and not all(flags):
        assert flags.index(False) > flags.index(True), "a load-bearing finding was listed after an ordinary one"


def test_a_case_file_prints_the_numbered_findings(case_with_evidence) -> None:
    case, _ = case_with_evidence
    text, _ = _render(case["id"], "case_file")
    assert "Numbered findings" in text
    assert re.search(r"\bF-01\b", text)


# --------------------------------------------------------------------------- through the API


def test_the_endpoint_records_the_profile_that_was_asked_for(client, case_with_evidence) -> None:
    case, headers = case_with_evidence
    response = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers, json={"profile": "briefing"})
    assert response.status_code == 202, response.text
    assert response.json()["profile"] == "briefing"


def test_a_caller_that_asks_for_nothing_still_gets_the_full_case_file(client, case_with_evidence) -> None:
    """Callers written before profiles existed keep getting what they were always getting."""
    case, headers = case_with_evidence
    response = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["profile"] == "case_file"


def test_an_unknown_profile_is_refused(client, case_with_evidence) -> None:
    case, headers = case_with_evidence
    response = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers, json={"profile": "everything"})
    assert response.status_code == 422
