"""Deterministic indicator extraction and conservative canonical normalization for investigator review."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser

PATTERNS = {
    "phone": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "upi_id": re.compile(r"\b[a-zA-Z0-9._-]{2,120}@[a-zA-Z][a-zA-Z0-9.-]{1,80}\b"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "url": re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE),
    "ifsc": re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    "account_number": re.compile(r"(?:A/C|ACCOUNT(?:\s+NO\.?)?)\s*[:#-]?\s*(\d{9,18})", re.IGNORECASE),
    "utr": re.compile(r"(?:UTR|REFERENCE(?:\s+ID)?|TXN(?:\s+ID)?)\s*[:#-]?\s*([A-Z0-9-]{8,32})", re.IGNORECASE),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "person": re.compile(r"(?:Name|Beneficiary|Sender|Receiver|From|To)\s*[:#-]\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})"),
}
AMOUNT_PATTERN = re.compile(r"(?:₹|INR|RS\.?|AMOUNT\s*[:=-]?)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE)
DATE_PATTERNS = [re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\b"), re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{4}[, ]+\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?\b", re.IGNORECASE), re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b")]


def normalize(entity_type: str, value: str) -> str:
    value = value.strip()
    if entity_type == "phone":
        return "+91" + re.sub(r"\D", "", value)[-10:]
    if entity_type in {"upi_id", "email", "url", "ifsc", "utr"}:
        return value.lower().rstrip(".,;:)")
    if entity_type == "account_number":
        return value.replace(" ", "")
    if entity_type == "person":
        return " ".join(part.capitalize() for part in value.split())
    return value


def extract_indicators(text: str) -> list[tuple[str, str, str, float]]:
    indicators: list[tuple[str, str, str, float]] = []
    for entity_type, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)
            indicators.append((entity_type, value.strip(), normalize(entity_type, value), 0.93 if entity_type in {"upi_id", "email", "ifsc", "utr", "account_number"} else 0.86))
    for match in AMOUNT_PATTERN.finditer(text):
        indicators.append(("amount", match.group(1), match.group(1).replace(",", ""), 0.95))
    return list({(item[0], item[2]): item for item in indicators}.values())


def extract_timestamp(text: str) -> tuple[datetime | None, str | None, str]:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            raw = match.group(0)
            try:
                parsed = date_parser.parse(raw, dayfirst=True, fuzzy=False)
                return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc), raw, "minute" if ":" in raw else "day")
            except (ValueError, OverflowError):
                continue
    return None, None, "unknown"


def extract_transaction_fields(text: str, metadata: dict) -> dict[str, str | float | None]:
    columns = {str(key).lower(): str(value) for key, value in metadata.get("columns", {}).items()}
    source = columns.get("amount") or columns.get("value") or text
    match = AMOUNT_PATTERN.search(f"INR {source}") if source != text else AMOUNT_PATTERN.search(text)
    try:
        amount = float(Decimal(match.group(1).replace(",", ""))) if match else None
    except InvalidOperation:
        amount = None
    sender = columns.get("sender") or columns.get("from")
    receiver = columns.get("receiver") or columns.get("to") or columns.get("beneficiary")
    reference = columns.get("reference") or columns.get("reference_id") or columns.get("utr") or columns.get("transaction_id")
    return {"amount": amount, "sender": sender, "receiver": receiver, "reference": reference}

