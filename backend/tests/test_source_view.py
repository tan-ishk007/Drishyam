"""Opening a stored statement at the place in the file it was read from.

The product's central claim is that every statement can be traced to its source. These hold the
part of that claim a reviewer actually experiences: that the place is found in each kind of file,
that it is the *right* place, and that a place which cannot be found is reported as not found
rather than approximated. A box drawn in the wrong spot is worse than no box: it tells a reviewer
they have verified something they have not.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import EntityRelation, Entity, EvidenceFile
from app.services import source_view
from scripts import benchmark_case


@pytest.fixture
def sourced_case(client, case_factory):
    """The benchmark case, which is built to contain one of every file shape."""
    case, headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
    return case, headers


def _evidence(case_id: str, fragment: str) -> EvidenceFile:
    db = SessionLocal()
    try:
        found = next(
            item
            for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))
            if fragment in item.original_name
        )
        db.expunge(found)
        return found
    finally:
        db.close()


def _view(evidence: EvidenceFile, **target) -> source_view.SourceView:
    db = SessionLocal()
    try:
        return source_view.build(db, db.merge(evidence), target=source_view.Target(**target))
    finally:
        db.close()


# --------------------------------------------------------------------------- each kind of file


def test_an_image_marks_the_region_that_reads_the_value(sourced_case) -> None:
    """The winning moment: a claim opens as a box drawn round the pixels it was read from."""
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "screenshot_plain"), value="+919876543210")

    assert view.kind == "image"
    assert view.located
    assert view.width and view.height, "a region cannot be drawn without the canvas it sits on"

    marked = [region for region in view.regions if region.highlight]
    assert marked, view.note
    assert sum(1 for region in view.regions if region.cited) == 1, "exactly one region is the citation"
    assert all("9876543210" in region.text.replace(" ", "") for region in marked)
    for region in marked:
        x0, y0, x1, y1 = region.bbox
        assert 0 <= x0 < x1 <= view.width and 0 <= y0 < y1 <= view.height
        assert (x1 - x0) < view.width, "a box around the whole canvas marks nothing"


def test_a_table_marks_the_cited_cell(sourced_case) -> None:
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "cdr_synthetic"), row=2, column="a_party")

    assert view.kind == "table"
    assert view.located and view.highlight_summary.startswith("row 2")
    cited = [row for row in view.rows if row.cited]
    assert len(cited) == 1 and cited[0].number == 2
    assert cited[0].cited_columns == ["a_party"]
    assert "a_party" in view.header


def test_a_text_file_marks_the_cited_line(sourced_case) -> None:
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "surveillance"), line_start=7)

    assert view.kind == "text"
    assert view.located
    assert [line.number for line in view.lines if line.cited] == [7]


def test_a_pdf_marks_the_cited_page_and_line(sourced_case) -> None:
    """A PDF's bytes cannot be read as text here, so it is shown from the lines recorded at
    extraction -- which are the lines the case was actually built on."""
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "fir_primary"), page=1, line_start=6)

    assert view.kind == "text"
    assert view.located
    cited = [line for line in view.lines if line.cited]
    assert cited and all(line.page == 1 for line in cited)


# --------------------------------------------------------------------------- finding by value


def test_a_value_alone_finds_its_place_when_no_reference_locates_it(sourced_case) -> None:
    """A stored image reference covers the whole canvas, so the value has to do the locating."""
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "cdr_synthetic"), value="+91 99887 76655")
    assert view.located, view.note
    assert any(row.highlight for row in view.rows), "punctuation should not decide whether a value is found"


# --------------------------------------------------------------------------- everywhere else


def test_a_value_is_marked_everywhere_it_appears_not_only_where_it_was_cited(sourced_case) -> None:
    """A handle cited once as a sender may sit three more times as a receiver.

    Showing only the citation answers "where was this read" and hides most of what the file says
    about the value. Both marks are needed, and they must stay distinguishable: one is provenance,
    the other is context.
    """
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "transactions"), row=2, column="sender", value="skyline.manpower@upi")

    cited = [row for row in view.rows if row.cited]
    marked = [row for row in view.rows if row.highlight]
    assert len(cited) == 1 and cited[0].number == 2
    assert len(marked) > len(cited), "the value appears elsewhere in this file and was not marked there"
    assert view.occurrence_summary, "the panel must say that the value appears elsewhere"

    for row in marked:
        for column in row.highlight_columns:
            assert "skyline" in row.cells[column].casefold(), "a cell was marked that does not carry the value"


def test_the_citation_is_marked_even_when_it_holds_a_different_value(sourced_case) -> None:
    """The cited cell is the cited cell. It stays marked whether or not it carries the traced value.

    An entity is opened through a relationship, and a relationship's reference points at its
    subject -- which is often not the entity the reader clicked.
    """
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "transactions"), row=2, column="sender", value="skyline.manpower@upi")
    cited = next(row for row in view.rows if row.cited)
    assert cited.cited_columns == ["sender"]


def test_a_table_carries_its_own_text_as_well_as_its_grid(sourced_case) -> None:
    """A parsed grid is an interpretation. A reviewer checking a record is owed the bytes."""
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "cdr_synthetic"), row=2, column="a_party")
    assert view.raw_lines, "a text-shaped table must also be readable as text"
    assert [line.number for line in view.raw_lines if line.cited] == [2]
    assert "a_party" in view.raw_lines[0].text, "line 1 of the file is its header"


def test_a_pdf_is_also_offered_as_a_marked_page(sourced_case) -> None:
    """A PDF is a picture of a record.

    Citing "page 1, line 6" makes a reviewer count lines, and a citation somebody has to count
    lines to find is a citation they will not check. The page is rendered and the same two marks
    are placed on it, in the pixel coordinates of that render.
    """
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "fir_primary"), page=1, line_start=6, value="Ravi Kumar")

    assert view.page_image and view.page_number == 1
    assert view.width and view.height, "marks cannot be placed without the rendered page size"

    cited = [region for region in view.regions if region.cited]
    others = [region for region in view.regions if region.highlight and not region.cited]
    assert len(cited) == 1, "exactly one region is the citation"
    assert others, "the traced value appears elsewhere on this page and was not marked"

    for region in view.regions:
        x0, y0, x1, y1 = region.bbox
        assert 0 <= x0 < x1 <= view.width and 0 <= y0 < y1 <= view.height


def test_the_rendered_page_is_a_png_at_the_scale_the_marks_assume(sourced_case) -> None:
    """Any other scale would put every box in the wrong place."""
    from app.services.storage import get_private_path

    case, _ = sourced_case
    evidence = _evidence(case["id"], "fir_primary")
    view = _view(evidence, page=1, line_start=6)

    image = source_view.render_page(get_private_path(evidence.storage_key), 1)
    assert image[1:4] == b"PNG" and image[0] == 0x89

    from PIL import Image
    import io as _io

    with Image.open(_io.BytesIO(image)) as rendered:
        assert rendered.size == (view.width, view.height)


def test_the_page_endpoint_refuses_a_file_that_has_no_pages(client, sourced_case) -> None:
    case, headers = sourced_case
    evidence = _evidence(case["id"], "cdr_synthetic")
    response = client.get(f"/api/v1/cases/{case['id']}/evidence/{evidence.id}/page/1", headers=headers)
    assert response.status_code == 400


# --------------------------------------------------------------------------- refusing to guess


def test_a_place_that_cannot_be_found_is_reported_not_approximated(sourced_case) -> None:
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "cdr_synthetic"), value="+919000000001")

    assert view.located is False
    assert view.note, "an unlocatable reference must say so"
    assert not any(row.highlight or row.cited for row in view.rows), "nothing may be marked when nothing was found"


def test_a_row_outside_the_table_marks_nothing(sourced_case) -> None:
    case, _ = sourced_case
    view = _view(_evidence(case["id"], "cdr_synthetic"), row=9999, column="a_party")
    assert view.located is False
    assert not any(row.highlight or row.cited for row in view.rows)


# --------------------------------------------------------------------------- through the API


def test_the_endpoint_returns_the_marked_view(client, sourced_case) -> None:
    case, headers = sourced_case
    evidence = _evidence(case["id"], "cdr_synthetic")
    response = client.get(
        f"/api/v1/cases/{case['id']}/evidence/{evidence.id}/source-view",
        headers=headers,
        params={"row": 2, "column": "a_party"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "table" and body["located"] is True
    assert [row["number"] for row in body["rows"] if row["cited"]] == [2]


def test_another_users_evidence_is_not_readable(client, sourced_case, account) -> None:
    """Reading a file's contents is a disclosure. It is gated exactly as the download is."""
    case, _ = sourced_case
    evidence = _evidence(case["id"], "cdr_synthetic")
    _, outsider = account()
    response = client.get(
        f"/api/v1/cases/{case['id']}/evidence/{evidence.id}/source-view",
        headers=outsider,
        params={"row": 2},
    )
    assert response.status_code in {403, 404}
    assert "a_party" not in response.text


def test_every_relation_in_the_case_opens_somewhere(sourced_case) -> None:
    """Not every reference will resolve, but each must return a view naming its own file.

    A relationship whose source cannot even be identified is not traceable evidence, whatever the
    provenance columns say.
    """
    case, _ = sourced_case
    db = SessionLocal()
    try:
        relations = list(db.scalars(select(EntityRelation).where(EntityRelation.case_id == case["id"])))
        labels = {item.id: item.value for item in db.scalars(select(Entity).where(Entity.case_id == case["id"]))}
    finally:
        db.close()

    assert relations, "the benchmark case produced no relationships to open"
    located = 0
    for relation in relations:
        evidence = _evidence(case["id"], "")
        db = SessionLocal()
        try:
            source = db.get(EvidenceFile, relation.source_evidence_id)
            assert source is not None, "a relationship names an evidence file that does not exist"
            view = source_view.build(
                db,
                source,
                target=source_view.Target.from_reference(relation.source_reference, value=labels.get(relation.subject_entity_id)),
            )
        finally:
            db.close()
        assert view.original_name == source.original_name
        located += 1 if view.located else 0

    assert located == len(relations), f"only {located} of {len(relations)} relationships could be opened at their source"
