"""Deterministic, format-specific extraction.

This layer is mandatory and must keep working when every model provider is down. Anything it
produces with `basis=direct` is **authoritative**: the model layer may add interpretation around it
but may never overwrite it.
"""

from __future__ import annotations

import email
import logging
import re
from dataclasses import dataclass, field
from email import policy
from pathlib import Path
from typing import Any, Protocol

from app.evidence_intelligence import patterns
from app.evidence_intelligence.detection import DetectedType
from app.evidence_intelligence.ocr import (
    ChatScreenshotLayoutAdapter,
    OCRResult,
    TesseractOCRAdapter,
)
from app.evidence_intelligence.references import SourceReference
from app.evidence_intelligence.schema import (
    RAW_EXTRACTION_VERSION,
    FieldProvenance,
    ObservationBasis,
    SourceType,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

NATIVE_EXTRACTOR_VERSION = "native-extract-v1"
PDF_NATIVE_TEXT_FLOOR = 20

CHAT_MESSAGE_PATTERN = re.compile(
    r"^\[?(?P<timestamp>\d{1,2}[/-]\d{1,2}[/-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s?(?:[AaPp]\.?[Mm]\.?)?)\]?"
    r"\s*[-–]?\s*(?P<sender>[^:]{1,60}?):\s?(?P<body>.*)$"
)
CHAT_SYSTEM_PATTERN = re.compile(
    r"^\[?(?P<timestamp>\d{1,2}[/-]\d{1,2}[/-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s?(?:[AaPp]\.?[Mm]\.?)?)\]?"
    r"\s*[-–]?\s*(?P<body>.+)$"
)
MEDIA_OMITTED_PATTERN = re.compile(r"<\s*(?:media|image|video|audio|sticker|document)\s+omitted\s*>", re.IGNORECASE)

AUTHORITATIVE_FIELDS = frozenset(
    {
        "amount",
        "event_time",
        "transaction_reference",
        "account_identifiers",
        "phone_numbers",
        "email_addresses",
        "device_identifier",
        "sender",
        "receiver",
        "message_direction",
        "chat_participant_identifier",
    }
)

# Narrative sources whose text carries report structure and stated roles.
REPORT_SOURCE_TYPES = frozenset({SourceType.FIR, SourceType.POLICE_REPORT, SourceType.SURVEILLANCE})

BANK_COLUMN_ALIASES = {
    "amount": ("amount", "txn amount", "transaction amount", "value", "credit", "debit"),
    "transaction_reference": ("utr", "reference", "reference id", "reference_no", "transaction id", "txn id", "rrn"),
    "event_time": ("date", "timestamp", "txn date", "transaction date", "value date", "time"),
    "sender": ("sender", "from", "payer", "remitter", "debit account"),
    "receiver": ("receiver", "to", "beneficiary", "payee", "credit account"),
    "account_identifiers": ("account", "account no", "account number", "a/c", "ifsc", "upi", "upi id"),
    "narration": ("narration", "particulars", "description", "remarks", "purpose"),
}
# A CDR names the two ends of a call in separate columns. Reading them into one list, as this map
# previously did, threw away who dialled -- so a call log could only ever produce a symmetric
# "these two were in contact" edge. Mapping the A-party and B-party onto the stated-role fields is
# what lets a directed CALLED relationship exist at all.
CALL_LOG_COLUMN_ALIASES = {
    "sender": ("a-party", "a party", "aparty", "caller", "calling number", "calling party", "from", "originating number", "msisdn_a", "a_number"),
    "receiver": ("b-party", "b party", "bparty", "callee", "called number", "called party", "to", "terminating number", "msisdn_b", "b_number"),
    # Kept for logs that print one bare number column and leave the roles unstated.
    "phone_numbers": ("number", "phone", "contact", "msisdn"),
    "event_time": ("date", "time", "timestamp", "call date", "start time", "call start"),
    "message_direction": ("direction", "call type", "call_type", "type"),
    "duration": ("duration", "call duration", "seconds", "duration_seconds"),
    "device_identifier": ("imei", "device", "device id", "imsi"),
    # A cell site is where the handset was, not a place name, so it stays an attribute of the event
    # rather than becoming a location node.
    "cell_site": ("cell id", "cell_id", "cell", "tower", "tower id", "site id", "lac", "cgi"),
}


@dataclass
class ExtractionUnit:
    """One atomic, separately reviewable observation drawn from the source."""

    unit_key: str
    kind: str
    text: str
    reference: SourceReference
    facts: dict[str, FieldProvenance] = field(default_factory=dict)
    layout: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_key": self.unit_key,
            "kind": self.kind,
            "text": self.text,
            "reference": self.reference.to_dict(),
            "facts": {name: provenance.model_dump(mode="json") for name, provenance in self.facts.items()},
            "layout": self.layout,
            "quality_flags": self.quality_flags,
        }


