"""One fictional case, generated with the answers written down beside it.

Every file here is invented. No real person, number, plate, account or place is described, and the
material is labelled as synthetic inside the documents themselves so a page that escapes this
directory still says what it is.

The point of this module is not the evidence. It is `GROUND_TRUTH`: a declaration of what a correct
system would find, what it must refuse to find, and where the case is deliberately hard. Without
that, an accuracy claim is an assertion. With it, the claim is a measurement anyone can re-run.

The case is built so that the same identity appears in several sources -- a phone in an FIR, a call
record, a screenshot and a transfer -- because cross-source resolution cannot be demonstrated at
all if every identifier lives in one file.

Four deliberate hard cases, each of which a careless system fails in a specific, visible way:

  1. A handwritten field the page does not resolve. Completing "97?4?8821?" into a whole number is
     fabrication, and no phone beginning 97 exists anywhere else in this case, so an invented one
     is unambiguous.
  2. Two people whose names differ by one letter. "Yash Kumar Gupta" and "Yash Kumar Gupt" are named in
     different sources as different people. Merging them collapses two nodes into a false one.
  3. A timestamp two sources disagree about. Both readings must survive; silently choosing one
     hides a discrepancy an investigator needs to see.
  4. A malformed file. It must fail on its own without taking the rest of the case down with it.

`scripts/run_benchmark.py` ingests these and measures against the declarations below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "generated_evidence" / "benchmark"

SYNTHETIC_BANNER = "SYNTHETIC BENCHMARK MATERIAL - FICTIONAL - NOT A REAL RECORD"

# --------------------------------------------------------------------------- the cast

YASH = "Yash Kumar Gupta"
YASH_LOOKALIKE = "Yash Kumar Gupt"  # a different person, named in a different source
RAVI = "Ravi Kumar"
MOHAN = "Mohan Lal"
PRIYA = "Priya Sharma"

YASH_PHONE = "+919876543210"
RAVI_PHONE = "+919988776655"
MOHAN_PHONE = "+919123456789"

PLATE_A = "MH12DE1433"
PLATE_B = "MH04AB2211"

ORG = "Skyline Manpower Pvt Ltd"
UPI = "skyline.manpower@upi"
ACCOUNT = "123456789012"
UTR = "SYNBEN202607121947"

# The two readings of one call. The FIR narrative and the call record disagree by half an hour.
# The window an investigator would declare for this case: the evening of the incident. Several
# rules only mean anything against a declared window -- contact "before the incident" has no
# referent without one -- so the benchmark declares one rather than leaving those rules untested.
INCIDENT_WINDOW = ("2026-07-12T21:00:00+00:00", "2026-07-12T23:59:00+00:00")

FIR_CALL_TIME = "21:15"
CDR_CALL_TIME = "21:45"

# The handwritten field. A system that completes it invents a number in a range nothing else in
# this case uses, which is what makes the fabrication measurable rather than a matter of opinion.
SMUDGED_FIELD = "97?4?8821?"
FABRICATION_PREFIX = "97"

# Two of the numbers in this CDR are recorded against one handset.
#
# It is the single most useful thing a CDR carries beyond the calls themselves: one person running
# two numbers leaves exactly this trace, and no amount of call-pattern analysis finds it. The third
# number sits on its own handset so the rule has something to stay silent about.
HANDSET_SHARED = "358240051111110"
HANDSET_ALONE = "358240052222220"


def _font(size: int, *, bold: bool = False):
    """A real scalable face, or the generator silently produces a different benchmark.

    The fallback is not a cosmetic downgrade. `load_default()` returns a small bitmap face that
    ignores `size`, so a screenshot built on it carries text a fraction of the intended height --
    and the blurred screenshot, whose whole job is to be degraded but still readable, comes out
    with no recoverable text at all. That file then fails ingest instead of being marked a
    degraded source, and the benchmark quietly measures something else.

    So the Windows and macOS paths are listed beside the Linux ones: this script runs on a
    developer's machine as often as in the container, and both have to produce the same files.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError(
        "No scalable font found. Install DejaVu (Linux) or run where Arial exists; the bitmap "
        "fallback produces a benchmark that does not match the one this script documents."
    )


# --------------------------------------------------------------------------- ground truth


@dataclass(frozen=True)
class ExpectedEntity:
    """An identity a correct system finds, and the files it must be traceable to."""

    entity_type: str
    normalized_value: str
    label: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedRelation:
    subject: str
    predicate: str
    object: str
    note: str


