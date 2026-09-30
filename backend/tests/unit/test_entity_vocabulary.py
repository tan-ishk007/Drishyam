"""The entity classes SIH26189 names: people, locations, vehicles, phones, organisations.

The tests that matter most here are the negative ones. A criminal-network graph is only useful if
its nodes are real: a false node invents a connection between two files that share nothing, and an
investigator has no way to tell that from a true one. So each extractor is tested against the
identifiers it sits next to in real evidence -- IFSC codes, account numbers, UTRs, timestamps --
and must stay silent on all of them.
"""

from __future__ import annotations

import pytest

from app.evidence_intelligence import patterns
from app.services.entity_resolution import canonicalize

# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Vehicle MH12DE1433 seen at the gate", "MH12DE1433"),
        ("car MH 12 DE 1433 parked outside", "MH12DE1433"),
        ("plate DL-8C-AB-1234 noted by the constable", "DL8CAB1234"),
        ("Bike KA05MJ9087 recovered", "KA05MJ9087"),
        ("new series 22 BH 1234 AB", "22BH1234AB"),
    ],
)
def test_registration_plates_are_read_however_they_are_spaced(text: str, expected: str) -> None:
    assert patterns.find_vehicle_identifiers(text) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "IFSC HDFC0012345 branch code",
        "A/C 123456789012",
        "UTR SBIN1234567890",
        "phone +91 98765 43210",
        "2024-03-12 21:15 timestamp",
        "INR 12,000 paid",
        "ZZ 99 XX 1234",  # no such state code
    ],
)
def test_nothing_that_merely_looks_like_a_plate_becomes_a_vehicle(text: str) -> None:
    assert patterns.find_vehicle_identifiers(text) == []


def test_a_plate_is_one_node_however_it_was_typed() -> None:
    spaced = canonicalize("vehicle_identifiers", "MH 12 DE 1433")
    packed = canonicalize("vehicle_identifiers", "mh12de1433")
    assert spaced is not None and packed is not None
    assert spaced.canonical_value == packed.canonical_value


# ---------------------------------------------------------------------------
# Organisations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Paid to Shreeji Traders Pvt. Ltd. on Monday", "Shreeji Traders Pvt. Ltd."),
        ("Acme Logistics LLP raised the invoice", "Acme Logistics LLP"),
        ("transfer to HDFC Bank", "HDFC Bank"),
        ("State Bank of India, Andheri branch", "State Bank of India"),
    ],
)
def test_organisations_need_a_legal_or_business_suffix(text: str, expected: str) -> None:
    assert expected in patterns.find_organisations(text)


@pytest.mark.parametrize("text", ["the bank said no", "he paid the amount", "Ravi Kumar met Yash"])
def test_a_capitalised_phrase_alone_is_not_an_organisation(text: str) -> None:
    assert patterns.find_organisations(text) == []


@pytest.mark.parametrize(
    ("written_one_way", "written_another"),
    [
        ("Shreeji Traders", "Shreeji Traders Pvt. Ltd."),
        ("Acme Logistics", "Acme Logistics LLP"),
        ("Zeta Infra", "Zeta Infra Private Limited"),
    ],
)
def test_a_legal_form_does_not_split_one_counterparty_into_two_nodes(written_one_way: str, written_another: str) -> None:
    assert patterns.normalize_organisation(written_one_way) == patterns.normalize_organisation(written_another)


@pytest.mark.parametrize(("left", "right"), [("Acme Motors", "Acme Traders"), ("HDFC Bank", "HDFC Capital")])
def test_two_different_businesses_are_never_folded_together(left: str, right: str) -> None:
    """A false merge asserts a relationship the evidence never recorded, so it is worse than a split."""
    assert patterns.normalize_organisation(left) != patterns.normalize_organisation(right)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("FIR registered at PS Andheri East", "Andheri East"),
        ("Andheri Police Station, Mumbai", "Andheri"),
        ("District Thane, Maharashtra", "Thane"),
        ("Village Kalwa near the river", "Kalwa"),
        # Here the descriptor is part of the name, not an administrative marker.
        ("last seen at Linking Road", "Linking Road"),
        ("met at Shivaji Nagar", "Shivaji Nagar"),
        ("Crawford Market area", "Crawford Market"),
    ],
)
def test_a_place_is_read_only_where_the_source_marks_one(text: str, expected: str) -> None:
    assert expected in patterns.find_locations(text)


