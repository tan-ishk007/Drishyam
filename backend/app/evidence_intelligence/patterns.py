"""Deterministic identifier patterns shared by every extractor.

Kept separate from `app/extraction/normalizer.py` so the legacy `mvp-v1` pipeline keeps its exact
current behaviour while the grounded pipeline can evolve its own rules.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser

# The leading zero is the STD-prefixed form -- 09876543210 -- which is how a great many Indian
# numbers are written down, and it was silently unmatched: the lookbehind rejected the digits
# after the zero because a digit preceded them. The resolver has always canonicalised that form,
# so cross-case matching was relying on a spelling nothing ever extracted.
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{9}(?!\d)")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
UPI_PATTERN = re.compile(r"\b[a-zA-Z0-9._-]{2,120}@[a-zA-Z][a-zA-Z0-9.-]{1,80}\b")
IFSC_PATTERN = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
ACCOUNT_PATTERN = re.compile(r"(?:A/C|ACCOUNT(?:\s+NO\.?)?)\s*[:#-]?\s*(\d{9,18})", re.IGNORECASE)
UTR_PATTERN = re.compile(r"(?:UTR|RRN|REFERENCE(?:\s+ID)?|TXN(?:\s+ID)?|TRANSACTION\s+ID)\s*[:#-]?\s*([A-Z0-9-]{8,32})", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
DEVICE_PATTERN = re.compile(r"(?:IMEI|DEVICE(?:\s+ID)?)\s*[:#-]?\s*([A-Z0-9-]{8,32})", re.IGNORECASE)

CURRENCY_SYMBOLS = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR"}
AMOUNT_PATTERN = re.compile(
    r"(?P<currency>₹|INR|RS\.?|\$|USD|€|EUR)?\s*(?P<value>\d[\d,]*(?:\.\d{1,2})?)\s*(?P<trailing>₹|INR|RS\.?|\$|USD|€|EUR|rupees|rupaye)?",
    re.IGNORECASE,
)

_MONTH_NAME = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"

# One calendar date, written any of the ways evidence actually writes them.
_DATE = "|".join(
    (
        r"\d{4}-\d{2}-\d{2}",
        rf"\d{{1,2}}\s+{_MONTH_NAME}\s+\d{{4}}",
        rf"{_MONTH_NAME}\s+\d{{1,2}},?\s+\d{{4}}",
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
    )
)
_CLOCK = r"\d{1,2}:\d{2}(?::\d{2})?"
_MERIDIEM = r"[AaPp]\.?[Mm]\.?"
_OFFSET = r"[+-]\d{4}"

# Ordered most-specific first. A rule only fires when the date and the time are written next to
# each other; a date at the top of a screen is never welded onto a clock time further down.
TIMESTAMP_RULES: list[tuple[re.Pattern[str], str]] = [
    # 2024-03-12T21:15 / 2024-03-12 21:15:00
    (re.compile(rf"(?P<date>\d{{4}}-\d{{2}}-\d{{2}})[ T](?P<time>{_CLOCK})(?P<tz>\s*{_OFFSET})?"), "exact"),
    # 12/03/2024, 21:16  ·  12 Mar 2024 21:15:00 +0530  ·  02 Sep 2026 at 11:42 am
    (
        re.compile(
            rf"(?P<date>{_DATE})(?:,)?\s*(?:at\s+)?(?P<time>{_CLOCK}\s*(?:{_MERIDIEM})?)(?P<tz>\s*{_OFFSET})?",
            re.IGNORECASE,
        ),
        "exact",
    ),
    # 11:42 am on 02 Sep 2026
    (
        re.compile(rf"(?P<time>{_CLOCK}\s*{_MERIDIEM})\s*(?:on\s+)?(?P<date>{_DATE})", re.IGNORECASE),
        "exact",
    ),
    # A bare calendar date.
    (re.compile(rf"(?P<date>{_DATE})", re.IGNORECASE), "date_only"),
    # A bare clock reading. It fixes a time of day but says nothing about which day.
    (re.compile(rf"(?P<time>{_CLOCK}\s*{_MERIDIEM})"), "time_only"),
]

# Kept for callers that only need "does this look like a date"; the rules above drive parsing.
DATE_PATTERNS = [pattern for pattern, _ in TIMESTAMP_RULES]

# A chat screen prints a calendar divider once and then switches to relative words. Everything
# after "Today" belongs to an unstated day, so the earlier divider must not be reused as its date.
RELATIVE_DAY_PATTERN = re.compile(r"\b(?:today|yesterday|aaj|kal)\b", re.IGNORECASE)

MIN_PLAUSIBLE_AMOUNT = 1
# A number with no currency marker beside it is only treated as an amount above this floor.
# Below it the digits are far more likely to be a count, an index or part of an identifier.
MIN_BARE_AMOUNT = 100
MAX_BARE_AMOUNT_DIGITS = 9

# OCR renders the rupee sign as whatever glyph is closest. These count as a currency marker only
# when they touch the digits, so "Total = 500" stays a bare number while "=12,000" is INR 12,000.
OCR_RUPEE_GLYPHS = "=%¥₩₹"

# Words that establish a number is money. Without a currency marker *and* without one of these on
# the same line, digits are just digits — "SYNTHETIC-ACCOUNT-8233 212,000" is an account row, not a
# payment, and reading it as one invents a transaction that the evidence never recorded.
MONEY_CONTEXT_PATTERN = re.compile(
    r"\b(?:paid|pay|pays|payment|sent|send|sending|bhej\w*|bheja|transferr?\w*|"
    r"debit\w*|credit\w*|amount|amt|balance|bal|fee|fees|charge[sd]?|refund\w*|"
    r"deposit\w*|withdraw\w*|receiv\w*|total|due|paise|rupay\w*|rupees?|remit\w*|"
    r"invoice|price|cost|cash|worth)\b",
    re.IGNORECASE,
)


# What a figure IS, not merely that it is money. "Your balance is now INR 29,500" and "Paid to
# Release Desk 12,000" are both amounts; only one of them is money that moved. Reading every figure
# as a transaction put a balance quoted in an email into the transaction trail as though someone had
# transferred it, which is precisely the kind of claim the evidence does not make.
AMOUNT_ROLE_PATTERNS = (
    ("balance", re.compile(r"\b(?:closing|available|avl|current|opening)?\s*(?:balance|bal|wallet|holdings?|corpus)\b", re.IGNORECASE)),
    ("payment", re.compile(r"\b(?:paid|sent|debited|credited|transferred|remitted|withdrawn|deposited|received)\b", re.IGNORECASE)),
    ("fee", re.compile(r"\b(?:fees?|charges?|commission|penalty|fine|tax|gst)\b", re.IGNORECASE)),
    ("request", re.compile(r"\b(?:pay|send|transfer|remit|deposit|requires?|required|needs?|due|payable)\b", re.IGNORECASE)),
)
AMOUNT_ROLE_UNKNOWN = "unknown"


def classify_amount_role(text: str, quote: str, *, index: int | None = None) -> str:
    """Say what the figure is, judged only by the words printed beside it.

    The line carrying the amount is the whole evidence. A word elsewhere on the page describes a
    different figure, and borrowing it would be the same guess this module exists to refuse.

    `index` is where the figure actually matched. Without it the first textual occurrence of the
    quote has to stand in, and a page that prints the same figure twice — an email subject and its
    body — would be classified from the wrong line.
    """
    if index is None:
        index = text.find(quote)
    line = _line_around(text, max(index, 0))
    for role, pattern in AMOUNT_ROLE_PATTERNS:
        if pattern.search(line):
            return role
    return AMOUNT_ROLE_UNKNOWN


def _line_around(text: str, index: int) -> str:
    """The single line a match sits on. Money context has to be adjacent to be evidence of money."""
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return text[start:] if end == -1 else text[start:end]


# OCR substitutes a punctuation glyph for the letter it resembles, the same way it does for the
# rupee sign. "bhej de" on a phone screenshot comes back as "bhe} de", and the money word that
# makes the digits beside it an amount is then invisible -- so a real payment request was dropped
# because of one misread character.
#
# Only non-alphanumeric glyphs are folded, and only for the context lookup. Digits are never
# touched, so no value is altered by this: it decides whether a word is a money word, never what
# a number is worth.
_OCR_LETTER_LOOKALIKES = str.maketrans({"}": "j", "{": "j", "|": "l", "!": "l", "@": "a", "$": "s"})


def _fold_ocr_glyphs(line: str) -> str:
    return line.translate(_OCR_LETTER_LOOKALIKES)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return "+91" + digits[-10:] if len(digits) >= 10 else value.strip()


def normalize_identifier(entity_type: str, value: str) -> str:
    value = value.strip()
    if entity_type == "phone":
        return normalize_phone(value)
    if entity_type in {"email", "upi_id", "url", "ifsc", "utr", "transaction_reference"}:
        return value.lower().rstrip(".,;:)")
    if entity_type in {"account_number", "device_identifier"}:
        return re.sub(r"[\s-]", "", value)
    return value


# People write a mobile number in groups far more often than as ten unbroken
# digits -- "98765 43210" on an FIR, "+91-98765-43210" in a signature block.
# PHONE_PATTERN requires the ten digits to be adjacent, so every grouped
# number was invisible to the extractor and never became a node. Only the two
# groupings actually in use are accepted; a permissive rule would weld together
# two unrelated numbers sitting in adjacent table cells.
PHONE_GROUPED_PATTERN = re.compile(
    r"(?<!\d)(?:\+?91[\s-]?)?(?:[6-9]\d{4}[\s-]\d{5}|[6-9]\d{2}[\s-]\d{3}[\s-]\d{4})(?!\d)"
)


def find_phone_numbers(text: str) -> list[str]:
    found = {normalize_phone(match.group(0)) for match in PHONE_PATTERN.finditer(text)}
    found |= {normalize_phone(match.group(0)) for match in PHONE_GROUPED_PATTERN.finditer(text)}
    return sorted(found)


def find_email_addresses(text: str) -> list[str]:
    return sorted({match.group(0).lower() for match in EMAIL_PATTERN.finditer(text)})


def find_account_identifiers(text: str) -> list[str]:
    found = {match.group(1) for match in ACCOUNT_PATTERN.finditer(text)}
    found |= {match.group(0).upper() for match in IFSC_PATTERN.finditer(text)}
    for match in UPI_PATTERN.finditer(text):
        candidate = match.group(0)
        if not EMAIL_PATTERN.fullmatch(candidate):
            found.add(candidate.lower())
    return sorted(found)


def find_transaction_reference(text: str) -> str | None:
    match = UTR_PATTERN.search(text)
    return match.group(1).strip() if match else None


def find_device_identifier(text: str) -> str | None:
    match = DEVICE_PATTERN.search(text)
    return match.group(1).strip() if match else None


# A phone number written in groups, including OCR misreads of the country code such as
# "+9] 87072 93840". The strict phone pattern cannot match those, and without this guard the middle
# group gets read as a rupee amount.
GROUPED_DIGITS_PATTERN = re.compile(r"(?<!\d)\d{4,6}[\s-]\d{4,6}(?!\d)")


def _protected_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges that belong to an identifier or a date, not to a monetary amount.

    Without this, the digits inside `HDFC0012345678` or `12 Mar 2024` get read as rupee values.
    """
    spans: list[tuple[int, int]] = []
    for pattern in (PHONE_PATTERN, PHONE_GROUPED_PATTERN, UTR_PATTERN, ACCOUNT_PATTERN, IFSC_PATTERN, EMAIL_PATTERN, UPI_PATTERN, URL_PATTERN, DEVICE_PATTERN, *DATE_PATTERNS):
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    for match in GROUPED_DIGITS_PATTERN.finditer(text):
        if sum(character.isdigit() for character in match.group(0)) >= 10:
            spans.append((match.start(), match.end()))
    return spans


