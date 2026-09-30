"""OCR and layout analysis that return geometry, never a flat string.

Every block carries an id and a bounding box so a field can cite the exact pixels it came from.
Layout analysis is deliberately conservative: it reports what the geometry supports and marks
everything else unknown rather than guessing a chat's orientation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.evidence_intelligence.references import SourceReference

logger = logging.getLogger(__name__)

OCR_ADAPTER_VERSION = "tesseract-blocks-v1"
LAYOUT_ADAPTER_VERSION = "layout-heuristics-v1"

MIN_BLOCK_CONFIDENCE = 30.0
BLURRY_MEAN_CONFIDENCE = 55.0
HEADER_BAND_RATIO = 0.14
# How much closer to one margin a block must sit before its side is considered established.
# OCR returns the extent of the *text*, not of the bubble drawn around it, so a short message
# produces a narrow box: requiring it to reach the edge would leave most messages undecided.
# Asking which margin it hugs works for both short and long messages.
BUBBLE_MARGIN_DOMINANCE = 0.12


@dataclass
class OCRBlock:
    block_id: str
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]
    page: int = 1

    def reference(self, evidence_id: str) -> SourceReference:
        return SourceReference(
            evidence_id=evidence_id,
            kind="ocr_block",
            page=self.page,
            ocr_block_id=self.block_id,
            bbox=self.bbox,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "text": self.text,
            "confidence": round(self.confidence, 2),
            "bbox": [round(value, 2) for value in self.bbox],
            "page": self.page,
        }


def _reads_better(candidate: "OCRResult", baseline: "OCRResult") -> bool:
    """Whether a prepared image gave a genuinely better reading than the untouched one.

    Confidence alone is not enough: an image that yields two very confident fragments has not been
    read better than one that yields the whole page slightly less confidently. Recovered characters
    are weighed alongside the engine's own confidence.
    """
    candidate_text = len(candidate.text.strip())
    baseline_text = len(baseline.text.strip())
    if candidate_text == 0:
        return False
    if baseline_text == 0:
        return True
    confidence_gain = (candidate.mean_confidence or 0) - (baseline.mean_confidence or 0)
    text_gain = (candidate_text - baseline_text) / baseline_text
    return text_gain > 0.05 or (text_gain >= -0.02 and confidence_gain > 3.0)


@dataclass
class OCRResult:
    blocks: list[OCRBlock] = field(default_factory=list)
    width: int = 0
    height: int = 0
    mean_confidence: float | None = None
    engine: str = OCR_ADAPTER_VERSION
    quality_flags: list[str] = field(default_factory=list)
    # What the image was like, and what was done to it before reading. Recorded so a reviewer
    # judging a poor reading can see whether the source or the reader was the problem.
    quality_report: dict[str, Any] = field(default_factory=dict)
    preprocessing_applied: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "width": self.width,
            "height": self.height,
            "mean_confidence": round(self.mean_confidence, 2) if self.mean_confidence is not None else None,
            "quality_flags": self.quality_flags,
            "quality_report": self.quality_report,
            "preprocessing_applied": self.preprocessing_applied,
            "blocks": [block.to_dict() for block in self.blocks],
        }


class OCRAdapter(Protocol):
    """Any OCR engine that can return text with per-block geometry."""

    def read(self, path: Path, *, page: int = 1) -> OCRResult: ...


class TesseractOCRAdapter:
    """pytesseract backed OCR. Uses image_to_data so bounding boxes survive."""

    version = OCR_ADAPTER_VERSION

    def read(self, path: Path, *, page: int = 1) -> OCRResult:
        from PIL import Image

        with Image.open(path) as handle:
            image = handle.convert("RGB")
            return self.read_image(image, page=page)

    def read_image(self, image: Any, *, page: int = 1) -> OCRResult:
        from app.evidence_intelligence import preprocessing

        prepared, report, applied = preprocessing.prepared_for_reading(image)
        result = self._read_once(image, page=page)

        if applied:
            # Preparation is only kept when it actually reads better. Sharpening a page that was
            # already legible can lose thin strokes, so the untouched reading stays the default and
            # has to be beaten on confidence, not merely replaced.
            enhanced = self._read_once(prepared, page=page)
            if _reads_better(enhanced, result):
                result, applied = enhanced, applied
            else:
                applied = []
        result.quality_report = report.to_dict()
        result.preprocessing_applied = applied
        for flag in report.flags:
            if flag not in result.quality_flags:
                result.quality_flags.append(flag)

        # A chat header is light text on a dark bar, which Tesseract reads poorly. When the header
        # band comes back empty, retry just that strip inverted rather than reporting a missing
        # participant identifier for what is the normal appearance of a WhatsApp screenshot.
        if result.height and not any(block.bbox[1] <= result.height * HEADER_BAND_RATIO for block in result.blocks):
            result = self._merge_header_retry(image, result, page=page)
        return result

    def _merge_header_retry(self, image: Any, result: OCRResult, *, page: int) -> OCRResult:
        from PIL import ImageOps

        band_height = max(1, int(result.height * HEADER_BAND_RATIO))
        try:
            band = ImageOps.invert(image.crop((0, 0, result.width, band_height)).convert("RGB"))
        except (OSError, ValueError):
            return result

        header = self._read_once(band, page=page)
        if not header.blocks:
            return result

        # Cropping from the top-left keeps coordinates in the original image's frame.
        renumbered = [
            OCRBlock(
                block_id=f"block-h{index}",
                text=block.text,
                confidence=block.confidence,
                bbox=block.bbox,
                page=page,
            )
            for index, block in enumerate(header.blocks, start=1)
        ]
        merged = [*renumbered, *result.blocks]
        confidences = [block.confidence for block in merged if block.confidence > 0]
        return OCRResult(
            blocks=merged,
            width=result.width,
            height=result.height,
            mean_confidence=sum(confidences) / len(confidences) if confidences else result.mean_confidence,
            quality_flags=_quality_flags(merged, result.mean_confidence, result.height),
        )

    def _read_once(self, image: Any, *, page: int = 1) -> OCRResult:
        import pytesseract
        from pytesseract import Output

        data = pytesseract.image_to_data(image, config="--psm 6", output_type=Output.DICT)
        width, height = image.size
        grouped: dict[tuple[int, int, int], list[int]] = {}
        for index, level in enumerate(data["level"]):
            if level != 5 or not str(data["text"][index]).strip():
                continue
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            grouped.setdefault(key, []).append(index)

        blocks: list[OCRBlock] = []
        confidences: list[float] = []
        for order, (_, indexes) in enumerate(sorted(grouped.items()), start=1):
            words = [str(data["text"][index]).strip() for index in indexes]
            word_confidences = [float(data["conf"][index]) for index in indexes if float(data["conf"][index]) >= 0]
            left = min(float(data["left"][index]) for index in indexes)
            top = min(float(data["top"][index]) for index in indexes)
            right = max(float(data["left"][index]) + float(data["width"][index]) for index in indexes)
            bottom = max(float(data["top"][index]) + float(data["height"][index]) for index in indexes)
            confidence = sum(word_confidences) / len(word_confidences) if word_confidences else 0.0
            confidences.extend(word_confidences)
            blocks.append(
                OCRBlock(
                    block_id=f"block-{order}",
                    text=" ".join(words),
                    confidence=confidence,
                    bbox=(left, top, right, bottom),
                    page=page,
                )
            )

        mean_confidence = sum(confidences) / len(confidences) if confidences else None
        return OCRResult(
            blocks=blocks,
            width=width,
            height=height,
            mean_confidence=mean_confidence,
            quality_flags=_quality_flags(blocks, mean_confidence, height),
        )


def _quality_flags(blocks: list[OCRBlock], mean_confidence: float | None, height: int) -> list[str]:
    """Report degraded sources so downstream scoring can demand review."""
    flags: list[str] = []
    if not blocks:
        flags.append("incomplete")
        return flags
    if mean_confidence is not None and mean_confidence < BLURRY_MEAN_CONFIDENCE:
        flags.append("blurry")
    if sum(1 for block in blocks if block.confidence < MIN_BLOCK_CONFIDENCE) > len(blocks) / 3:
        flags.append("low_quality")
    if height and max(block.bbox[3] for block in blocks) >= height - 2:
        flags.append("cropped")
    if height and min(block.bbox[1] for block in blocks) <= 1:
        flags.append("cropped")
    return sorted(set(flags))


@dataclass
class ChatLayout:
    """What the pixel geometry of a chat screenshot supports — and nothing more."""

    header_blocks: list[OCRBlock] = field(default_factory=list)
    header_identifier: str | None = None
    header_identifier_block: OCRBlock | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    orientation_confident: bool = False
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer": LAYOUT_ADAPTER_VERSION,
            "header_identifier": self.header_identifier,
            "header_identifier_block": self.header_identifier_block.block_id if self.header_identifier_block else None,
            "header_blocks": [block.block_id for block in self.header_blocks],
            "orientation_confident": self.orientation_confident,
            "quality_flags": self.quality_flags,
            "messages": self.messages,
        }


class LayoutAnalysisAdapter(Protocol):
    def analyze(self, result: OCRResult) -> ChatLayout: ...


class ChatScreenshotLayoutAdapter:
    """Heuristic bubble/header analysis.

    Direction is reported only when a block sits clearly on one side of the canvas. Anything in the
    ambiguous middle band is left `unknown` — a wrong direction claim is worse than no claim.
    """

    version = LAYOUT_ADAPTER_VERSION

    MEDIA_MARKERS = ("<media omitted>", "media omitted", "image omitted", "video omitted", "sticker omitted")
    FORWARD_MARKERS = ("forwarded", "forwarded many times")
    CALL_MARKERS = ("missed voice call", "missed video call", "incoming call", "outgoing call", "call ended")

    def analyze(self, result: OCRResult) -> ChatLayout:
        if not result.blocks or not result.width:
            return ChatLayout(quality_flags=result.quality_flags)

        header_cutoff = result.height * HEADER_BAND_RATIO
        header_blocks = [block for block in result.blocks if block.bbox[1] <= header_cutoff]
        body_blocks = [block for block in result.blocks if block.bbox[1] > header_cutoff]

        identifier, identifier_block = _header_identifier(header_blocks)
        messages: list[dict[str, Any]] = []
        oriented = 0

        for index, block in enumerate(body_blocks):
            lowered = block.text.lower()

            # Which margin does this block hug? A left-hugging bubble reads as incoming, a
            # right-hugging one as outgoing. When neither margin clearly wins, the interface
            # orientation is not established and the direction stays unknown — a wrong direction
            # claim is worse than no claim.
            left_gap = block.bbox[0] / result.width
            right_gap = 1 - (block.bbox[2] / result.width)

            if left_gap + BUBBLE_MARGIN_DOMINANCE <= right_gap:
                direction, direction_basis = "incoming", "direct_visual"
                oriented += 1
            elif right_gap + BUBBLE_MARGIN_DOMINANCE <= left_gap:
                direction, direction_basis = "outgoing", "direct_visual"
                oriented += 1
            else:
                direction, direction_basis = None, "unknown"

            messages.append(
                {
                    "message_index": index,
                    "block_id": block.block_id,
                    "text": block.text,
                    "bbox": [round(value, 2) for value in block.bbox],
                    "confidence": round(block.confidence, 2),
                    "direction": direction,
                    "direction_basis": direction_basis,
                    "is_media_placeholder": any(marker in lowered for marker in self.MEDIA_MARKERS),
                    "is_forwarded": any(marker in lowered for marker in self.FORWARD_MARKERS),
                    "is_call_entry": any(marker in lowered for marker in self.CALL_MARKERS),
                }
            )

        flags = list(result.quality_flags)
        if not header_blocks:
            flags.append("cropped")
        if messages and oriented < len(messages) / 2:
            flags.append("ambiguous")

        return ChatLayout(
            header_blocks=header_blocks,
            header_identifier=identifier,
            header_identifier_block=identifier_block,
            messages=messages,
            orientation_confident=bool(messages) and oriented >= len(messages) / 2,
            quality_flags=sorted(set(flags)),
        )


def _header_identifier(header_blocks: list[OCRBlock]) -> tuple[str | None, OCRBlock | None]:
    """Return the participant identifier shown in the header.

    This is only ever a `chat_participant_identifier`. The header of a chat proves who the
    conversation is with, never who sent or received a particular message.
    """
    from app.evidence_intelligence.patterns import PHONE_PATTERN

    for block in header_blocks:
        match = PHONE_PATTERN.search(block.text)
        if match:
            return match.group(0).strip(), block

    for block in header_blocks:
        candidate = block.text.strip()
        if _plausible_participant_name(candidate):
            return candidate, block
    return None, None


# Strings that label a screen rather than name a person. Accepting them produces confident
# nonsense such as chat_participant_identifier = "Transaction Successful".
_HEADER_NOISE = {
    "transaction successful", "payment successful", "transaction failed", "transfer details",
    "payment details", "inbox", "sent", "drafts", "chats", "status", "calls", "settings",
    "search", "details", "receipt", "gmail", "whatsapp", "messages", "notifications",
}


def _plausible_participant_name(candidate: str) -> bool:
    """Whether a header string could identify a person or account rather than label the screen."""
    if not candidate or len(candidate) > 64:
        return False
    if candidate.casefold().strip(" :·-") in _HEADER_NOISE:
        return False

    digits = sum(character.isdigit() for character in candidate)
    # A garbled phone number still identifies the conversation. OCR routinely mangles the country
    # code ("+91 98765..." read as "4919878..."), so a long digit run is accepted even though the
    # strict phone pattern rejected it — the value is stored exactly as read, never "corrected".
    if digits >= 8:
        return True

    letters = sum(character.isalpha() for character in candidate)
    # OCR of an icon row yields fragments like "= L) e" — mostly punctuation, no real word.
    if letters < 3 or letters * 2 < len(candidate):
        return False
    return any(len(word) >= 3 and word.isalpha() for word in candidate.replace("+", " ").split())
