"""File-type parser registry with actual text, table, PDF, email, and OCR extraction paths."""

from __future__ import annotations

import csv
import email
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz
import pandas as pd
import pytesseract
from PIL import Image


@dataclass
class ParsedRecord:
    raw_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    record_type: str = "message"


@dataclass
class ParsedDocument:
    content: str
    records: list[ParsedRecord]
    method: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _records_from_lines(text: str, record_type: str) -> list[ParsedRecord]:
    return [ParsedRecord(raw_text=line.strip(), metadata={"line": index + 1}, record_type=record_type)
            for index, line in enumerate(text.splitlines()) if line.strip()]


def _parse_text(path: Path, evidence_kind: str) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="strict")
    record_type = "phishing_email" if path.suffix.lower() == ".eml" or evidence_kind == "phishing_email" else "message"
    if path.suffix.lower() == ".eml":
        message = email.message_from_string(text)
        body = ""
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            body = message.get_payload(decode=True).decode(message.get_content_charset() or "utf-8", errors="replace")
        text = "\n".join(value for value in [f"From: {message.get('From', '')}", f"To: {message.get('To', '')}", f"Subject: {message.get('Subject', '')}", body] if value)
    return ParsedDocument(text, _records_from_lines(text, record_type), "text_parser", 0.98)


def _parse_csv(path: Path) -> ParsedDocument:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(4096)
        if not sample.strip():
            raise ValueError("CSV evidence is empty")
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        stream.seek(0)
        reader = csv.DictReader(stream, dialect=dialect)
        if not reader.fieldnames or len(reader.fieldnames) < 2:
            raise ValueError("CSV evidence needs a header and at least two columns")
        records = []
        for row_number, row in enumerate(reader, start=2):
            cleaned = {str(key).strip().lower(): str(value).strip() for key, value in row.items() if key and value is not None}
            if cleaned:
                records.append(ParsedRecord(" | ".join(f"{key}: {value}" for key, value in cleaned.items()), {"row": row_number, "columns": cleaned}, "bank_transaction"))
    if not records:
        raise ValueError("CSV evidence did not contain transaction rows")
    return ParsedDocument("\n".join(record.raw_text for record in records), records, "csv_parser", 0.99)


def _parse_xlsx(path: Path) -> ParsedDocument:
    frame = pd.read_excel(path)
    if frame.empty or len(frame.columns) < 2:
        raise ValueError("Spreadsheet evidence needs a non-empty table with at least two columns")
    records = []
    for row_number, row in enumerate(frame.fillna("").to_dict(orient="records"), start=2):
        cleaned = {str(key).strip().lower(): str(value).strip() for key, value in row.items() if str(value).strip()}
        records.append(ParsedRecord(" | ".join(f"{key}: {value}" for key, value in cleaned.items()), {"row": row_number, "columns": cleaned}, "bank_transaction"))
    return ParsedDocument("\n".join(record.raw_text for record in records), records, "xlsx_parser", 0.99)


def _ocr_image(image: Image.Image) -> str:
    text = pytesseract.image_to_string(image, config="--psm 6")
    if not text.strip():
        raise ValueError("OCR did not recover readable text from image evidence")
    return text


def _parse_image(path: Path) -> ParsedDocument:
    with Image.open(path) as image:
        text = _ocr_image(image.convert("RGB"))
    return ParsedDocument(text, _records_from_lines(text, "ocr_document"), "tesseract_ocr", 0.78)


def _parse_pdf(path: Path, evidence_kind: str) -> ParsedDocument:
    document = fitz.open(path)
    try:
        text = "\n".join(page.get_text("text") for page in document)
        method, confidence = "pymupdf_text", 0.96
        if len(text.strip()) < 20:
            images = [Image.open(io.BytesIO(page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png"))).convert("RGB") for page in document]
            text = "\n".join(_ocr_image(image) for image in images)
            method, confidence = "pymupdf_render+tesseract_ocr", 0.74
    finally:
        document.close()
    if not text.strip():
        raise ValueError("PDF parser did not recover readable content")
    record_type = "complaint_statement" if evidence_kind in {"complaint", "fir", "complaint_fir"} else "document"
    return ParsedDocument(text, _records_from_lines(text, record_type), method, confidence)


def parse_evidence(path: Path, *, source_category: str) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".eml"}:
        return _parse_text(path, source_category)
    if suffix == ".csv":
        return _parse_csv(path)
    if suffix == ".xlsx":
        return _parse_xlsx(path)
    if suffix == ".pdf":
        return _parse_pdf(path, source_category)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return _parse_image(path)
    raise ValueError(f"No parser registered for {suffix}")
