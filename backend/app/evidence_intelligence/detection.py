"""File type and content detection.

Detection reads the bytes rather than trusting the filename, then narrows the result using the
uploader's declared category. A wrong `source_type` routes evidence down the wrong extractor, so
ambiguity resolves to the more general type rather than the more convenient one.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.evidence_intelligence.schema import SourceType

DETECTOR_VERSION = "content-detect-v1"

CHAT_EXPORT_LINE = re.compile(
    r"^\[?\d{1,2}[/-]\d{1,2}[/-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s?(?:[AaPp]\.?[Mm]\.?)?\]?\s*[-–]?\s*[^:]{1,60}:",
)
BANK_COLUMN_MARKERS = {"amount", "credit", "debit", "balance", "utr", "reference", "transaction", "narration", "particulars"}
CALL_LOG_COLUMN_MARKERS = {"duration", "call_type", "call type", "caller", "callee", "number", "direction"}
# A record that names both ends of the call separately carries who dialled, which a plain
# call log does not. Recognising it by its header means an operator export is read correctly
# even when the uploader did not pick the category.
CDR_COLUMN_MARKERS = {"a-party", "a party", "b-party", "b party", "calling number", "called number",
                     "originating number", "terminating number", "msisdn_a", "msisdn_b", "a_number", "b_number"}

# Narrative report sources. They parse like any document, but the extractor reads report
# structure and stated roles out of them as well.
CATEGORY_HINTS = {
    "whatsapp_screenshot": SourceType.SCREENSHOT,
    "screenshot": SourceType.SCREENSHOT,
    "chat_screenshot": SourceType.SCREENSHOT,
    "chat_export": SourceType.CHAT_EXPORT,
    "whatsapp_export": SourceType.CHAT_EXPORT,
    "bank_statement": SourceType.BANK_RECORD,
    "bank_record": SourceType.BANK_RECORD,
    "call_log": SourceType.CALL_LOG,
    "phishing_email": SourceType.EMAIL,
    "email": SourceType.EMAIL,
    # SIH26189 names police reports and surveillance notes as primary sources. They are
    # ordinary documents to the parser; the category is what tells the extractor to also read
    # the report header and the stated roles in the narrative.
    "complaint_fir": SourceType.FIR,
    "fir": SourceType.FIR,
    "police_report": SourceType.POLICE_REPORT,
    "surveillance": SourceType.SURVEILLANCE,
    "surveillance_report": SourceType.SURVEILLANCE,
    "cdr": SourceType.CDR,
}

# Narrative report sources. They parse like any document, but the extractor reads report
# structure and the roles stated in the narrative out of them as well.
DOCUMENT_REPORT_TYPES = frozenset({SourceType.FIR, SourceType.POLICE_REPORT, SourceType.SURVEILLANCE})


@dataclass(frozen=True)
class DetectedType:
    source_type: SourceType
    extension: str
    mime: str
    detector_version: str = DETECTOR_VERSION
    basis: str = "content"

    def to_dict(self) -> dict[str, str]:
        return {
            "source_type": self.source_type.value,
            "extension": self.extension,
            "mime": self.mime,
            "detector_version": self.detector_version,
            "basis": self.basis,
        }


class FileTypeDetector(Protocol):
    def detect(self, path: Path, *, declared_category: str, declared_mime: str | None = None) -> DetectedType: ...


class ContentFileTypeDetector:
    version = DETECTOR_VERSION

    def detect(self, path: Path, *, declared_category: str, declared_mime: str | None = None) -> DetectedType:
        extension = path.suffix.lower()
        prefix = path.read_bytes()[:4096] if path.is_file() else b""
        mime = _sniff_mime(prefix, extension, declared_mime)
        hinted = CATEGORY_HINTS.get(declared_category)

        if extension in {".png", ".jpg", ".jpeg"}:
            source_type = SourceType.SCREENSHOT if hinted is SourceType.SCREENSHOT else SourceType.IMAGE
            return DetectedType(source_type, extension, mime, basis="content+category" if hinted else "content")

        if extension == ".pdf":
            if hinted in DOCUMENT_REPORT_TYPES:
                return DetectedType(hinted, extension, mime, basis="content+category")
            return DetectedType(SourceType.PDF, extension, mime)

        if extension == ".eml":
            return DetectedType(SourceType.EMAIL, extension, mime)

        if extension == ".csv":
            return DetectedType(_tabular_type(path, hinted), extension, mime, basis="content+headers")

        if extension == ".xlsx":
            return DetectedType(hinted or SourceType.SPREADSHEET, extension, mime, basis="content+category" if hinted else "content")

        if extension == ".txt":
            if hinted in DOCUMENT_REPORT_TYPES:
                return DetectedType(hinted, extension, mime, basis="category")
            if hinted in {SourceType.CHAT_EXPORT, SourceType.EMAIL}:
                return DetectedType(hinted, extension, mime, basis="category")
            return DetectedType(_text_type(path), extension, mime, basis="content")

        return DetectedType(hinted or SourceType.UNKNOWN, extension, mime, basis="fallback")


def _sniff_mime(prefix: bytes, extension: str, declared_mime: str | None) -> str:
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if prefix.startswith(b"PK\x03\x04") and extension == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if extension == ".eml":
        return "message/rfc822"
    if extension == ".csv":
        return "text/csv"
    if extension == ".txt":
        return "text/plain"
    return declared_mime or "application/octet-stream"


def _text_type(path: Path) -> SourceType:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:8192]
    except OSError:
        return SourceType.DOCUMENT
    lines = [line.strip() for line in head.splitlines() if line.strip()]
    if lines and sum(1 for line in lines[:40] if CHAT_EXPORT_LINE.match(line)) >= max(2, len(lines[:40]) // 4):
        return SourceType.CHAT_EXPORT
    if any(line.lower().startswith(("from:", "to:", "subject:", "message-id:")) for line in lines[:20]):
        return SourceType.EMAIL
    return SourceType.DOCUMENT


def _tabular_type(path: Path, hinted: SourceType | None) -> SourceType:
    if hinted in {SourceType.BANK_RECORD, SourceType.CALL_LOG, SourceType.CDR}:
        return hinted
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = [str(cell).strip().lower() for cell in next(reader, [])]
    except (OSError, StopIteration, csv.Error):
        return SourceType.CSV
    joined = set(header)
    if joined & CDR_COLUMN_MARKERS:
        return SourceType.CDR
    if joined & CALL_LOG_COLUMN_MARKERS and not joined & {"amount", "credit", "debit", "balance"}:
        return SourceType.CALL_LOG
    if joined & BANK_COLUMN_MARKERS:
        return SourceType.BANK_RECORD
    return SourceType.CSV