@dataclass
class ExtractionLayer:
    layer: str
    extractor: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"layer": self.layer, "extractor": self.extractor, "payload": self.payload}


@dataclass
class RawExtraction:
    source_type: SourceType
    text: str
    units: list[ExtractionUnit] = field(default_factory=list)
    layers: list[ExtractionLayer] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    version: str = RAW_EXTRACTION_VERSION
    extractor: str = NATIVE_EXTRACTOR_VERSION

    def layer(self, name: str) -> ExtractionLayer | None:
        return next((item for item in self.layers if item.layer == name), None)


class NativeExtractionAdapter(Protocol):
    def extract(self, path: Path, *, evidence_id: str, detected: DetectedType) -> RawExtraction: ...


def _direct(value: Any, *, quote: str, reference: SourceReference, confidence: float) -> FieldProvenance:
    return FieldProvenance.observed(value, quote=quote, reference=reference, confidence=confidence)


def _unknown(reason: str) -> FieldProvenance:
    return FieldProvenance.unestablished(reason)


_TIME_SPECIFICITY = {"exact": 3, "approximate": 2, "date_only": 1, "time_only": 0}


def _best_timestamp(ocr_result: OCRResult, evidence_id: str) -> tuple[dict, str] | None:
    """Pick the most specific timestamp on the page, not merely the first one OCR happened to read.

    A receipt prints "11:42 am on 02 Sep 2026" in one block and a bare date elsewhere; taking
    whichever block came first was how a 11:42 am payment became midnight. When the page states a
    date in one place and a clock in another, the two are combined and marked `approximate` — the
    day and the time are both observed, only their pairing is read off the layout.
    """
    dated: tuple[int, dict, str] | None = None
    clock: tuple[dict, str] | None = None

    for block in ocr_result.blocks:
        parsed, quote, precision = patterns.find_timestamp(block.text, context=ocr_result.text)
        if not quote:
            continue
        reference = block.reference(evidence_id)
        if parsed is None:
            if clock is None:
                clock = ({"value": None, "quote": quote, "reference": reference}, "time_only")
            continue
        rank = _TIME_SPECIFICITY.get(precision, 0)
        if dated is None or rank > dated[0]:
            dated = (rank, {"value": parsed, "quote": quote, "reference": reference}, precision)

    if dated is None:
        return (clock[0], clock[1]) if clock else None

    _, found, precision = dated
    if precision == "date_only" and clock is not None:
        combined = patterns.find_timestamp(f"{found['quote']} {clock[0]['quote']}")
        if combined[0] is not None:
            return (
                {
                    "value": combined[0],
                    "quote": f"{found['quote']} / {clock[0]['quote']}",
                    "reference": found["reference"],
                },
                "approximate",
            )
    return found, precision


def _block_scoped_facts(ocr_result: OCRResult, evidence_id: str) -> dict[str, FieldProvenance]:
    """Re-derive the scalar fields against individual OCR blocks.

    The record covers the whole image, but a reviewer needs to be shown the exact region a value
    came from — so the amount, timestamp and reference point at the block that actually contains
    them rather than at the full canvas.
    """
    facts: dict[str, FieldProvenance] = {}
    for block in ocr_result.blocks:
        reference = block.reference(evidence_id)

        if "amount" not in facts and (found := patterns.find_amount_detail(block.text)):
            value, currency, quote, role = found
            facts["amount"] = _direct(
                {"value": value, "currency": currency, "role": role},
                quote=quote,
                reference=reference,
                confidence=0.94 if currency else 0.8,
            )

        if "transaction_reference" not in facts and (ref := patterns.find_transaction_reference(block.text)):
            facts["transaction_reference"] = _direct(ref, quote=ref, reference=reference, confidence=0.93)

    if timestamp := _best_timestamp(ocr_result, evidence_id):
        found, precision = timestamp
        moment = found["value"]
        # A time-only reading keeps its quote so the reviewer still sees "5:45 pm", but no datetime
        # is asserted: the source never stated which day it was.
        facts["event_time"] = FieldProvenance(
            value=moment.isoformat() if moment is not None else None,
            basis=ObservationBasis.DIRECT,
            quote=found["quote"],
            source_reference=found["reference"].to_dict(),
            confidence=0.85 if moment is not None else 0.6,
            validation_status=ValidationStatus.VALIDATED,
        )
        if moment is None:
            facts["event_time"].reason = (
                "The source shows a time of day but never states the calendar date, so no date is asserted."
            )
        facts["event_time_precision"] = FieldProvenance(
            value=precision,
            basis=ObservationBasis.DIRECT,
            quote=found["quote"],
            source_reference=found["reference"].to_dict(),
            confidence=0.85,
            validation_status=ValidationStatus.VALIDATED,
        )
    return facts


