"""add trustify receipts and tamper-evident audit chain

Revision ID: 4a7f6b93de21
Revises: 2b44d632b1b2
"""
from alembic import op
import sqlalchemy as sa

revision = "4a7f6b93de21"
down_revision = "2b44d632b1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"], unique=False)
    op.create_table(
        "trustify_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("verification_id", sa.String(length=96), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("audit_chain_hash", sa.String(length=64), nullable=True),
        sa.Column("review_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("generator_version", sa.String(length=64), nullable=False),
        sa.Column("manifest_storage_key", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id"),
        sa.UniqueConstraint("verification_id"),
    )
    op.create_index("ix_trustify_receipts_case_id", "trustify_receipts", ["case_id"], unique=False)
    op.create_index("ix_trustify_receipts_verification_id", "trustify_receipts", ["verification_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_trustify_receipts_verification_id", table_name="trustify_receipts")
    op.drop_index("ix_trustify_receipts_case_id", table_name="trustify_receipts")
    op.drop_table("trustify_receipts")
    op.drop_index("ix_audit_logs_event_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "event_hash")
    op.drop_column("audit_logs", "previous_hash")
