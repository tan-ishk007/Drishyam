"""What arrived since a reader last opened a case.

Coming back after a week means reading everything again to find the three things that changed. The
value of this feature is entirely in being trustworthy: a digest that padded a quiet week, or that
reported things the reader cannot see, or that quietly cleared itself when glanced at, would teach
them to skip it -- which costs more than showing nothing.
"""

from __future__ import annotations

import pytest

from scripts import benchmark_case


def _digest(client, case, headers) -> dict:
    response = client.get(f"/api/v1/cases/{case['id']}/whats-new", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _seen(client, case, headers) -> None:
    assert client.post(f"/api/v1/cases/{case['id']}/whats-new/seen", headers=headers).status_code == 204


def _add_evidence(client, case, headers, name: str = "later.txt") -> None:
    response = client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        headers=headers,
        data={"source_category": "other"},
        files={"file": (name, b"SYNTHETIC TEST ONLY. Added later.", "text/plain")},
    )
    assert response.status_code == 201, response.text


def test_a_first_visit_says_so_rather_than_listing_everything(client, case_factory) -> None:
    case, headers = case_factory()
    digest = _digest(client, case, headers)

    assert digest["first_visit"] is True
    assert digest["changes"] == []
    assert "nothing to compare against" in digest["statement"]


def test_an_unchanged_case_says_nothing_is_new(client, case_factory) -> None:
    """Padding a quiet week with restated old facts teaches the reader to skip the digest."""
    case, headers = case_factory()
    _seen(client, case, headers)

    digest = _digest(client, case, headers)
    assert digest["first_visit"] is False
    assert digest["changes"] == []
    assert digest["statement"] == "Nothing has been added to this case since you last opened it."


def test_new_evidence_is_reported_by_name(client, case_factory) -> None:
    case, headers = case_factory()
    _seen(client, case, headers)
    _add_evidence(client, case, headers, "witness-statement.txt")

    digest = _digest(client, case, headers)
    evidence = next(item for item in digest["changes"] if item["kind"] == "evidence")
    assert evidence["count"] == 1
    assert "witness-statement.txt" in evidence["examples"]


def test_the_digest_states_nothing_about_what_any_of_it_means(client, case_factory) -> None:
    case, headers = case_factory()
    _seen(client, case, headers)
    _add_evidence(client, case, headers)

    digest = _digest(client, case, headers)
    for change in digest["changes"]:
        assert "your read" in change["detail"] or "not" in change["detail"], (
            f"{change['kind']} states a conclusion: {change['detail']}"
        )


def test_reading_the_digest_does_not_clear_it(client, case_factory) -> None:
    """A reader who glanced at it and was called away must not lose those changes for good."""
    case, headers = case_factory()
    _seen(client, case, headers)
    _add_evidence(client, case, headers)

    first = _digest(client, case, headers)
    again = _digest(client, case, headers)
    assert first["changes"] == again["changes"], "the digest cleared itself on being read"


def test_marking_it_seen_clears_it(client, case_factory) -> None:
    case, headers = case_factory()
    _seen(client, case, headers)
    _add_evidence(client, case, headers)
    assert _digest(client, case, headers)["changes"]

    _seen(client, case, headers)
    assert _digest(client, case, headers)["changes"] == []


def test_the_digest_is_per_user_not_per_case(client, case_factory, account) -> None:
    """What is new to a returning investigator is not new to the colleague who uploaded it."""
    case, owner = case_factory()
    colleague_email, colleague = account()
    client.post(
        f"/api/v1/cases/{case['id']}/members",
        headers=owner,
        json={"email": colleague_email, "case_role": "investigator"},
    )

    _seen(client, case, owner)
    _seen(client, case, colleague)
    _add_evidence(client, case, owner)
    _seen(client, case, owner)

    assert _digest(client, case, owner)["changes"] == [], "the owner has seen it"
    assert _digest(client, case, colleague)["changes"], "the colleague has not"


def test_an_outsider_gets_nothing(client, case_factory, account) -> None:
    case, _ = case_factory()
    _, outsider = account()
    assert client.get(f"/api/v1/cases/{case['id']}/whats-new", headers=outsider).status_code in {403, 404}
    assert client.post(f"/api/v1/cases/{case['id']}/whats-new/seen", headers=outsider).status_code in {403, 404}


def test_patterns_and_relationships_are_reported_after_processing(client, case_factory) -> None:
    case, headers = case_factory()
    _seen(client, case, headers)
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )

    kinds = {item["kind"] for item in _digest(client, case, headers)["changes"]}
    assert "evidence" in kinds
    assert "relationships" in kinds