def _identifier_facts(text: str, reference: SourceReference) -> dict[str, FieldProvenance]:
    """Identifiers that are literally present in the text. Nothing here is inferred."""
    facts: dict[str, FieldProvenance] = {}
    if phones := patterns.find_phone_numbers(text):
        facts["phone_numbers"] = _direct(phones, quote=", ".join(phones), reference=reference, confidence=0.94)
    if emails := patterns.find_email_addresses(text):
        facts["email_addresses"] = _direct(emails, quote=", ".join(emails), reference=reference, confidence=0.95)
    if accounts := patterns.find_account_identifiers(text):
        facts["account_identifiers"] = _direct(accounts, quote=", ".join(accounts), reference=reference, confidence=0.93)
    if reference_id := patterns.find_transaction_reference(text):
        facts["transaction_reference"] = _direct(reference_id, quote=reference_id, reference=reference, confidence=0.95)
    if device := patterns.find_device_identifier(text):
        facts["device_identifier"] = _direct(device, quote=device, reference=reference, confidence=0.92)

    # SIH26189 entity classes. Confidence differs by how much shape the class
    # actually has: a registration plate is close to unique, an organisation is
    # a suffix heuristic, and a place name is the weakest reading of the four.
    if vehicles := patterns.find_vehicle_identifiers(text):
        facts["vehicle_identifiers"] = _direct(vehicles, quote=", ".join(vehicles), reference=reference, confidence=0.93)
    if organisations := patterns.find_organisations(text):
        facts["organisation_names"] = _direct(organisations, quote=", ".join(organisations), reference=reference, confidence=0.80)
        facts["organisation_names"].reason = "Read from a legal-form or business suffix; the entity behind the name is not established."
    if people := patterns.find_person_names(text):
        facts["person_names"] = _direct(people, quote=", ".join(people), reference=reference, confidence=0.75)
        facts["person_names"].reason = "The source states this role and name. It does not establish that the person is the same individual named elsewhere."
        # The role the source attached to each name. Matched by the same patterns that found
        # the names and, until now, discarded on the way out.
        if roles := patterns.find_person_roles(text):
            facts["person_roles"] = _direct(roles, quote=", ".join(f"{name}: {role}" for name, role in sorted(roles.items())), reference=reference, confidence=0.75)
            facts["person_roles"].reason = "The role is what this source calls the person. Another source may call the same person something else."
    if places := patterns.find_locations(text):
        facts["location_names"] = _direct(places, quote=", ".join(places), reference=reference, confidence=0.65)
        facts["location_names"].reason = "A place marker names this location. A shared place is weak evidence of a shared party."
    if found := patterns.find_amount_detail(text):
        value, currency, quote, role = found
        facts["amount"] = _direct(
            {"value": value, "currency": currency, "role": role},
            quote=quote,
            reference=reference,
            confidence=0.96 if currency else 0.82,
        )
        if currency is None:
            facts["amount"].reason = "A numeric amount is visible but no currency symbol accompanies it."
    return facts


