"""The mandatory WhatsApp screenshot acceptance path.

Each test maps to one numbered expectation in the upgrade specification. Synthetic evidence only.
"""

from __future__ import annotations

import hashlib

import pytest

from app.evidence_intelligence.detection import ContentFileTypeDetector
from app.evidence_intelligence.extraction import DeterministicExtractor
from app.evidence_intelligence.providers.mock import ScriptedVLMAdapter
from app.evidence_intelligence.providers.router import ModelRouter
from app.evidence_intelligence.schema import ObservationBasis, SourceType
from tests.fixtures import synthetic

EVIDENCE_ID = "ev-screenshot-1"
MESSAGE_TEXT = "bhai is number pe 25000 bhej de"


def _extract(tmp_path, *, ocr_result=None, blurry=False, crop_header=False):
    path = synthetic.whatsapp_screenshot(tmp_path / "chat.png", blurry=blurry, crop_header=crop_header)
    detected = ContentFileTypeDetector().detect(path, declared_category="whatsapp_screenshot")
    extractor = DeterministicExtractor(
        ocr_adapter=synthetic.FakeOCRAdapter(
            ocr_result or synthetic.whatsapp_ocr_result(header=not crop_header, blurry=blurry)
        )
    )
    return path, extractor.extract(path, evidence_id=EVIDENCE_ID, detected=detected)


def _message_unit(extraction):
    """An image yields exactly one record; splitting it per OCR line destroys the context."""
    assert len(extraction.units) == 1, f"expected one record per image, got {len(extraction.units)}"
    return extraction.units[0]


def _layout_messages(extraction):
    return extraction.layer("layout").payload["messages"]


def test_screenshot_is_detected_as_a_screenshot(tmp_path):
    _, extraction = _extract(tmp_path)
    assert extraction.source_type is SourceType.SCREENSHOT


def test_1_exact_visible_text_is_preserved(tmp_path):
    _, extraction = _extract(tmp_path)
    unit = _message_unit(extraction)
    # Hinglish wording, spelling and spacing survive untouched inside the full-image text.
    assert MESSAGE_TEXT in unit.text
    assert "theek hai bhej raha hu" in unit.text


def test_2_ocr_block_and_image_region_references_are_present(tmp_path):
    _, extraction = _extract(tmp_path)
    unit = _message_unit(extraction)

    # The record addresses the whole image ...
    assert unit.reference.kind == "image_region"
    assert unit.reference.bbox is not None and len(unit.reference.bbox) == 4

    # ... while each extracted value still cites the exact OCR block it was read from.
    amount = unit.facts["amount"]
    assert amount.source_reference["ocr_block_id"]
    assert amount.source_reference["bbox"] is not None
    assert amount.source_reference["kind"] == "ocr_block"


def test_3_header_number_is_only_a_chat_participant_identifier(tmp_path):
    _, extraction = _extract(tmp_path)
    unit = _message_unit(extraction)

    identifier = unit.facts["chat_participant_identifier"]
    assert identifier.value == synthetic.SYNTHETIC_HEADER_NUMBER
    assert identifier.basis is ObservationBasis.DIRECT
    # The header proves who the conversation is with, never who sent this message.
    assert unit.facts["sender"].value is None
    assert unit.facts["receiver"].value is None


def test_4_amount_is_extracted_and_grounded(tmp_path):
    _, extraction = _extract(tmp_path)
    amount = _message_unit(extraction).facts["amount"]

    assert amount.value["value"] == 25000.0
    assert amount.basis is ObservationBasis.DIRECT
    assert amount.quote in MESSAGE_TEXT
    # No currency symbol is visible, so currency stays unstated rather than assumed to be INR.
    assert amount.value["currency"] is None


