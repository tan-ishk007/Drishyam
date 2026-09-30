"""The response cache: identical work is never paid for twice.

The cache key already covered the evidence hash, parser version, provider, model, prompt version
and the image bytes, and its docstring already promised this. Only the audit row was deduplicated,
though, so the model was called again on every reprocess -- tens of seconds per image on a local
vision model, for an answer already on record.

No test here touches the network; the provider is scripted and counts its own calls.
"""

from __future__ import annotations

import pytest

from app.evidence_intelligence.detection import ContentFileTypeDetector
from app.evidence_intelligence.extraction import DeterministicExtractor
from app.evidence_intelligence.providers.mock import ScriptedVLMAdapter
from app.evidence_intelligence.providers.router import CachedResponse, ModelRouter
from tests.fixtures import synthetic

MESSAGE_TEXT = "bhai is number pe 25000 bhej de"


@pytest.fixture
def chat_unit(tmp_path):
    path = synthetic.whatsapp_chat_export(tmp_path / "chat.txt")
    detected = ContentFileTypeDetector().detect(path, declared_category="chat_export")
    extraction = DeterministicExtractor().extract(path, evidence_id="ev-chat", detected=detected)
    unit = next(item for item in extraction.units if MESSAGE_TEXT in item.text)
    return unit, extraction


def _payload(unit):
    return {
        "observed_text": unit.text,
        "normalized_summary": "Asks for a transfer to a number that is not shown.",
        "observation_basis": "inferred",
        "requires_human_review": True,
        "model_confidence": 0.8,
    }


def _normalize(router, unit, extraction):
    return router.normalize(unit, extraction, evidence_sha256="hash-a", ocr_result=None)


def test_without_a_cache_reader_the_provider_is_still_called(chat_unit) -> None:
    """The reader is optional. A router given none behaves exactly as it always did."""
    unit, extraction = chat_unit
    adapter = ScriptedVLMAdapter(payload=_payload(unit))
    router = ModelRouter(local=adapter, escalation=None)

    _normalize(router, unit, extraction)
    _normalize(router, unit, extraction)
    assert len(adapter.calls) == 2


def test_a_known_answer_is_reused_instead_of_asking_again(chat_unit) -> None:
    unit, extraction = chat_unit
    adapter = ScriptedVLMAdapter(payload=_payload(unit))
    seen: dict[str, CachedResponse] = {}

    recording = ModelRouter(local=adapter, escalation=None)
    outcome = _normalize(recording, unit, extraction)
    for attempt in outcome.attempts:
        if attempt.payload is not None:
            seen[attempt.cache_key] = CachedResponse(raw_output=attempt.raw_output, payload=attempt.payload)
    assert len(adapter.calls) == 1, "the first pass must actually ask the provider"

    replaying = ModelRouter(local=adapter, escalation=None, cache_lookup=seen.get)
    replayed = _normalize(replaying, unit, extraction)

    assert len(adapter.calls) == 1, "the provider was asked again for an answer already on record"
    assert any(attempt.status == "cached" for attempt in replayed.attempts)


def test_a_reused_answer_is_labelled_as_reused(chat_unit) -> None:
    """A cached attempt must not be indistinguishable from a fresh call in the audit trail."""
    unit, extraction = chat_unit
    adapter = ScriptedVLMAdapter(payload=_payload(unit))
    seen: dict[str, CachedResponse] = {}
    first = _normalize(ModelRouter(local=adapter, escalation=None), unit, extraction)
    for attempt in first.attempts:
        if attempt.payload is not None:
            seen[attempt.cache_key] = CachedResponse(raw_output=attempt.raw_output, payload=attempt.payload)

    replayed = _normalize(ModelRouter(local=adapter, escalation=None, cache_lookup=seen.get), unit, extraction)
    cached = [attempt for attempt in replayed.attempts if attempt.status == "cached"]
    assert cached
    assert cached[0].latency_ms == 0
    assert cached[0].payload is not None


def test_a_different_prompt_version_is_a_different_question(chat_unit, monkeypatch) -> None:
    """Cached results must not survive a prompt change, or a wording fix would never take effect."""
    from app.evidence_intelligence.providers import prompts

    unit, extraction = chat_unit
    adapter = ScriptedVLMAdapter(payload=_payload(unit))
    seen: dict[str, CachedResponse] = {}
    first = _normalize(ModelRouter(local=adapter, escalation=None), unit, extraction)
    for attempt in first.attempts:
        if attempt.payload is not None:
            seen[attempt.cache_key] = CachedResponse(raw_output=attempt.raw_output, payload=attempt.payload)

    monkeypatch.setattr(prompts, "PROMPT_VERSION", "grounded-normalize-test-next")
    _normalize(ModelRouter(local=adapter, escalation=None, cache_lookup=seen.get), unit, extraction)
    assert len(adapter.calls) == 2, "a new prompt version reused an answer from the old wording"


def test_different_evidence_is_a_different_question(chat_unit) -> None:
    unit, extraction = chat_unit
    adapter = ScriptedVLMAdapter(payload=_payload(unit))
    seen: dict[str, CachedResponse] = {}

    first = ModelRouter(local=adapter, escalation=None)
    outcome = first.normalize(unit, extraction, evidence_sha256="hash-a", ocr_result=None)
    for attempt in outcome.attempts:
        if attempt.payload is not None:
            seen[attempt.cache_key] = CachedResponse(raw_output=attempt.raw_output, payload=attempt.payload)

    second = ModelRouter(local=adapter, escalation=None, cache_lookup=seen.get)
    second.normalize(unit, extraction, evidence_sha256="hash-b", ocr_result=None)
    assert len(adapter.calls) == 2, "a different evidence file reused another file's answer"