def find_amount_detail(text: str, *, declared_monetary: bool = False) -> tuple[float, str | None, str, str] | None:
    """Return (value, currency, exact quote, role) for the first plausible amount.

    Currency stays `None` when the source shows only a bare number. Assuming INR because the case
    is Indian would be exactly the kind of common-sense filling the evidence rules forbid.

    `declared_monetary` is for callers reading a cell the source itself labelled as money — a bank
    statement column headed "Amount". There the header is the evidence that the digits are money,
    so the surrounding-words check would only reject a value the source has already declared.
    """
    protected = _protected_spans(text)
    for match in AMOUNT_PATTERN.finditer(text):
        raw_value = match.group("value")
        if not raw_value or not any(character.isdigit() for character in raw_value):
            continue
        start, end = match.span("value")
        if any(begin < end and start < finish for begin, finish in protected):
            continue
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_-/"):
            continue
        if end < len(text) and (text[end].isalnum() or text[end] in "_-/"):
            continue
        try:
            value = float(Decimal(raw_value.replace(",", "")))
        except InvalidOperation:
            continue
        if value < MIN_PLAUSIBLE_AMOUNT:
            continue

        marker = (match.group("currency") or match.group("trailing") or "").strip().lower().rstrip(".")
        currency = CURRENCY_SYMBOLS.get(marker) or ("INR" if marker in {"rupees", "rupaye"} else None)
        quote = match.group(0).strip()

        if currency is None and start > 0 and text[start - 1] in OCR_RUPEE_GLYPHS:
            # OCR reduces the rupee sign to whatever glyph is nearest in shape. Touching the digits
            # is what makes it a marker: "=12,000" is a price tag, "Total = 500" is not.
            currency = "INR"
            quote = text[start - 1 : end]

        if currency is None:
            digits = raw_value.replace(",", "").split(".")[0]
            if value < MIN_BARE_AMOUNT or len(digits) > MAX_BARE_AMOUNT_DIGITS:
                continue
            if not declared_monetary and not MONEY_CONTEXT_PATTERN.search(_fold_ocr_glyphs(_line_around(text, start))):
                # No currency marker and no money word on the line. "SYNTHETIC-ACCOUNT-8233 212,000"
                # is an account row; calling it a payment invents a transaction the source never
                # recorded, which is the single worst thing this extractor can do.
                continue
        return value, currency, quote, classify_amount_role(text, quote, index=start)
    return None