def test_5_payment_intent_is_inferred_not_asserted(tmp_path):
    _, extraction = _extract(tmp_path)
    unit = _message_unit(extraction)

    model_payload = {
        "observed_text": MESSAGE_TEXT,
        "normalized_summary": "Asks the recipient to send 25000 to a number that is not shown.",
        "observation_basis": "inferred",
        "event_type": {
            "value": "possible_payment_request",
            "basis": "inferred",
            "quote": MESSAGE_TEXT,
            "source_reference": unit.reference.locator,
            "confidence": 0.78,
        },
        "model_confidence": 0.8,
        "requires_human_review": True,
    }
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(name="ollama", model="qwen2.5vl:7b", payload=model_payload),
        escalation=None,
    ).normalize(unit, extraction, evidence_sha256="hash", ocr_result=synthetic.whatsapp_ocr_result())

    assert outcome.record.event_type == "possible_payment_request"
    assert outcome.record.field_provenance["event_type"].basis is ObservationBasis.INFERRED
    assert outcome.record.observation_basis is ObservationBasis.INFERRED


def test_6_missing_sender_and_receiver_stay_null(tmp_path):
    _, extraction = _extract(tmp_path)
    unit = _message_unit(extraction)

    # The model tries to name a sender that never appears in the source.
    outcome = ModelRouter(
        local=ScriptedVLMAdapter(
            name="ollama",
            model="qwen2.5vl:7b",
            payload={
                "observed_text": MESSAGE_TEXT,
                "observation_basis": "inferred",
                "sender": {"value": "Amit Sharma", "basis": "direct", "quote": "Amit Sharma", "confidence": 0.9},
                "receiver": {"value": synthetic.SYNTHETIC_BENEFICIARY_NUMBER, "basis": "direct", "quote": "9876500011", "confidence": 0.9},
                "requires_human_review": False,
            },
        ),
        escalation=None,
    ).normalize(unit, extraction, evidence_sha256="hash", ocr_result=synthetic.whatsapp_ocr_result())

    assert outcome.record.sender is None
    assert outcome.record.receiver is None
    report = outcome.attempts[0].grounding_report
    assert "sender" in report["ungrounded"] and "receiver" in report["ungrounded"]


def test_7_per_message_direction_is_measured_from_the_layout(tmp_path):
    _, clear = _extract(tmp_path)
    directions = {message["direction"] for message in _layout_messages(clear)}

    # The left-hugging bubble reads as incoming, the right-hugging one as outgoing.
    assert "incoming" in directions and "outgoing" in directions
    for message in _layout_messages(clear):
        if message["direction"]:
            assert message["direction_basis"] == "direct_visual"


def test_7b_centred_bubble_leaves_direction_unresolved(tmp_path):
    _, ambiguous = _extract(tmp_path, ocr_result=synthetic.whatsapp_ocr_result(ambiguous_direction=True))
    centred = [m for m in _layout_messages(ambiguous) if m["text"].startswith("bhai")]

    assert centred and centred[0]["direction"] is None
    assert centred[0]["direction_basis"] == "unknown"


def test_7c_image_level_direction_is_unknown_when_sides_are_mixed(tmp_path):
    """A screenshot holding both an incoming and an outgoing bubble has no single direction."""
    _, extraction = _extract(tmp_path)
    direction = _message_unit(extraction).facts["message_direction"]

    assert direction.value is None
    assert direction.basis is ObservationBasis.UNKNOWN
    assert "both sides" in direction.reason


def test_8_degraded_source_forces_human_review(tmp_path):
    _, extraction = _extract(tmp_path, blurry=True)
    assert "blurry" in extraction.quality_flags

    unit = _message_unit(extraction)
    outcome = ModelRouter(local=None, escalation=None).normalize(unit, extraction, evidence_sha256="hash")

    assert outcome.record.requires_human_review is True
    assert "blurry" in outcome.record.review_reason


def test_8b_cropped_header_forces_review_and_leaves_identifier_null(tmp_path):
    _, extraction = _extract(tmp_path, crop_header=True)
    unit = _message_unit(extraction)

    assert "cropped" in extraction.quality_flags
    assert "chat_participant_identifier" not in unit.facts

    outcome = ModelRouter(local=None, escalation=None).normalize(unit, extraction, evidence_sha256="hash")
    assert outcome.record.requires_human_review is True