@pytest.mark.parametrize("text", ["Ravi Kumar paid the amount", "Please send it today", "INR 25,000 transferred"])
def test_text_without_a_place_marker_yields_no_location(text: str) -> None:
    """Open-domain place detection over Indian text buries the review queue, so a marker is required."""
    assert patterns.find_locations(text) == []


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Complainant: Ravi Kumar", "Ravi Kumar"),
        ("Accused - Yash Kumar Gupta", "Yash Kumar Gupta"),
        ("Name: Priya Sharma", "Priya Sharma"),
        ("Beneficiary: Anil Gupta", "Anil Gupta"),
        ("Ravi Kumar S/o Mohan Lal", "Mohan Lal"),
    ],
)
def test_a_person_is_read_only_where_a_role_is_stated(text: str, expected: str) -> None:
    assert expected in patterns.find_person_names(text)


@pytest.mark.parametrize(
    "text",
    [
        "Mumbai Central Station is busy",  # a place, capitalised
        "The Accused was seen leaving",  # a role with no name after it
        "Ravi met Yash yesterday",  # names with no stated role
        "To: ravi@example.com",  # a labelled identifier, not a name
        "From: +91 98765 43210",
    ],
)
def test_capitalisation_alone_never_creates_a_person(text: str) -> None:
    assert patterns.find_person_names(text) == []


def test_the_same_name_twice_is_one_node_but_not_a_confirmed_identity() -> None:
    """Two people share a name far more often than they share an account.

    The node records that the name was written down twice. Whether it is the same individual is a
    review decision, which is why the person weight in the connection graph stays low.
    """
    first = canonicalize("person_names", "Ravi Kumar")
    second = canonicalize("person_names", "ravi  kumar")
    assert first is not None and second is not None
    assert first.canonical_value == second.canonical_value == "ravi kumar"


# ---------------------------------------------------------------------------
# Phone numbers written in groups
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["+919876543210", "+91 9876543210", "9876543210", "+91 98765 43210", "98765 43210", "+91-98765-43210", "987 654 3210"],
)
def test_a_mobile_number_is_found_however_it_is_grouped(text: str) -> None:
    """FIRs and signature blocks group the digits; before this the grouped forms were invisible."""
    assert patterns.find_phone_numbers(text) == ["+919876543210"]


@pytest.mark.parametrize("text", ["12345 67890", "A/C 123456789012", "INR 25,000 paid", "2024-03-12 21:15"])
def test_grouped_digits_that_are_not_mobile_numbers_are_left_alone(text: str) -> None:
    assert patterns.find_phone_numbers(text) == []


def test_a_grouped_phone_number_is_never_read_as_money() -> None:
    """The middle group of a spaced number is five digits, which is exactly amount-shaped."""
    assert patterns.find_amount_detail("call 98765 43210 now") is None


# ---------------------------------------------------------------------------
# End to end over one FIR-shaped document
# ---------------------------------------------------------------------------

_FIR = """FIRST INFORMATION REPORT
FIR No: 0142/2026        PS Andheri East, District Mumbai Suburban
Complainant: Ravi Kumar S/o Mohan Lal
Accused: Yash Kumar Gupta
Contact: +91 98765 43210
On 12/03/2026 at 21:15 a vehicle MH12DE1433 was seen near Linking Road.
A payment of INR 25,000 was made to Shreeji Traders Pvt. Ltd.
Beneficiary: Anil Gupta   A/C 123456789012
"""


def test_one_fir_yields_every_entity_class_the_problem_statement_names() -> None:
    observed = {
        "person": patterns.find_person_names(_FIR),
        "vehicle": patterns.find_vehicle_identifiers(_FIR),
        "location": patterns.find_locations(_FIR),
        "organisation": patterns.find_organisations(_FIR),
        "phone": patterns.find_phone_numbers(_FIR),
    }
    empty = sorted(name for name, values in observed.items() if not values)
    assert not empty, f"no {', '.join(empty)} extracted from an FIR that states each one"

    assert "Ravi Kumar" in observed["person"]
    assert observed["vehicle"] == ["MH12DE1433"]
    assert "Andheri East" in observed["location"]
    assert "Shreeji Traders Pvt. Ltd." in observed["organisation"]
    assert observed["phone"] == ["+919876543210"]


def test_every_extracted_class_resolves_to_a_graph_node() -> None:
    """Extraction is only useful if the value reaches the graph as an identity."""
    resolved = {
        canonicalize(field, value).entity_type
        for field, values in (
            ("person_names", patterns.find_person_names(_FIR)),
            ("vehicle_identifiers", patterns.find_vehicle_identifiers(_FIR)),
            ("location_names", patterns.find_locations(_FIR)),
            ("organisation_names", patterns.find_organisations(_FIR)),
            ("phone_numbers", patterns.find_phone_numbers(_FIR)),
        )
        for value in values
        if canonicalize(field, value) is not None
    }
    assert {"person", "vehicle", "location", "organisation", "phone"} <= resolved
