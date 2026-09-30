"""Versioned prompts and the strict JSON contract handed to any model.

The prompt version is stored on every record. Changing the wording below requires bumping
`PROMPT_VERSION`, otherwise cached results from the old wording would be reused silently.
"""

from __future__ import annotations

import json
from typing import Any

from app.evidence_intelligence.extraction import ExtractionUnit, RawExtraction
from app.evidence_intelligence.ocr import OCRResult

PROMPT_VERSION = "grounded-normalize-v4"

SYSTEM_PROMPT = """You are a forensic evidence normalizer for an investigation platform.
You describe what a piece of evidence shows. You never decide what it means legally.

ABSOLUTE RULES

1. Use only details present in the material you are given. If something is not in the source, it
   does not exist for you.
2. Preserve the original wording exactly in `observed_text`, including Hindi, English, Roman
   Hinglish, abbreviations, spelling mistakes, slang and emojis. Never translate, correct or clean
   it. Put interpretation in `normalized_summary` instead.
3. Every non-null material field must carry a `quote` copied character-for-character from the
   source, plus the `source_reference` id you were given for that region, row, line or block.
4. Use null for sender, receiver, beneficiary, identity, amount, timestamp or location that the
   source does not establish. Never fill a gap with a plausible guess. null is a correct answer.
5. A phone number or name in a chat header identifies the conversation, not a message role. Put it
   in `chat_participant_identifier`. Never promote it to `sender` or `receiver` unless the source
   directly shows that role.
6. Message meaning and intent are `inferred` unless an explicit structured field states them. A
   request for money is at most `possible_payment_request`, marked inferred.
7. Never invent hidden media, cropped-off text, unseen numbers, identities, locations or
   relationships. If a message references something not visible, that thing stays null.
8. Never output a criminal, fraudulent, guilty, culprit, or legal conclusion, and never assign
   responsibility. Describe the observation only.
9. Corroboration and contradiction are candidates for a human reviewer, never settled findings.
10. Set `requires_human_review` to true whenever identity, role, beneficiary, amount or timing is
    unresolved, ambiguous, or the source is blurry, cropped or incomplete.
11. For a handwritten or degraded value, set `readability` and copy the characters exactly into
    `literal_transcription` BEFORE any normalising:
    - "readable": the text is visible and the transcription is reliable.
    - "partially_readable": some characters are uncertain. Keep every visible character in
      `literal_transcription`, leave `value` null, and set needs_review. Never complete a partial
      number into a whole one: "98?7?2" stays "98?7?2" and never becomes a phone number.
    - "unreadable": return null and say why in `reason`.
12. Transcribe before you interpret. Read the characters that are actually printed first, then fill
    the structured fields from that transcription. Reading straight into categories makes it easy
    to call a value unreadable that a plain transcription recovers without difficulty.
13. Record the entity classes below only where the source writes them down. Each is a list of the
    exact strings visible in the source; leave the list empty when the source shows none.
    - `vehicle_identifiers`: registration plates, exactly as printed.
    - `organisation_names`: companies, banks, firms, agencies, departments.
    - `person_names`: a name the source attaches to a stated role (complainant, accused, sender,
      beneficiary, driver, owner). A capitalised word is not a name. A place is not a person.
    - `location_names`: places the source names as places -- a police station, district, village,
      road, area or landmark.
    None of these establishes identity. The same name in two sources is a lead for a reviewer to
    check, never a confirmed match, and you must not merge, correct or complete any of them.

`basis` values: "direct" for text plainly readable in the source, "direct_visual" for a fact the
layout itself shows (such as a bubble sitting on one side), "inferred" for contextual reading, and
"unknown" when the source does not establish it.

SHAPE — every material field is an OBJECT, never a bare value. Copy this shape exactly:

{
  "observed_text": "<source text, verbatim>",
  "normalized_summary": "<what it means, in plain English>",
  "observation_basis": "inferred",
  "event_type": {"value": "possible_payment_request", "basis": "inferred",
                 "quote": "<exact words that suggest it>", "source_reference": "<id you were given>",
                 "confidence": 0.7},
  "amount": {"value": {"value": 25000, "currency": null}, "basis": "direct",
             "quote": "25000", "source_reference": "<id>", "confidence": 0.95},
  "chat_participant_identifier": {"value": "+910000000000", "basis": "direct",
                                  "quote": "+910000000000", "source_reference": "<id>",
                                  "confidence": 0.9},
  "sender": {"value": null, "basis": "unknown",
             "reason": "The account identity is not visible in this source."},
  "receiver": {"value": null, "basis": "unknown",
               "reason": "No recipient is shown."},
  "phone_numbers": [], "email_addresses": [], "account_identifiers": [],
  "vehicle_identifiers": [], "organisation_names": [],
  "person_names": [], "location_names": [],
  "model_confidence": 0.8,
  "requires_human_review": true,
  "review_reason": "<why a person should check this>"
}

`observed_text`, `normalized_summary`, the three list fields, `model_confidence`,
`requires_human_review` and `review_reason` are plain values. Everything else is the object shape
above. Write each key at most once.

Return one JSON object. No prose, no markdown fence."""