class DeterministicExtractor:
    """Dispatches to the right format handler and always returns geometry where it exists."""

    version = NATIVE_EXTRACTOR_VERSION

    def __init__(self, ocr_adapter: Any | None = None, layout_adapter: Any | None = None) -> None:
        self.ocr = ocr_adapter or TesseractOCRAdapter()
        self.layout = layout_adapter or ChatScreenshotLayoutAdapter()

    def extract(self, path: Path, *, evidence_id: str, detected: DetectedType) -> RawExtraction:
        source_type = detected.source_type
        if source_type in {SourceType.SCREENSHOT, SourceType.IMAGE}:
            return self._image(path, evidence_id=evidence_id, source_type=source_type)
        if source_type is SourceType.CHAT_EXPORT:
            return self._chat_export(path, evidence_id=evidence_id)
        if source_type is SourceType.EMAIL:
            return self._email(path, evidence_id=evidence_id)
        if source_type in {SourceType.CSV, SourceType.BANK_RECORD, SourceType.CALL_LOG, SourceType.CDR, SourceType.SPREADSHEET}:
            return self._tabular(path, evidence_id=evidence_id, source_type=source_type, extension=detected.extension)
        if source_type in {SourceType.PDF, *REPORT_SOURCE_TYPES}:
            # A police report or surveillance note is a document; the source type only changes what
            # the extractor additionally looks for in the text it recovers.
            extraction = (
                self._pdf(path, evidence_id=evidence_id, source_type=source_type)
                if detected.extension == ".pdf"
                else self._plain_document(path, evidence_id=evidence_id, source_type=source_type)
            )
            if source_type in REPORT_SOURCE_TYPES:
                _report_enrichment(extraction, evidence_id=evidence_id)
            return extraction
        return self._plain_document(path, evidence_id=evidence_id, source_type=source_type)

    # ---------------------------------------------------------------- images

    def _image(self, path: Path, *, evidence_id: str, source_type: SourceType) -> RawExtraction:
        ocr_result: OCRResult = self.ocr.read(path)
        layout = self.layout.analyze(ocr_result)
        metadata = _image_metadata(path)

        layers = [
            ExtractionLayer("ocr", self.ocr.version, ocr_result.to_dict()),
            ExtractionLayer("layout", self.layout.version, layout.to_dict()),
            ExtractionLayer("file_metadata", "pillow-exif-v1", metadata),
        ]

        header_provenance: FieldProvenance | None = None
        if layout.header_identifier and layout.header_identifier_block:
            header_provenance = _direct(
                layout.header_identifier,
                quote=layout.header_identifier_block.text,
                reference=layout.header_identifier_block.reference(evidence_id),
                confidence=0.9,
            )

        # One image is one observation. Splitting it into per-OCR-line units strips away the very
        # context a screenshot carries — an address next to a name, an amount under a heading — and
        # sends the model fragments like "tome «" with nothing to interpret them against.
        full_text = ocr_result.text
        whole = SourceReference(
            evidence_id=evidence_id,
            kind="image_region",
            page=1,
            bbox=(0.0, 0.0, float(ocr_result.width), float(ocr_result.height)),
        )
        facts = _identifier_facts(full_text, whole)
        facts.update(_block_scoped_facts(ocr_result, evidence_id))

        directions = {message["direction"] for message in layout.messages if message["direction"]}
        if len(directions) == 1:
            only = directions.pop()
            facts["message_direction"] = FieldProvenance(
                value=only,
                basis=ObservationBasis.DIRECT_VISUAL,
                quote=full_text[:200],
                source_reference=whole.to_dict(),
                confidence=0.8,
                validation_status=ValidationStatus.VALIDATED,
            )
        else:
            facts["message_direction"] = _unknown(
                "The image shows message regions on both sides or none clearly, so a single direction is not established."
            )

        facts.setdefault("sender", _unknown("No sender role is established by the image alone."))
        facts.setdefault("receiver", _unknown("No recipient role is established by the image alone."))
        if header_provenance:
            facts["chat_participant_identifier"] = header_provenance

        if any(message["is_media_placeholder"] for message in layout.messages):
            facts["media_content"] = _unknown("A media placeholder is visible; its contents are not present in this source.")

        unit = ExtractionUnit(
            unit_key="image:1",
            kind="image",
            text=full_text,
            reference=whole,
            facts=facts,
            layout={
                "blocks": len(ocr_result.blocks),
                "messages": layout.messages,
                "header_identifier": layout.header_identifier,
                "orientation_confident": layout.orientation_confident,
                "width": ocr_result.width,
                "height": ocr_result.height,
            },
            quality_flags=layout.quality_flags,
        )

        return RawExtraction(
            source_type=source_type,
            text=full_text,
            units=[unit] if full_text.strip() else [],
            layers=layers,
            quality_flags=sorted(set(layout.quality_flags)),
        )

    # ----------------------------------------------------------- chat export

    def _chat_export(self, path: Path, *, evidence_id: str) -> RawExtraction:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        units: list[ExtractionUnit] = []
        raw_messages: list[dict[str, Any]] = []

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            match = CHAT_MESSAGE_PATTERN.match(stripped)
            system = None if match else CHAT_SYSTEM_PATTERN.match(stripped)

            if not match and not system:
                # A wrapped continuation belongs to the message above it; original wording is kept intact.
                if units and units[-1].kind == "chat_message":
                    previous = units[-1]
                    previous.text = f"{previous.text}\n{line}"
                    raw_messages[-1]["body"] = previous.text
                continue

            index = len(units)
            reference = SourceReference(
                evidence_id=evidence_id,
                kind="chat_message",
                line_start=line_number,
                line_end=line_number,
                message_index=index,
            )
            timestamp_quote = (match or system).group("timestamp")
            body = match.group("body") if match else system.group("body")
            sender_label = match.group("sender").strip() if match else None

            facts = _identifier_facts(body, reference)
            parsed, quote, precision = patterns.find_timestamp(timestamp_quote)
            if parsed:
                facts["event_time"] = _direct(parsed.isoformat(), quote=quote or timestamp_quote, reference=reference, confidence=0.96)
                facts["event_time_precision"] = FieldProvenance(
                    value=precision,
                    basis=ObservationBasis.DIRECT,
                    quote=quote or timestamp_quote,
                    source_reference=reference.to_dict(),
                    confidence=0.96,
                    validation_status=ValidationStatus.VALIDATED,
                )

            if sender_label:
                # The export prints a sender label verbatim, so the label itself is directly observed.
                facts["sender"] = _direct(sender_label, quote=sender_label, reference=reference, confidence=0.93)
            else:
                facts["sender"] = _unknown("This line is a system notice and names no sender.")
            facts["receiver"] = _unknown("A chat export does not state a per-message recipient.")

            if MEDIA_OMITTED_PATTERN.search(body):
                facts["media_content"] = _unknown("Media was omitted from this export; its contents are unknown.")

            units.append(
                ExtractionUnit(
                    unit_key=f"message:{index}",
                    kind="chat_message" if match else "chat_system_notice",
                    text=body,
                    reference=reference,
                    facts=facts,
                    layout={"is_media_placeholder": bool(MEDIA_OMITTED_PATTERN.search(body)), "sender_label": sender_label},
                )
            )
            raw_messages.append({"message_index": index, "line": line_number, "timestamp": timestamp_quote, "sender": sender_label, "body": body})

        return RawExtraction(
            source_type=SourceType.CHAT_EXPORT,
            text=text,
            units=units,
            layers=[ExtractionLayer("native_text", self.version, {"line_count": len(lines), "messages": raw_messages})],
            quality_flags=[] if units else ["incomplete"],
        )

    # ----------------------------------------------------------------- email

    def _email(self, path: Path, *, evidence_id: str) -> RawExtraction:
        message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
        headers = {
            name: str(message.get(name))
            for name in ("From", "To", "Cc", "Bcc", "Date", "Subject", "Message-ID", "Reply-To")
            if message.get(name)
        }
        attachments = [
            {"filename": part.get_filename(), "mime": part.get_content_type(), "bytes": len(part.get_payload(decode=True) or b"")}
            for part in message.walk()
            if part.get_content_disposition() == "attachment"
        ]
        body = _email_body(message)

        header_facts: dict[str, FieldProvenance] = {}
        for name, value in headers.items():
            reference = SourceReference(evidence_id=evidence_id, kind="email_header", header_name=name)
            if name == "From":
                header_facts["sender"] = _direct(value, quote=value, reference=reference, confidence=0.97)
            if name == "To":
                header_facts["receiver"] = _direct(value, quote=value, reference=reference, confidence=0.97)
            if name == "Date":
                parsed, quote, precision = patterns.find_timestamp(value)
                if parsed:
                    header_facts["event_time"] = _direct(parsed.isoformat(), quote=quote or value, reference=reference, confidence=0.97)
                    header_facts["event_time_precision"] = FieldProvenance(
                        value=precision,
                        basis=ObservationBasis.DIRECT,
                        quote=quote or value,
                        source_reference=reference.to_dict(),
                        confidence=0.97,
                        validation_status=ValidationStatus.VALIDATED,
                    )

        body_reference = SourceReference(evidence_id=evidence_id, kind="email_body")
        # Message-ID is an envelope identifier, not a correspondent, so it is kept out of the
        # address sweep. Header facts are applied last because a parsed header outranks a regex hit.
        scanned = "\n".join([*(value for name, value in headers.items() if name != "Message-ID"), body])
        facts = {**_identifier_facts(scanned, body_reference), **header_facts}

        text = "\n".join([*(f"{name}: {value}" for name, value in headers.items()), "", body])
        unit = ExtractionUnit(
            unit_key="email:0",
            kind="email",
            text=text,
            reference=body_reference,
            facts=facts,
            layout={"headers": headers, "attachments": attachments, "has_attachments": bool(attachments)},
        )
        return RawExtraction(
            source_type=SourceType.EMAIL,
            text=text,
            units=[unit],
            layers=[
                ExtractionLayer("native_text", self.version, {"headers": headers, "attachments": attachments, "body_characters": len(body)}),
            ],
        )

    # --------------------------------------------------------------- tabular

    def _tabular(self, path: Path, *, evidence_id: str, source_type: SourceType, extension: str) -> RawExtraction:
        rows, header = _read_table(path, extension)
        aliases = CALL_LOG_COLUMN_ALIASES if source_type in {SourceType.CALL_LOG, SourceType.CDR} else BANK_COLUMN_ALIASES
        mapping = _map_columns(header, aliases)

        units: list[ExtractionUnit] = []
        for row_number, row in rows:
            cells = {key: str(value).strip() for key, value in row.items() if key and str(value).strip()}
            if not cells:
                continue
            row_text = " | ".join(f"{key}: {value}" for key, value in cells.items())
            row_reference = SourceReference(evidence_id=evidence_id, kind="table_row", row=row_number)
            facts = _identifier_facts(row_text, row_reference)

            for canonical, column in mapping.items():
                raw_value = cells.get(column)
                if not raw_value:
                    continue
                cell_reference = SourceReference(evidence_id=evidence_id, kind="table_cell", row=row_number, column=column)
                facts.update(_cell_fact(canonical, raw_value, cell_reference))

            for canonical in ("sender", "receiver"):
                if canonical not in facts:
                    facts[canonical] = _unknown(f"No column in this table states the {canonical}.")

            units.append(
                ExtractionUnit(
                    unit_key=f"row:{row_number}",
                    kind="table_row",
                    text=row_text,
                    reference=row_reference,
                    facts=facts,
                    layout={"columns": cells, "row": row_number},
                )
            )

        return RawExtraction(
            source_type=source_type,
            text="\n".join(unit.text for unit in units),
            units=units,
            layers=[
                ExtractionLayer(
                    "structured",
                    self.version,
                    {"header": header, "row_count": len(units), "column_mapping": mapping},
                )
            ],
            quality_flags=[] if units else ["incomplete"],
        )

    # ------------------------------------------------------------------- pdf

    def _pdf(self, path: Path, *, evidence_id: str, source_type: SourceType = SourceType.PDF) -> RawExtraction:
        import fitz

        document = fitz.open(path)
        units: list[ExtractionUnit] = []
        pages: list[dict[str, Any]] = []
        ocr_pages: list[dict[str, Any]] = []
        quality_flags: list[str] = []

        try:
            for page_number, page in enumerate(document, start=1):
                native_text = page.get_text("text")
                if len(native_text.strip()) >= PDF_NATIVE_TEXT_FLOOR:
                    pages.append({"page": page_number, "characters": len(native_text), "method": "native"})
                    units.extend(_paragraph_units(native_text, evidence_id=evidence_id, page=page_number))
                    continue

                # Scanned page: fall back to page-wise OCR so geometry is still recorded.
                ocr_result = self._ocr_pdf_page(page, page_number)
                ocr_pages.append(ocr_result.to_dict())
                quality_flags.extend(ocr_result.quality_flags)
                pages.append({"page": page_number, "characters": len(ocr_result.text), "method": "ocr"})
                for block in ocr_result.blocks:
                    reference = block.reference(evidence_id)
                    units.append(
                        ExtractionUnit(
                            unit_key=f"page:{page_number}:{block.block_id}",
                            kind="ocr_block",
                            text=block.text,
                            reference=reference,
                            facts=_identifier_facts(block.text, reference),
                            quality_flags=ocr_result.quality_flags,
                        )
                    )
        finally:
            document.close()

        layers = [ExtractionLayer("native_text", self.version, {"pages": pages})]
        if ocr_pages:
            layers.append(ExtractionLayer("ocr", self.ocr.version, {"pages": ocr_pages}))

        return RawExtraction(
            source_type=SourceType.PDF,
            text="\n".join(unit.text for unit in units),
            units=units,
            layers=layers,
            quality_flags=sorted(set(quality_flags)),
        )

    def _ocr_pdf_page(self, page: Any, page_number: int) -> OCRResult:
        import io

        import fitz
        from PIL import Image

        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        with Image.open(io.BytesIO(pixmap.tobytes("png"))) as handle:
            return self.ocr.read_image(handle.convert("RGB"), page=page_number)

    # -------------------------------------------------------------- document

    def _plain_document(self, path: Path, *, evidence_id: str, source_type: SourceType) -> RawExtraction:
        text = path.read_text(encoding="utf-8", errors="replace")
        units = _paragraph_units(text, evidence_id=evidence_id, page=None)
        return RawExtraction(
            source_type=source_type if source_type is not SourceType.UNKNOWN else SourceType.DOCUMENT,
            text=text,
            units=units,
            layers=[ExtractionLayer("native_text", self.version, {"characters": len(text), "lines": len(text.splitlines())})],
            quality_flags=[] if units else ["incomplete"],
        )


