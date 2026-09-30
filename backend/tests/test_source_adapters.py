"""The sources SIH26189 names: CDR records and police/surveillance reports.

Each adapter earns exactly one thing the generic parser could not give: a CDR states who dialled,
and a report states what someone did. Both are only read where the source actually says it, so most
of what is asserted here is the refusal.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.evidence_intelligence import patterns
from app.evidence_intelligence.detection import ContentFileTypeDetector
from app.evidence_intelligence.schema import SourceType
from app.models.entities import EntityRelation, NormalizedRecord
from app.services.relationship_builder import (
    CALLED,
    COMMUNICATED_WITH,
    LOCATED_AT,
    MENTIONED_WITH,
    USED_VEHICLE,
)

CDR_WITH_ROLES = (
    "a-party,b-party,call date,duration_seconds,cell id,imei\n"
    "+919876543210,+919988776655,14/08/2026 09:00,182,MUM-CELL-4471,356938035643809\n"
    "+919988776655,+919123456789,14/08/2026 10:34,70,MUM-CELL-2210,356938035643809\n"
)
CALL_LOG_WITHOUT_ROLES = (
    "date,time,direction,number,contact,duration_seconds\n"
    "14/08/2026,09:00,incoming,+919876543210,+919988776655,182\n"
)
FIR_TEXT = """FIRST INFORMATION REPORT
FIR No: 0142/2026    Police Station: Andheri East
Offence u/s 420, 406 IPC
Complainant: Ravi Kumar S/o Mohan Lal
The complainant states that accused Yash Kumar Gupta was driving vehicle MH12DE1433 near the toll plaza.
Accused Yash Kumar Gupta was seen at Linking Road on the same evening.
"""


# --------------------------------------------------------------------------- report structure


def test_a_report_header_is_read_as_printed() -> None:
    assert patterns.find_fir_number(FIR_TEXT) == "0142/2026"
    assert patterns.find_police_station(FIR_TEXT) == "Andheri East"
    assert patterns.find_fir_sections(FIR_TEXT) == ["420 IPC", "406 IPC"]


def test_a_station_name_never_runs_past_its_own_line() -> None:
    """A greedy match swallowed the first word of the line below ("Andheri East Offence")."""
    assert patterns.find_police_station("Police Station: Andheri East\nOffence u/s 420 IPC") == "Andheri East"


@pytest.mark.parametrize("text", ["no report header here", "The police station was closed."])
def test_report_fields_stay_absent_when_the_source_has_no_header(text: str) -> None:
    assert patterns.find_fir_number(text) is None
    assert patterns.find_police_station(text) is None


# --------------------------------------------------------------------------- stated roles


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("The complainant states that accused Yash Kumar Gupta was driving vehicle MH12DE1433.", ("Yash Kumar Gupta", "MH12DE1433")),
        ("Complainant: Ravi Kumar used MH12DE1433 on that day.", ("Ravi Kumar", "MH12DE1433")),
    ],
)
def test_a_person_is_linked_to_a_vehicle_only_by_a_stated_verb(sentence: str, expected: tuple[str, str]) -> None:
    assert [(person, vehicle) for person, vehicle, _ in patterns.find_person_vehicle_links(sentence)] == [expected]


@pytest.mark.parametrize(
    "text",
    [
        # Two sentences: the source states nothing that joins them.
        "Accused: Yash Kumar Gupta fled. Vehicle MH12DE1433 was recovered later.",
        # One sentence, but no verb of use.
        "Complainant: Ravi Kumar and vehicle MH12DE1433 are listed in the annexure.",
    ],
)
def test_a_vehicle_link_is_refused_without_a_stated_verb_in_the_same_sentence(text: str) -> None:
    assert patterns.find_person_vehicle_links(text) == []


def test_a_person_is_placed_only_by_a_stated_verb() -> None:
    links = patterns.find_person_location_links("Accused Yash Kumar Gupta was seen at Linking Road on the same evening.")
    assert [(person, place) for person, place, _ in links] == [("Yash Kumar Gupta", "Linking Road")]


@pytest.mark.parametrize(
    "text",
    [
        "Complainant: Ravi Kumar filed the report. Linking Road is nearby.",
        "Accused: Yash Kumar Gupta and Linking Road appear in the annexure.",
    ],
)
def test_a_location_link_is_refused_without_a_stated_verb(text: str) -> None:
    assert patterns.find_person_location_links(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The complainant states that accused Yash Kumar Gupta was driving.", ["Yash Kumar Gupta"]),
        ("Accused Yash Kumar Gupta was seen at Linking Road.", ["Yash Kumar Gupta"]),
        ("driver Anil Gupta refused to stop", ["Anil Gupta"]),
    ],
)
def test_a_role_word_in_the_narrative_names_a_person(text: str, expected: list[str]) -> None:
    """A report header writes "Accused: X"; the body writes "accused X was driving"."""
    assert patterns.find_person_names(text) == expected


@pytest.mark.parametrize(
    "text",
    ["The accused was seen leaving.", "the complainant filed it.", "Accused persons fled.", "the driver of the vehicle"],
)
def test_a_role_word_alone_never_names_a_person(text: str) -> None:
    """The following word must be capitalised. Case-insensitive matching lost that guard entirely."""
    assert patterns.find_person_names(text) == []


# --------------------------------------------------------------------------- detection


def _detect(body: str, name: str, category: str) -> SourceType:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / name
        path.write_text(body, encoding="utf-8")
        return ContentFileTypeDetector().detect(path, declared_category=category).source_type


def test_a_call_record_naming_both_ends_is_recognised_as_a_cdr() -> None:
    assert _detect(CDR_WITH_ROLES, "export.csv", "cdr") is SourceType.CDR
    # ...and by its header alone, when the uploader picked no category.
    assert _detect(CDR_WITH_ROLES, "export.csv", "unknown") is SourceType.CDR


def test_a_call_log_without_role_columns_stays_a_call_log() -> None:
    assert _detect(CALL_LOG_WITHOUT_ROLES, "calls.csv", "call_log") is SourceType.CALL_LOG


def test_a_declared_report_keeps_its_type_although_it_is_a_plain_document() -> None:
    assert _detect(FIR_TEXT, "fir.txt", "complaint_fir") is SourceType.FIR
    assert _detect("Observation notes.", "note.txt", "surveillance") is SourceType.SURVEILLANCE


# --------------------------------------------------------------------------- end to end


@pytest.fixture
def adapter_case(client, case_factory):
    case, headers = case_factory()
    with tempfile.TemporaryDirectory() as directory:
        for name, body, category in (("cdr.csv", CDR_WITH_ROLES, "cdr"), ("fir.txt", FIR_TEXT, "complaint_fir")):
            path = Path(directory) / name
            path.write_text(body, encoding="utf-8")
            with path.open("rb") as stream:
                response = client.post(
                    f"/api/v1/cases/{case['id']}/evidence",
                    headers=headers,
                    data={"source_category": category},
                    files={"file": (name, stream, "application/octet-stream")},
                )
            assert response.status_code == 201, response.text
    return case, headers


def _relations(case_id: str) -> list[EntityRelation]:
    db = SessionLocal()
    try:
        return list(db.scalars(select(EntityRelation).where(EntityRelation.case_id == case_id)).all())
    finally:
        db.close()


def test_a_cdr_states_who_dialled(adapter_case) -> None:
    case, _ = adapter_case
    calls = [row for row in _relations(case["id"]) if row.relation_type == CALLED]
    assert calls, "a CDR naming an A-party and a B-party produced no directed call"
    for row in calls:
        assert row.directed is True
        assert row.basis == "stated_roles"


def test_a_cdr_does_not_also_record_the_symmetric_edge(adapter_case) -> None:
    """One fact, one edge. Both would make the pair look twice as supported as it is."""
    case, _ = adapter_case
    assert not [row for row in _relations(case["id"]) if row.relation_type == COMMUNICATED_WITH]


def test_a_report_sentence_produces_the_role_it_states(adapter_case) -> None:
    case, _ = adapter_case
    by_type = {row.relation_type: row for row in _relations(case["id"])}
    assert USED_VEHICLE in by_type, "the FIR states a person was driving a vehicle"
    assert LOCATED_AT in by_type, "the FIR states a person was seen at a place"
    for relation_type in (USED_VEHICLE, LOCATED_AT):
        assert by_type[relation_type].directed is True
        assert by_type[relation_type].basis == "stated_in_sentence"
        assert by_type[relation_type].source_reference


def test_a_stated_role_suppresses_the_weak_duplicate(adapter_case) -> None:
    """The co-occurrence edge must not reappear on a later pass.

    `_add` returns nothing for an edge that already exists, and the builder runs over the whole case
    each time any evidence is processed -- so a guard written on "did this pass insert anything"
    silently stopped working on the second upload.
    """
    case, _ = adapter_case
    rows = _relations(case["id"])
    stated_pairs = {(row.subject_entity_id, row.object_entity_id) for row in rows if row.basis != "co_occurrence"}
    weak_pairs = {
        tuple(sorted((row.subject_entity_id, row.object_entity_id)))
        for row in rows
        if row.relation_type == MENTIONED_WITH
    }
    overlap = {pair for pair in stated_pairs if tuple(sorted(pair)) in weak_pairs}
    assert not overlap, f"{len(overlap)} pairs carry both a stated relationship and a weak duplicate"


def test_the_report_header_reaches_the_record(adapter_case) -> None:
    case, _ = adapter_case
    db = SessionLocal()
    try:
        records = db.scalars(
            select(NormalizedRecord).where(NormalizedRecord.case_id == case["id"], NormalizedRecord.source_type == "fir")
        ).all()
    finally:
        db.close()
    headers = [record.event_attributes for record in records if (record.event_attributes or {}).get("fir_number")]
    assert headers, "no record carried the FIR header"
    assert headers[0]["fir_number"] == "0142/2026"
    assert headers[0]["police_station"] == "Andheri East"


def test_a_cell_site_is_an_attribute_and_never_a_place(adapter_case) -> None:
    """A cell ID says where the handset was, not the name of anywhere."""
    case, _ = adapter_case
    db = SessionLocal()
    try:
        records = db.scalars(
            select(NormalizedRecord).where(NormalizedRecord.case_id == case["id"], NormalizedRecord.source_type == "cdr")
        ).all()
    finally:
        db.close()
    assert records
    assert any((record.event_attributes or {}).get("cell_site") for record in records)
    for record in records:
        assert "MUM-CELL-4471" not in (record.location_names or [])
