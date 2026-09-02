"""add account settings and server sessions

Revision ID: f2a819c4d05e
Revises: e9d91a7c4b2e
Create Date: 2026-08-25 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a819c4d05e"
down_revision = "e9d91a7c4b2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("language", sa.String(length=80), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=True),
        sa.Column("date_format", sa.String(length=40), nullable=True),
        sa.Column("time_format", sa.String(length=40), nullable=True),
        sa.Column("items_per_page", sa.Integer(), nullable=True),
        sa.Column("theme", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_settings_user_id"), "account_settings", ["user_id"], unique=True)
    op.create_table(
        "account_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_id", sa.String(length=128), nullable=False),
        sa.Column("device_label", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id"),
    )
    op.create_index(op.f("ix_account_sessions_user_id"), "account_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_account_sessions_token_id"), "account_sessions", ["token_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_account_sessions_token_id"), table_name="account_sessions")
    op.drop_index(op.f("ix_account_sessions_user_id"), table_name="account_sessions")
    op.drop_table("account_sessions")
    op.drop_index(op.f("ix_account_settings_user_id"), table_name="account_settings")
    op.drop_table("account_settings")