@dataclass(frozen=True)
class GroundTruth:
    entities: tuple[ExpectedEntity, ...]
    relations: tuple[ExpectedRelation, ...]
    must_not_merge: tuple[tuple[str, str], ...]
    forbidden_phone_prefix: str
    conflicting_readings: tuple[str, ...]
    malformed_file: str
    degraded_files: tuple[str, ...] = field(default=())
    # The entity types this ground truth lists *completely*, and therefore the only ones where
    # precision means anything.
    #
    # Recall can be measured for every type: it asks how much of what is declared was found, and a
    # partial list still answers that. Precision asks the opposite -- how much of what was found is
    # real -- and that question needs the list to be exhaustive, or a correctly extracted entity
    # nobody bothered to annotate is scored as an error.
    #
    # Locations, references and amounts are deliberately absent. The documents mention a district, a
    # transaction reference and several sums that are perfectly real and simply not part of what
    # this benchmark asserts, so measuring precision against them would punish the system for being
    # right.
    exhaustive_types: tuple[str, ...] = ("person", "vehicle", "organisation", "account", "phone", "upi")
    # Patterns deliberately planted in the evidence, and the rule each one should raise.
    #
    # Measuring extraction is not the same as measuring detection. A benchmark that only counted
    # entities would score full marks on a case whose rules never fired, so what was planted is
    # declared here and the harness checks each one was actually found.
    planted_patterns: tuple[tuple[str, str], ...] = (
        ("SHARED_DEVICE", "two numbers in the CDR are recorded against one handset"),
        ("PRE_INCIDENT_COMMUNICATION", "repeated contact in the hours before the declared incident"),
        ("RELAY_CONTACT", "a contacts b, then b contacts c, inside a short window"),
    )


GROUND_TRUTH = GroundTruth(
    entities=(
        ExpectedEntity("phone", "9876543210", YASH_PHONE, ("fir_primary", "cdr", "screenshot_plain", "transactions")),
        ExpectedEntity("phone", "9988776655", RAVI_PHONE, ("fir_primary", "cdr", "screenshot_dark")),
        ExpectedEntity("phone", "9123456789", MOHAN_PHONE, ("cdr", "surveillance")),
        ExpectedEntity("person", "yash kumar gupta", YASH, ("fir_primary", "screenshot_plain")),
        ExpectedEntity("person", "yash kumar gupt", YASH_LOOKALIKE, ("surveillance",)),
        ExpectedEntity("person", "ravi kumar", RAVI, ("fir_primary", "fir_supplementary")),
        ExpectedEntity("person", "mohan lal", MOHAN, ("fir_supplementary", "surveillance")),
        ExpectedEntity("person", "priya sharma", PRIYA, ("fir_primary",)),
        ExpectedEntity("vehicle", "MH12DE1433", PLATE_A, ("fir_supplementary", "surveillance")),
        ExpectedEntity("vehicle", "MH04AB2211", PLATE_B, ("surveillance",)),
        ExpectedEntity("location", "linking road", "Linking Road", ("surveillance",)),
        ExpectedEntity("location", "andheri east", "Andheri East", ("fir_primary", "surveillance")),
        ExpectedEntity("location", "bandra", "Bandra Police Station", ("fir_primary", "fir_supplementary")),
        ExpectedEntity("organisation", "skyline manpower", ORG, ("fir_primary",)),
        ExpectedEntity("upi", UPI, UPI, ("transactions", "screenshot_plain")),
        ExpectedEntity("account", ACCOUNT, ACCOUNT, ("transactions", "fir_supplementary")),
    ),
    relations=(
        ExpectedRelation(YASH_PHONE, "CALLED", RAVI_PHONE, "two calls in the CDR before the incident window"),
        ExpectedRelation(YASH_PHONE, "CALLED", MOHAN_PHONE, "one call in the CDR"),
        ExpectedRelation(PLATE_A, "LOCATED_AT", "Linking Road", "the surveillance note places the vehicle there twice"),
        ExpectedRelation(MOHAN, "USED_VEHICLE", PLATE_A, "the supplementary report names him as the driver"),
    ),
    must_not_merge=(("yash kumar gupta", "yash kumar gupt"),),
    forbidden_phone_prefix=FABRICATION_PREFIX,
    conflicting_readings=(FIR_CALL_TIME, CDR_CALL_TIME),
    malformed_file="malformed",
    degraded_files=("screenshot_blurred", "screenshot_dark"),
)


# --------------------------------------------------------------------------- the evidence