def find_amount(text: str, *, declared_monetary: bool = False) -> tuple[float, str | None, str] | None:
    """The amount alone, for callers that do not care what kind of figure it is."""
    found = find_amount_detail(text, declared_monetary=declared_monetary)
    return (found[0], found[1], found[2]) if found else None


def _relative_day_supersedes(scope: str, raw: str) -> bool:
    """True when a "Today"/"Yesterday" divider appears after this calendar date in the source.

    A chat screen prints the date once and then switches to relative words, so the messages below
    such a divider belong to an unstated day. Reusing the earlier date for them is a fabrication.
    """
    position = scope.find(raw)
    if position == -1:
        return False
    return RELATIVE_DAY_PATTERN.search(scope, position + len(raw)) is not None


def _parse_moment(date_text: str, time_text: str | None, offset: str | None) -> datetime | None:
    candidate = " ".join(part.strip() for part in (date_text, time_text, offset) if part)
    try:
        parsed = date_parser.parse(candidate, dayfirst=True, fuzzy=False)
    except (ValueError, OverflowError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def find_timestamp(text: str, *, context: str | None = None) -> tuple[datetime | None, str | None, str]:
    """Return (parsed UTC datetime, exact quote, precision).

    Two readings are deliberately refused rather than guessed. A clock with no date beside it
    yields `None` — the time of day is observed, the day is not, and letting the parser default the
    date to today is how a 5:58 pm email ended up stamped with the day the report was generated.
    A calendar date that a later "Today" divider supersedes is skipped for the same reason.

    `context` is the wider source the text was cut from; the divider check reads it so a per-block
    scan still sees the divider that appears further down the same screenshot.
    """
    scope = text if context is None else context
    for pattern, precision in TIMESTAMP_RULES:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            if precision == "time_only":
                return None, raw, "time_only"
            groups = match.groupdict()
            if precision == "date_only" and _relative_day_supersedes(scope, raw):
                continue
            parsed = _parse_moment(groups.get("date") or raw, groups.get("time"), groups.get("tz"))
            if parsed is None:
                continue
            return parsed, raw, precision
    return None, None, "unknown"


# ---------------------------------------------------------------------------
# Criminal-network entity vocabulary (SIH26189)
#
# SIH26189 asks for people, locations, vehicles, phone numbers and
# organisations. Phones and account identifiers are handled above; the three
# classes below are new.
#
# Each one is deliberately conservative. A criminal-network graph is only
# useful if its nodes are real, and a false node is worse than a missing one:
# it invents a connection between two files that share nothing. So none of
# these extractors guess from shape alone -- a vehicle needs a real state
# code, an organisation needs a legal-form suffix, and a location needs an
# explicit marker naming it as a place.
# ---------------------------------------------------------------------------

# Registration-plate state and UT codes. Validating against this list is what
# separates "MH 12 DE 1433" from four characters that merely look like a plate.
VEHICLE_STATE_CODES = frozenset(
    """AN AP AR AS BR CG CH DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP
       MZ NL OD OR PB PY RJ SK TN TR TS UA UK UP WB""".split()
)

# MH12DE1433 / MH 12 DE 1433 / MH-12-DE-1433 / DL-8C-AB-1234
# The RTO code carries a trailing letter in several regions -- Delhi writes
# DL 8C AB 1234 -- so the digits may be followed by one.
VEHICLE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<state>[A-Za-z]{2})[\s-]?(?P<rto>\d{1,2}[A-Za-z]?)[\s-]?(?P<series>[A-Za-z]{1,3})[\s-]?(?P<number>\d{4})(?![A-Za-z0-9])"
)
# Bharat series: 22 BH 1234 AB
VEHICLE_BH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<year>\d{2})[\s-]?(?P<bh>BH)[\s-]?(?P<number>\d{4})[\s-]?(?P<series>[A-Za-z]{1,2})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def normalize_vehicle(value: str) -> str:
    """One plate, one spelling. Spacing and hyphens vary with whoever typed it."""
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def find_vehicle_identifiers(text: str) -> list[str]:
    """Registration plates literally present in the text.

    An IFSC code such as HDFC0012345 cannot match: the boundary guards refuse a
    partial read of a longer alphanumeric run, and the state code must be real.
    """
    found: set[str] = set()
    for match in VEHICLE_PATTERN.finditer(text):
        if match.group("state").upper() in VEHICLE_STATE_CODES:
            found.add(normalize_vehicle(match.group(0)))
    for match in VEHICLE_BH_PATTERN.finditer(text):
        found.add(normalize_vehicle(match.group(0)))
    return sorted(found)