def _report_enrichment(extraction: RawExtraction, *, evidence_id: str) -> None:
    """Read what a police report or surveillance note states about itself, and about who did what.

    Two separate things, and they are kept separate on purpose.

    The header fields -- FIR number, sections, station -- are printed metadata. They are attached to
    the first unit as attributes of the document, not as claims about anyone.

    The role links are read one sentence at a time, and only where the sentence carries the verb.
    "Yash Kumar Gupta was driving MH12DE1433" states that he used it; the same two strings appearing in
    different sentences on the same page state nothing, and turning that into a relationship is the
    invention this pipeline exists to refuse.
    """
    whole = SourceReference(evidence_id=evidence_id, kind="document")

    header: dict[str, FieldProvenance] = {}
    if number := patterns.find_fir_number(extraction.text):
        header["fir_number"] = _direct(number, quote=number, reference=whole, confidence=0.97)
    if sections := patterns.find_fir_sections(extraction.text):
        header["fir_sections"] = _direct(sections, quote=", ".join(sections), reference=whole, confidence=0.94)
    if station := patterns.find_police_station(extraction.text):
        header["police_station"] = _direct(station, quote=station, reference=whole, confidence=0.95)
    if header and extraction.units:
        extraction.units[0].facts.update(header)

    for unit in extraction.units:
        if vehicle_links := patterns.find_person_vehicle_links(unit.text):
            unit.facts["stated_vehicle_use"] = _direct(
                [[person, vehicle] for person, vehicle, _ in vehicle_links],
                quote=vehicle_links[0][2],
                reference=unit.reference,
                confidence=0.82,
            )
        if presence_links := patterns.find_person_location_links(unit.text):
            unit.facts["stated_presence"] = _direct(
                [[person, place] for person, place, _ in presence_links],
                quote=presence_links[0][2],
                reference=unit.reference,
                confidence=0.78,
            )
            unit.facts["stated_presence"].reason = (
                "The sentence places the person somewhere. It does not establish that they were there at any stated time."
            )
        if vehicle_presence := patterns.find_vehicle_location_links(unit.text):
            unit.facts["stated_vehicle_presence"] = _direct(
                [[plate, place] for plate, place, _ in vehicle_presence],
                quote=vehicle_presence[0][2],
                reference=unit.reference,
                confidence=0.80,
            )
            unit.facts["stated_vehicle_presence"].reason = (
                "The sentence places the vehicle somewhere. It says nothing about who was in it."
            )


