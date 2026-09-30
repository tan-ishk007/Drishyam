"""Show a stored statement where it lives in the file it was read from.

Every relationship, entity and finding in this system already carries a source reference -- a cell,
a line, a page, an image region. Until now that reference could be printed but not opened, so the
claim "every statement can be traced to its source" was true of the data and invisible to the
person who had to act on it.

This assembles what a viewer needs to show one evidence file and mark the place a reference points
at. Nothing here re-reads or re-interprets the evidence: the regions come from the OCR artifact
written at ingest, the rows come from the file itself, and the lines come from the extraction units
recorded at the time. A viewer built on freshly re-run extraction would show a reader something the
case was never decided on.

Three shapes, because three is how many ways a file can be looked at:

    image  -- the picture, plus the text regions found on it and where they sit
    table  -- the header and rows, addressed by row number and column name
    text   -- numbered lines, addressed by line number and page

Two kinds of mark, and the difference between them is the difference between two questions:

    cited       the one place the stored reference points at -- "this claim was read here"
    occurrence  every other place in the same file that carries the same value -- "and here is
                everywhere else this value appears"

A reviewer asks both. The first is provenance and the second is context: a UPI handle cited once in
the sender column of row 2 may also sit in the receiver column of rows 3 and 4, and a panel that
showed only the citation would have hidden two thirds of what the file says about it.

The marks are *located*, never invented. When a reference cannot be resolved to a place in the file
the view says so and marks nothing, because a box drawn in the wrong place is worse than no box at
all -- it tells a reviewer they have verified something they have not.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import EvidenceFile, RawExtractionArtifact
from app.services.storage import get_private_path

logger = logging.getLogger(__name__)

VIEW_VERSION = "source-view-v1"

# Text files are shown from their own bytes. Anything else that reads as text -- a PDF above all --
# is shown from the units recorded at extraction, because those are what the case was built on.
PLAIN_TEXT_SUFFIXES = {".txt", ".log", ".md", ".eml", ".json"}
TABLE_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}
IMAGE_PREFIX = "image/"

# A file this size is not something a reviewer scrolls; it is something they download.
MAX_TEXT_LINES = 4000
MAX_TABLE_ROWS = 2000

# A PDF page is rendered at twice its natural size so the marks sit on readable text rather than on
# a thumbnail. Higher costs bandwidth for no gain on a screen.
PDF_RENDER_SCALE = 2.0

# A search string longer than this is more likely to span a line break than to match, and a line
# that wraps in the file will never be found whole.
PDF_SEARCH_LIMIT = 80


@dataclass
class Region:
    """One text region found on an image, in the image's own pixel coordinates."""

    id: str
    text: str
    bbox: tuple[float, float, float, float]
    page: int
    confidence: float | None = None
    highlight: bool = False
    cited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "bbox": [round(value, 2) for value in self.bbox],
            "page": self.page,
            "confidence": self.confidence,
            "highlight": self.highlight,
            "cited": self.cited,
        }


@dataclass
class Row:
    number: int
    cells: dict[str, str]
    highlight: bool = False
    highlight_columns: list[str] = field(default_factory=list)
    cited: bool = False
    cited_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "cells": self.cells,
            "highlight": self.highlight,
            "highlight_columns": self.highlight_columns,
            "cited": self.cited,
            "cited_columns": self.cited_columns,
        }


@dataclass
class Line:
    number: int
    text: str
    page: int | None = None
    highlight: bool = False
    cited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "text": self.text,
            "page": self.page,
            "highlight": self.highlight,
            "cited": self.cited,
        }


