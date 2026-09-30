"""Drafting the next request from what the case already records.

An investigator finishes reading the network and then writes a requisition by hand. The facts they
need are already here: which identifiers appear, which link rests on a single observation, when the
recorded contact happened. This assembles them.

The tests are about restraint. Every number in a draft must trace to a stated relationship; a period
must come from an observed time rather than being widened to something convenient; and no sentence
may say that anybody did anything, because a requisition goes out over an officer's name and this
case does not know that.
"""

from __future__ import annotations

import pytest

from scripts import benchmark_case


@pytest.fixture
def worked_case(client, case_factory):
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


def _draft(client, case, headers) -> dict:
    response = client.get(f"/api/v1/cases/{case['id']}/grounded/requisition/draft", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_network_page_can_produce_the_next_request(client, worked_case) -> None:
    """The done-when."""
    case, headers = worked_case
    draft = _draft(client, case, headers)

    assert draft["subjects"], "the benchmark case records identifiers worth asking about"
    assert draft["text"].startswith("Subject: Request for records")
    assert draft["case_number"] == case["case_number"]


def test_every_number_traces_to_a_stated_relationship(client, worked_case) -> None:
    """A request that cannot say why it is asking is a fishing expedition."""
    case, headers = worked_case
    for subject in _draft(client, case, headers)["subjects"]:
        assert subject["basis"], f"{subject['value']} is requested with no stated basis"
        assert "observation" in subject["basis"]
        assert subject["evidence"], "a basis that names no evidence file cannot be checked"


def test_a_period_comes_from_a_recorded_time_or_is_not_proposed(client, worked_case) -> None:
    """Widening a request to a range nobody observed turns a proportionate ask into a general one."""
    case, headers = worked_case
    for subject in _draft(client, case, headers)["subjects"]:
        if subject["period_from"] is None:
            assert "no period is proposed" in subject["basis"]
        else:
            assert subject["period_to"] >= subject["period_from"]


def test_the_draft_states_its_own_basis_and_that_it_is_not_a_submission(client, worked_case) -> None:
    case, headers = worked_case
    draft = _draft(client, case, headers)

    assert "not a submission" in draft["closing"]
    assert "send it under your own name" in draft["closing"]


def test_no_sentence_says_anybody_did_anything(client, worked_case) -> None:
    case, headers = worked_case
    draft = _draft(client, case, headers)
    text = draft["text"].lower()

    for forbidden in ("suspect", "accused of", "committed", "guilty", "conspired", "involved in the offence"):
        assert forbidden not in text, f"the draft asserts {forbidden!r}"
    # The guard is a blunt substring scan on purpose. One that had to understand negation would
    # eventually read "has not committed" as an accusation, or miss a real one.
    assert "states that any person" in draft["text"]


def test_a_fragile_link_is_asked_about_first(client, worked_case) -> None:
    """The only recorded link between two parts of a network is the first thing worth confirming."""
    case, headers = worked_case
    subjects = _draft(client, case, headers)["subjects"]
    load_bearing = [index for index, item in enumerate(subjects) if item["load_bearing"]]

    if load_bearing:
        assert load_bearing[0] == 0, "a fragile link should lead the request"
        assert "only recorded link" in subjects[0]["basis"]


def test_a_case_with_nothing_in_it_proposes_nothing(client, case_factory) -> None:
    case, headers = case_factory()
    draft = _draft(client, case, headers)

    assert draft["subjects"] == []
    assert "nothing to request" in draft["text"]


def test_a_case_with_no_incident_window_says_where_its_periods_came_from(client, worked_case) -> None:
    case, headers = worked_case
    assert "No incident window has been declared" in _draft(client, case, headers)["text"]


def test_drafting_is_recorded(client, worked_case) -> None:
    case, headers = worked_case
    _draft(client, case, headers)

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "requisition.draft" in [item["action"] for item in entries]


def test_an_outsider_gets_no_draft(client, worked_case, account) -> None:
    case, _ = worked_case
    _, outsider = account()
    response = client.get(f"/api/v1/cases/{case['id']}/grounded/requisition/draft", headers=outsider)
    assert response.status_code in {403, 404}
