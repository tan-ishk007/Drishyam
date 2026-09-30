"""Synthetic evidence builders.

Everything here is fabricated for testing. No real person, phone number, account, transaction or
uploaded file appears in this module, and nothing in it may be copied from a live case.

Phone numbers use the +91 98765 xxxxx range reserved for fiction in the project's test data.
"""

from __future__ import annotations

from pathlib import Path

from app.evidence_intelligence.ocr import ChatLayout, OCRBlock, OCRResult

CANVAS_WIDTH = 800
CANVAS_HEIGHT = 1200

SYNTHETIC_HEADER_NUMBER = "+91 9876543210"
SYNTHETIC_BENEFICIARY_NUMBER = "9876500011"
SYNTHETIC_UTR = "HDFC0012345678"


# --------------------------------------------------------------------------- text-based evidence


def whatsapp_chat_export(path: Path) -> Path:
    """A Hinglish chat export with a media placeholder and a system notice."""
    path.write_text(
        "12/03/2024, 9:15 pm - Messages are end-to-end encrypted.\n"
        "12/03/2024, 9:16 pm - Ramesh Kumar: bhai is number pe 25000 bhej de\n"
        "12/03/2024, 9:17 pm - Ramesh Kumar: <Media omitted>\n"
        "12/03/2024, 9:18 pm - Ravi: theek hai, UTR: " + SYNTHETIC_UTR + " check kar lena\n"
        "12/03/2024, 9:19 pm - Ramesh Kumar: thanks bhai 🙏\n",
        encoding="utf-8",
    )
    return path


def chat_export_without_timestamps(path: Path) -> Path:
    path.write_text("Ramesh: bhej diya kya\nRavi: haan\n", encoding="utf-8")
    return path


def phishing_email(path: Path, *, amount: str = "Rs 25000") -> Path:
    path.write_text(
        "From: payments@example-bank.test\n"
        "To: victim@example.test\n"
        "Cc: audit@example.test\n"
        "Reply-To: no-reply@example-bank.test\n"
        "Subject: Urgent: pending payment of " + amount + "\n"
        "Date: Tue, 12 Mar 2024 21:15:00 +0530\n"
        "Message-ID: <synthetic-001@example.test>\n"
        "\n"
        "Please transfer " + amount + " to account 123456789012 today.\n"
        "Reference " + SYNTHETIC_UTR + ".\n",
        encoding="utf-8",
    )
    return path


def bank_statement_csv(path: Path, *, amount: str = "25000", reference: str = SYNTHETIC_UTR) -> Path:
    path.write_text(
        "Date,Narration,Reference,Amount,Beneficiary\n"
        f"12/03/2024,UPI transfer,{reference},{amount},ramesh@okexamplebank\n"
        "13/03/2024,UPI transfer,HDFC0099999999,20000,ramesh@okexamplebank\n",
        encoding="utf-8",
    )
    return path


def conflicting_bank_statement_csv(path: Path) -> Path:
    """Same reference as `bank_statement_csv`, different amount — a contradiction candidate."""
    path.write_text(
        "Date,Narration,Reference,Amount,Beneficiary\n"
        f"12/03/2024,UPI transfer,{SYNTHETIC_UTR},20000,ramesh@okexamplebank\n",
        encoding="utf-8",
    )
    return path


def call_log_csv(path: Path) -> Path:
    path.write_text(
        "Date,Number,Call Type,Duration\n"
        f"12/03/2024,{SYNTHETIC_BENEFICIARY_NUMBER},outgoing,142\n"
        "13/03/2024,9876500022,incoming,58\n",
        encoding="utf-8",
    )
    return path


def native_text_pdf(path: Path) -> Path:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 100), "Synthetic complaint statement", fontsize=14)
    page.insert_text((72, 130), f"Transfer of Rs 25000 with reference {SYNTHETIC_UTR}.", fontsize=11)
    page.insert_text((72, 160), "Contact number 9876543210 was used by the complainant.", fontsize=11)
    document.save(path)
    document.close()
    return path


def scanned_pdf(path: Path) -> Path:
    """A PDF whose page carries an image rather than extractable text."""
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.draw_rect(fitz.Rect(50, 50, 500, 300), color=(0, 0, 0), width=1)
    document.save(path)
    document.close()
    return path


# ------------------------------------------------------------------------------ image evidence


