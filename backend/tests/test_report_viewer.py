"""Reading a report without downloading it, and opening a finding at its source.

The only way to see what a report said was to download the PDF. That is the wrong moment to hand
somebody a copy: the decision to pass a document on is made after reading it, and a file in a
downloads folder is a copy nobody is tracking any more.

Two things are load-bearing here. Search returns the rectangle of every occurrence rather than a
count, because a count leaves the reader to go and find the thing themselves. And a report's
findings are read back from what it stored when it was generated, never recomputed: an FIR that
cites "DRISHYAM finding F-07" must keep meaning the statement the printed report carries, even
after the case has moved on around it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Report
from scripts import benchmark_case


@pytest.fixture
def generated(client, case_factory):
    """A case with a real generated report behind it."""
    case, headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
    created = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    assert created.status_code in {200, 201, 202}, created.text
    report_id = created.json()["id"]

    db = SessionLocal()
    try:
        report = db.scalar(select(Report).where(Report.id == report_id))
        assert report is not None and report.storage_key, "the worker should have generated this report"
    finally:
        db.close()
    return case, headers, report_id


def _base(case_id: str, report_id: str) -> str:
    return f"/api/v1/cases/{case_id}/reports/{report_id}"


# --------------------------------------------------------------------------- reading it


def test_a_report_can_be_read_without_downloading_it(client, generated) -> None:
    case, headers, report_id = generated
    response = client.get(f"{_base(case['id'], report_id)}/pages", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pages"] > 1, "the case file report runs to several pages"
    assert body["width"] > 0 and body["height"] > 0


def test_every_page_renders(client, generated) -> None:
    case, headers, report_id = generated
    total = client.get(f"{_base(case['id'], report_id)}/pages", headers=headers).json()["pages"]

    for number in (1, total // 2 or 1, total):
        page = client.get(f"{_base(case['id'], report_id)}/pages/{number}", headers=headers)
        assert page.status_code == 200, f"page {number} did not render"
        assert page.headers["content-type"] == "image/png"
        assert len(page.content) > 1000


def test_opening_a_report_to_read_it_is_recorded(client, generated) -> None:
    """Reading a report and downloading one are the same access; only the copy differs."""
    case, headers, report_id = generated
    client.get(f"{_base(case['id'], report_id)}/pages", headers=headers)

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    actions = [item["action"] for item in entries]
    assert "report.read" in actions


def test_an_outsider_cannot_read_the_report(client, generated, account) -> None:
    case, _, report_id = generated
    _, outsider = account()
    assert client.get(f"{_base(case['id'], report_id)}/pages", headers=outsider).status_code in {403, 404}
    assert client.get(f"{_base(case['id'], report_id)}/pages/1", headers=outsider).status_code in {403, 404}


# --------------------------------------------------------------------------- searching it


def test_search_marks_every_occurrence_rather_than_counting_them(client, generated) -> None:
    case, headers, report_id = generated
    response = client.get(f"{_base(case['id'], report_id)}/search", headers=headers, params={"q": "DRISHYAM"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] > 0, "the report names the system it came from"
    assert len(body["matches"]) == body["total"] or body["truncated"]
    for match in body["matches"]:
        assert match["page"] >= 1
        assert len(match["bbox"]) == 4
        assert match["bbox"][2] > match["bbox"][0], "a mark with no width cannot be drawn"


def test_text_that_is_not_there_says_so_plainly(client, generated) -> None:
    case, headers, report_id = generated
    body = client.get(
        f"{_base(case['id'], report_id)}/search", headers=headers, params={"q": "zzqqxx-not-in-any-report"}
    ).json()

    assert body["total"] == 0
    assert body["matches"] == []
    assert "not about the case" in body["note"], "absence from a document is not absence from the case"


def test_a_search_too_short_to_mean_anything_is_refused(client, generated) -> None:
    case, headers, report_id = generated
    body = client.get(f"{_base(case['id'], report_id)}/search", headers=headers, params={"q": "a"}).json()

    assert body["total"] == 0
    assert "at least" in body["note"]


def test_searching_is_recorded(client, generated) -> None:
    case, headers, report_id = generated
    client.get(f"{_base(case['id'], report_id)}/search", headers=headers, params={"q": "Yash"})

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "report.search" in [item["action"] for item in entries]


# --------------------------------------------------------------------------- a finding opens its evidence


def test_every_finding_carries_the_place_it_was_read_from(client, generated) -> None:
    case, headers, report_id = generated
    body = client.get(f"{_base(case['id'], report_id)}/findings", headers=headers).json()

    assert body["findings"], "the benchmark case produces numbered findings"
    for finding in body["findings"]:
        assert finding["id"].startswith("F-")
        assert finding["statement"]
        assert finding["evidence_id"], "a finding that names no file cannot be opened"
        assert "source_reference" in finding


def test_findings_are_read_back_as_printed_not_recomputed(client, generated) -> None:
    """An FIR citing F-07 must keep meaning the statement the printed report carries."""
    case, headers, report_id = generated
    first = client.get(f"{_base(case['id'], report_id)}/findings", headers=headers).json()["findings"]

    # The case moves on: another file arrives and adds relationships.
    with next(iter(benchmark_case.generate().values())).open("rb") as stream:
        client.post(
            f"/api/v1/cases/{case['id']}/evidence",
            headers=headers,
            data={"source_category": "other"},
            files={"file": ("added-later.csv", stream, "application/octet-stream")},
        )

    again = client.get(f"{_base(case['id'], report_id)}/findings", headers=headers).json()["findings"]
    assert [item["id"] for item in again] == [item["id"] for item in first]
    assert [item["statement"] for item in again] == [item["statement"] for item in first]


def test_a_finding_whose_evidence_is_gone_says_so_rather_than_failing(client, generated) -> None:
    case, headers, report_id = generated
    db = SessionLocal()
    try:
        report = db.scalar(select(Report).where(Report.id == report_id))
        kept = list(report.findings)
        kept[0] = {**kept[0], "evidence_id": "an-id-no-longer-in-this-case"}
        report.findings = kept
        db.commit()
    finally:
        db.close()

    body = client.get(f"{_base(case['id'], report_id)}/findings", headers=headers).json()
    orphan = body["findings"][0]

    assert orphan["openable"] is False
    assert "no longer held in this case" in orphan["unopenable_reason"]
    assert orphan["id"] == "F-01", "it keeps its number rather than renumbering everything after it"
