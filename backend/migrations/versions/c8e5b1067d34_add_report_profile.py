"""Give a report an audience.

One document was being asked to serve four readers at once: a station officer who needs the shape
of the network in two minutes, an investigator working the case, a court that must be given the
evidence register and the integrity record with no interpretation attached, and the next officer
picking the case up. Serving all four produced a report that served none of them well -- the
briefing was buried on page nine and the court annexure was mixed in with rankings a court has no
business being handed as fact.

`profile` is deliberately separate from `redaction_profile`. Redaction decides what must be hidden
from a reader; the profile decides what that reader is being given. A court annexure with nothing
redacted and a briefing with a victim's name removed are both ordinary combinations, and folding
the two axes into one column would have made them inexpressible.

Existing reports were full case files, so that is what they become.

Revision ID: c8e5b1067d34
Revises: b7c4f0a29d31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8e5b1067d34"
down_revision = "b7c4f0a29d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("profile", sa.String(length=32), nullable=False, server_default="case_file"),
    )


def downgrade() -> None:
    op.drop_column("reports", "profile")