# Two different kinds of trailing word, kept apart on purpose.
#
# A *legal form* is not identity. "Shreeji Traders" and "Shreeji Traders Pvt.
# Ltd." are one counterparty written two ways, so the legal form is stripped
# before comparison or the node splits in half.
_ORG_LEGAL_FORM = r"(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Public\s+Limited|Ltd\.?|Limited|LLP|Corporation|Corp\.?|Inc\.?)"

# A *descriptor* is identity. Stripping it would fold "Acme Motors" and "Acme
# Traders" into one node -- inventing a link between two separate businesses.
# A false merge is worse than a split, so these survive normalisation.
_ORG_DESCRIPTOR = (
    r"(?:Bank|Enterprises?|Traders?|Trading\s+Co\.?|Industries|Technologies|Techno|"
    r"Solutions|Services|Associates|Agency|Agencies|Motors|Logistics|Transports?|"
    r"Builders|Constructions?|Infra|Finance|Capital|Foundation|Trust|Society|"
    r"&\s*Sons|and\s+Sons)"
)
_ORG_SUFFIX = rf"(?:{_ORG_DESCRIPTOR}|{_ORG_LEGAL_FORM})"

# An optional "of <Place>" tail keeps "State Bank of India" whole rather than
# truncating it to "State Bank" at the suffix.
ORGANISATION_PATTERN = re.compile(
    rf"\b(?P<name>(?:[A-Z][A-Za-z&.\-]{{1,20}}\s+){{0,3}}[A-Z][A-Za-z&.\-]{{1,20}}"
    rf"\s+{_ORG_SUFFIX}"
    rf"(?:\s+of\s+[A-Z][A-Za-z]{{1,20}}(?:\s+[A-Z][A-Za-z]{{1,20}}){{0,2}})?"
    rf"(?:\s+{_ORG_LEGAL_FORM})?)(?![A-Za-z])"
)


