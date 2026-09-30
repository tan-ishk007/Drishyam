"""How the grounded pass behaves when a provider call fails.

The model pass reaches a local daemon and, on escalation, a remote provider. Those calls fail
transiently, and before this the first failure cost the evidence its timeline, transactions and
graph edges permanently. These tests pin the recovery rule: retry what might succeed, give up
immediately on what cannot.
"""

from __future__ import annotations

import pytest

from app.services import pipeline


class FakeSession:
    """Enough of a Session for `_run_grounded`: it fetches evidence and probes for artifacts."""

    def __init__(self, *, evidence=object(), has_artifacts=True):
        self._evidence = evidence
        self._has_artifacts = has_artifacts
        self.rollbacks = 0
        self.commits = 0

    def get(self, _model, _identifier):
        return self._evidence

    def scalar(self, _statement):
        return "artifact-id" if self._has_artifacts else None

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(pipeline.time, "sleep", lambda _seconds: None)


def _run_returning(monkeypatch, outcomes):
    """Patch the grounded pipeline to yield `outcomes` in order; exceptions are raised."""
    calls = {"count": 0}

    def fake(_db, _evidence):
        index = calls["count"]
        calls["count"] += 1
        result = outcomes[index]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.services.grounded_pipeline.run_grounded_pipeline", fake)
    return calls


def test_a_transient_provider_failure_is_retried_and_recovers(monkeypatch):
    calls = _run_returning(monkeypatch, [ConnectionError("provider hiccup"), {"records": 1}])
    session = FakeSession()

    outcome = pipeline._run_grounded(session, "evidence-1")

    assert outcome["status"] == "completed"
    assert outcome["records"] == 1
    assert outcome["attempts"] == 2
    assert calls["count"] == 2


def test_retries_are_bounded_and_the_failure_is_recorded(monkeypatch):
    calls = _run_returning(monkeypatch, [ConnectionError("down")] * pipeline.GROUNDED_MAX_ATTEMPTS)
    recorded: list[tuple] = []
    monkeypatch.setattr(
        pipeline,
        "_record_grounded_failure",
        lambda _db, evidence_id, exc, attempts: recorded.append((evidence_id, type(exc).__name__, attempts)),
    )
    session = FakeSession()

    outcome = pipeline._run_grounded(session, "evidence-1")

    assert outcome == {"status": "failed", "reason": "ConnectionError", "attempts": pipeline.GROUNDED_MAX_ATTEMPTS}
    assert calls["count"] == pipeline.GROUNDED_MAX_ATTEMPTS
    # The reviewer needs to see why the evidence has no grounded reading.
    assert recorded == [("evidence-1", "ConnectionError", pipeline.GROUNDED_MAX_ATTEMPTS)]


def test_an_unreadable_file_is_not_retried(monkeypatch):
    """No raw artifact means extraction itself failed; a second attempt reaches the same answer."""
    calls = _run_returning(monkeypatch, [ValueError("cannot decode image")] * pipeline.GROUNDED_MAX_ATTEMPTS)
    monkeypatch.setattr(pipeline, "_record_grounded_failure", lambda *_args: None)
    session = FakeSession(has_artifacts=False)

    outcome = pipeline._run_grounded(session, "evidence-1")

    assert outcome["status"] == "failed"
    assert outcome["attempts"] == 1
    assert calls["count"] == 1


def test_missing_evidence_is_skipped_without_calling_the_model(monkeypatch):
    calls = _run_returning(monkeypatch, [{"records": 1}])
    session = FakeSession(evidence=None)

    assert pipeline._run_grounded(session, "gone") == {"status": "skipped", "reason": "evidence_missing"}
    assert calls["count"] == 0
