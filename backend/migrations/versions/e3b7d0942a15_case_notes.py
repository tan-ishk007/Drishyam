"""What an investigator knows, kept beside what the system read.

An investigator holds things no evidence file states: what a witness said on the doorstep, which of
two spellings is the same person, why a lead was dropped. Today that goes in a notebook and leaves
with them.

A note is stored apart from extracted facts and always will be. It carries an author and a time,
and everywhere it is shown it is marked as commentary rather than evidence -- a note that could be
mistaken for something a source stated would undo the distinction the whole extraction layer is
built around.

Revision ID: e3b7d0942a15
Revises: d1a5c93f47e6
"""

from alembic import op
import sqlalchemy as sa

revision = "e3b7d0942a15"
down_revision = "d1a5c93f47e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_case_notes_case_id", "case_notes", ["case_id"])
    op.create_index("ix_case_notes_subject", "case_notes", ["case_id", "subject_type", "subject_id"])


def downgrade() -> None:
    op.drop_index("ix_case_notes_subject", table_name="case_notes")
    op.drop_index("ix_case_notes_case_id", table_name="case_notes")
    op.drop_table("case_notes")
