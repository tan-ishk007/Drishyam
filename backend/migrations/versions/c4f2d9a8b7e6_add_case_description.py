"""Add exact investigator-entered case description storage.

Revision ID: c4f2d9a8b7e6
Revises: f2a819c4d05e
"""

from alembic import op
import sqlalchemy as sa


revision = "c4f2d9a8b7e6"
down_revision = "f2a819c4d05e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "description")