"""Record the entity classes SIH26189 asks for.

The extractor read identifiers -- phones, accounts, references -- because the earlier product was
aimed at payment fraud. SIH26189 asks for people, locations, vehicles, phone numbers and
organisations, and three of those five had nowhere to be stored.

These are JSON lists to match the identifier columns beside them, and they are server-defaulted to
an empty list so existing rows stay valid without a backfill. A row written before this revision
observed no vehicle; it did not observe an unknown one.

Revision ID: a3d7e21f9c58
Revises: f2b6c81d34a9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3d7e21f9c58"
down_revision = "f2b6c81d34a9"
branch_labels = None
depends_on = None

_COLUMNS = ("vehicle_identifiers", "organisation_names", "person_names", "location_names")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column(
            "normalized_records",
            sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("normalized_records", name)
