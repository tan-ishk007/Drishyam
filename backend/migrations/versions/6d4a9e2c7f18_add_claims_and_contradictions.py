"""add empty claims and contradictions schema

Revision ID: 6d4a9e2c7f18
Revises: 4a7f6b93de21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "6d4a9e2c7f18"
down_revision = "4a7f6b93de21"
branch_labels = None
depends_on = None


claim_status = postgresql.ENUM("DRAFT", "NEEDS_REVIEW", "CORROBORATED", "CHALLENGED", "ARCHIVED", name="claim_status", create_type=False)
source_relationship = postgresql.ENUM("SUPPORTS", "CHALLENGES", "CONTEXT", name="source_relationship", create_type=False)
contradiction_status = postgresql.ENUM("OPEN", "RESOLVED", "DISMISSED", name="contradiction_status", create_type=False)


def upgrade() -> None:
    claim_status.create(op.get_bind(), checkfirst=True)
    source_relationship.create(op.get_bind(), checkfirst=True)
    contradiction_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=80), nullable=False),
        sa.Column("scope_note", sa.Text(), nullable=True),
        sa.Column("status", claim_status, nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_case_id", "claims", ["case_id"], unique=False)
    op.create_index("ix_claims_case_status_created", "claims", ["case_id", "status", "created_at"], unique=False)
    op.create_table(
        "claim_source_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("relationship", source_relationship, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", "source_type", "source_id", "relationship", name="uq_claim_source_link"),
    )
    op.create_index("ix_claim_source_links_claim_id", "claim_source_links", ["claim_id"], unique=False)
    op.create_table(
        "contradictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", contradiction_status, nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contradictions_case_id", "contradictions", ["case_id"], unique=False)
    op.create_index("ix_contradictions_case_status_created", "contradictions", ["case_id", "status", "created_at"], unique=False)
    op.create_table(
        "contradiction_source_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contradiction_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("relationship", source_relationship, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contradiction_id"], ["contradictions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contradiction_id", "source_type", "source_id", "relationship", name="uq_contradiction_source_link"),
    )
    op.create_index("ix_contradiction_source_links_contradiction_id", "contradiction_source_links", ["contradiction_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_contradiction_source_links_contradiction_id", table_name="contradiction_source_links")
    op.drop_table("contradiction_source_links")
    op.drop_index("ix_contradictions_case_status_created", table_name="contradictions")
    op.drop_index("ix_contradictions_case_id", table_name="contradictions")
    op.drop_table("contradictions")
    op.drop_index("ix_claim_source_links_claim_id", table_name="claim_source_links")
    op.drop_table("claim_source_links")
    op.drop_index("ix_claims_case_status_created", table_name="claims")
    op.drop_index("ix_claims_case_id", table_name="claims")
    op.drop_table("claims")
    contradiction_status.drop(op.get_bind(), checkfirst=True)
    source_relationship.drop(op.get_bind(), checkfirst=True)
    claim_status.drop(op.get_bind(), checkfirst=True)
