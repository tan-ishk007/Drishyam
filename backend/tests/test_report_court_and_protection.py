"""Three promises a report makes the moment it leaves the building.

    It shows the evidence, not a description of it. A finding printed as "page 1, line 6" asks a
    reader to go and look; the line itself asks nothing of them.

    It says what it cannot support. A document that lists only what it found invites the reader to
    treat the list as complete.

    It does not name a protected person unless somebody decided it should. SIH26189 comes from the
    Women Safety Division, and a complainant's name printed across a document that will be copied,
    mailed and filed is a disclosure the report makes on her behalf every time it is generated.

The last of those is the one worth being strict about. Redaction applied at each place a name is
printed holds only where somebody remembered it, so the test here is not that the new sections
redact -- it is that the name appears nowhere in the whole document.
"""

from __future__ import annotations

import re

import fitz
import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Case, Report, User
from app.services import reporting
from scripts import benchmark_case

PROTECTED_NAME = "Priya Sharma"


@pytest.fixture
def protected_case(client, case_factory):
    """The benchmark case, with a protected identity declared on it."""
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
        record = db.get(Case, case["id"])
        record.victim_alias = PROTECTED_NAME
        db.commit()
    finally:
        db.close()
    return case, headers


def _render(case_id: str, profile: str = "case_file", redaction: str = "protected"):
    db = SessionLocal()
    try:
        author = db.scalar(select(User).limit(1))
        record = reporting.create_report_record(
            db, case_id=case_id, generated_by_id=author.id, profile=profile, redaction_profile=redaction
        )
        db.commit()
        report_id = record.id
    finally:
        db.close()

    assert reporting.generate_report(report_id)["status"] == "succeeded"

    db = SessionLocal()
    try:
        stored = db.get(Report, report_id)
        path = reporting.get_report_path(stored.storage_key)
        version = stored.version
    finally:
        db.close()

    with fitz.open(path) as document:
        text = re.sub(r"\s+", " ", "\n".join(page.get_text() for page in document))
        images = sum(len(page.get_images()) for page in document)
    return text, images, version


# --------------------------------------------------------------------------- E: shown, not described


def test_the_case_file_shows_findings_at_their_source(protected_case) -> None:
    case, _ = protected_case
    text, images, _ = _render(case["id"])

    assert "Findings shown at their source" in text
    assert "cut from the evidence itself" in text
    assert images > 0, "the section promises pictures and carried none"


def test_a_crop_is_a_piece_of_the_evidence_not_a_redrawing(protected_case, tmp_path) -> None:
    """The crop has to come out of the file, or the claim it supports is not the one being made."""
    from PIL import Image

    from app.core.config import get_settings
    from app.models.entities import EvidenceFile
    from app.services.storage import get_private_path

    case, _ = protected_case
    _render(case["id"])

    crops = sorted((get_settings().generated_reports_root / case["id"]).glob("crop-*.png"))
    assert crops, "no source crop was produced for a case containing screenshots and a PDF"

    db = SessionLocal()
    try:
        screenshots = [
            item
            for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case["id"]))
            if (item.detected_mime or "").startswith("image/")
        ]
        sizes = []
        for item in screenshots:
            with Image.open(get_private_path(item.storage_key)) as picture:
                sizes.append(picture.size)
    finally:
        db.close()

    widest = max(width for width, _ in sizes)
    tallest = max(height for _, height in sizes)
    for path in crops:
        with Image.open(path) as crop:
            assert crop.size[0] <= widest and crop.size[1] <= tallest
            assert crop.size[1] < tallest, "a crop the height of the page is not a crop"


# --------------------------------------------------------------------------- F: for a court


def test_the_annexure_carries_a_certificate_form_it_does_not_sign(protected_case) -> None:
    """The statute requires a person to certify. No system can attest to its own operation."""
    case, _ = protected_case
    text, _, _ = _render(case["id"], profile="court_annexure")

    assert "Certificate for electronic evidence" in text
    assert "Bharatiya Sakshya Adhiniyam 2023" in text
    assert "Part A — Particulars held on record" in text
    assert "Part B — Declaration to be signed" in text
    assert "DRISHYAM does not certify this record" in text
    assert "Signature" in text


def test_the_annexure_says_how_to_check_it_has_not_been_altered(protected_case) -> None:
    case, _ = protected_case
    text, _, version = _render(case["id"], profile="court_annexure")

    assert "Verifying this document" in text
    assert f"-R{version}" in text, "the verification identifier is not printed"
    assert "Evidence hash manifest" in text
    assert "a document cannot contain the hash of itself" in text


@pytest.mark.parametrize("profile", ["case_file", "court_annexure"])
def test_the_report_states_what_it_does_not_establish(protected_case, profile: str) -> None:
    case, _ = protected_case
    text, _, _ = _render(case["id"], profile=profile)

    assert "What this report does not establish" in text
    for limit in ("does not establish identity", "does not establish intent", "does not establish guilt"):
        assert limit in text


# --------------------------------------------------------------------------- G: a protected person


@pytest.mark.parametrize("profile", ["case_file", "briefing", "court_annexure", "handover"])
def test_a_protected_name_appears_nowhere_in_the_document(protected_case, profile: str) -> None:
    """Not "the new sections redact" -- the name is absent from the whole document.

    Anything weaker is a guarantee that holds until somebody adds a table and forgets.
    """
    case, _ = protected_case
    text, _, _ = _render(case["id"], profile=profile)

    assert PROTECTED_NAME not in text, f"the {profile} printed the protected name"
    assert "Protected person A" in text


def test_naming_the_person_is_a_decision_and_the_report_says_so(protected_case) -> None:
    case, _ = protected_case
    text, _, _ = _render(case["id"], redaction="identified")

    assert PROTECTED_NAME in text
    assert "explicit choice at generation" in text


def test_protection_is_what_a_caller_gets_without_asking(client, protected_case) -> None:
    case, headers = protected_case
    response = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["redaction_profile"] == "protected"


def test_a_case_with_no_protected_identity_withholds_nothing_and_says_so(client, case_factory) -> None:
    """Nothing is guessed. A report that masked whichever name looked vulnerable would be making an
    identification of its own while claiming to avoid one."""
    case, headers = case_factory()
    text, _, _ = _render(case["id"])
    assert "No protected identity is declared on this case" in text
