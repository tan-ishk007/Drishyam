"""What a source calls a person, kept rather than discarded.

The person patterns already matched the role — complainant, accused, victim, witness, driver,
owner — and `find_person_names` returned the name alone, so the first question an investigator asks
about a name on a page was the one piece of information extraction threw away.

The distinctions below are the whole value of the feature. A form with a "Name:" field has not
assigned anybody a role. "S/o Mohan Lal" names a parent for identification, not a party to the
case. And a name somebody gave for themselves is weaker than a role a report assigns, which is
exactly the difference between the two Yashes in the benchmark case.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.evidence_intelligence import patterns
from app.models.entities import Entity, EntityOccurrence
from scripts import benchmark_case


# --------------------------------------------------------------------------- reading the role


@pytest.mark.parametrize(
    ("text", "name", "role"),
    [
        ("Complainant: Priya Sharma", "Priya Sharma", "complainant"),
        ("Accused (1): Yash Kumar Gupta, contact +919876543210", "Yash Kumar Gupta", "accused"),
        ("Driver: Mohan Lal", "Mohan Lal", "driver"),
        ("Witness: Ramesh Chandra", "Ramesh Chandra", "witness"),
        ("Informant: Anita Rao", "Anita Rao", "complainant"),
        ("Suspect: Vikram Singh", "Vikram Singh", "accused"),
    ],
)
def test_a_report_header_states_the_role(text: str, name: str, role: str) -> None:
    assert patterns.find_person_roles(text) == {name: role}


@pytest.mark.parametrize(
    ("text", "name", "role"),
    [
        ("The complainant states that accused Yash Kumar Gupta called her.", "Yash Kumar Gupta", "accused"),
        ("Later that evening witness Ramesh Chandra saw the vehicle.", "Ramesh Chandra", "witness"),
        ("The driver Mohan Lal remained in the vehicle.", "Mohan Lal", "driver"),
    ],
)
def test_the_narrative_states_the_role_too(text: str, name: str, role: str) -> None:
    """A header writes "Accused:"; the body writes "accused Yash Kumar Gupta was driving"."""
    assert patterns.find_person_roles(text)[name] == role


# --------------------------------------------------------------------------- what is not a role


def test_a_name_field_is_not_a_case_role() -> None:
    """"Name: Mohan Lal" says the form has a name field. It does not make him anything."""
    assert patterns.find_person_roles("Name: Mohan Lal") == {"Mohan Lal": "named"}


def test_a_parent_named_for_identification_is_not_a_party() -> None:
    """Indian records write "Ravi Kumar S/o Mohan Lal" to disambiguate. Mohan Lal is not accused."""
    roles = patterns.find_person_roles("Ravi Kumar S/o Mohan Lal")
    assert roles.get("Mohan Lal") == "relative"
    assert "accused" not in roles.values()


def test_a_name_somebody_gave_for_themselves_is_labelled_as_such() -> None:
    roles = patterns.find_person_roles("A person identifying himself as Yash Kumar Gupt was seen speaking to the driver.")
    assert roles == {"Yash Kumar Gupt": "self-identified"}


def test_an_assigned_role_outranks_a_self_given_name() -> None:
    """Where one passage gives two readings of the same name, the stronger one is kept."""
    text = "A person identifying himself as Yash Kumar Gupta was seen. Accused: Yash Kumar Gupta"
    assert patterns.find_person_roles(text)["Yash Kumar Gupta"] == "accused"


def test_text_with_no_stated_role_yields_none() -> None:
    assert patterns.find_person_roles("The vehicle left towards Andheri East at 21:30 hrs.") == {}


def test_a_name_does_not_run_past_the_end_of_its_sentence() -> None:
    """A dot is allowed inside a name so initials survive, and that let a sentence-ending period
    glue the next word on: "Complainant: Priya Sharma. Accused (1): ..." was read as one person
    called "Priya Sharma. Accused" — and the over-long match swallowed the label, so the accused
    was never found at all."""
    text = "Complainant: Priya Sharma. Accused (1): Yash Kumar Gupta. Driver: Mohan Lal."
    assert patterns.find_person_names(text) == ["Mohan Lal", "Priya Sharma", "Yash Kumar Gupta"]
    assert patterns.find_person_roles(text) == {
        "Priya Sharma": "complainant",
        "Yash Kumar Gupta": "accused",
        "Mohan Lal": "driver",
    }


def test_an_initial_is_still_part_of_the_name() -> None:
    """The boundary must not cost the thing the dot was allowed for."""
    assert patterns.find_person_names("Accused: R. Kumar") == ["R. Kumar"]


# --------------------------------------------------------------------------- through the pipeline


@pytest.fixture
def roled_case(client, case_factory):
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


def _roles(case_id: str) -> dict[str, set[str]]:
    db = SessionLocal()
    try:
        names = {item.id: item.value for item in db.scalars(select(Entity).where(Entity.case_id == case_id))}
        found: dict[str, set[str]] = {}
        for occurrence in db.scalars(select(EntityOccurrence).where(EntityOccurrence.case_id == case_id)):
            if occurrence.stated_role:
                found.setdefault(names.get(occurrence.entity_id, "?"), set()).add(occurrence.stated_role)
        return found
    finally:
        db.close()


def test_the_role_reaches_the_occurrence_it_was_read_from(roled_case) -> None:
    case, _ = roled_case
    roles = _roles(case["id"])

    assert roles.get("Yash Kumar Gupta") == {"accused"}
    assert roles.get("Priya Sharma") == {"complainant"}
    assert roles.get("Yash Kumar Gupt") == {"self-identified"}, "the weaker basis must stay distinguishable"


def test_only_a_person_carries_a_role(roled_case) -> None:
    """A phone number has no role. Giving it one would assert something no source stated."""
    case, _ = roled_case
    db = SessionLocal()
    try:
        kinds = {item.id: item.entity_type for item in db.scalars(select(Entity).where(Entity.case_id == case["id"]))}
        for occurrence in db.scalars(select(EntityOccurrence).where(EntityOccurrence.case_id == case["id"])):
            if occurrence.stated_role:
                assert kinds.get(occurrence.entity_id) == "person", f"{occurrence.stated_role} on a {kinds.get(occurrence.entity_id)}"
    finally:
        db.close()


def test_a_role_belongs_to_the_source_that_stated_it(roled_case) -> None:
    """Recorded against the occurrence, not the entity: one person can be read two ways."""
    case, _ = roled_case
    db = SessionLocal()
    try:
        for occurrence in db.scalars(select(EntityOccurrence).where(EntityOccurrence.case_id == case["id"])):
            if occurrence.stated_role:
                assert occurrence.evidence_id, "a role with no source is not traceable"
                assert occurrence.source_reference is not None
    finally:
        db.close()
