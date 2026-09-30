"""Deterministic extraction across every supported format.

This layer must keep working with no model provider reachable, so nothing here touches the router.
"""

from __future__ import annotations

from app.evidence_intelligence import patterns
from app.evidence_intelligence.detection import ContentFileTypeDetector
from app.evidence_intelligence.extraction import DeterministicExtractor
from app.evidence_intelligence.schema import ObservationBasis, SourceType
from tests.fixtures import synthetic

detector = ContentFileTypeDetector()
extractor = DeterministicExtractor()


def _run(path, category, evidence_id="ev-1"):
    detected = detector.detect(path, declared_category=category)
    return detected, extractor.extract(path, evidence_id=evidence_id, detected=detected)


# ------------------------------------------------------------------------------ identifiers


def test_amount_ignores_digits_belonging_to_identifiers():
    # The digits inside a UTR are not a rupee value.
    assert patterns.find_amount("UTR: HDFC0012345678 confirm karo") is None
    assert patterns.find_amount("Tue, 12 Mar 2024 21:15:00 +0530") is None
    assert patterns.find_amount("call 9876543210 now") is None


def test_amount_requires_a_currency_marker_for_small_numbers():
    assert patterns.find_amount("send 25 now") is None
    value, currency, quote = patterns.find_amount("send Rs 25 now")
    assert (value, currency, quote.strip()) == (25.0, "INR", "Rs 25")


def test_bare_large_number_is_an_amount_without_assuming_currency():
    value, currency, _ = patterns.find_amount("bhai is number pe 25000 bhej de")
    assert value == 25000.0
    assert currency is None


def test_currency_is_recorded_when_the_source_states_it():
    assert patterns.find_amount("₹25,000 bhejo")[1] == "INR"
    assert patterns.find_amount("USD 400 transferred")[1] == "USD"


# ------------------------------------------------------------------------------- chat export


def test_chat_export_parses_timestamp_sender_and_boundaries(tmp_path):
    path = synthetic.whatsapp_chat_export(tmp_path / "chat.txt")
    detected, extraction = _run(path, "chat_export")

    assert detected.source_type is SourceType.CHAT_EXPORT
    messages = [unit for unit in extraction.units if unit.kind == "chat_message"]
    assert len(messages) == 4

    first = messages[0]
    assert first.text == "bhai is number pe 25000 bhej de"
    assert first.facts["sender"].value == "Ramesh Kumar"
    assert first.facts["sender"].basis is ObservationBasis.DIRECT
    assert first.facts["event_time"].value.startswith("2024-03-12T21:16")
    assert first.reference.kind == "chat_message"
    assert first.reference.message_index == 1


def test_chat_export_receiver_is_never_invented(tmp_path):
    path = synthetic.whatsapp_chat_export(tmp_path / "chat.txt")
    _, extraction = _run(path, "chat_export")

    for unit in extraction.units:
        assert unit.facts["receiver"].value is None
        assert unit.facts["receiver"].basis is ObservationBasis.UNKNOWN


def test_media_omitted_is_recorded_as_unknown_content(tmp_path):
    path = synthetic.whatsapp_chat_export(tmp_path / "chat.txt")
    _, extraction = _run(path, "chat_export")

    media = next(unit for unit in extraction.units if "Media omitted" in unit.text)
    assert media.facts["media_content"].value is None
    assert media.facts["media_content"].basis is ObservationBasis.UNKNOWN
    assert media.layout["is_media_placeholder"] is True


def test_chat_without_timestamps_yields_no_false_times(tmp_path):
    path = synthetic.chat_export_without_timestamps(tmp_path / "chat.txt")
    _, extraction = _run(path, "chat_export")

    for unit in extraction.units:
        assert "event_time" not in unit.facts or unit.facts["event_time"].value is None


def test_utr_in_chat_is_captured_as_a_transaction_reference(tmp_path):
    path = synthetic.whatsapp_chat_export(tmp_path / "chat.txt")
    _, extraction = _run(path, "chat_export")

    unit = next(unit for unit in extraction.units if synthetic.SYNTHETIC_UTR in unit.text)
    assert unit.facts["transaction_reference"].value == synthetic.SYNTHETIC_UTR


# ------------------------------------------------------------------------------------ email


def test_email_headers_are_parsed_deterministically(tmp_path):
    path = synthetic.phishing_email(tmp_path / "mail.eml")
    detected, extraction = _run(path, "phishing_email")

    assert detected.source_type is SourceType.EMAIL
    unit = extraction.units[0]
    headers = unit.layout["headers"]
    for name in ("From", "To", "Cc", "Reply-To", "Subject", "Date", "Message-ID"):
        assert name in headers

    assert unit.facts["sender"].value == "payments@example-bank.test"
    assert unit.facts["receiver"].value == "victim@example.test"
    assert unit.facts["sender"].source_reference["header_name"] == "From"
    assert unit.facts["event_time"].value.startswith("2024-03-12T15:45")


def test_email_message_id_is_not_treated_as_a_correspondent(tmp_path):
    path = synthetic.phishing_email(tmp_path / "mail.eml")
    _, extraction = _run(path, "phishing_email")

    addresses = extraction.units[0].facts["email_addresses"].value
    assert "synthetic-001@example.test" not in addresses