@dataclass
class SourceView:
    evidence_id: str
    original_name: str
    media_type: str
    kind: str
    located: bool
    highlight_summary: str
    occurrence_summary: str = ""
    note: str | None = None
    width: int | None = None
    height: int | None = None
    page_count: int | None = None
    # True when the file can be shown as a rendered page carrying marks, rather than only as text.
    # A PDF is a picture of a document, and marking the page is the only way to show a reader the
    # place rather than tell them its number.
    page_image: bool = False
    page_number: int | None = None
    regions: list[Region] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    # The file's own bytes, line by line, for a table -- so a reviewer can switch from the parsed
    # grid to the text that actually arrived. A parsed view is an interpretation, however faithful.
    raw_lines: list[Line] = field(default_factory=list)
    truncated: bool = False
    view_version: str = VIEW_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "original_name": self.original_name,
            "media_type": self.media_type,
            "kind": self.kind,
            "located": self.located,
            "highlight_summary": self.highlight_summary,
            "occurrence_summary": self.occurrence_summary,
            "note": self.note,
            "width": self.width,
            "height": self.height,
            "page_count": self.page_count,
            "page_image": self.page_image,
            "page_number": self.page_number,
            "regions": [item.to_dict() for item in self.regions],
            "header": self.header,
            "rows": [item.to_dict() for item in self.rows],
            "lines": [item.to_dict() for item in self.lines],
            "raw_lines": [item.to_dict() for item in self.raw_lines],
            "truncated": self.truncated,
            "view_version": self.view_version,
        }


@dataclass(frozen=True)
class Target:
    """Where in the file to look, as the stored reference describes it."""

    value: str | None = None
    row: int | None = None
    column: str | None = None
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    block_id: str | None = None

    @classmethod
    def from_reference(cls, reference: dict[str, Any] | None, value: str | None = None) -> "Target":
        reference = reference or {}
        return cls(
            value=value,
            row=reference.get("row"),
            column=reference.get("column"),
            page=reference.get("page"),
            line_start=reference.get("line_start"),
            line_end=reference.get("line_end"),
            block_id=reference.get("ocr_block_id"),
        )


# --------------------------------------------------------------------------- matching


