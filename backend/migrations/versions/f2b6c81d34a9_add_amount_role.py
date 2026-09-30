"""Record what a monetary figure is, not only how much it is.

Every amount was projected into the transaction trail, so a balance quoted in an email — "your
investment balance of INR 29,500" — appeared alongside real payments and was added into the case
total. The figure is real; calling it a transaction is a claim the evidence never made. This column
carries the classification so the projection can tell them apart.

Revision ID: f2b6c81d34a9
Revises: e5a3b71c2d64
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b6c81d34a9"
down_revision = "e5a3b71c2d64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "normalized_records",
        sa.Column("amount_role", sa.String(length=16), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("normalized_records", "amount_role")