def _fir_primary() -> Path:
    target = OUTPUT / "fir_primary_synthetic.pdf"
    pdf = canvas.Canvas(str(target), pagesize=A4)
    _, height = A4
    lines = [
        SYNTHETIC_BANNER,
        "",
        "FIRST INFORMATION REPORT",
        "FIR No: 0142/2026        Police Station: Bandra Police Station",
        "District: Mumbai Suburban        Date: 12/07/2026",
        "",
        f"Complainant: {PRIYA}",
        f"Accused (1): {YASH}, contact {YASH_PHONE}",
        f"Accused (2): {RAVI}, contact {RAVI_PHONE}",
        f"Organisation named in the complaint: {ORG}",
        "",
        "BRIEF FACTS",
        f"The complainant states that she was contacted by {YASH} on {YASH_PHONE} regarding",
        f"an employment offer at {ORG}. She states that a call was received at {FIR_CALL_TIME} hrs on",
        "12/07/2026 and that she was asked to travel to Andheri East the same evening.",
        f"She further states that {RAVI} spoke to her on {RAVI_PHONE} and confirmed the arrangement.",
        "",
        "This is fictional benchmark material generated for system validation only.",
    ]
    text = pdf.beginText(48, height - 60)
    text.setFont("Helvetica", 11)
    for line in lines:
        text.textLine(line)
    pdf.drawText(text)
    pdf.save()
    return target


def _fir_supplementary() -> Path:
    """The supplementary report, carrying the handwritten field that does not resolve."""
    target = OUTPUT / "fir_supplementary_synthetic.pdf"
    pdf = canvas.Canvas(str(target), pagesize=A4)
    _, height = A4
    lines = [
        SYNTHETIC_BANNER,
        "",
        "SUPPLEMENTARY POLICE REPORT",
        "FIR No: 0142/2026        Police Station: Bandra Police Station",
        "Date: 13/07/2026",
        "",
        f"Vehicle used: {PLATE_A}",
        f"Driver: {MOHAN}",
        f"Account stated by the complainant: {ACCOUNT}",
        f"Accused (2) named in the primary report: {RAVI}",
        "",
        "The following number was written by hand on the complaint form and could not be read",
        f"in full at the time of scanning: {SMUDGED_FIELD}",
        "It is recorded here exactly as it appears and has not been completed.",
        "",
        "This is fictional benchmark material generated for system validation only.",
    ]
    text = pdf.beginText(48, height - 60)
    text.setFont("Helvetica", 11)
    for line in lines:
        text.textLine(line)
    pdf.drawText(text)
    pdf.save()
    return target


def _screenshot(name: str, *, dark: bool, blur: float) -> Path:
    """A chat screenshot, optionally in dark mode and optionally out of focus."""
    target = OUTPUT / f"{name}.png"
    background = (18, 20, 24) if dark else (250, 248, 244)
    ink = (232, 232, 232) if dark else (24, 24, 24)
    bubble = (36, 42, 48) if dark else (222, 246, 214)

    image = Image.new("RGB", (900, 1200), background)
    draw = ImageDraw.Draw(image)
    draw.text((28, 24), SYNTHETIC_BANNER, fill=ink, font=_font(17, bold=True))
    draw.text((28, 60), YASH_PHONE if not dark else RAVI_PHONE, fill=ink, font=_font(26, bold=True))

    messages = (
        [
            ("12/07/2026 20:40", f"{YASH} here. Reporting for the Andheri East work."),
            ("12/07/2026 20:52", f"Send the fee to {UPI} before you travel."),
            ("12/07/2026 21:05", "Confirm once it is done."),
        ]
        if not dark
        else [
            ("12/07/2026 21:20", f"Call {RAVI_PHONE} when you reach."),
            ("12/07/2026 21:26", "The pickup is arranged for tonight."),
            ("12/07/2026 21:31", "Do not discuss this on the phone."),
        ]
    )

    y = 140
    for stamp, body in messages:
        draw.rounded_rectangle((28, y, 872, y + 200), radius=18, fill=bubble)
        draw.text((52, y + 24), stamp, fill=ink, font=_font(20))
        for index, chunk in enumerate([body[i : i + 44] for i in range(0, len(body), 44)]):
            draw.text((52, y + 66 + index * 40), chunk, fill=ink, font=_font(26))
        y += 240

    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    image.save(target)
    return target