def _fold(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _contains(haystack: str, needle: str) -> bool:
    """Does this text contain that value, ignoring how either is punctuated?

    A number is written "+91 98765 43210" in a chat header and "9876543210" in a question, and OCR
    puts spaces wherever it likes. Comparing the alphanumerics is the only comparison that holds.
    """
    folded = _fold(needle)
    return bool(folded) and folded in _fold(haystack)


def _artifact(db: Session, evidence_id: str, layer: str) -> dict[str, Any] | None:
    artifact = db.scalar(
        select(RawExtractionArtifact)
        .where(RawExtractionArtifact.evidence_id == evidence_id, RawExtractionArtifact.layer == layer)
        .order_by(RawExtractionArtifact.created_at.desc())
    )
    return (artifact.payload_json or {}) if artifact else None


# --------------------------------------------------------------------------- image


def _image_view(db: Session, evidence: EvidenceFile, target: Target) -> SourceView:
    ocr = _artifact(db, evidence.id, "ocr") or {}
    width, height = ocr.get("width"), ocr.get("height")
    regions = [
        Region(
            id=str(block.get("block_id") or f"block-{index}"),
            text=str(block.get("text") or ""),
            bbox=tuple(float(value) for value in (block.get("bbox") or (0, 0, 0, 0))),  # type: ignore[arg-type]
            page=int(block.get("page") or 1),
            confidence=block.get("confidence"),
        )
        for index, block in enumerate(ocr.get("blocks") or [], start=1)
    ]

    view = SourceView(
        evidence_id=evidence.id,
        original_name=evidence.original_name,
        media_type=evidence.detected_mime or "application/octet-stream",
        kind="image",
        located=False,
        highlight_summary="",
        width=width,
        height=height,
        page_count=1,
        regions=regions,
    )

    if not regions:
        view.note = "No text regions were recorded for this image, so a region cannot be marked on it."
        return view

    # A named block is the most exact thing a reference can carry, so it is the citation.
    if target.block_id:
        for region in regions:
            if region.id == target.block_id:
                region.cited = region.highlight = True

    # Then everywhere else on the page that carries the same value. The stored bbox for an image
    # record covers the whole canvas -- true, and useless to look at -- so the value does the work.
    if target.value:
        for region in regions:
            if _contains(region.text, target.value):
                region.highlight = True

    cited = [region for region in regions if region.cited]
    marked = [region for region in regions if region.highlight]

    if cited:
        view.located = True
        view.highlight_summary = f"region {cited[0].id} reading “{cited[0].text[:60]}”"
    elif marked:
        # Nothing named one region, so the first place the value appears is what was read.
        marked[0].cited = True
        view.located = True
        view.highlight_summary = f"text region reading “{marked[0].text[:60]}”"
    else:
        view.note = (
            "This image is the source, but the exact region could not be located on it. "
            "The value may have been read from the image as a whole rather than from one region."
        )
        return view

    others = len(marked) - 1 if marked else 0
    if others > 0:
        view.occurrence_summary = f"also appears in {others} other region{'' if others == 1 else 's'} on this image"
    return view


# --------------------------------------------------------------------------- table


def _read_rows(path: Path, suffix: str) -> tuple[list[str], list[dict[str, str]]]:
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd

        frame = pd.read_excel(path).fillna("")
        header = [str(column) for column in frame.columns]
        return header, [{str(key): str(value) for key, value in record.items()} for record in frame.to_dict(orient="records")]

    text = path.read_text(encoding="utf-8", errors="replace")
    delimiter = "\t" if suffix == ".tsv" else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = list(reader.fieldnames or [])
    return header, [{key: str(value) if value is not None else "" for key, value in record.items() if key} for record in reader]


def _mark_raw_lines(view: SourceView, path: Path, target: Target) -> None:
    """Carry the file's own text alongside the parsed grid.

    A parsed table is an interpretation, however faithful, and a reviewer checking a claim against
    a record is entitled to the bytes that arrived. Only a text-shaped table can be shown this way;
    a spreadsheet has no lines to show.
    """
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    for index, content in enumerate(text.splitlines()[:MAX_TEXT_LINES], start=1):
        line = Line(number=index, text=content)
        # Row 1 of the file is the header, and the parsed rows are numbered from 2, so the two
        # numberings already agree -- the cited row is the file line of the same number.
        line.cited = target.row is not None and index == target.row
        line.highlight = line.cited or bool(target.value and _contains(content, target.value))
        view.raw_lines.append(line)


def _table_view(evidence: EvidenceFile, path: Path, suffix: str, target: Target) -> SourceView:
    header, records = _read_rows(path, suffix)
    truncated = len(records) > MAX_TABLE_ROWS

    rows: list[Row] = []
    # Row 1 is the header, so the first record is row 2 -- the same numbering the extractor used
    # when it wrote the reference, and the same one a spreadsheet shows.
    for offset, record in enumerate(records[:MAX_TABLE_ROWS], start=2):
        rows.append(Row(number=offset, cells=record))

    view = SourceView(
        evidence_id=evidence.id,
        original_name=evidence.original_name,
        media_type=evidence.detected_mime or "text/csv",
        kind="table",
        located=False,
        highlight_summary="",
        header=header,
        rows=rows,
        truncated=truncated,
    )

    # The citation: the one cell the stored reference names.
    if target.row is not None:
        for row in rows:
            if row.number == target.row:
                row.cited = row.highlight = True
                if target.column and target.column in row.cells:
                    # Only the cited list. The cited cell is where the claim was read, which is
                    # frequently not a cell holding the value being traced: a relationship's
                    # reference points at its subject, and a reader opening an entity through that
                    # relationship is usually looking for the object.
                    row.cited_columns = [target.column]

    # Then every other cell in the file carrying the same value. A handle cited once as a sender
    # may sit three more times as a receiver, and a panel that showed only the citation would have
    # hidden most of what this file says about it.
    if target.value:
        for row in rows:
            hits = [name for name, cell in row.cells.items() if _contains(cell, target.value)]
            if hits:
                row.highlight = True
                row.highlight_columns = sorted(set(row.highlight_columns) | set(hits))

    cited = [row for row in rows if row.cited]
    marked = [row for row in rows if row.highlight]

    if cited:
        view.located = True
        view.highlight_summary = f"row {cited[0].number}" + (f", column “{target.column}”" if target.column else "")
    elif marked:
        marked[0].cited, marked[0].cited_columns = True, list(marked[0].highlight_columns)
        view.located = True
        view.highlight_summary = f"row {marked[0].number}" + (
            f", column “{marked[0].cited_columns[0]}”" if marked[0].cited_columns else ""
        )
    else:
        view.note = "This table is the source, but the cited row could not be located in it."
        return view

    citations = {(row.number, column) for row in rows if row.cited for column in row.cited_columns}
    others = sum(1 for row in marked for column in row.highlight_columns if (row.number, column) not in citations)
    if others > 0:
        view.occurrence_summary = f"this value appears in {others} cell{'' if others == 1 else 's'} of this file"

    _mark_raw_lines(view, path, target)
    return view


# --------------------------------------------------------------------------- text


def _lines_from_units(db: Session, evidence: EvidenceFile) -> list[Line]:
    """Lines as the extractor recorded them, which is what the case was actually built on."""
    units = (_artifact(db, evidence.id, "units") or {}).get("units") or []
    lines: list[Line] = []
    for unit in units:
        reference = unit.get("reference") or {}
        start = reference.get("line_start")
        if start is None:
            continue
        lines.append(Line(number=int(start), text=str(unit.get("text") or ""), page=reference.get("page")))
    return sorted(lines, key=lambda item: (item.page or 0, item.number))


def _lines_from_file(path: Path) -> list[Line]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [Line(number=index, text=line) for index, line in enumerate(text.splitlines(), start=1)]


def _pdf_page_marks(path: Path, page_number: int, cited_text: str | None, value: str | None) -> tuple[int, int, list[Region], int]:
    """Where the cited line and the traced value sit on a rendered PDF page.

    A PDF is a picture of a document. Telling a reviewer "page 1, line 6" makes them count lines;
    drawing the box makes them look. PyMuPDF is already how this project reads PDFs, and it reports
    the rectangle of any text it finds, so the same page a reader sees can carry the same two marks
    an image carries.

    Coordinates come back in points and are scaled to the rendered pixel size, so the client can
    place them as percentages without knowing anything about PDF geometry.
    """
    import fitz

    regions: list[Region] = []
    with fitz.open(path) as document:
        count = document.page_count
        index = max(0, min(page_number - 1, count - 1))
        page = document[index]
        # The same rounding the renderer uses, so the marks and the picture agree to the pixel.
        # Deriving the size arithmetically was off by one against the rendered page.
        canvas = (page.rect * fitz.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE)).irect
        width, height = canvas.width, canvas.height

        def find(needle: str) -> list[Any]:
            needle = needle.strip()
            if not needle:
                return []
            for attempt in (needle[:PDF_SEARCH_LIMIT], needle[:40], needle[:24]):
                hits = page.search_for(attempt)
                if hits:
                    return hits
            return []

        seen: set[tuple[int, int, int, int]] = set()
        for needle, cited in ((cited_text, True), (value, False)):
            if not needle:
                continue
            for order, rect in enumerate(find(needle), start=1):
                box = (
                    rect.x0 * PDF_RENDER_SCALE,
                    rect.y0 * PDF_RENDER_SCALE,
                    rect.x1 * PDF_RENDER_SCALE,
                    rect.y1 * PDF_RENDER_SCALE,
                )
                key = tuple(int(value) for value in box)  # type: ignore[assignment]
                if key in seen:
                    continue
                seen.add(key)  # type: ignore[arg-type]
                regions.append(Region(
                    id=f"p{index + 1}-{'cited' if cited else 'also'}-{order}",
                    text=needle[:PDF_SEARCH_LIMIT],
                    bbox=box,
                    page=index + 1,
                    highlight=True,
                    cited=cited,
                ))

    return width, height, regions, count


