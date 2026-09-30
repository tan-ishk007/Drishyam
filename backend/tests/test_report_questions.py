"""Asking about a report, with nothing behind it but the report and the case.

A reader with a nineteen-page document asks three kinds of question. Where did this come from goes
to the case assistant, which reads the case's own rows. Where does it say that returns the report's
own words. Everything else is declined.

The declining is the part that matters. A system that guesses at the edge of what it knows is worse
than one that stops, because the reader cannot tell the guesses from the answers -- and the only
claim this product really makes is that nothing leaves the machine, which one careless feature ends.
"""

from __future__ import annotations

import pytest

from scripts import benchmark_case


@pytest.fixture
def generated(client, case_factory):
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
    return case, headers, created.json()["id"]


def _ask(client, case, headers, report_id: str, question: str) -> dict:
    response = client.post(
        f"/api/v1/cases/{case['id']}/reports/{report_id}/ask", headers=headers, json={"question": question}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- questions of fact


def test_a_reader_can_ask_about_a_finding_and_get_its_source(client, generated) -> None:
    """The done-when."""
    case, headers, report_id = generated
    body = _ask(client, case, headers, report_id, "What is F-01 based on?")

    assert body["kind"] == "finding"
    assert body["finding"]["id"] == "F-01"
    assert body["finding"]["file"], "an answer with no source is a claim"
    assert "read from" in body["answer"]


@pytest.mark.parametrize("phrasing", ["F-2", "F-02", "finding 2", "Finding no. 2"])
def test_a_finding_is_recognised_however_it_is_cited(client, generated, phrasing: str) -> None:
    """The number is what gets typed, because it is what other documents cite."""
    case, headers, report_id = generated
    body = _ask(client, case, headers, report_id, f"Where did {phrasing} come from?")
    assert body["kind"] == "finding"
    assert body["finding"]["id"] == "F-02"


def test_the_answer_is_what_the_report_printed_not_a_fresh_account(client, generated) -> None:
    """A paraphrase of a filed document is a second version of it, and the reader cannot tell which
    one they are reading."""
    case, headers, report_id = generated
    printed = client.get(f"/api/v1/cases/{case['id']}/reports/{report_id}/findings", headers=headers).json()
    first = printed["findings"][0]

    body = _ask(client, case, headers, report_id, "Explain F-01")
    assert first["statement"] in body["answer"]


def test_a_question_about_the_case_reaches_the_assistant(client, generated) -> None:
    case, headers, report_id = generated
    body = _ask(client, case, headers, report_id, "What connects +919876543210 and +919988776655?")

    assert body["kind"] == "case"
    assert body["answer"]


# --------------------------------------------------------------------------- questions about the document


def test_where_does_it_say_that_is_answered_from_the_document(client, generated) -> None:
    case, headers, report_id = generated
    body = _ask(client, case, headers, report_id, "Where does it say DRISHYAM?")

    assert body["kind"] == "wording"
    assert body["occurrences"], "the word is in the report"
    assert "nothing has been rephrased" in body["answer"]


def test_words_not_in_the_report_are_reported_carefully(client, generated) -> None:
    case, headers, report_id = generated
    body = _ask(client, case, headers, report_id, "Where does it say zzqqxx-never-written?")

    assert body["kind"] == "wording"
    assert body["occurrences"] == []
    assert "not about the case" in body["answer"]


# --------------------------------------------------------------------------- what it refuses


@pytest.mark.parametrize(
    "question",
    [
        "Who is responsible for this?",
        "Do you think he is guilty?",
        "What should I do next?",
        "How likely is a conviction?",
    ],
)
def test_a_question_outside_scope_is_declined_rather_than_guessed(client, generated, question: str) -> None:
    case, headers, report_id = generated
    body = _ask(client, case, headers, report_id, question)

    assert body["kind"] == "declined"
    assert "outside what this can answer" in body["answer"]


def test_the_scope_is_stated_on_every_answer(client, generated) -> None:
    case, headers, report_id = generated
    for question in ("What is F-01 based on?", "Who is responsible?"):
        body = _ask(client, case, headers, report_id, question)
        assert "no part of the report or the case is sent anywhere" in body["scope"]


def test_asking_is_recorded(client, generated) -> None:
    case, headers, report_id = generated
    _ask(client, case, headers, report_id, "What is F-01 based on?")

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "report.question" in [item["action"] for item in entries]


def test_an_outsider_cannot_ask(client, generated, account) -> None:
    case, _, report_id = generated
    _, outsider = account()
    response = client.post(
        f"/api/v1/cases/{case['id']}/reports/{report_id}/ask", headers=outsider, json={"question": "What is F-01?"}
    )
    assert response.status_code in {403, 404}