def test_9_model_disagreement_preserves_both_outputs_and_flags_conflict(tmp_path):
    _, extraction = _extract(tmp_path)
    unit = _message_unit(extraction)
    locator = unit.reference.locator

    local_payload = {
        "observed_text": MESSAGE_TEXT,
        "observation_basis": "inferred",
        "event_type": {"value": "possible_payment_request", "basis": "inferred", "quote": MESSAGE_TEXT, "source_reference": locator, "confidence": 0.8},
        "requires_human_review": True,
    }
    escalation_payload = {
        **local_payload,
        "event_type": {"value": "casual_greeting", "basis": "inferred", "quote": "bhai", "source_reference": locator, "confidence": 0.7},
    }

    outcome = ModelRouter(
        local=ScriptedVLMAdapter(name="ollama", model="qwen2.5vl:7b", payload=local_payload),
        escalation=ScriptedVLMAdapter(name="groq", model="qwen/qwen3.8-27b", payload=escalation_payload),
    ).normalize(unit, extraction, evidence_sha256="hash", ocr_result=synthetic.whatsapp_ocr_result(), force_escalation=True)

    assert "event_type" in outcome.conflicts
    assert outcome.record.requires_human_review is True
    assert outcome.record.validation_status.value == "mismatch"

    providers = {attempt.provider for attempt in outcome.attempts}
    assert providers == {"ollama", "groq"}
    # Neither reading is discarded; the reviewer sees both.
    assert all(attempt.raw_output for attempt in outcome.attempts)


def test_10_original_bytes_and_hash_are_untouched_by_processing(tmp_path):
    path, _ = _extract(tmp_path)
    before = path.read_bytes()
    digest_before = hashlib.sha256(before).hexdigest()

    # Run the full extraction and normalization a second time over the same file.
    _extract(tmp_path)

    after = path.read_bytes()
    assert after == before
    assert hashlib.sha256(after).hexdigest() == digest_before


@pytest.mark.skipif(not synthetic.tesseract_available(), reason="Tesseract executable is not installed in this environment")
def test_real_tesseract_reads_the_synthetic_screenshot(tmp_path):
    """Runs only where the OCR binary exists; the rest of the suite uses a scripted OCR adapter."""
    path = synthetic.whatsapp_screenshot(tmp_path / "chat.png")
    detected = ContentFileTypeDetector().detect(path, declared_category="whatsapp_screenshot")
    extraction = DeterministicExtractor().extract(path, evidence_id=EVIDENCE_ID, detected=detected)

    assert extraction.layer("ocr") is not None
    assert extraction.layer("ocr").payload["blocks"]

    # Real OCR garbles the surrounding Hinglish, so the unit is located by the digits rather than
    # by an exact string match. The amount must survive that imperfection.
    amounts = [unit.facts["amount"].value["value"] for unit in extraction.units if "amount" in unit.facts]
    assert 25000.0 in amounts


@pytest.mark.skipif(not synthetic.tesseract_available(), reason="Tesseract executable is not installed in this environment")
def test_real_tesseract_recovers_the_light_on_dark_header(tmp_path):
    """A WhatsApp header is white text on a dark bar — the normal case, not an edge case."""
    path = synthetic.whatsapp_screenshot(tmp_path / "chat.png")
    detected = ContentFileTypeDetector().detect(path, declared_category="whatsapp_screenshot")
    extraction = DeterministicExtractor().extract(path, evidence_id=EVIDENCE_ID, detected=detected)

    layout = extraction.layer("layout").payload
    assert layout["header_identifier"], "header band was not recovered from the dark bar"
    # A present header must not be reported as a cropped source.
    assert "cropped" not in extraction.quality_flags


@pytest.mark.skipif(not synthetic.tesseract_available(), reason="Tesseract executable is not installed in this environment")
def test_real_tesseract_resolves_both_bubble_directions(tmp_path):
    """OCR returns the text extent, not the bubble; direction must still resolve for short messages."""
    path = synthetic.whatsapp_screenshot(tmp_path / "chat.png")
    detected = ContentFileTypeDetector().detect(path, declared_category="whatsapp_screenshot")
    extraction = DeterministicExtractor().extract(path, evidence_id=EVIDENCE_ID, detected=detected)

    directions = [message["direction"] for message in extraction.layer("layout").payload["messages"]]
    assert "incoming" in directions and "outgoing" in directions
