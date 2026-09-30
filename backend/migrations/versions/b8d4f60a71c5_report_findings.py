"""Keep the findings a report printed, alongside the report.

A report is a snapshot. Its findings are numbered F-01 upwards in the order the case rested on them
at the moment it was generated, and an FIR or a chargesheet can cite those numbers. Recomputing the
list later would renumber it: a relationship added or reviewed since would shift every finding after
it, and "DRISHYAM finding F-07" would quietly come to mean a different statement than the one the
printed document carries.

So the list is stored with the report it belongs to, each entry keeping the evidence file and the
exact place inside it, which is what lets a number in the document open the row it was read from.

Revision ID: b8d4f60a71c5
Revises: a7c3e5f81b02
"""

from alembic import op
import sqlalchemy as sa

revision = "b8d4f60a71c5"
down_revision = "a7c3e5f81b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("findings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "findings")
