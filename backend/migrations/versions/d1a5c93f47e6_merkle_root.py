"""Fix which evidence files a report covered, in one value.

The report already prints every evidence hash, which lets a reader check any file they hold. It
does not fix the set: a file quietly dropped from a later report leaves the remaining hashes all
still correct. A root over the whole set changes if anything is added, removed or reordered, and
supports an inclusion proof that one file was in the case without revealing the others.

Revision ID: d1a5c93f47e6
Revises: c9e7a1b53d80
"""

from alembic import op
import sqlalchemy as sa

revision = "d1a5c93f47e6"
down_revision = "c9e7a1b53d80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trustify_receipts", sa.Column("merkle_root", sa.String(64), nullable=True))
    op.add_column("trustify_receipts", sa.Column("merkle_leaves", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trustify_receipts", "merkle_leaves")
    op.drop_column("trustify_receipts", "merkle_root")
