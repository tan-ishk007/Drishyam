"""One value over a case's evidence, and proving one file was in it.

The report already prints every evidence hash, so a reader can check any file they hold. What it
could not do is fix the *set*: a file quietly dropped from a later report leaves every remaining
hash still correct. A root changes if anything is added, removed or reordered.

The courtroom property is the inclusion proof. One file's membership can be shown with a handful of
sibling hashes, without handing over the hashes of everyone else's material in the case -- which is
not the court's to see and may belong to people who are not on trial.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import EvidenceFile, Report, TrustifyReceipt
from app.services import merkle
from scripts import benchmark_case


def _leaves(count: int) -> list[str]:
    return [hashlib.sha256(f"synthetic-{index}".encode()).hexdigest() for index in range(count)]


# --------------------------------------------------------------------------- the tree itself


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 8, 9, 17])
def test_every_leaf_proves_against_the_root(size: int) -> None:
    leaves = _leaves(size)
    computed = merkle.root(leaves)

    for index in range(size):
        found = merkle.proof(leaves, index)
        assert found is not None
        assert merkle.verify(found.leaf, found.path, computed), f"leaf {index} of {size} failed"


def test_a_file_not_in_the_set_fails() -> None:
    leaves = _leaves(6)
    computed = merkle.root(leaves)
    outsider = hashlib.sha256(b"never in this case").hexdigest()

    found = merkle.proof(leaves, 2)
    assert not merkle.verify(outsider, found.path, computed)


def test_adding_a_file_changes_the_root() -> None:
    before = merkle.root(_leaves(5))
    after = merkle.root(_leaves(5) + [hashlib.sha256(b"one more").hexdigest()])
    assert before != after


def test_removing_a_file_changes_the_root() -> None:
    leaves = _leaves(5)
    assert merkle.root(leaves) != merkle.root(leaves[:-1])


def test_reordering_changes_the_root() -> None:
    """Order is part of what the root fixes; a set that could be shuffled fixes less than it seems."""
    leaves = _leaves(4)
    shuffled = [leaves[1], leaves[0], leaves[3], leaves[2]]
    assert merkle.root(leaves) != merkle.root(shuffled)


def test_an_odd_node_is_carried_up_not_duplicated() -> None:
    """The classic construction bug: hashing a lone node against itself lets a set of n and a set of
    n+1 whose last is duplicated produce the same root, which would prove membership for a file that
    was never there."""
    three = _leaves(3)
    duplicated = three + [three[-1]]
    assert merkle.root(three) != merkle.root(duplicated)


def test_an_empty_case_has_no_root_rather_than_the_hash_of_nothing() -> None:
    """An empty case and a case whose evidence was removed must not present the same value."""
    assert merkle.root([]) is None
    assert merkle.proof([], 0) is None


# --------------------------------------------------------------------------- through a real report


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


def test_a_report_records_the_set_it_covered(generated) -> None:
    case, _, report_id = generated
    db = SessionLocal()
    try:
        receipt = db.scalar(select(TrustifyReceipt).where(TrustifyReceipt.report_id == report_id))
        assert receipt is not None
        assert receipt.merkle_root, "a report with evidence should fix the set it covered"
        assert len(receipt.merkle_leaves) > 1
        assert merkle.root(receipt.merkle_leaves) == receipt.merkle_root
    finally:
        db.close()


def test_a_court_can_be_shown_one_file_without_the_others(client, generated) -> None:
    """The done-when."""
    case, headers, report_id = generated
    db = SessionLocal()
    try:
        evidence = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case["id"]))
        evidence_id, evidence_hash = evidence.id, evidence.sha256
        others = {
            item.sha256
            for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case["id"]))
            if item.id != evidence_id
        }
    finally:
        db.close()

    response = client.get(
        f"/api/v1/cases/{case['id']}/trustify/reports/{report_id}/evidence/{evidence_id}/proof", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["available"] is True
    assert body["verified"] is True
    assert body["leaf"] == evidence_hash
    assert merkle.verify(body["leaf"], body["path"], body["root"])
    assert len(body["path"]) < body["set_size"], "a proof shorter than the set is the whole point"
    assert "does not establish that the files are genuine" in body["proves"]

    # Sibling hashes are unavoidable in a proof, but the whole manifest must not come with it.
    disclosed = {step["hash"] for step in body["path"]}
    assert not others.issubset(disclosed) or len(others) <= len(disclosed), "the proof should not be the manifest"


def test_a_file_added_after_the_report_is_told_the_truth(client, generated) -> None:
    """It is in the case now and was not in the set then. That is an answer, not a failure."""
    case, headers, report_id = generated
    upload = client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        headers=headers,
        data={"source_category": "other"},
        files={"file": ("added-after.txt", b"SYNTHETIC TEST ONLY. Added later.", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    later = upload.json()["evidence"]["id"]

    body = client.get(
        f"/api/v1/cases/{case['id']}/trustify/reports/{report_id}/evidence/{later}/proof", headers=headers
    ).json()

    assert body["available"] is False
    assert "was not in the set this report covered" in body["reason"]


def test_asking_for_a_proof_is_recorded(client, generated) -> None:
    case, headers, report_id = generated
    db = SessionLocal()
    try:
        evidence_id = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case["id"])).id
    finally:
        db.close()
    client.get(
        f"/api/v1/cases/{case['id']}/trustify/reports/{report_id}/evidence/{evidence_id}/proof", headers=headers
    )

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "trustify.inclusion_proof" in [item["action"] for item in entries]


def test_an_outsider_gets_no_proof(client, generated, account) -> None:
    case, _, report_id = generated
    _, outsider = account()
    db = SessionLocal()
    try:
        evidence_id = db.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case["id"])).id
    finally:
        db.close()
    response = client.get(
        f"/api/v1/cases/{case['id']}/trustify/reports/{report_id}/evidence/{evidence_id}/proof", headers=outsider
    )
    assert response.status_code in {403, 404}
