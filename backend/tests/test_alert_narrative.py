"""Alerts that tell the story behind them, and the line that story must not cross.

An alert used to be a count and a list of file ids. A reader who wanted to know what actually
happened had to reconstruct it from the records -- the work the alert existed to save them. Each
alert now carries the sourced facts in the order the sources record them, every line openable at the
page or row it came from.

The risk this creates is the reason most of this file exists. A sequence reads like a story, and a
story invites the reader to supply the connective tissue nobody recorded: he called her *because*,
they met *in order to*. So every statement any rule produces is checked for causal language, every
sequence closes with the line saying whose job the meaning is, and the silences are stated as facts
about the record rather than about the world.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.alerts import narrative
from app.alerts.network_rules import evaluate_network_alerts
from app.core.db import SessionLocal
from app.models.entities import Alert
from scripts import benchmark_case

# The benchmark FIR puts the incident on the evening of 12 July 2026.
INCIDENT = "2026-07-12T21:00:00+00:00"


@pytest.fixture
def worked_case(client, case_factory):
    case, headers = case_factory()
    client.patch(
        f"/api/v1/cases/{case['id']}/incident-window",
        headers=headers,
        json={"date_range_start": INCIDENT, "date_range_end": "2026-07-12T23:59:00+00:00"},
    )
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
    _evaluate(case["id"])
    return case, headers


def _evaluate(case_id: str) -> dict:
    db = SessionLocal()
    try:
        counts = evaluate_network_alerts(db, case_id)
        db.commit()
        return counts
    finally:
        db.close()


def _alerts(case_id: str) -> list[Alert]:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(Alert).where(Alert.case_id == case_id)))
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


def _statements(alerts: list[Alert]) -> list[str]:
    lines = [alert.explanation for alert in alerts]
    for alert in alerts:
        lines.extend(step["statement"] for step in alert.sequence or [])
    return lines


# --------------------------------------------------------------------------- the sequence


def test_every_alert_carries_its_sequence(worked_case) -> None:
    case, _ = worked_case
    alerts = _alerts(case["id"])

    assert alerts, "the benchmark case raises alerts"
    for alert in alerts:
        assert alert.sequence, f"{alert.rule_code} states a pattern without showing what it is built from"


def test_every_fact_in_a_sequence_can_be_opened(worked_case) -> None:
    """A line that names no file is a claim the reader has to take on trust."""
    case, _ = worked_case
    for alert in _alerts(case["id"]):
        for step in alert.sequence:
            if step["kind"] != "fact":
                continue
            assert step["evidence_id"], f"{alert.rule_code} has a fact with no source file"
            assert step["statement"].strip()


def test_a_sequence_is_in_the_order_the_sources_time_it(worked_case) -> None:
    case, _ = worked_case
    for alert in _alerts(case["id"]):
        timed = [step["when"] for step in alert.sequence if step["kind"] == "fact" and step["when"]]
        assert timed == sorted(timed), f"{alert.rule_code} tells its story out of order"


def test_every_sequence_closes_on_the_same_line(worked_case) -> None:
    """The system orders facts. It does not read them, and each sequence says so."""
    case, _ = worked_case
    for alert in _alerts(case["id"]):
        assert alert.sequence[-1]["kind"] == "closing"
        assert alert.sequence[-1]["statement"] == narrative.SEQUENCE_CLOSING


# --------------------------------------------------------------------------- the line it must not cross


def test_no_line_anywhere_states_a_cause(worked_case) -> None:
    """The sources record what happened, never why. Neither may any sentence built from them."""
    case, _ = worked_case
    for line in _statements(_alerts(case["id"])):
        lowered = f" {line.lower()} "
        for forbidden in narrative.FORBIDDEN_IN_A_STATEMENT:
            assert forbidden not in lowered, f"causal language {forbidden!r} in: {line}"


def test_a_silence_is_stated_as_a_fact_about_the_record(worked_case) -> None:
    case, _ = worked_case
    gaps = [
        step
        for alert in _alerts(case["id"])
        for step in alert.sequence
        if step["kind"] == "gap" and "no contact" in step["statement"]
    ]
    for gap in gaps:
        assert "not the same as nothing having happened" in gap["statement"]


def test_an_untimed_fact_is_kept_but_not_placed() -> None:
    """Slotting a fact with no established time between two timed ones would invent an order."""
    steps = [
        narrative.Step(statement="Second.", when=__import__("datetime").datetime(2026, 7, 12, 21, 0)),
        narrative.Step(statement="First.", when=__import__("datetime").datetime(2026, 7, 12, 19, 0)),
        narrative.Step(statement="Untimed."),
    ]
    rendered = narrative.sequence(steps)
    facts = [item for item in rendered if item["kind"] == "fact"]

    assert [item["statement"] for item in facts] == ["First.", "Second.", "Untimed."]
    assert facts[-1]["when"] is None
    assert any("no established time" in item["statement"] for item in rendered)


def test_a_pattern_with_one_fact_still_renders() -> None:
    rendered = narrative.sequence([narrative.Step(statement="Only this.", evidence_id="e1")])
    assert [item["kind"] for item in rendered] == ["fact", "closing"]


# --------------------------------------------------------------------------- the five new rules


# The benchmark case is one evening: three parties calling each other between 19:47 and 22:03. A
# relay is exactly the shape that data has. Sudden silence is not -- there is no later record for a
# pair to be silent through -- and a rule that fired on it anyway would be reporting its own
# thresholds rather than the evidence. It is exercised on data built for it instead.
EXPECTED_ON_BENCHMARK = {"RELAY_CONTACT"}


def test_the_new_rules_fire_on_the_benchmark_case(worked_case) -> None:
    case, _ = worked_case
    raised = {alert.rule_code for alert in _alerts(case["id"])}
    missing = EXPECTED_ON_BENCHMARK - raised
    assert not missing, f"expected these patterns in the benchmark data: {missing}"


def test_a_rule_stays_silent_on_a_case_with_nothing_in_it(case_factory) -> None:
    """A rule that fires on an empty case is reporting its own thresholds, not the evidence."""
    case, _ = case_factory()
    counts = _evaluate(case["id"])
    assert counts["total_new"] == 0
    assert _alerts(case["id"]) == []


def test_reprocessing_raises_no_duplicates(worked_case) -> None:
    case, _ = worked_case
    before = len(_alerts(case["id"]))

    assert _evaluate(case["id"])["total_new"] == 0, "a second run must add nothing"
    assert len(_alerts(case["id"])) == before


def test_no_alert_names_another_case(client, case_factory, worked_case) -> None:
    """Cross-case disclosure is what the case-level authorisation model exists to prevent."""
    case, headers = worked_case
    other, _ = case_factory(headers)
    for alert in _alerts(case["id"]):
        assert other["id"] not in (alert.explanation + str(alert.sequence))
        assert other["case_number"] not in alert.explanation


def test_every_alert_names_at_least_one_evidence_file(worked_case) -> None:
    case, _ = worked_case
    for alert in _alerts(case["id"]):
        assert alert.affected_evidence_ids, f"{alert.rule_code} tells a reviewer to look at nothing"


# --------------------------------------------------------------------------- contact that stops


def test_silence_is_measured_against_the_end_of_the_record_not_the_end_of_the_pair(client, case_factory) -> None:
    """Without that comparison every pair looks silent at the edge of the data, because that is
    where the evidence stops -- not where the contact did."""
    from datetime import datetime, timedelta, timezone

    from app.models.entities import Entity, EntityRelation
    from app.services import temporal

    case, headers = case_factory()
    # Entities and relations may not exist without a source. Uploading one file gives the synthetic
    # rows something real to point at rather than working around the invariant that guarantees
    # every edge in this system can be opened.
    upload = client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        headers=headers,
        data={"source_category": "other"},
        files={"file": ("synthetic-note.txt", b"SYNTHETIC TEST ONLY.", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    evidence_id = upload.json()["evidence"]["id"]

    db = SessionLocal()
    try:
        made = []
        for value in ("+919000000001", "+919000000002", "+919000000003"):
            entity = Entity(
                case_id=case["id"], entity_type="phone", value=value, normalized_value=value,
                source_evidence_id=evidence_id, source_reference="synthetic-note.txt row 1",
                extraction_method="synthetic_test", confidence=0.9,
            )
            db.add(entity)
            made.append(entity)
        db.flush()
        quiet_pair, talking_pair = made[0], made[1]
        opens = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)

        def contact(subject, object_, at):
            db.add(EntityRelation(
                case_id=case["id"], subject_entity_id=subject.id, object_entity_id=object_.id,
                relation_type="CALLED", directed=True, observed_at=at,
                idempotency_key=f"synthetic:{subject.id}:{object_.id}:{at.isoformat()}",
                source_evidence_id=evidence_id, source_reference={"row": 1},
                extraction_method="synthetic_test", confidence=0.9,
            ))

        # A pair in daily contact for four days, then nothing.
        for day in range(4):
            contact(quiet_pair, talking_pair, opens + timedelta(days=day))
        # The record keeps going for another fortnight, with a different pair still in contact.
        for day in range(4, 18):
            contact(talking_pair, made[2], opens + timedelta(days=day))
        db.commit()

        findings = temporal.sudden_silence(db, case["id"])
    finally:
        db.close()

    silent = {finding["pair"] for finding in findings}
    assert tuple(sorted((quiet_pair.id, talking_pair.id))) in silent, "the pair that stopped must be reported"
    assert tuple(sorted((talking_pair.id, made[2].id))) not in silent, (
        "a pair still in contact at the end of the record has not gone silent"
    )


# --------------------------------------------------------------------------- one handset, two numbers


def test_two_numbers_on_one_handset_are_reported(worked_case) -> None:
    """The strongest thing a CDR carries beyond the calls, and nothing else finds it."""
    case, _ = worked_case
    shared = [alert for alert in _alerts(case["id"]) if alert.rule_code == "SHARED_DEVICE"]

    assert shared, "the benchmark CDR records two numbers against one handset"
    assert "different numbers are recorded against the same handset" in shared[0].explanation


def test_a_shared_handset_does_not_say_who_it_belongs_to(worked_case) -> None:
    """One person with two numbers, a phone passed on, a SIM moved -- the record says none of it."""
    case, _ = worked_case
    for alert in _alerts(case["id"]):
        if alert.rule_code != "SHARED_DEVICE":
            continue
        assert "does not say which of those it was" in alert.explanation
        assert "same person" not in alert.explanation.lower()


def test_the_handset_is_attributed_to_the_party_whose_record_it_is(client, case_factory) -> None:
    """A call record's IMEI belongs to the calling party, not to the number they rang.

    Attributing it to both would have this rule announce that two people share a handset on the
    evidence of a single call between them -- the false accusation it exists to avoid.
    """
    case, headers = case_factory()
    rows = "\n".join([
        "a_party,b_party,date,time,duration_seconds,cell_id,call_type,imei",
        "+919000000011,+919000000022,12/07/2026,19:47,60,MUM-0001,outgoing,111111111111111",
        "+919000000011,+919000000033,12/07/2026,20:10,60,MUM-0001,outgoing,111111111111111",
    ])
    upload = client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        headers=headers,
        data={"source_category": "cdr"},
        files={"file": ("one_caller.csv", rows.encode(), "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    _evaluate(case["id"])

    shared = [alert for alert in _alerts(case["id"]) if alert.rule_code == "SHARED_DEVICE"]
    assert shared == [], (
        "one number called two others from one handset; nothing there is shared and no alert is due"
    )
