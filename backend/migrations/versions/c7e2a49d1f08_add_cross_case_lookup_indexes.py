"""add cross-case lookup indexes

Revision ID: c7e2a49d1f08
Revises: b8f31a6d92e4
"""

from alembic import op


revision = "c7e2a49d1f08"
down_revision = "b8f31a6d92e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_entities_type_normalized_case", "entities", ["entity_type", "normalized_value", "case_id"], unique=False)
    op.create_index("ix_evidence_sha256_case", "evidence_files", ["sha256", "case_id"], unique=False)
    op.create_index("ix_transactions_reference_case", "transactions", ["reference_id", "case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_transactions_reference_case", table_name="transactions")
    op.drop_index("ix_evidence_sha256_case", table_name="evidence_files")
    op.drop_index("ix_entities_type_normalized_case", table_name="entities")
