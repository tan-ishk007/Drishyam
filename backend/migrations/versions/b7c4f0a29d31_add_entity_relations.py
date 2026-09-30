"""Give the graph typed edges between entities.

Until now the only link the system could draw was "this identifier appears in that file"
(entity_occurrences). That answers what two files have in common. SIH26189 asks for a relationship
map between people, phones, accounts, vehicles and organisations, which needs an edge whose two
ends are entities and whose type says what the source actually stated.

source_evidence_id and source_reference are NOT NULL on purpose. A relationship the reviewer cannot
open is not intelligence, and enforcing that at the column level keeps traceability coverage at
100% by construction.

Revision ID: b7c4f0a29d31
Revises: a3d7e21f9c58
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7c4f0a29d31"
down_revision = "a3d7e21f9c58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_relations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_entity_id", sa.String(length=36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_entity_id", sa.String(length=36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("directed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_evidence_id", sa.String(length=36), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), sa.ForeignKey("normalized_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_reference", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("basis", sa.String(length=32), nullable=False, server_default="co_occurrence"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_precision", sa.String(length=24), nullable=False, server_default="unknown"),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="machine_extracted"),
        sa.Column("reviewed_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entity_relations_case_id", "entity_relations", ["case_id"])
    op.create_index("ix_entity_relations_case_type", "entity_relations", ["case_id", "relation_type"])
    op.create_index("ix_entity_relations_subject", "entity_relations", ["case_id", "subject_entity_id"])
    op.create_index("ix_entity_relations_object", "entity_relations", ["case_id", "object_entity_id"])
    op.create_index("ix_entity_relations_case_time", "entity_relations", ["case_id", "observed_at"])
    op.create_index("ix_entity_relations_review", "entity_relations", ["case_id", "verification_status"])
    op.create_index("ix_entity_relations_source_evidence", "entity_relations", ["source_evidence_id"])


def downgrade() -> None:
    op.drop_table("entity_relations")