def _text_view(db: Session, evidence: EvidenceFile, storage_key: str, suffix: str, target: Target) -> SourceView:
    # A plain text file is shown from its own bytes, so a reviewer sees blank lines and spacing
    # exactly as the file has them. A PDF cannot be read that way here, so its recorded lines are
    # used -- and the original is still one click away in the same panel.
    lines = _lines_from_units(db, evidence)
    if suffix in PLAIN_TEXT_SUFFIXES:
        lines = _lines_from_file(get_private_path(storage_key))

    truncated = len(lines) > MAX_TEXT_LINES
    lines = lines[:MAX_TEXT_LINES]
    pages = {line.page for line in lines if line.page}

    view = SourceView(
        evidence_id=evidence.id,
        original_name=evidence.original_name,
        media_type=evidence.detected_mime or "text/plain",
        kind="text",
        located=False,
        highlight_summary="",
        page_count=max(pages) if pages else None,
        lines=lines,
        truncated=truncated,
    )

    if not lines:
        view.note = "No readable lines were recorded for this file. The original can still be opened."
        return view

    if target.line_start is not None:
        end = target.line_end if target.line_end is not None else target.line_start
        for line in lines:
            if target.page and line.page and line.page != target.page:
                continue
            if target.line_start <= line.number <= end:
                line.cited = line.highlight = True

    if target.value:
        for line in lines:
            if _contains(line.text, target.value):
                line.highlight = True

    cited = [line for line in lines if line.cited]
    marked = [line for line in lines if line.highlight]

    if cited:
        view.located = True
        first, last = cited[0].number, cited[-1].number
        span = f"line {first}" if first == last else f"lines {first}–{last}"
        view.highlight_summary = (f"page {cited[0].page}, " if cited[0].page else "") + span
    elif marked:
        marked[0].cited = True
        view.located = True
        view.highlight_summary = (f"page {marked[0].page}, " if marked[0].page else "") + f"line {marked[0].number}"
    else:
        view.note = "This file is the source, but the cited line could not be located in it."
        return view

    others = len(marked) - len(cited or [marked[0]])
    if others > 0:
        view.occurrence_summary = f"also appears on {others} other line{'' if others == 1 else 's'} of this file"

    # A PDF can be shown as the page itself, with the same marks drawn on it.
    if suffix == ".pdf":
        anchor = next((line for line in lines if line.cited), None)
        try:
            width, height, regions, count = _pdf_page_marks(
                get_private_path(storage_key),
                anchor.page or 1 if anchor else (target.page or 1),
                anchor.text if anchor else None,
                target.value,
            )
        except Exception:  # noqa: BLE001 - a page that will not render must not take the panel down
            logger.info("Could not render page marks for evidence %s", evidence.id, exc_info=True)
        else:
            view.page_image = bool(regions) or bool(width and height)
            view.page_number = anchor.page or 1 if anchor else (target.page or 1)
            view.width, view.height, view.regions = width, height, regions
            view.page_count = count
    return view


