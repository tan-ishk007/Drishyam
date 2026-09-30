"""The benchmark case, and the defects it found.

`scripts/run_benchmark.py` reports numbers. This file holds the parts that must not regress: the
four restraint properties, which are wrong at any accuracy, and the specific extraction faults the
benchmark exposed the first time it ran.

Each fault below was found by measuring, not by reading the code, which is the argument for the
benchmark existing at all.
"""

from __future__ import annotations

import pytest

from app.evidence_intelligence import patterns
from app.evidence_intelligence.extraction import BANK_COLUMN_ALIASES, CALL_LOG_COLUMN_ALIASES, _map_columns
from app.services.entity_resolution import canonicalize
from scripts import benchmark_case
from scripts.run_benchmark import (
    check_conflict_survives,
    check_malformed_is_contained,
    check_no_fabricated_number,
    check_similar_names_stay_apart,
)

from app.core.db import SessionLocal


# --------------------------------------------------------------------------- table headers


def test_an_underscored_cdr_header_maps_to_the_a_party_column() -> None:
    """Real exports write "a_party"; the alias list wrote "a-party" and matched exactly.

    The A-party column went unmapped, so who dialled whom was lost and a call record could only
    produce the symmetric "these two were in contact" -- never the directed CALLED it exists for.
    """
    header = ["a_party", "b_party", "date", "time", "duration_seconds", "cell_id", "call_type"]
    mapping = _map_columns(header, CALL_LOG_COLUMN_ALIASES)
    assert mapping["sender"] == "a_party"
    assert mapping["receiver"] == "b_party"


def test_an_underscored_account_header_is_recognised() -> None:
    mapping = _map_columns(["date", "amount", "account_number", "reference"], BANK_COLUMN_ALIASES)
    assert mapping["account_identifiers"] == "account_number"


@pytest.mark.parametrize("written", ["A-Party", "a party", "APARTY", " a_party "])
def test_the_same_header_written_any_way_maps_the_same(written: str) -> None:
    assert _map_columns([written, "b_party"], CALL_LOG_COLUMN_ALIASES).get("sender") == written


def test_a_header_that_merely_contains_an_alias_is_not_matched() -> None:
    """Folding separators must not turn exact matching into substring matching."""
    assert "event_time" not in _map_columns(["date_of_birth"], BANK_COLUMN_ALIASES)


# --------------------------------------------------------------------------- locations


def test_a_place_name_stops_at_the_next_field_label() -> None:
    """A form puts fields side by side, and the district ran on into the next label.

    "District: Mumbai Suburban    Date: 12/07/2026" was read as a place called
    "Mumbai Suburban Date".
    """
    assert patterns.find_locations("District: Mumbai Suburban        Date: 12/07/2026") == ["Mumbai Suburban"]


def test_a_place_name_that_is_not_followed_by_a_label_is_kept_whole() -> None:
    assert patterns.find_locations("Vehicle parked at Linking Road.") == ["Linking Road"]
    assert patterns.find_locations("District: Thane") == ["Thane"]


# --------------------------------------------------------------------------- surveillance language


def test_a_name_introduced_rather_than_labelled_is_read() -> None:
    """A surveillance note writes no headers. It writes the way an officer speaks."""
    assert patterns.find_person_names("A person identifying himself as Yash Kumar Gupt was seen.") == ["Yash Kumar Gupt"]
    assert patterns.find_person_names("who gave his name as Mohan Lal") == ["Mohan Lal"]


def test_a_capitalised_word_after_an_ordinary_one_is_still_not_a_name() -> None:
    """The legal idiom "one Yash Kumar Gupt" reduces to "one" plus a capital, and read "one Rule"."""
    assert patterns.find_person_names("This is one Rule that should not match.") == []


def test_a_sentence_that_parks_a_vehicle_somewhere_places_it_there() -> None:
    """The one fact a surveillance log exists to record produced no edge at all.

    The presence vocabulary held "seen" and "located" but not "observed" or "parked", and the
    presence rule paired only people with places -- so a plate at a location was unrepresentable.
    """
    links = patterns.find_vehicle_location_links("19:40 hrs - Vehicle MH12DE1433 observed parked at Linking Road.")
    assert [(plate, place) for plate, place, _ in links] == [("MH12DE1433", "Linking Road")]


def test_a_vehicle_merely_moving_through_is_not_placed_there() -> None:
    """A verb of motion places nobody anywhere, and a presence edge should not claim it did."""
    assert patterns.find_vehicle_location_links("Vehicle MH12DE1433 left Linking Road towards Andheri East.") == []


def test_every_vehicle_presence_link_quotes_the_sentence_that_stated_it() -> None:
    text = "22:15 hrs - Second vehicle MH04AB2211 observed at Linking Road. No occupant identified."
    for _, _, quote in patterns.find_vehicle_location_links(text):
        assert quote in text


# --------------------------------------------------------------------------- one person, one node


@pytest.mark.parametrize("field_name", ["sender", "receiver", "chat_participant_identifier"])
def test_a_named_party_resolves_to_the_person_node(field_name: str) -> None:
    """A payer column and an FIR complainant naming one person made two nodes.

    Both were weak in exactly the same way -- a name written down is not proof of identity -- so
    the split bought nothing and cost the link between the statement and the report.
    """
    identity = canonicalize(field_name, "Priya Sharma")
    assert identity is not None
    assert (identity.entity_type, identity.canonical_value) == ("person", "priya sharma")
    assert identity == canonicalize("person_names", "Priya Sharma")


def test_a_handle_in_a_receiver_column_resolves_to_the_handle_it_already_is() -> None:
    identity = canonicalize("receiver", "skyline.manpower@upi")
    assert identity is not None
    assert (identity.entity_type, identity.canonical_value) == ("upi", "skyline.manpower@upi")


def test_a_number_in_a_party_column_is_still_a_phone() -> None:
    identity = canonicalize("sender", "+91 98765 43210")
    assert identity is not None
    assert (identity.entity_type, identity.canonical_value) == ("phone", "9876543210")


# --------------------------------------------------------------------------- restraint, end to end


@pytest.fixture
def benchmark_run(client, case_factory):
    """The whole benchmark case, ingested through the real API."""
    case, headers = case_factory()
    outcomes: dict[str, dict] = {}
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            response = client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
        outcomes[name] = {"http_status": response.status_code}
    return case["id"], outcomes


def test_the_four_restraint_properties_hold(benchmark_run) -> None:
    """Reported one by one, because which of them broke is the whole information."""
    case_id, outcomes = benchmark_run
    db = SessionLocal()
    try:
        checks = [
            check_no_fabricated_number(db, case_id),
            check_similar_names_stay_apart(db, case_id),
            check_conflict_survives(db, case_id),
            check_malformed_is_contained(outcomes),
        ]
    finally:
        db.close()

    failures = [f"{item.name}: {item.explanation}" for item in checks if item.status != "pass"]
    assert not failures, "\n".join(failures)
