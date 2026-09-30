"""Reading a generated report without downloading it, and searching inside it.

The only way to see what a report said was to download the PDF. That is a poor place to leave a
reviewer: the decision to hand a document to somebody else is made *after* reading it, and a file
sitting in a downloads folder is a copy nobody is tracking any more. Worse, a nineteen-page report
is exactly the kind of document where the question is "where does it say that", and a downloaded
PDF answers that in a different application with none of the case's context around it.

This renders report pages through the same machinery that already renders evidence pages, so a
mark on a report page means the same thing as a mark on a source page: this is the place, located,
not approximated. Searching returns the rectangle of every hit rather than a count, because a count
tells a reader how much they have to go and find for themselves.

Nothing here interprets the report. It finds text and reports where it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.source_view import PDF_RENDER_SCALE, render_page

REPORT_VIEW_VERSION = "report-view-v1"

# Below this a search matches most of the document and marks stop meaning anything. Stated to the
# reader rather than silently ignored.
MIN_SEARCH_LENGTH = 2

# A ceiling on how many rectangles one search returns. A reader given four hundred marks has been
# given a coloured page, not an answer -- so the ceiling is reported alongside the true total.
MAX_MARKS = 200


@dataclass
class Match:
    """One occurrence of the searched text, and the box it occupies on its page."""

    page: int
    bbox: tuple[float, float, float, float]
    order: int

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page, "bbox": list(self.bbox), "order": self.order}


@dataclass
class ReportPages:
    pages: int
    width: int
    height: int
    version: str = REPORT_VIEW_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {"pages": self.pages, "width": self.width, "height": self.height, "version": self.version}


@dataclass
class SearchResult:
    query: str
    total: int
    matches: list[Match] = field(default_factory=list)
    truncated: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "total": self.total,
            "matches": [item.to_dict() for item in self.matches],
            "truncated": self.truncated,
            "note": self.note,
        }


def describe(path: Path) -> ReportPages:
    """How many pages the report has, and the size they render at.

    The size comes from the first page at the render scale the marks are measured against. A client
    that placed marks against any other size would put every box in the wrong place.
    """
    import fitz

    with fitz.open(path) as document:
        if document.page_count == 0:
            return ReportPages(pages=0, width=0, height=0)
        canvas = (document[0].rect * fitz.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE)).irect
        return ReportPages(pages=document.page_count, width=canvas.width, height=canvas.height)


def page_png(path: Path, page_number: int) -> bytes:
    """One report page, rendered exactly as the evidence viewer renders a source page."""
    return render_page(path, page_number)


def search(path: Path, query: str) -> SearchResult:
    """Every occurrence of the text, with the rectangle of each one.

    Returning boxes rather than a count is the whole point: "14 matches" leaves the reader to find
    fourteen things, while fourteen marks on the pages leaves them nothing to find.
    """
    import fitz

    cleaned = query.strip()
    if len(cleaned) < MIN_SEARCH_LENGTH:
        return SearchResult(
            query=cleaned,
            total=0,
            note=(
                f"Enter at least {MIN_SEARCH_LENGTH} characters. A shorter search matches most of the document, "
                "and a page of marks says nothing about where the answer is."
            ),
        )

    matches: list[Match] = []
    total = 0
    with fitz.open(path) as document:
        for index in range(document.page_count):
            for rect in document[index].search_for(cleaned):
                total += 1
                if len(matches) >= MAX_MARKS:
                    continue
                matches.append(Match(
                    page=index + 1,
                    bbox=(
                        rect.x0 * PDF_RENDER_SCALE,
                        rect.y0 * PDF_RENDER_SCALE,
                        rect.x1 * PDF_RENDER_SCALE,
                        rect.y1 * PDF_RENDER_SCALE,
                    ),
                    order=total,
                ))

    result = SearchResult(query=cleaned, total=total, matches=matches, truncated=total > len(matches))
    if result.truncated:
        result.note = (
            f"{total} occurrences were found; the first {len(matches)} are marked. Narrow the search to see the rest "
            "marked rather than counted."
        )
    elif total == 0:
        result.note = "This text does not appear in the report. That is a fact about this document, not about the case."
    else:
        result.note = f"{total} occurrence{'' if total == 1 else 's'}, each marked where it appears."
    return result
