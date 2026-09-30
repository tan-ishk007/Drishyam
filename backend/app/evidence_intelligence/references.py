"""One provenance address shared by every extractor, so any field can point back at its source.

A source reference must be able to name a file, a PDF page, a line range in a text export, an OCR
block and its pixel region, an email header, a CSV row/column, or a document paragraph.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

SourceKind = Literal[
    "file",
    "page",
    "line_range",
    "ocr_block",
    "image_region",
    "email_header",
    "email_body",
    "table_cell",
    "table_row",
    "paragraph",
    "chat_message",
    "file_metadata",
    "reviewer_decision",
]


@dataclass(frozen=True)
class SourceReference:
    evidence_id: str
    kind: SourceKind = "file"
    sha256: str | None = None
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    ocr_block_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    header_name: str | None = None
    row: int | None = None
    column: str | None = None
    paragraph_index: int | None = None
    message_index: int | None = None
    review_decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = list(self.bbox) if self.bbox else None
        return payload

    @property
    def locator(self) -> str:
        """Short human-readable address for review UIs and report footnotes."""
        if self.kind == "ocr_block" and self.ocr_block_id:
            return f"image:{self.ocr_block_id}"
        if self.kind == "image_region" and self.bbox:
            return "image:region:" + ",".join(str(int(value)) for value in self.bbox)
        if self.kind == "page":
            return f"page:{self.page}"
        if self.kind == "line_range":
            return f"line:{self.line_start}" if self.line_start == self.line_end else f"line:{self.line_start}-{self.line_end}"
        if self.kind == "email_header" and self.header_name:
            return f"header:{self.header_name}"
        if self.kind in {"table_cell", "table_row"}:
            return f"row:{self.row}" + (f":{self.column}" if self.column else "")
        if self.kind == "paragraph":
            return f"paragraph:{self.paragraph_index}"
        if self.kind == "chat_message":
            return f"message:{self.message_index}"
        if self.kind == "reviewer_decision" and self.review_decision_id:
            return f"review:{self.review_decision_id}"
        if self.kind == "file_metadata":
            return "file:metadata"
        return "file"


def from_dict(payload: dict[str, Any]) -> SourceReference:
    bbox = payload.get("bbox")
    known = {field for field in SourceReference.__dataclass_fields__}
    values = {key: value for key, value in payload.items() if key in known}
    values["bbox"] = tuple(float(value) for value in bbox) if bbox else None
    return SourceReference(**values)
