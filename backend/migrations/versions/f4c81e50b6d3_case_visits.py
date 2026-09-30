"""When each user last opened each case.

Coming back to a case after a week means reading everything again to find the three things that
changed. Recording the visit is what lets the case answer "what is new" before it shows anything
else.

Per user, deliberately. What is new to one investigator is not new to the colleague who uploaded
it, and a shared "last opened" would be wrong for everybody but the last person through the door.

Revision ID: f4c81e50b6d3
Revises: e3b7d0942a15
"""

from alembic import op
import sqlalchemy as sa

revision = "f4c81e50b6d3"
down_revision = "e3b7d0942a15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_visits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "user_id", name="uq_case_visit"),
    )


def downgrade() -> None:
    op.drop_table("case_visits")