def normalize_organisation(value: str) -> str:
    """Fold to a comparison key. Legal form and punctuation are not identity."""
    folded = value.strip()
    # Repeat: "Pvt. Ltd." is two forms stacked, and one pass would leave "pvt".
    while True:
        stripped = re.sub(rf"[\s,.]+{_ORG_LEGAL_FORM}\s*$", "", folded, flags=re.IGNORECASE)
        if stripped == folded:
            break
        folded = stripped
    folded = re.sub(r"[^a-z0-9]+", " ", folded.casefold()).strip()
    return folded or re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def find_organisations(text: str) -> list[str]:
    return sorted({" ".join(match.group("name").split()) for match in ORGANISATION_PATTERN.finditer(text)})


# A place is recognised only where the source labels it as one. Open-domain
# place-name detection over Indian text produces far more noise than leads and
# would bury the review queue, so a marker is required.
_PLACE_WORD = r"[A-Z][A-Za-z]{1,24}"
_PLACE_PHRASE = rf"{_PLACE_WORD}(?:\s+{_PLACE_WORD}){{0,3}}"

# Each rule says whether the marker sits OUTSIDE the captured name or is part
# of it. "PS Andheri" names Andheri -- the marker is administrative. "Linking
# Road" names Linking Road; dropping "Road" there would leave a fragment that
# is not the name of anywhere.
LOCATION_RULES: tuple[tuple[re.Pattern[str], bool], ...] = (
    # PS Andheri  ·  P.S. Andheri East  ·  Police Station Andheri
    (re.compile(rf"\b(?:P\.?\s?S\.?|Police\s+Station|Thana)\s*[:\-]?\s*(?P<name>{_PLACE_PHRASE})"), True),
    # Andheri Police Station  ·  Andheri Thana
    (re.compile(rf"\b(?P<name>{_PLACE_PHRASE})\s+(?:Police\s+Station|Thana)\b"), True),
    # District Thane  ·  Village Kalwa  ·  Taluka X
    (re.compile(rf"\b(?:District|Distt\.?|Village|Taluka|Tehsil)\s*[:\-]?\s*(?P<name>{_PLACE_PHRASE})"), True),
    # Thane District  ·  Kalwa Taluka
    (re.compile(rf"\b(?P<name>{_PLACE_PHRASE})\s+(?:District|Taluka|Tehsil)\b"), True),
    # Linking Road  ·  Shivaji Nagar  ·  Dadar Chowk  ·  Crawford Market
    (
        re.compile(rf"\b(?P<name>{_PLACE_PHRASE}\s+(?:Road|Marg|Nagar|Colony|Chowk|Market|Bazaar|Chowki|Galli|Vihar|Puram|Pura|Ganj))\b"),
        False,
    ),
)