def whatsapp_screenshot(path: Path, *, blurry: bool = False, crop_header: bool = False) -> Path:
    """Draw a synthetic chat screenshot. Used for byte/hash checks and real-OCR runs."""
    from PIL import Image, ImageDraw, ImageFilter

    image = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (233, 229, 222))
    draw = ImageDraw.Draw(image)

    if not crop_header:
        draw.rectangle([0, 0, CANVAS_WIDTH, 120], fill=(7, 94, 84))
        draw.text((30, 45), SYNTHETIC_HEADER_NUMBER, fill=(255, 255, 255))

    draw.rounded_rectangle([40, 220, 420, 330], radius=12, fill=(255, 255, 255))
    draw.text((60, 265), "bhai is number pe 25000 bhej de", fill=(20, 20, 20))

    draw.rounded_rectangle([380, 380, 760, 490], radius=12, fill=(220, 248, 198))
    draw.text((400, 425), "theek hai bhej raha hu", fill=(20, 20, 20))

    if blurry:
        image = image.filter(ImageFilter.GaussianBlur(radius=3))

    image.save(path, format="PNG")
    return path


# ------------------------------------------------------------------- OCR stand-ins with geometry


def _block(block_id: str, text: str, bbox: tuple[float, float, float, float], confidence: float) -> OCRBlock:
    return OCRBlock(block_id=block_id, text=text, confidence=confidence, bbox=bbox, page=1)


def whatsapp_ocr_result(
    *,
    header: bool = True,
    blurry: bool = False,
    ambiguous_direction: bool = False,
    include_timestamp: bool = True,
) -> OCRResult:
    """OCR output shaped like a real Tesseract read of `whatsapp_screenshot`.

    Geometry matters more than pixels for the layout, grounding and routing logic under test, and
    the Tesseract binary is not installed in every environment.
    """
    confidence = 40.0 if blurry else 92.0
    blocks: list[OCRBlock] = []

    if header:
        blocks.append(_block("block-1", SYNTHETIC_HEADER_NUMBER, (30.0, 40.0, 300.0, 80.0), confidence))

    # A left-hugging bubble reads as incoming. The ambiguous variant sits inside the centre band on
    # both edges, so neither side is supported and direction must stay unresolved.
    incoming_bbox = (300.0, 220.0, 500.0, 330.0) if ambiguous_direction else (40.0, 220.0, 420.0, 330.0)
    blocks.append(_block("block-2", "bhai is number pe 25000 bhej de", incoming_bbox, confidence))
    blocks.append(_block("block-3", "theek hai bhej raha hu", (380.0, 380.0, 760.0, 490.0), confidence))

    if include_timestamp:
        blocks.append(_block("block-4", "9:16 pm", (600.0, 500.0, 700.0, 530.0), confidence))

    quality_flags: list[str] = []
    if blurry:
        quality_flags.append("blurry")
    if not header:
        quality_flags.append("cropped")

    return OCRResult(
        blocks=blocks,
        width=CANVAS_WIDTH,
        height=CANVAS_HEIGHT,
        mean_confidence=confidence,
        quality_flags=sorted(set(quality_flags)),
    )


class FakeOCRAdapter:
    """Returns a scripted `OCRResult` so OCR-dependent paths run without the Tesseract binary."""

    version = "fake-ocr-v1"

    def __init__(self, result: OCRResult | None = None) -> None:
        self.result = result or whatsapp_ocr_result()

    def read(self, path: Path, *, page: int = 1) -> OCRResult:
        return self.result

    def read_image(self, image, *, page: int = 1) -> OCRResult:
        return self.result


def tesseract_available() -> bool:
    """True when the Tesseract executable can actually be invoked."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


__all__ = [
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "SYNTHETIC_BENEFICIARY_NUMBER",
    "SYNTHETIC_HEADER_NUMBER",
    "SYNTHETIC_UTR",
    "ChatLayout",
    "FakeOCRAdapter",
    "bank_statement_csv",
    "call_log_csv",
    "chat_export_without_timestamps",
    "conflicting_bank_statement_csv",
    "native_text_pdf",
    "phishing_email",
    "scanned_pdf",
    "tesseract_available",
    "whatsapp_chat_export",
    "whatsapp_ocr_result",
    "whatsapp_screenshot",
]