def render_page(path: Path, page_number: int) -> bytes:
    """One PDF page as a PNG, at the scale the marks were measured against.

    The marks are reported in rendered pixels, so the picture they are drawn on has to be rendered
    the same way. Any other scale would put every box in the wrong place.
    """
    import fitz

    with fitz.open(path) as document:
        index = max(0, min(page_number - 1, document.page_count - 1))
        pixmap = document[index].get_pixmap(matrix=fitz.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE))
        return pixmap.tobytes("png")


# --------------------------------------------------------------------------- entry point


def build(db: Session, evidence: EvidenceFile, *, target: Target) -> SourceView:
    """Assemble the view of one evidence file, with the cited place marked where it can be found."""
    suffix = Path(evidence.original_name or "").suffix.lower()
    media_type = evidence.detected_mime or ""

    # An image view is assembled entirely from the OCR artifact, so it never needs the bytes. Only
    # the table and text views read the file, and the path is resolved there -- fetching an object
    # that is not going to be read would fail a view that had everything it needed.
    if media_type.startswith(IMAGE_PREFIX):
        return _image_view(db, evidence, target)
    if suffix in TABLE_SUFFIXES or media_type in {"text/csv", "text/tab-separated-values"}:
        return _table_view(evidence, get_private_path(evidence.storage_key), suffix or ".csv", target)
    return _text_view(db, evidence, evidence.storage_key, suffix, target)
