"""Record every evidence item an identifier appears in.

Additive. `entities.source_evidence_id` is left in place and still populated; it simply stops being
the only answer to "where was this seen", which is what made cross-evidence links invisible.

Revision ID: e5a3b71c2d64
Revises: d1c8f4e7a930
"""

from alembic import op
import sqlalchemy as sa


revision = "e5a3b71c2d64"
down_revision = "d1c8f4e7a930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_occurrences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_id", sa.String(length=36), sa.ForeignKey("normalized_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("field_name", sa.String(length=64), nullable=True),
        sa.Column("observed_value", sa.String(length=512), nullable=False),
        sa.Column("source_reference", sa.JSON(), nullable=False),
        sa.Column("detection_method", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity_id", "evidence_id", "field_name", name="uq_entity_occurrence"),
    )
    op.create_index("ix_entity_occurrences_case_id", "entity_occurrences", ["case_id"])
    op.create_index("ix_entity_occurrences_entity_id", "entity_occurrences", ["entity_id"])
    op.create_index("ix_entity_occurrences_evidence_id", "entity_occurrences", ["evidence_id"])
    op.create_index("ix_entity_occurrence_case_entity", "entity_occurrences", ["case_id", "entity_id"])
    op.create_index("ix_entity_occurrence_case_evidence", "entity_occurrences", ["case_id", "evidence_id"])


def downgrade() -> None:
    op.drop_table("entity_occurrences")