def _field_schema(value_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value": value_schema,
            "basis": {"type": "string", "enum": ["direct", "direct_visual", "inferred", "unknown"]},
            "quote": {"type": ["string", "null"]},
            "source_reference": {"type": ["string", "null"]},
            "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "reason": {"type": ["string", "null"]},
            "readability": {"type": ["string", "null"], "enum": ["readable", "partially_readable", "unreadable", "not_applicable", None]},
            "literal_transcription": {"type": ["string", "null"]},
        },
        "required": ["value", "basis"],
    }


_NULLABLE_STRING = {"type": ["string", "null"]}

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "observed_text": _NULLABLE_STRING,
        "normalized_summary": _NULLABLE_STRING,
        "event_type": _field_schema(_NULLABLE_STRING),
        "event_time": _field_schema(_NULLABLE_STRING),
        "event_time_precision": {"type": "string", "enum": ["exact", "date_only", "approximate", "inferred", "unknown"]},
        "participant_a": _field_schema(_NULLABLE_STRING),
        "participant_b": _field_schema(_NULLABLE_STRING),
        "sender": _field_schema(_NULLABLE_STRING),
        "receiver": _field_schema(_NULLABLE_STRING),
        "message_direction": _field_schema({"type": ["string", "null"], "enum": ["incoming", "outgoing", "unknown", None]}),
        "chat_participant_identifier": _field_schema(_NULLABLE_STRING),
        "phone_numbers": {"type": "array", "items": {"type": "string"}},
        "email_addresses": {"type": "array", "items": {"type": "string"}},
        "account_identifiers": {"type": "array", "items": {"type": "string"}},
        "vehicle_identifiers": {"type": "array", "items": {"type": "string"}},
        "organisation_names": {"type": "array", "items": {"type": "string"}},
        "person_names": {"type": "array", "items": {"type": "string"}},
        "location_names": {"type": "array", "items": {"type": "string"}},
        "transaction_reference": _field_schema(_NULLABLE_STRING),
        "amount": _field_schema(
            {
                "type": ["object", "null"],
                "additionalProperties": False,
                "properties": {"value": {"type": ["number", "null"]}, "currency": _NULLABLE_STRING},
            }
        ),
        "location": _field_schema(_NULLABLE_STRING),
        "device_identifier": _field_schema(_NULLABLE_STRING),
        "observation_basis": {"type": "string", "enum": ["direct", "direct_visual", "inferred", "unknown"]},
        "model_confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "requires_human_review": {"type": "boolean"},
        "review_reason": _NULLABLE_STRING,
    },
    "required": ["observed_text", "observation_basis", "requires_human_review"],
}


def build_user_prompt(
    unit: ExtractionUnit,
    extraction: RawExtraction,
    *,
    ocr_result: OCRResult | None = None,
    authoritative: dict[str, Any] | None = None,
) -> str:
    """Assemble the grounding material for one extraction unit.

    Deterministic parser values are shown as immutable so the model normalizes around them instead
    of contradicting them.
    """
    sections: list[str] = [
        f"SOURCE TYPE: {extraction.source_type.value}",
        f"SOURCE REFERENCE ID FOR THIS UNIT: {unit.reference.locator}",
        "",
        "EXACT SOURCE TEXT (reproduce verbatim in observed_text):",
        unit.text or "(no text recovered)",
    ]

    if unit.layout:
        sections += ["", "LAYOUT OBSERVATIONS (geometry only, already measured):", json.dumps(unit.layout, ensure_ascii=False)]

    if ocr_result and ocr_result.blocks:
        readable = [
            {"source_reference": block.reference(unit.reference.evidence_id).locator, "text": block.text, "bbox": [round(v) for v in block.bbox]}
            for block in ocr_result.blocks[:60]
        ]
        sections += ["", "OCR BLOCKS AVAILABLE FOR CITATION (cite these ids only):", json.dumps(readable, ensure_ascii=False)]

    if authoritative:
        sections += [
            "",
            "DETERMINISTIC PARSER VALUES — THESE ARE FIXED AND AUTHORITATIVE.",
            "Do not contradict, re-derive or 'correct' them. Leave the matching fields as given.",
            json.dumps(authoritative, ensure_ascii=False, default=str),
        ]

    if extraction.quality_flags:
        sections += [
            "",
            f"SOURCE QUALITY FLAGS: {', '.join(extraction.quality_flags)}",
            "Degraded sources require requires_human_review = true.",
        ]

    sections += ["", "Return the JSON object now."]
    return "\n".join(sections)