def normalize_location(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# Administrative markers, stripped only from rules that place them outside the
# name. A greedy phrase can still pull one in from either edge.
_LOCATION_MARKERS = frozenset("police station thana district distt village taluka tehsil".split())


# A word, then a colon: the source is labelling the next field, not naming this one.
_LABEL_AHEAD = re.compile(r"[A-Za-z.]+\s*:")


def find_locations(text: str) -> list[str]:
    """Places the source explicitly marks as places."""
    found: set[str] = set()
    for rule, strip_markers in LOCATION_RULES:
        for match in rule.finditer(text):
            words = match.group("name").split()
            # A form puts its fields side by side: "District: Mumbai Suburban  Date: 12/07/2026".
            # The phrase runs on into the next field's label, and "Date" is capitalised like any
            # place name, so the district was recorded as "Mumbai Suburban Date". A word the source
            # immediately follows with a colon is a label for what comes after it, not part of what
            # came before.
            while len(words) > 1 and _LABEL_AHEAD.match(text, match.end("name") - len(words[-1])):
                words.pop()
            if strip_markers:
                while words and words[0].casefold().rstrip(".") in _LOCATION_MARKERS:
                    words.pop(0)
                while words and words[-1].casefold().rstrip(".") in _LOCATION_MARKERS:
                    words.pop()
            name = " ".join(words)
            if len(normalize_location(name)) >= 3:
                found.add(name)
    return sorted(found)


# Names carry no shape of their own, so a person is read only where the source
# labels the role. Detecting capitalised word runs as names would turn every
# heading and place into a person.
PERSON_LABEL_PATTERN = re.compile(
    r"\b(?P<role>Name|Full\s+Name|Complainant|Complaint\s+By|Accused|Victim|Informant|Witness|"
    r"Beneficiary|Sender|Receiver|Recipient|Payee|Payer|Driver|Owner|Applicant|Suspect|From|To)"
    r"\s*(?:\([^)]{1,20}\))?\s*[:\-]\s*(?P<name>[A-Z][A-Za-z.]{1,20}(?:(?<![A-Za-z]{2}\.)\s+[A-Z][A-Za-z.]{1,20}){0,3})"
)
# Indian records name a parent or spouse to disambiguate: "Ravi Kumar S/o Mohan Lal".
PERSON_RELATION_PATTERN = re.compile(
    r"\b[SDWsdw]\s?/\s?[Oo]\.?\s*(?P<name>[A-Z][A-Za-z.]{1,20}(?:(?<![A-Za-z]{2}\.)\s+[A-Z][A-Za-z.]{1,20}){0,3})"
)
# A report header writes "Accused: Yash Kumar Gupta"; the narrative below it writes "accused Yash
# Yadav was driving". The role is stated either way, and reading only the header form meant every
# name in the body of an FIR was invisible. The name must still be capitalised, so "the accused was
# seen" ends at "was" and yields nothing.
# The role word may be capitalised or not; the name may not. re.IGNORECASE cannot express that --
# it would also relax [A-Z] on the name and let "states that accused Yash" through as a person,
# which is exactly what it did. The role alternatives therefore carry their own case classes.
PERSON_INLINE_ROLE_PATTERN = re.compile(
    r"\b(?P<role>[Aa]ccused|[Cc]omplainant|[Vv]ictim|[Ii]nformant|[Ww]itness|[Ss]uspect|[Dd]eceased"
    r"|[Pp]etitioner|[Rr]espondent|[Dd]river|[Oo]wner)\s+"
    r"(?P<name>[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,3})"
)


# A surveillance note or a statement rarely writes a label. It writes the way an officer speaks:
# "a person identifying himself as Yash Kumar Gupt", "one Mohan Lal was seen", "who gave his name as
# Ravi Kumar". The role is stated as plainly as any header does it, and reading only the labelled
# and inline-role forms left every name in a surveillance note invisible -- which is the one source
# type SIH26189 names that has no header at all.
#
# The introducing phrase is what supplies the role here, so the name still never comes from
# capitalisation alone. The bare legal idiom "one Yash Kumar Gupt" is deliberately not among them:
# it reduces to "one" plus a capitalised word, and read "This is one Rule" as a person.
PERSON_INTRODUCTION_PATTERN = re.compile(
    r"\b(?:identif(?:ying|ied)\s+(?:himself|herself|themselves)\s+as"
    r"|(?:who\s+)?gave\s+(?:his|her|their)\s+name\s+as"
    r"|(?:by\s+)?the\s+name\s+of)\s+"
    r"(?P<name>[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,3})"
)


def normalize_person(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# What a source calls somebody, reduced to the words a case actually turns on. The label is kept
# verbatim in the provenance quote; this is the reading of it, and it is the first thing any
# investigator asks about a name on a page.
#
# `named` and `relative` are deliberately not case roles. "Name: Yash Kumar Gupta" says only that the
# form has a name field, and "S/o Mohan Lal" names a parent for identification -- reporting either
# as "accused" would be the system inventing a role the source never stated.
ROLE_READINGS: dict[str, str] = {
    "name": "named",
    "full name": "named",
    "complainant": "complainant",
    "complaint by": "complainant",
    "informant": "complainant",
    "accused": "accused",
    "suspect": "accused",
    "victim": "victim",
    "deceased": "victim",
    "witness": "witness",
    "driver": "driver",
    "owner": "owner",
    "beneficiary": "beneficiary",
    "sender": "sender",
    "payer": "sender",
    "from": "sender",
    "receiver": "receiver",
    "recipient": "receiver",
    "payee": "receiver",
    "to": "receiver",
    "applicant": "applicant",
    "petitioner": "petitioner",
    "respondent": "respondent",
}

# A name the person gave for themselves, and a name given as somebody's parent or spouse. Both are
# weaker than a role a report assigns, and saying which is which is the point.
SELF_STATED_ROLE = "self-identified"
RELATIVE_ROLE = "relative"

PERSON_PATTERNS = (
    (PERSON_LABEL_PATTERN, None),
    (PERSON_RELATION_PATTERN, RELATIVE_ROLE),
    (PERSON_INLINE_ROLE_PATTERN, None),
    (PERSON_INTRODUCTION_PATTERN, SELF_STATED_ROLE),
)


def _name_before_the_full_stop(raw: str) -> str:
    """Stop a name where its sentence ends.

    The patterns refuse to cross the boundary themselves -- trimming afterwards was not enough,
    because the over-long match had already consumed the next role label and "Accused (1): Yash
    Yadav" was never seen at all. This remains as the tidy-up for a trailing period.

    A dot is allowed inside a name so initials survive -- "R. Kumar", "Yash K." -- but the same
    dot lets a sentence-ending period glue the next capitalised word on: "Complainant: Priya
    Sharma. Accused (1): ..." was read as one person called "Priya Sharma. Accused". An initial is
    one or two characters; anything longer ending in a period is the end of a sentence.
    """
    words: list[str] = []
    for word in " ".join(raw.split()).split(" "):
        words.append(word)
        if word.endswith(".") and len(word.rstrip(".")) > 1:
            break
    return " ".join(words).strip(" .")


def _person_matches(text: str):
    """Every name a source states, with the role it states alongside it."""
    for pattern, fixed_role in PERSON_PATTERNS:
        for match in pattern.finditer(text):
            name = _name_before_the_full_stop(match.group("name"))
            # A label followed by an email or phone is an identifier, not a name.
            if EMAIL_PATTERN.search(name) or any(character.isdigit() for character in name):
                continue
            if len(normalize_person(name)) < 3:
                continue
            if fixed_role is not None:
                role = fixed_role
            else:
                stated = " ".join(match.group("role").split()).casefold()
                role = ROLE_READINGS.get(stated, stated)
            yield name, role, match.group(0)


def find_person_names(text: str) -> list[str]:
    """Names the source attaches to a stated role. Never inferred from capitalisation."""
    return sorted({name for name, _role, _quote in _person_matches(text)})


def find_person_roles(text: str) -> dict[str, str]:
    """What each named person is called by this source.

    The role was being matched and discarded: the extractor recognised "Accused (2): Ravi Kumar"
    and kept only the name, so the first question an investigator asks -- is this the complainant
    or the accused -- was the one thing the system threw away.

    A role is what *this source* says. The same person can be a witness in one file and a suspect
    in another, so nothing here is written to the person; it is recorded against the place it was
    read from. Where two readings collide in one passage the stronger one wins: a report that
    assigns a role outranks a name somebody gave for themselves.
    """
    strength = {SELF_STATED_ROLE: 0, RELATIVE_ROLE: 0, "named": 1}
    roles: dict[str, str] = {}
    for name, role, _quote in _person_matches(text):
        current = roles.get(name)
        if current is None or strength.get(role, 2) > strength.get(current, 2):
            roles[name] = role
    return roles


# ---------------------------------------------------------------------------
# Police report structure (SIH26189 source #1)
#
# An FIR states its own metadata in a header before the narrative begins. These
# read only what the form prints; nothing is inferred from the body text.
# ---------------------------------------------------------------------------

FIR_NUMBER_PATTERN = re.compile(r"\bF\.?\s?I\.?\s?R\.?\s*(?:No\.?|Number)?\s*[:\-]?\s*(?P<value>\d{1,5}\s*/\s*\d{2,4})", re.IGNORECASE)
# "u/s 420 IPC", "under sections 66C, 66D IT Act"
FIR_SECTIONS_PATTERN = re.compile(
    r"\b(?:u/?s|under\s+sections?|sections?)\s*[:\-]?\s*(?P<value>\d{1,4}[A-Z]?(?:\s*(?:,|and|&|/)\s*\d{1,4}[A-Z]?)*)"
    r"(?:\s*(?:of\s+)?(?P<act>IPC|I\.P\.C\.|IT\s+Act|CrPC|BNS|BNSS|NDPS(?:\s+Act)?))?",
    re.IGNORECASE,
)
# The station name must stay on the label's own line. Using `\s` between the words let the match
# run past the newline and swallow the first word of the line below ("Andheri East Offence").
FIR_STATION_PATTERN = re.compile(
    r"\b(?:Police[^\S\n]+Station|P\.?[^\S\n]?S\.?|Thana)[^\S\n]*[:\-][^\S\n]*"
    r"(?P<value>[A-Z][A-Za-z]{1,24}(?:[^\S\n]+[A-Z][A-Za-z]{1,24}){0,3})"
)


def find_fir_number(text: str) -> str | None:
    match = FIR_NUMBER_PATTERN.search(text)
    return re.sub(r"\s+", "", match.group("value")) if match else None


def find_fir_sections(text: str) -> list[str]:
    """Sections invoked, each kept with the act when the source names one."""
    found: list[str] = []
    for match in FIR_SECTIONS_PATTERN.finditer(text):
        act = re.sub(r"\s+", " ", (match.group("act") or "")).strip().upper().replace(".", "")
        for section in re.split(r"\s*(?:,|and|&|/)\s*", match.group("value")):
            section = section.strip().upper()
            if not section:
                continue
            label = f"{section} {act}".strip()
            if label not in found:
                found.append(label)
    return found


def find_police_station(text: str) -> str | None:
    match = FIR_STATION_PATTERN.search(text)
    return " ".join(match.group("value").split()) if match else None


# ---------------------------------------------------------------------------
# Stated roles inside one sentence
#
# A relationship between a person and a vehicle or a place is only read where
# the source writes the verb. "Ravi Kumar was driving MH12DE1433" states one;
# "Ravi Kumar ... MH12DE1433" somewhere on the same page states nothing, and
# reading it as a relationship is the invention this project exists to refuse.
# The match must also stay inside a single sentence -- a subject in one sentence
# and a plate in the next are two separate facts.
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# was driving / drove / riding / travelling in / on board
_DRIVING_VERB = r"(?:driv\w*|rid\w*|travell?\w*\s+in|aboard|on\s+board|using|used)"
# seen at / present at / residing at / located at / arrested at / observed parked at
# A surveillance log is written in a vocabulary of its own -- "observed", "parked", "stationed",
# "waiting" -- and none of it was here, so the source type SIH26189 names for exactly this fact
# produced no presence at all. These are stative: they say something was somewhere. Verbs of
# motion are deliberately absent, because "proceeded towards Andheri East" places nobody there.
_PRESENCE_VERB = (
    r"(?:seen|spotted|sighted|noticed|observed|present|residing|resident|living|located|found"
    r"|arrested|apprehended|met|parked|stationed|waiting|standing|halted|stopped)"
)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text or "") if part.strip()]


