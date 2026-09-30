"""Merge entity nodes that two extraction generations split apart.

The deterministic regex extractor and the grounded pipeline both write into `entities`, and until
now they disagreed on how to canonicalize a value: one wrote a phone as "+919876543210", the other
keyed on the last ten digits. The same number therefore existed twice -- one node holding the
relationships and occurrences, the other holding the event links -- so the graph showed two people
where there was one, and a number seen in a chat never joined the same number seen in a statement.

The extractors now share one resolver. This repairs the rows written before that.

Running it twice changes nothing the second time. It reads every entity, re-resolves it, and where
several rows in a case resolve to one node it keeps the row that already carries the resolved key
(or, failing that, the best-linked row), repoints every reference at it, and deletes the rest.
Rows that would collide with a link the survivor already has are dropped rather than duplicated.

    python -m scripts.merge_split_entities [--apply]

Without --apply it only reports.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import delete, select, update

from app.core.db import SessionLocal
from app.models.entities import Entity, EventEntity
from app.services.entity_resolution import canonicalize_indicator

try:  # These arrived with the grounded pipeline and may be absent in an older schema.
    from app.models.entities import EntityOccurrence, EntityRelation
except ImportError:  # pragma: no cover - defensive
    EntityOccurrence = EntityRelation = None  # type: ignore[assignment]


def _resolved_key(entity: Entity) -> tuple[str, str]:
    """The node this row belongs to, or the row's own key when nothing resolves it."""
    identity = canonicalize_indicator(entity.entity_type, entity.value or entity.normalized_value)
    if identity is None:
        return entity.entity_type, entity.normalized_value
    return identity.entity_type, identity.canonical_value


def _survivor(rows: list[Entity], key: tuple[str, str], links: dict[str, int]) -> Entity:
    already_canonical = [row for row in rows if (row.entity_type, row.normalized_value) == key]
    pool = already_canonical or rows
    return max(pool, key=lambda row: (links.get(row.id, 0), row.created_at or 0, row.id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the merge instead of reporting it")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        entities = list(session.scalars(select(Entity)))
        links: dict[str, int] = defaultdict(int)
        for entity_id in session.scalars(select(EventEntity.entity_id)):
            links[entity_id] += 1
        if EntityRelation is not None:
            for column in (EntityRelation.subject_entity_id, EntityRelation.object_entity_id):
                for entity_id in session.scalars(select(column)):
                    links[entity_id] += 1
        if EntityOccurrence is not None:
            for entity_id in session.scalars(select(EntityOccurrence.entity_id)):
                links[entity_id] += 1

        groups: dict[tuple[str, tuple[str, str]], list[Entity]] = defaultdict(list)
        for entity in entities:
            groups[(entity.case_id, _resolved_key(entity))].append(entity)

        merged = relabelled = 0
        for (case_id, key), rows in sorted(groups.items()):
            keeper = _survivor(rows, key, links)
            losers = [row for row in rows if row.id is not keeper.id and row.id != keeper.id]

            if (keeper.entity_type, keeper.normalized_value) != key:
                print(f"  relabel {keeper.id[:8]} {keeper.entity_type}/{keeper.normalized_value!r} -> {key[0]}/{key[1]!r}")
                relabelled += 1
                if args.apply:
                    keeper.entity_type, keeper.normalized_value = key

            # Seeded once per group and carried across losers. The session does not autoflush, so
            # re-reading the survivor's links for each loser would not show the repoints already
            # made for the previous one, and three duplicates merging into one survivor would each
            # claim the same (event, relationship) slot.
            taken: set[tuple[str, str]] = set()
            held: set[tuple[str, str]] = set()
            if args.apply and losers:
                taken = {tuple(row) for row in session.execute(select(EventEntity.event_id, EventEntity.relationship_type).where(EventEntity.entity_id == keeper.id))}
                if EntityOccurrence is not None:
                    held = {tuple(row) for row in session.execute(select(EntityOccurrence.evidence_id, EntityOccurrence.field_name).where(EntityOccurrence.entity_id == keeper.id))}

            for loser in losers:
                print(
                    f"  merge   {loser.id[:8]} ({loser.extraction_method}, {links.get(loser.id, 0)} links)"
                    f" -> {keeper.id[:8]} ({keeper.extraction_method}) in case {case_id[:8]} as {key[0]}/{key[1]!r}"
                )
                merged += 1
                if not args.apply:
                    continue

                # Repoint only what would not collide with a link the survivor already holds.
                for link in session.scalars(select(EventEntity).where(EventEntity.entity_id == loser.id)):
                    if (link.event_id, link.relationship_type) in taken:
                        session.delete(link)
                    else:
                        link.entity_id = keeper.id
                        taken.add((link.event_id, link.relationship_type))

                if EntityOccurrence is not None:
                    for occurrence in session.scalars(select(EntityOccurrence).where(EntityOccurrence.entity_id == loser.id)):
                        if (occurrence.evidence_id, occurrence.field_name) in held:
                            session.delete(occurrence)
                        else:
                            occurrence.entity_id = keeper.id
                            held.add((occurrence.evidence_id, occurrence.field_name))

                if EntityRelation is not None:
                    for column in (EntityRelation.subject_entity_id, EntityRelation.object_entity_id):
                        session.execute(update(EntityRelation).where(column == loser.id).values(**{column.key: keeper.id}))
                    # A relation between the two halves of one node is a relation to itself.
                    session.execute(delete(EntityRelation).where(EntityRelation.subject_entity_id == EntityRelation.object_entity_id))

                session.flush()
                session.delete(loser)

        if args.apply:
            session.commit()
            print(f"\napplied: {merged} node(s) merged, {relabelled} relabelled")
        else:
            print(f"\ndry run: {merged} node(s) would merge, {relabelled} would be relabelled (pass --apply to write)")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