def test_email_amount_comes_from_the_body_not_the_date(tmp_path):
    path = synthetic.phishing_email(tmp_path / "mail.eml")
    _, extraction = _run(path, "phishing_email")

    amount = extraction.units[0].facts["amount"].value
    # The figure first appears in "Subject: Urgent: pending payment of Rs 25000". "Payment" does not
    # say whether money moved or is being demanded, so the role stays unknown rather than guessing.
    assert amount == {"value": 25000.0, "currency": "INR", "role": "unknown"}
    # The body line, read on its own, is unambiguous — the classifier is reading the right line.
    assert patterns.classify_amount_role("Please transfer Rs 25000 to account 123456789012", "Rs 25000") == "request"


# --------------------------------------------------------------------------- tabular evidence


def test_bank_csv_maps_columns_and_keeps_row_provenance(tmp_path):
    path = synthetic.bank_statement_csv(tmp_path / "bank.csv")
    detected, extraction = _run(path, "bank_statement")

    assert detected.source_type is SourceType.BANK_RECORD
    mapping = extraction.layer("structured").payload["column_mapping"]
    assert mapping["amount"] == "Amount"
    assert mapping["transaction_reference"] == "Reference"

    first = extraction.units[0]
    assert first.facts["amount"].value["value"] == 25000.0
    assert first.facts["amount"].source_reference["row"] == 2
    assert first.facts["amount"].source_reference["column"] == "Amount"
    assert first.facts["transaction_reference"].value == synthetic.SYNTHETIC_UTR


def test_bank_csv_leaves_sender_unestablished(tmp_path):
    path = synthetic.bank_statement_csv(tmp_path / "bank.csv")
    _, extraction = _run(path, "bank_statement")

    sender = extraction.units[0].facts["sender"]
    assert sender.value is None
    assert "No column" in sender.reason


def test_call_log_is_detected_and_phone_numbers_preserved(tmp_path):
    path = synthetic.call_log_csv(tmp_path / "calls.csv")
    detected, extraction = _run(path, "call_log")

    assert detected.source_type is SourceType.CALL_LOG
    numbers = extraction.units[0].facts["phone_numbers"].value
    assert "+91" + synthetic.SYNTHETIC_BENEFICIARY_NUMBER in numbers


# ---------------------------------------------------------------------------------- documents


def test_native_pdf_uses_text_extraction_and_records_pages(tmp_path):
    path = synthetic.native_text_pdf(tmp_path / "statement.pdf")
    detected, extraction = _run(path, "complaint")

    assert detected.source_type is SourceType.PDF
    pages = extraction.layer("native_text").payload["pages"]
    assert pages[0]["method"] == "native"
    assert extraction.layer("ocr") is None

    unit = next(unit for unit in extraction.units if synthetic.SYNTHETIC_UTR in unit.text)
    assert unit.reference.page == 1
    assert unit.facts["transaction_reference"].value == synthetic.SYNTHETIC_UTR


def test_scanned_pdf_falls_back_to_page_wise_ocr(tmp_path):
    path = synthetic.scanned_pdf(tmp_path / "scan.pdf")
    detected = detector.detect(path, declared_category="document")
    scanned_extractor = DeterministicExtractor(ocr_adapter=synthetic.FakeOCRAdapter())
    extraction = scanned_extractor.extract(path, evidence_id="ev-pdf", detected=detected)

    pages = extraction.layer("native_text").payload["pages"]
    assert pages[0]["method"] == "ocr"
    assert extraction.layer("ocr") is not None
    assert all(unit.reference.page == 1 for unit in extraction.units)


# ------------------------------------------------------------------------------------- image


def test_image_metadata_is_a_separate_layer_and_absence_is_not_suspicious(tmp_path):
    path = synthetic.whatsapp_screenshot(tmp_path / "chat.png")
    detected = detector.detect(path, declared_category="whatsapp_screenshot")
    extraction = DeterministicExtractor(ocr_adapter=synthetic.FakeOCRAdapter()).extract(
        path, evidence_id="ev-img", detected=detected
    )

    metadata = extraction.layer("file_metadata").payload
    assert metadata["width"] == synthetic.CANVAS_WIDTH
    assert "not evidence of tampering" in metadata["note"]
    # OCR, layout and metadata stay in separate layers.
    assert {layer.layer for layer in extraction.layers} == {"ocr", "layout", "file_metadata"}


def test_plain_image_category_is_not_upgraded_to_screenshot(tmp_path):
    path = synthetic.whatsapp_screenshot(tmp_path / "photo.png")
    detected = detector.detect(path, declared_category="photograph")
    assert detected.source_type is SourceType.IMAGE


def test_ocr_garbled_phone_is_not_read_as_an_amount():
    """OCR turns "+91 87072 93840" into "+9] 87072 93840"; the middle group is not a rupee value."""
    assert patterns.find_amount("<€ +9] 87072 93840 OO & : 24 August 2025") is None
    assert patterns.find_amount("call 98765 43210 now") is None
    # Real amounts beside a phone number are still found.
    assert patterns.find_amount("Send INR 25,000 to invest.demo@upi")[0] == 25000.0
