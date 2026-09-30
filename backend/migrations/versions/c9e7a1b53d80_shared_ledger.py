"""The shared identifier ledger.

The one store in this product that several forces read and write, which is the only situation where
a chained shared record earns its cost. It holds a keyed digest of an identifier, a case reference
and a contact -- never the identifier, never anything about what a case contains.

Chained, so whoever hosts it cannot quietly remove an entry, backdate one, or reorder them.

Revision ID: c9e7a1b53d80
Revises: b8d4f60a71c5
"""

from alembic import op
import sqlalchemy as sa

revision = "c9e7a1b53d80"
down_revision = "b8d4f60a71c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identifier_digest", sa.String(64), nullable=False),
        sa.Column("case_reference", sa.String(64), nullable=False),
        sa.Column("contact", sa.String(320), nullable=False),
        sa.Column("published_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("source_case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="SET NULL")),
        sa.Column("previous_hash", sa.String(64)),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("identifier_digest", "case_reference", name="uq_ledger_digest_case"),
    )
    op.create_index("ix_ledger_entries_identifier_digest", "ledger_entries", ["identifier_digest"])
    op.create_index("ix_ledger_entries_source_case_id", "ledger_entries", ["source_case_id"])
    op.create_index("ix_ledger_published_at", "ledger_entries", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_ledger_published_at", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_source_case_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_identifier_digest", table_name="ledger_entries")
    op.drop_table("ledger_entries")
