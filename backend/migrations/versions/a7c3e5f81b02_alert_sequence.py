"""Record the sourced sequence behind an alert.

An alert has always carried one paragraph of explanation. A paragraph cannot be opened: a reader
who wants to know what actually happened has to go and find the records themselves, which is the
work the alert was supposed to save them.

The sequence is stored rather than recomputed at read time. It is what the sources recorded when
the rule fired; recomputing it later would let a reviewed alert quietly change its story as records
around it are corrected. Nullable, because alerts raised before this column existed genuinely have
no sequence and must say so rather than being given an empty one that reads as "nothing happened".

Revision ID: a7c3e5f81b02
Revises: d4f1a92b7e60
"""

from alembic import op
import sqlalchemy as sa

revision = "a7c3e5f81b02"
down_revision = "d4f1a92b7e60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("sequence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "sequence")
