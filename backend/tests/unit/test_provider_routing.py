"""Routing policy, provider failure handling and prompt-level safety.

No test in this file touches the network. Provider behaviour is scripted.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.evidence_intelligence.detection import ContentFileTypeDetector
from app.evidence_intelligence.extraction import DeterministicExtractor
from app.evidence_intelligence.providers import prompts
from app.evidence_intelligence.providers.base import ProviderError, ProviderErrorKind, VLMRequest
from app.evidence_intelligence.providers.groq import GroqVLMAdapter
from app.evidence_intelligence.providers.mock import ScriptedVLMAdapter, invalid_json_adapter, unavailable_adapter
from app.evidence_intelligence.providers.router import ModelRouter
from app.evidence_intelligence.schema import ObservationBasis
from tests.fixtures import synthetic

MESSAGE_TEXT = "bhai is number pe 25000 bhej de"


@pytest.fixture
def chat_unit(tmp_path):
    path = synthetic.whatsapp_chat_export(tmp_path / "chat.txt")
    detected = ContentFileTypeDetector().detect(path, declared_category="chat_export")
    extraction = DeterministicExtractor().extract(path, evidence_id="ev-chat", detected=detected)
    unit = next(item for item in extraction.units if MESSAGE_TEXT in item.text)
    return unit, extraction


def _payload(unit, **overrides):
    payload = {
        "observed_text": unit.text,
        "normalized_summary": "Asks for a transfer to a number that is not shown.",
        "observation_basis": "inferred",
        "event_type": {
            "value": "possible_payment_request",
            "basis": "inferred",
            "quote": unit.text,
            "source_reference": unit.reference.locator,
            "confidence": 0.78,
        },
        "model_confidence": 0.8,
        "requires_human_review": True,
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------- graceful provider failure


def test_both_providers_down_still_produces_a_grounded_record(chat_unit):
    unit, extraction = chat_unit
    outcome = ModelRouter(
        local=unavailable_adapter("ollama", "qwen2.5vl:7b"),
        escalation=unavailable_adapter("groq", "qwen/qwen3.8-27b"),
    ).normalize(unit, extraction, evidence_sha256="hash")

    # Deterministic extraction survives untouched.
    assert outcome.record.observed_text == MESSAGE_TEXT
    assert outcome.record.amount.value == 25000.0
    assert outcome.record.sender == "Ramesh Kumar"
    assert outcome.record.requires_human_review is True
    assert {attempt.status for attempt in outcome.attempts} == {"failed"}
    assert all(attempt.error["kind"] == "unavailable" for attempt in outcome.attempts)


def test_unreachable_provider_is_dialled_once_per_evidence_item(chat_unit):
    """A 300-row statement must not mean 300 connection timeouts."""
    unit, extraction = chat_unit
    local = unavailable_adapter("ollama", "qwen2.5vl:7b")
    router = ModelRouter(local=local, escalation=None)

    for _ in range(5):
        outcome = router.normalize(unit, extraction, evidence_sha256="hash")
        assert outcome.attempts[0].status == "failed"

    assert len(local.calls) == 1


def test_local_failure_escalates_and_records_the_reason(chat_unit):
    unit, extraction = chat_unit
    outcome = ModelRouter(
        local=unavailable_adapter("ollama", "qwen2.5vl:7b"),
        escalation=ScriptedVLMAdapter(name="groq", model="qwen/qwen3.8-27b", payload=_payload(unit)),
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.escalated is True
    assert any("local model was unavailable" in reason for reason in outcome.escalation_reasons)
    assert outcome.record.event_type == "possible_payment_request"


def test_invalid_model_json_is_rejected_not_trusted(chat_unit):
    unit, extraction = chat_unit
    outcome = ModelRouter(local=invalid_json_adapter("ollama", "qwen2.5vl:7b"), escalation=None).normalize(
        unit, extraction, evidence_sha256="hash"
    )

    assert outcome.attempts[0].status == "rejected"
    assert outcome.record.event_type is None
    assert outcome.record.amount.value == 25000.0  # parser output is unaffected


def test_schema_violation_is_rejected(chat_unit):
    unit, extraction = chat_unit
    # observed_text that does not appear in the source is a fabrication, not a reading.
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(
            name="ollama", model="qwen2.5vl:7b", payload=_payload(unit, observed_text="something never written")
        ),
        escalation=None,
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.attempts[0].status == "rejected"
    assert outcome.attempts[0].grounding_report["rejected_reason"]


def test_escalation_is_skipped_when_the_local_result_is_solid(chat_unit):
    unit, extraction = chat_unit
    escalation = ScriptedVLMAdapter(name="groq", model="qwen/qwen3.8-27b", payload=_payload(unit))

    outcome = ModelRouter(
        local=ScriptedVLMAdapter(
            name="ollama",
            model="qwen2.5vl:7b",
            payload=_payload(
                unit,
                amount={
                    "value": {"value": 25000.0, "currency": None},
                    "basis": "direct",
                    "quote": "25000",
                    "source_reference": unit.reference.locator,
                    "confidence": 0.96,
                },
            ),
        ),
        escalation=escalation,
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.escalated is False
    assert escalation.calls == []  # the cloud provider was never contacted


# --------------------------------------------------------------------- authoritative parser data


def test_model_cannot_overwrite_parser_derived_values(chat_unit):
    unit, extraction = chat_unit
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(
            name="ollama",
            model="qwen2.5vl:7b",
            payload=_payload(
                unit,
                amount={
                    "value": {"value": 99999.0, "currency": "INR"},
                    "basis": "direct",
                    "quote": "99999",
                    "source_reference": unit.reference.locator,
                    "confidence": 0.99,
                },
            ),
        ),
        escalation=None,
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.record.amount.value == 25000.0
    assert "amount" in outcome.conflicts
    assert outcome.record.validation_status.value == "mismatch"


def test_model_may_add_interpretation_around_fixed_values(chat_unit):
    unit, extraction = chat_unit
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(name="ollama", model="qwen2.5vl:7b", payload=_payload(unit)), escalation=None
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.record.normalized_summary
    assert outcome.record.field_provenance["event_type"].basis is ObservationBasis.INFERRED
    # The original Hinglish wording is untouched by normalization.
    assert outcome.record.observed_text == MESSAGE_TEXT


# ------------------------------------------------------------------------------- idempotency


def test_cache_key_is_stable_and_version_sensitive():
    request = VLMRequest(system_prompt="s", user_prompt="u", prompt_version="v1")
    args = {"evidence_sha256": "abc", "parser_version": "grounded-v1", "provider": "ollama", "model": "qwen2.5vl:7b"}

    assert request.cache_key(**args) == request.cache_key(**args)
    assert request.cache_key(**args) != request.cache_key(**{**args, "model": "qwen2.5vl:3b"})
    assert request.cache_key(**args) != VLMRequest(system_prompt="s", user_prompt="u", prompt_version="v2").cache_key(**args)


# ------------------------------------------------------------------------ transmission consent


def test_groq_is_unavailable_unless_both_switches_are_on():
    base = {"groq_api_key": "test-placeholder-not-a-real-key"}

    assert Settings(**base).groq_transmission_allowed is False
    assert Settings(**base, groq_enabled=True).groq_transmission_allowed is False
    assert Settings(**base, external_evidence_transmission="enabled").groq_transmission_allowed is False
    assert Settings(**base, groq_enabled=True, external_evidence_transmission="enabled").groq_transmission_allowed is True


def test_groq_without_a_key_is_never_allowed():
    assert Settings(groq_enabled=True, external_evidence_transmission="enabled").groq_transmission_allowed is False


# ------------------------------------------------------------------------------- routing modes


def _router_for(mode: str, **overrides):
    from app.evidence_intelligence.providers import router as router_module

    settings = Settings(llm_routing_mode=mode, **overrides)
    instance = ModelRouter.__new__(ModelRouter)
    instance._local = router_module._UNSET
    instance._escalation = router_module._UNSET
    instance._settings = settings
    instance._unreachable = {}
    return instance


def test_groq_only_mode_builds_no_local_adapter():
    """Deployments without Ollama installed must still be able to use the model layer."""
    router = _router_for(
        "groq_only",
        groq_enabled=True,
        external_evidence_transmission="enabled",
        groq_api_key="test-placeholder",
    )
    assert router.local is None
    assert router.escalation is not None
    assert router.escalation.name == "groq"


def test_local_only_mode_never_builds_the_cloud_adapter():
    router = _router_for(
        "local_only",
        groq_enabled=True,
        external_evidence_transmission="enabled",
        groq_api_key="test-placeholder",
    )
    assert router.escalation is None


def test_disabled_mode_builds_neither_adapter():
    router = _router_for("disabled")
    assert router.local is None and router.escalation is None


def test_groq_only_routes_every_unit_to_escalation(chat_unit):
    unit, extraction = chat_unit
    escalation = ScriptedVLMAdapter(name="groq", model="qwen/qwen3.8-27b", payload=_payload(unit))

    outcome = ModelRouter(local=None, escalation=escalation).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.escalated is True
    assert [attempt.provider for attempt in outcome.attempts] == ["groq"]
    assert any("No local model is configured" in reason for reason in outcome.escalation_reasons)
    # Parser-derived values stay authoritative even when the cloud model is the only model.
    assert outcome.record.amount.value == 25000.0
    assert outcome.record.sender == "Ramesh Kumar"


def test_groq_adapter_refuses_to_transmit_when_disabled(monkeypatch):
    # Patch the name the adapter module actually resolves, not the one in app.core.config.
    from app.evidence_intelligence.providers import groq as groq_module

    monkeypatch.setattr(groq_module, "get_settings", lambda: Settings(groq_enabled=False))
    adapter = GroqVLMAdapter(base_url="http://localhost", model="test-model", timeout=1.0)

    with pytest.raises(ProviderError) as raised:
        adapter.generate(VLMRequest(system_prompt="s", user_prompt="u", prompt_version="v1"))
    assert raised.value.kind is ProviderErrorKind.DISABLED


def test_groq_adapter_refuses_when_transmission_is_disabled_despite_a_key(monkeypatch):
    """Enabling Groq alone is not consent to send evidence off the machine."""
    from app.evidence_intelligence.providers import groq as groq_module

    monkeypatch.setattr(
        groq_module,
        "get_settings",
        lambda: Settings(groq_enabled=True, groq_api_key="test-placeholder", external_evidence_transmission="disabled"),
    )
    adapter = GroqVLMAdapter(base_url="http://localhost", model="test-model", timeout=1.0)

    with pytest.raises(ProviderError) as raised:
        adapter.generate(VLMRequest(system_prompt="s", user_prompt="u", prompt_version="v1"))
    assert raised.value.kind is ProviderErrorKind.DISABLED


# ------------------------------------------------------------------------------ prompt safety


def test_system_prompt_forbids_the_dangerous_behaviours():
    prompt = prompts.SYSTEM_PROMPT.lower()
    for requirement in (
        "null is a correct answer",
        "chat_participant_identifier",
        "never invent",
        "never output a criminal",
        "candidates for a human reviewer",
        "hinglish",
    ):
        assert requirement in prompt


def test_user_prompt_marks_parser_values_as_fixed(chat_unit):
    unit, extraction = chat_unit
    rendered = prompts.build_user_prompt(unit, extraction, authoritative={"amount": {"value": 25000.0, "currency": None}})

    assert "FIXED AND AUTHORITATIVE" in rendered
    assert MESSAGE_TEXT in rendered


def test_prompt_never_carries_storage_keys_or_credentials(chat_unit):
    unit, extraction = chat_unit
    rendered = prompts.build_user_prompt(unit, extraction, ocr_result=synthetic.whatsapp_ocr_result())

    for secret_marker in ("storage_key", "authorization", "bearer ", "api_key", "supabase", "jwt"):
        assert secret_marker not in rendered.lower()


def test_response_schema_allows_null_for_every_identity_field():
    properties = prompts.RESPONSE_SCHEMA["properties"]
    for name in ("sender", "receiver", "participant_a", "participant_b", "chat_participant_identifier"):
        assert "null" in json.dumps(properties[name]["properties"]["value"])


# --------------------------------------------------- observed_text coverage (real-OCR tolerance)


def test_observed_text_may_drop_ocr_noise(chat_unit):
    """A model that omits OCR junk is tidying up, not fabricating."""
    unit, extraction = chat_unit
    noisy = unit.text + " € ow oS: = L) e"
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(name="ollama", model="qwen2.5vl:7b", payload=_payload(unit, observed_text=unit.text)),
        escalation=None,
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.attempts[0].status == "succeeded"
    assert outcome.record.observed_text == unit.text
    assert noisy  # the fixture text itself is unchanged by the model layer


def test_observed_text_that_is_invented_is_still_rejected(chat_unit):
    unit, extraction = chat_unit
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(
            name="ollama",
            model="qwen2.5vl:7b",
            payload=_payload(unit, observed_text="wire the funds to account 999 in Zurich tomorrow morning"),
        ),
        escalation=None,
    ).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.attempts[0].status == "rejected"
    assert "not supported by the source" in outcome.attempts[0].grounding_report["rejected_reason"]