def _cdr() -> Path:
    """A call detail record. The A-party and B-party columns are what make it a CDR."""
    target = OUTPUT / "cdr_synthetic.csv"
    rows = [
        "a_party,b_party,date,time,duration_seconds,cell_id,call_type,imei",
        f"{YASH_PHONE},{RAVI_PHONE},12/07/2026,19:47,212,MUM-BAN-0142,outgoing,{HANDSET_SHARED}",
        f"{YASH_PHONE},{RAVI_PHONE},12/07/2026,20:14,96,MUM-BAN-0142,outgoing,{HANDSET_SHARED}",
        f"{YASH_PHONE},{MOHAN_PHONE},12/07/2026,20:51,143,MUM-AND-0207,outgoing,{HANDSET_SHARED}",
        # The same call the FIR narrative places at 21:15. The record says 21:45.
        f"{RAVI_PHONE},{YASH_PHONE},12/07/2026,{CDR_CALL_TIME},64,MUM-AND-0207,incoming,{HANDSET_ALONE}",
        # Mohan's number appears on the handset Yash's number uses. One person, two numbers, or
        # one handset passed between two people -- the record says which numbers, never which of
        # those it was.
        f"{MOHAN_PHONE},{RAVI_PHONE},12/07/2026,22:03,38,MUM-AND-0207,outgoing,{HANDSET_SHARED}",
    ]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return target


def _transactions() -> Path:
    target = OUTPUT / "transactions_synthetic.csv"
    rows = [
        "date,amount,currency,sender,receiver,account_number,reference,narration",
        f"2026-07-12 20:58,25000.00,INR,{PRIYA},{UPI},{ACCOUNT},{UTR},Synthetic transfer for benchmark",
        f"2026-07-12 21:34,18000.00,INR,{PRIYA},{UPI},{ACCOUNT},SYNBEN202607122134,Synthetic second transfer",
        f"2026-07-13 09:12,9500.00,INR,{UPI},{YASH_PHONE},{ACCOUNT},SYNBEN202607130912,Synthetic onward transfer",
    ]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return target


def _surveillance() -> Path:
    """The note that introduces the near-duplicate name and the second vehicle."""
    target = OUTPUT / "surveillance_note_synthetic.txt"
    body = f"""{SYNTHETIC_BANNER}

SURVEILLANCE NOTE
Observation post: Linking Road, Bandra West
Date: 12/07/2026

19:40 hrs - Vehicle {PLATE_A} observed parked at Linking Road. Driver remained in the vehicle.
20:05 hrs - A person identifying himself as {YASH_LOOKALIKE} was seen speaking to the driver.
            This is not the accused named in FIR 0142/2026 and is recorded separately.
20:48 hrs - {MOHAN}, contact {MOHAN_PHONE}, was observed entering vehicle {PLATE_A}.
21:30 hrs - Vehicle {PLATE_A} left Linking Road towards Andheri East.
22:15 hrs - Second vehicle {PLATE_B} observed at Linking Road. No occupant identified.

This is fictional benchmark material generated for system validation only.
"""
    target.write_text(body, encoding="utf-8")
    return target


def _malformed() -> Path:
    """A file that claims to be a CSV and is not one.

    A quote is opened and never closed, and the row widths disagree. The case must survive it.
    """
    target = OUTPUT / "malformed_synthetic.csv"
    target.write_bytes(
        b"a_party,b_party,date,time\n"
        b'"+919876543210,+919988776655,12/07/2026,19:47\n'
        b"\x00\x01\x02 not text at all \xff\xfe\n"
        b"only,two\n"
    )
    return target


# --------------------------------------------------------------------------- assembly

# The declared source category for each file, which is what tells the extractor which structure to
# read. The keys are the names GROUND_TRUTH refers to.
ARTIFACTS: dict[str, str] = {
    "fir_primary": "complaint_fir",
    "fir_supplementary": "police_report",
    "screenshot_plain": "whatsapp_screenshot",
    "screenshot_dark": "whatsapp_screenshot",
    "screenshot_blurred": "whatsapp_screenshot",
    "cdr": "cdr",
    "transactions": "bank_statement",
    "surveillance": "surveillance",
    "malformed": "cdr",
}


def generate() -> dict[str, Path]:
    """Write the case to disk and return it keyed by the names the ground truth uses."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    return {
        "fir_primary": _fir_primary(),
        "fir_supplementary": _fir_supplementary(),
        "screenshot_plain": _screenshot("screenshot_plain_synthetic", dark=False, blur=0.0),
        "screenshot_dark": _screenshot("screenshot_dark_synthetic", dark=True, blur=0.0),
        "screenshot_blurred": _screenshot("screenshot_blurred_synthetic", dark=False, blur=2.0),
        "cdr": _cdr(),
        "transactions": _transactions(),
        "surveillance": _surveillance(),
        "malformed": _malformed(),
    }


if __name__ == "__main__":
    for name, path in sorted(generate().items()):
        print(f"{name:22} {path}")