def _paragraph_units(text: str, *, evidence_id: str, page: int | None) -> list[ExtractionUnit]:
    units: list[ExtractionUnit] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if len(stripped) < 3:
            continue
        reference = SourceReference(
            evidence_id=evidence_id,
            kind="page" if page else "line_range",
            page=page,
            line_start=index,
            line_end=index,
        )
        units.append(
            ExtractionUnit(
                unit_key=f"page:{page}:line:{index}" if page else f"line:{index}",
                kind="paragraph",
                text=stripped,
                reference=reference,
                facts=_identifier_facts(stripped, reference),
            )
        )
    return units


def _cell_fact(canonical: str, raw_value: str, reference: SourceReference) -> dict[str, FieldProvenance]:
    """Map one authoritative table cell onto a canonical field."""
    if canonical == "amount":
        # The column header already established that this cell holds money.
        found = patterns.find_amount_detail(raw_value, declared_monetary=True)
        if not found:
            return {}
        value, currency, quote, role = found
        return {
            "amount": _direct(
                {"value": value, "currency": currency, "role": role},
                quote=quote,
                reference=reference,
                confidence=0.98,
            )
        }
    if canonical == "event_time":
        parsed, quote, precision = patterns.find_timestamp(raw_value)
        if not parsed:
            return {}
        return {
            "event_time": _direct(parsed.isoformat(), quote=quote or raw_value, reference=reference, confidence=0.98),
            "event_time_precision": FieldProvenance(
                value=precision,
                basis=ObservationBasis.DIRECT,
                quote=quote or raw_value,
                source_reference=reference.to_dict(),
                confidence=0.98,
                validation_status=ValidationStatus.VALIDATED,
            ),
        }
    if canonical in {"account_identifiers", "phone_numbers", "email_addresses"}:
        # Normalized the same way as the regex sweep, otherwise the identical number would be
        # stored in two shapes and exact-match correlation would miss the link.
        entity_type = {"phone_numbers": "phone", "email_addresses": "email", "account_identifiers": "account_number"}[canonical]
        normalized = patterns.normalize_identifier(entity_type, raw_value)
        return {canonical: _direct([normalized], quote=raw_value, reference=reference, confidence=0.96)}
    if canonical == "narration":
        return {"narration": _direct(raw_value, quote=raw_value, reference=reference, confidence=0.99)}
    return {canonical: _direct(raw_value, quote=raw_value, reference=reference, confidence=0.97)}


