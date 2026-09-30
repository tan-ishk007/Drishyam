"""Seed the synthetic national record of registered cases.

In a real deployment this table is an extract from NCRB or a state CCTNS, loaded on a schedule and
owned by whoever is entitled to hold it. There is no such feed here, so this writes a small
fictional one that matches the benchmark case — enough to show what the lookup does without
pretending to be a national database.

**Every name and number below is invented.** They are the benchmark case's own identifiers, which
exist nowhere outside this repository.

The shape of the data is deliberate. Of the six records seeded, one is a conviction, two are still
open, one ended in acquittal, one was closed without a chargesheet and one was quashed. A demo
dataset of six convictions would make the feature look impressive and teach every viewer the exact
inference this product exists to refuse — that a prior record is evidence of the present one.

    python -m scripts.seed_prior_records [--clear]
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

from sqlalchemy import delete, select  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.models.entities import PriorRecord  # noqa: E402
from app.services.entity_resolution import canonicalize_indicator  # noqa: E402

SOURCE = "synthetic-national-dataset"


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


# (identifier_type, identifier as it would be written, subject, reference, station, district,
#  sections, registered, disposal, disposed, officer)
RECORDS = [
    (
        "phone", "+919876543210", "Yash Kumar Gupta",
        "FIR 0231/2024", "Andheri East Police Station", "Mumbai Suburban",
        ["BNS 318(4)", "IT Act 66D"], _at(2024, 8, 14),
        "chargesheeted", _at(2025, 1, 9), "PI A. Deshmukh",
    ),
    (
        "phone", "+919876543210", "Yash Kumar Gupta",
        "FIR 0044/2022", "Kurla Police Station", "Mumbai Suburban",
        ["BNS 316(2)"], _at(2022, 2, 3),
        "acquitted", _at(2023, 11, 27), "PI S. Rane",
    ),
    (
        "phone", "+919988776655", "Ravi Kumar",
        "FIR 0117/2025", "Bandra Police Station", "Mumbai Suburban",
        ["BNS 318(4)"], _at(2025, 5, 21),
        "under_investigation", None, "SI M. Kulkarni",
    ),
    (
        "phone", "+919123456789", "Mohan Lal",
        "FIR 0402/2021", "Goregaon Police Station", "Mumbai Suburban",
        ["MV Act 184"], _at(2021, 9, 2),
        "closed", _at(2022, 3, 18), "PSI R. Patil",
    ),
    (
        "vehicle", "MH12DE1433", None,
        "FIR 0088/2023", "Pune City Police Station", "Pune",
        ["BNS 303(2)"], _at(2023, 4, 11),
        "convicted", _at(2024, 7, 30), "PI D. Jadhav",
    ),
    (
        "upi", "skyline.manpower@upi", "Skyline Manpower Services",
        "FIR 0155/2025", "Cyber Police Station", "Thane",
        ["BNS 318(4)", "IT Act 66D"], _at(2025, 6, 8),
        "quashed", _at(2026, 2, 12), "API N. Shaikh",
    ),
]


def seed(clear: bool = False) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    written = 0
    try:
        if clear:
            db.execute(delete(PriorRecord).where(PriorRecord.source == SOURCE))
            db.commit()

        for (
            identifier_type, written_as, subject, reference, station, district,
            sections, registered, disposal, disposed, officer,
        ) in RECORDS:
            # Stored canonical, because that is what the lookup matches on. A record filed under the
            # way somebody happened to type a number would never be found again.
            resolved = canonicalize_indicator(identifier_type, written_as)
            if resolved is None:
                print(f"  skipped (not canonicalisable): {written_as}")
                continue

            exists = db.scalar(
                select(PriorRecord).where(
                    PriorRecord.record_reference == reference,
                    PriorRecord.identifier_type == resolved.entity_type,
                    PriorRecord.identifier_value == resolved.canonical_value,
                )
            )
            if exists is not None:
                continue

            db.add(PriorRecord(
                identifier_type=resolved.entity_type,
                identifier_value=resolved.canonical_value,
                subject_name=subject,
                record_reference=reference,
                police_station=station,
                district=district,
                sections=sections,
                registered_on=registered,
                disposal=disposal,
                disposal_on=disposed,
                contact_officer=officer,
                source=SOURCE,
            ))
            written += 1
        db.commit()
    finally:
        db.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove previously seeded synthetic records first")
    args = parser.parse_args()

    written = seed(clear=args.clear)
    print(f"seeded {written} synthetic prior record(s) from {len(RECORDS)} declared")
    print("Every identifier and name in this dataset is fictional and exists only in this repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