def find_person_vehicle_links(text: str) -> list[tuple[str, str, str]]:
    """(person, vehicle, quoted sentence) where one sentence states the person used the vehicle."""
    links: list[tuple[str, str, str]] = []
    for sentence in sentences(text):
        vehicles = find_vehicle_identifiers(sentence)
        if not vehicles or not re.search(_DRIVING_VERB, sentence, re.IGNORECASE):
            continue
        for person in find_person_names(sentence):
            for vehicle in vehicles:
                if (person, vehicle) not in {(item[0], item[1]) for item in links}:
                    links.append((person, vehicle, sentence))
    return links


def find_vehicle_location_links(text: str) -> list[tuple[str, str, str]]:
    """(plate, place, quoted sentence) where one sentence places a vehicle somewhere.

    A surveillance note is mostly this sentence: "Vehicle MH12DE1433 observed parked at Linking
    Road." The presence rule read only people, so the one fact a surveillance log exists to record
    produced no edge at all -- and the recurring-vehicle-at-a-location alert had nothing to fire on.

    A plate has a shape a person's name does not, so unlike a person it needs no stated role.
    """
    links: list[tuple[str, str, str]] = []
    for sentence in sentences(text):
        places = find_locations(sentence)
        if not places or not re.search(_PRESENCE_VERB, sentence, re.IGNORECASE):
            continue
        for plate in find_vehicle_identifiers(sentence):
            for place in places:
                if (plate, place) not in {(item[0], item[1]) for item in links}:
                    links.append((plate, place, sentence))
    return links


def find_person_location_links(text: str) -> list[tuple[str, str, str]]:
    """(person, place, quoted sentence) where one sentence places the person somewhere."""
    links: list[tuple[str, str, str]] = []
    for sentence in sentences(text):
        places = find_locations(sentence)
        if not places or not re.search(_PRESENCE_VERB, sentence, re.IGNORECASE):
            continue
        for person in find_person_names(sentence):
            for place in places:
                if (person, place) not in {(item[0], item[1]) for item in links}:
                    links.append((person, place, sentence))
    return links
