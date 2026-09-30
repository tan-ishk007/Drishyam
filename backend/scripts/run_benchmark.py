"""Ingest the benchmark case and measure what the system found against what is true of it.

This exists so the project can state accuracy per component with numbers. A single headline "AI
accuracy" figure is not defensible and invites exactly the challenge it cannot answer; a table of
per-component recall, each line re-derivable by running this script, can be defended line by line.

Two kinds of result, and the distinction matters:

  Measurements are reported, never graded. Recall on a deliberately blurred screenshot is a
  number to publish, not a bar to clear -- a system honest about what it could not read is behaving
  correctly, and a benchmark that punished it would push toward guessing.

  Restraint checks are pass or fail. Inventing a number nobody wrote, merging two people whose
  names differ by a letter, silently resolving a contradiction, or letting one malformed file take
  down a case are wrong at any accuracy.

The same run also records provider latency per file, which is how the local-versus-hosted model
question gets settled with data instead of impressions. Run it once per provider and compare.

    python -m scripts.run_benchmark [--json PATH] [--keep-case]

The case it creates is deleted afterwards unless --keep-case is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("EMAIL_PROVIDER", "console")
os.environ.setdefault("ALLOW_LOCAL_CONSOLE_EMAIL", "true")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import (  # noqa: E402
    Alert,
    Entity,
    EntityOccurrence,
    EntityRelation,
    Event,
    EventEntity,
    EvidenceFile,
    ModelInferenceRun,
    NormalizedRecord,
)
from scripts import benchmark_case  # noqa: E402

GROUND_TRUTH = benchmark_case.GROUND_TRUTH


# --------------------------------------------------------------------------- result shapes


@dataclass
class Measurement:
    """One component measured two ways, because one way is not enough to judge it by.

    **Recall** is how much of what is declared was found. A system can reach 1.0 by extracting
    everything it sees, which is why it must never be published alone.

    **Precision** is how much of what was found is real. It is the number that catches a phantom
    entity -- a digit misread out of a blurred image, a handle truncated halfway -- and it is the
    one an investigator actually depends on, because a wrong identity in a case file costs more
    than a missing one.

    `returned` is how many the system produced of this kind. It is None where the ground truth does
    not list the type completely, and precision is then reported as unmeasurable rather than
    guessed: scoring a correctly extracted entity nobody annotated as an error would be a worse
    lie than reporting no number at all.
    """

    name: str
    found: int
    expected: int
    returned: int | None = None
    detail: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return (self.found / self.expected) if self.expected else 1.0

    @property
    def precision(self) -> float | None:
        if self.returned is None:
            return None
        return (self.found / self.returned) if self.returned else 1.0

    @property
    def f1(self) -> float | None:
        """The harmonic mean, which a system cannot raise by sacrificing one side for the other."""
        precision = self.precision
        if precision is None:
            return None
        if precision + self.recall == 0:
            return 0.0
        return 2 * precision * self.recall / (precision + self.recall)

    def to_dict(self) -> dict:
        body = {
            "name": self.name,
            "found": self.found,
            "expected": self.expected,
            "recall": round(self.recall, 4),
            "detail": self.detail,
        }
        if self.returned is None:
            body["precision"] = None
            body["f1"] = None
            body["precision_note"] = (
                "Not measurable: this benchmark does not list every instance of this type, so an "
                "extraction it did not annotate cannot be told apart from a mistake."
            )
        else:
            body["returned"] = self.returned
            body["precision"] = round(self.precision, 4)
            body["f1"] = round(self.f1, 4)
        return body


@dataclass
class Check:
    """A property that is wrong at any accuracy, so it is graded rather than measured.

    `status` is deliberately three-valued. A check whose precondition did not hold -- the merge
    check when only one of the two names was ever extracted -- has not been verified, and calling
    that a pass would claim a guarantee nothing established.
    """

    name: str
    status: str  # "pass", "fail" or "not_verified"
    explanation: str

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "explanation": self.explanation}


# --------------------------------------------------------------------------- ingestion


def _otp_for(email: str) -> str:
    """The verification code, read from the local console mailbox the dev email provider writes."""
    from app.core.config import get_settings

    mailbox = get_settings().storage_root.parent / "dev_mailbox"
    for message in sorted(mailbox.glob("verification-*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        payload = json.loads(message.read_text(encoding="utf-8"))
        if payload["to"] == email:
            return payload["verification_code"]
    raise RuntimeError(
        f"No verification code was written for {email}. The benchmark needs the console email "
        "provider: set EMAIL_PROVIDER=console and ALLOW_LOCAL_CONSOLE_EMAIL=true."
    )


def _sign_up(client: TestClient) -> dict[str, str]:
    email = f"benchmark.{int(time.time())}@example.com"
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Benchmark Runner", "email": email, "password": "BenchmarkRunner!2026", "role": "investigator"},
    )
    signup.raise_for_status()
    verified = client.post("/api/v1/auth/verify", json={"email": email, "otp": _otp_for(email)})
    verified.raise_for_status()
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def ingest(client: TestClient, headers: dict[str, str]) -> tuple[str, dict[str, dict]]:
    """Upload every file of the benchmark case and record how each one fared."""
    case = client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "title": "SIH26189 benchmark case (synthetic)",
            "crime_type": "organised_network",
            "description": "Synthetic benchmark material. Fictional throughout.",
            "priority": "high",
        },
    )
    case.raise_for_status()
    case_id = case.json()["id"]

    # Declare the incident window. Without one, every rule that places contact relative to the
    # incident has nothing to place it against and stays silent -- which the harness would then
    # report as a detection failure rather than as the missing input it actually is.
    opens, closes = benchmark_case.INCIDENT_WINDOW
    client.patch(
        f"/api/v1/cases/{case_id}/incident-window",
        headers=headers,
        json={"date_range_start": opens, "date_range_end": closes},
    ).raise_for_status()

    artifacts = benchmark_case.generate()
    outcomes: dict[str, dict] = {}
    for name, path in artifacts.items():
        category = benchmark_case.ARTIFACTS[name]
        started = time.monotonic()
        with Path(path).open("rb") as stream:
            response = client.post(
                f"/api/v1/cases/{case_id}/evidence",
                headers=headers,
                data={"source_category": category},
                files={"file": (Path(path).name, stream, "application/octet-stream")},
            )
        elapsed = time.monotonic() - started
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        outcomes[name] = {
            "category": category,
            "http_status": response.status_code,
            "evidence_id": (body.get("evidence") or {}).get("id"),
            "seconds": round(elapsed, 2),
        }
    return case_id, outcomes


# --------------------------------------------------------------------------- measurement


def _entities(db, case_id: str) -> list[Entity]:
    return list(db.scalars(select(Entity).where(Entity.case_id == case_id)))


def _sources_for(db, entity: Entity) -> set[str]:
    """Every evidence file this identity was seen in, by both routes the system records."""
    files = set(db.scalars(select(EntityOccurrence.evidence_id).where(EntityOccurrence.entity_id == entity.id)))
    for event_id in db.scalars(select(EventEntity.event_id).where(EventEntity.entity_id == entity.id)):
        source = db.scalar(select(Event.source_file_id).where(Event.id == event_id))
        if source:
            files.add(source)
    if entity.source_evidence_id:
        files.add(entity.source_evidence_id)
    return files


def measure_entities(db, case_id: str) -> tuple[list[Measurement], dict[str, Entity]]:
    found = _entities(db, case_id)
    index = {(item.entity_type, item.normalized_value.casefold()): item for item in found}

    # What the system produced, per type, so precision has a denominator. Counted over distinct
    # canonical values: the same identity resolved from four files is one entity, and counting it
    # four times would make the figure describe the evidence rather than the extraction.
    returned_by_type: dict[str, set[str]] = {}
    for item in found:
        returned_by_type.setdefault(item.entity_type, set()).add((item.normalized_value or "").casefold())

    declared = {(item.entity_type, item.normalized_value.casefold()) for item in GROUND_TRUTH.entities}

    by_class: dict[str, Measurement] = {}
    resolved: dict[str, Entity] = {}
    for expected in GROUND_TRUTH.entities:
        measurement = by_class.setdefault(expected.entity_type, Measurement(f"entity — {expected.entity_type}", 0, 0))
        measurement.expected += 1
        hit = index.get((expected.entity_type, expected.normalized_value.casefold()))
        if hit is not None:
            measurement.found += 1
            # Keyed by both, because entities are declared by canonical value and the relations
            # below are declared by the label a reader recognises.
            resolved[expected.normalized_value] = hit
            resolved[expected.label] = hit
        else:
            measurement.detail.append(f"not found: {expected.label}")

    for entity_type, measurement in by_class.items():
        if entity_type not in GROUND_TRUTH.exhaustive_types:
            continue
        produced = returned_by_type.get(entity_type, set())
        measurement.returned = len(produced)
        # Name every extra. A precision figure with nothing behind it cannot be acted on, and each
        # of these is either a defect to fix or a gap in the ground truth to close.
        for value in sorted(produced):
            if (entity_type, value) not in declared:
                measurement.detail.append(f"found but not declared: {value}")

    return list(by_class.values()), resolved


def measure_cross_source(db, case_id: str, resolved: dict[str, Entity], outcomes: dict[str, dict]) -> Measurement:
    """Whether an identity written in several files became one node reachable from each of them.

    This is the measurement the product exists for. An identifier found four times in four files
    and stored as four nodes has been extracted but not resolved.
    """
    evidence_of = {name: data["evidence_id"] for name, data in outcomes.items()}
    measurement = Measurement("cross-source resolution (identity × source)", 0, 0)
    for expected in GROUND_TRUTH.entities:
        if len(expected.sources) < 2:
            continue
        entity = resolved.get(expected.normalized_value)
        seen = _sources_for(db, entity) if entity is not None else set()
        for source_name in expected.sources:
            measurement.expected += 1
            if evidence_of.get(source_name) and evidence_of[source_name] in seen:
                measurement.found += 1
            else:
                measurement.detail.append(f"{expected.label} not linked to {source_name}")
    return measurement


def measure_relations(db, case_id: str, resolved: dict[str, Entity]) -> Measurement:
    relations = list(db.scalars(select(EntityRelation).where(EntityRelation.case_id == case_id)))
    pairs = {(item.subject_entity_id, item.relation_type, item.object_entity_id) for item in relations}

    measurement = Measurement("relationship recall", 0, len(GROUND_TRUTH.relations))
    for expected in GROUND_TRUTH.relations:
        subject = resolved.get(expected.subject)
        target = resolved.get(expected.object)
        if subject is None or target is None:
            measurement.detail.append(f"{expected.subject} {expected.predicate} {expected.object}: an endpoint was never resolved")
            continue
        directed = (subject.id, expected.predicate, target.id) in pairs
        reverse = (target.id, expected.predicate, subject.id) in pairs
        if directed or reverse:
            measurement.found += 1
        else:
            measurement.detail.append(f"missing: {expected.subject} {expected.predicate} {expected.object} ({expected.note})")
    return measurement


def measure_image_only_identifiers(db, case_id: str, outcomes: dict[str, dict]) -> Measurement:
    """Identifiers that exist on the strength of one image and nothing else.

    Reading text off a photograph is where a wrong character becomes a wrong node. In this case a
    blurred screenshot yields "+919676543210" -- one digit away from a number written plainly in
    four other files -- and a truncated handle, both of which enter the graph looking exactly like
    an identifier somebody wrote down.

    This is reported, not graded. OCR misreads a degraded image; that is a fact about images, not a
    defect to be failed. What matters is that they are countable and nameable, so the review queue
    can be pointed at them and a claim about them can be stated honestly.

    Lower is better, so `found` counts the identifiers that were corroborated somewhere else.
    """
    image_sources = {
        data["evidence_id"]
        for name, data in outcomes.items()
        if benchmark_case.ARTIFACTS.get(name) in {"whatsapp_screenshot", "screenshot", "chat_screenshot"}
        and data["evidence_id"]
    }
    identifier_types = {"phone", "email", "upi", "account", "ifsc", "reference", "url", "vehicle", "device"}

    measurement = Measurement("identifiers corroborated outside an image", 0, 0)
    for entity in _entities(db, case_id):
        if entity.entity_type not in identifier_types:
            continue
        sources = _sources_for(db, entity)
        if not sources or not sources <= image_sources:
            measurement.expected += 1
            measurement.found += 1
            continue
        measurement.expected += 1
        measurement.detail.append(f"only an image supports {entity.value} ({entity.entity_type}) — a review lead, not a fact")
    return measurement


def measure_traceability(db, case_id: str) -> Measurement:
    """The headline claim: every stored statement names the evidence it came from."""
    rows = 0
    traced = 0
    for entity in _entities(db, case_id):
        rows += 1
        traced += 1 if entity.source_evidence_id and entity.source_reference else 0
    for relation in db.scalars(select(EntityRelation).where(EntityRelation.case_id == case_id)):
        rows += 1
        traced += 1 if relation.source_evidence_id and relation.source_reference else 0
    for record in db.scalars(select(NormalizedRecord).where(NormalizedRecord.case_id == case_id)):
        rows += 1
        traced += 1 if record.evidence_id else 0
    return Measurement("traceability coverage", traced, rows)


# --------------------------------------------------------------------------- restraint


def check_no_fabricated_number(db, case_id: str) -> Check:
    prefix = GROUND_TRUTH.forbidden_phone_prefix
    invented = [
        item.value
        for item in _entities(db, case_id)
        if item.entity_type == "phone" and item.normalized_value.lstrip("+").removeprefix("91").startswith(prefix)
    ]
    return Check(
        "a handwritten field that does not resolve is not completed",
        "fail" if invented else "pass",
        f"the smudged field was completed into: {', '.join(invented)}"
        if invented
        else "no number was invented from the smudged field",
    )


NAMES_CHECK = "two people whose names differ by one letter stay two nodes"


def check_similar_names_stay_apart(db, case_id: str) -> Check:
    """Merging is the failure. Extracting only one of the two is a recall miss, reported above.

    Reporting a miss as a merge failure would blame the wrong component and, worse, would make the
    check start passing the moment extraction got worse.
    """
    people = [item for item in _entities(db, case_id) if item.entity_type == "person"]
    by_value = {item.normalized_value.casefold(): item for item in people}

    for left, right in GROUND_TRUTH.must_not_merge:
        found_left, found_right = by_value.get(left), by_value.get(right)
        if found_left is not None and found_right is not None:
            if found_left.id == found_right.id:
                return Check(NAMES_CHECK, "fail", f"'{left}' and '{right}' resolved to the same node")
            continue
        present = [name for name in (left, right) if name in by_value] or ["neither"]
        return Check(
            NAMES_CHECK,
            "not_verified",
            f"only {', '.join(present)} was extracted, so nothing established whether the two would have been merged",
        )
    return Check(NAMES_CHECK, "pass", "both names are present as separate nodes")


def check_conflict_survives(db, case_id: str) -> Check:
    """Both readings of the disputed time must still be on record somewhere in the case."""
    corpus: list[str] = []
    for record in db.scalars(select(NormalizedRecord).where(NormalizedRecord.case_id == case_id)):
        corpus.append(f"{record.observed_text or ''} {record.event_time_raw or ''}")
    for event in db.scalars(select(Event).where(Event.case_id == case_id)):
        corpus.append(f"{event.description or ''} {event.original_time or ''} {event.occurred_at or ''}")
    blob = " ".join(corpus)
    missing = [reading for reading in GROUND_TRUTH.conflicting_readings if reading not in blob]
    return Check(
        "two sources that disagree about a time both stay on record",
        "fail" if missing else "pass",
        f"a reading was dropped rather than kept for review: {missing}" if missing else "both readings are retained",
    )


def check_malformed_is_contained(outcomes: dict[str, dict]) -> Check:
    malformed = outcomes.get(GROUND_TRUTH.malformed_file, {})
    others = {name: data for name, data in outcomes.items() if name != GROUND_TRUTH.malformed_file}
    healthy = [name for name, data in others.items() if data["http_status"] == 201]
    contained = len(healthy) == len(others)
    return Check(
        "one malformed file does not take the case down with it",
        "pass" if contained else "fail",
        f"the malformed file returned HTTP {malformed.get('http_status')} and the other {len(healthy)} files processed"
        if contained
        else f"other files failed alongside it: {sorted(set(others) - set(healthy))}",
    )


# --------------------------------------------------------------------------- provider timing


def provider_timing(db, case_id: str) -> dict:
    runs = list(db.scalars(select(ModelInferenceRun).where(ModelInferenceRun.case_id == case_id)))
    by_provider: dict[str, list[int]] = {}
    cached = 0
    for run in runs:
        if run.status == "cached":
            cached += 1
            continue
        if run.latency_ms is not None:
            by_provider.setdefault(f"{run.provider}:{run.model_name}", []).append(run.latency_ms)

    summary = {}
    for key, values in by_provider.items():
        summary[key] = {
            "calls": len(values),
            "median_ms": int(statistics.median(values)),
            "slowest_ms": max(values),
            "total_s": round(sum(values) / 1000, 1),
        }
    return {"providers": summary, "reused_from_cache": cached, "total_runs": len(runs)}


# --------------------------------------------------------------------------- reporting


def measure_planted_patterns(db, case_id: str) -> Measurement:
    """Whether the rules found the patterns deliberately planted in this evidence.

    Measuring extraction is not measuring detection. A benchmark that counted only entities would
    give full marks to a case whose rules never fired once, so the patterns the evidence was built
    to contain are declared in the ground truth and checked for here.

    Precision is left unmeasured on purpose. A rule firing on something nobody planted is not
    thereby wrong -- synthetic evidence has shapes its authors did not intend, and scoring those as
    false positives would push the rules toward finding less than is there.
    """
    raised = {
        row.rule_code
        for row in db.scalars(select(Alert).where(Alert.case_id == case_id))
    }
    measurement = Measurement("planted patterns detected", 0, 0)
    for rule_code, description in GROUND_TRUTH.planted_patterns:
        measurement.expected += 1
        if rule_code in raised:
            measurement.found += 1
        else:
            measurement.detail.append(f"not raised: {rule_code} — {description}")
    return measurement


def render(report: dict) -> str:
    lines = [
        "",
        "=" * 78,
        f"  DRISHYAM benchmark — {report['generated_at']}",
        f"  case: {report['case_id']}    files: {report['files']}",
        "=" * 78,
        "",
        "MEASURED (reported, not graded)",
        f"  {'component':<40} {'recall':>8} {'precis.':>8} {'F1':>7}   found/declared",
        "  " + "-" * 74,
    ]
    for item in report["measurements"]:
        precision = "     n/a" if item.get("precision") is None else f"{item['precision']*100:7.1f}%"
        f1 = "    n/a" if item.get("f1") is None else f"{item['f1']*100:6.1f}%"
        lines.append(
            f"  {item['name']:<40} {item['recall']*100:7.1f}% {precision} {f1}   {item['found']}/{item['expected']}"
            + (f" of {item['returned']} returned" if item.get("returned") is not None else "")
        )
        for note in item["detail"][:5]:
            lines.append(f"      - {note}")
    lines += [
        "",
        "  Recall is how much of what this benchmark declares was found. Precision is how much of",
        "  what was found is declared -- it is the figure that catches an entity the system invented,",
        "  and it is reported only for the types this benchmark lists completely. Where it reads n/a,",
        "  the ground truth is partial and any precision figure would punish correct extractions it",
        "  simply never annotated.",
    ]

    lines += ["", "RESTRAINT (pass or fail)"]
    marker = {"pass": "PASS", "fail": "FAIL", "not_verified": " -- "}
    for item in report["checks"]:
        lines.append(f"  [{marker[item['status']]}] {item['name']}")
        lines.append(f"         {item['explanation']}")

    lines += ["", "INGESTION"]
    for name, data in report["ingestion"].items():
        lines.append(f"  {name:<22} {data['category']:<20} HTTP {data['http_status']}  {data['seconds']:>6.2f}s")

    timing = report["model_calls"]
    lines += ["", "MODEL CALLS"]
    if timing["providers"]:
        for key, data in timing["providers"].items():
            lines.append(f"  {key:<34} {data['calls']:>3} calls   median {data['median_ms']:>6} ms   slowest {data['slowest_ms']:>6} ms   total {data['total_s']}s")
    else:
        lines.append("  no provider calls recorded (every answer was already on record, or no model is configured)")
    lines.append(f"  reused from cache: {timing['reused_from_cache']} of {timing['total_runs']} runs")

    failed = [item for item in report["checks"] if item["status"] == "fail"]
    unverified = [item for item in report["checks"] if item["status"] == "not_verified"]
    verdict = f"  {len(report['checks']) - len(failed) - len(unverified)}/{len(report['checks'])} restraint checks passed"
    if unverified:
        verdict += f", {len(unverified)} not verified"
    if failed:
        verdict += f", {len(failed)} FAILED"
    lines += ["", "=" * 78, verdict, "=" * 78, ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also write the full report to this path")
    parser.add_argument("--keep-case", action="store_true", help="leave the benchmark case in the database")
    args = parser.parse_args()

    with TestClient(app) as client:
        headers = _sign_up(client)
        case_id, outcomes = ingest(client, headers)

        db = SessionLocal()
        try:
            entity_measurements, resolved = measure_entities(db, case_id)
            measurements = [
                *entity_measurements,
                measure_cross_source(db, case_id, resolved, outcomes),
                measure_relations(db, case_id, resolved),
                measure_image_only_identifiers(db, case_id, outcomes),
                measure_traceability(db, case_id),
                measure_planted_patterns(db, case_id),
            ]
            checks = [
                check_no_fabricated_number(db, case_id),
                check_similar_names_stay_apart(db, case_id),
                check_conflict_survives(db, case_id),
                check_malformed_is_contained(outcomes),
            ]
            timing = provider_timing(db, case_id)
            evidence_count = len(list(db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))))
        finally:
            db.close()

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "case_id": case_id,
            "files": evidence_count,
            "measurements": [item.to_dict() for item in measurements],
            "checks": [item.to_dict() for item in checks],
            "ingestion": outcomes,
            "model_calls": timing,
        }

        print(render(report))
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"written: {args.json}")

        if not args.keep_case:
            client.delete(f"/api/v1/cases/{case_id}", headers=headers)

    return 1 if any(item.failed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