def _map_columns(header: list[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Match a table's headers to the fields they carry, ignoring how they are punctuated.

    An exported CSV writes "a_party" where the alias list says "a-party", and "account_number"
    where it says "account number". Matching the exact string meant a real CDR's A-party column
    went unmapped, so who dialled whom was lost and a call record could only ever produce the
    symmetric "these two were in contact" -- the directed CALLED relationship the column exists to
    support was never built. Separators carry no meaning in a header, so they are dropped on both
    sides. The alias lists keep their readable spellings; several now fold onto one key, which is
    what they always meant.
    """

    def fold(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.strip().lower())

    folded = {}
    for column in header:
        if column and fold(column):
            folded.setdefault(fold(column), column)

    mapping: dict[str, str] = {}
    for canonical, options in aliases.items():
        for option in options:
            match = folded.get(fold(option))
            if match is not None:
                mapping[canonical] = match
                break
    return mapping


def _read_table(path: Path, extension: str) -> tuple[list[tuple[int, dict[str, Any]]], list[str]]:
    if extension == ".xlsx":
        import pandas as pd

        frame = pd.read_excel(path).fillna("")
        header = [str(column) for column in frame.columns]
        rows = [(index, {str(key): value for key, value in row.items()}) for index, row in enumerate(frame.to_dict(orient="records"), start=2)]
        return rows, header

    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(4096)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|") if sample.strip() else csv.excel
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        header = list(reader.fieldnames or [])
        rows = [(index, dict(row)) for index, row in enumerate(reader, start=2)]
    return rows, header


def _email_body(message: Any) -> str:
    if not message.is_multipart():
        payload = message.get_payload(decode=True)
        if payload is None:
            return str(message.get_payload())
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace")
    parts = []
    for part in message.walk():
        if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
            payload = part.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(parts)


def _image_metadata(path: Path) -> dict[str, Any]:
    """EXIF and file metadata as its own layer. Absence of EXIF is not suspicious by itself."""
    from PIL import Image

    metadata: dict[str, Any] = {"byte_size": path.stat().st_size, "exif_present": False, "exif": {}}
    try:
        with Image.open(path) as image:
            metadata["format"] = image.format
            metadata["mode"] = image.mode
            metadata["width"], metadata["height"] = image.size
            exif = image.getexif()
            if exif:
                from PIL.ExifTags import TAGS

                metadata["exif_present"] = True
                metadata["exif"] = {TAGS.get(tag, str(tag)): str(value)[:200] for tag, value in exif.items()}
    except OSError:
        logger.debug("Image metadata could not be read for an evidence item")
    metadata["note"] = "Absence of EXIF metadata is common for screenshots and is not evidence of tampering."
    return metadata
