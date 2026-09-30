"""Keep the role a source states, not only the name it states.

The person extractor already matched "Complainant:", "Accused:", "Driver:" and the rest — the
pattern names those roles explicitly — and then returned the name alone. The first question any
investigator asks about a name on a page was the one piece of information extraction threw away.

Two columns, because a role belongs to a reading rather than to a person. `normalized_records`
carries what a record stated, and `entity_occurrences` carries what one source said about one
identity in one place. The same individual can be a witness in one file and a suspect in another,
and writing the role onto the entity would force the system to pick one and call it the truth.

Existing rows have no role recorded. That is the honest value: those sources were read before this
existed, and nothing here infers a role that was never captured.

Revision ID: d4f1a92b7e60
Revises: c8e5b1067d34
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4f1a92b7e60"
down_revision = "c8e5b1067d34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "normalized_records",
        sa.Column("person_roles", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("entity_occurrences", sa.Column("stated_role", sa.String(length=48), nullable=True))


def downgrade() -> None:
    op.drop_column("entity_occurrences", "stated_role")
    op.drop_column("normalized_records", "person_roles")
