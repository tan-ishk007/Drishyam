"""add identity provider fields and OTP purpose

Revision ID: e9d91a7c4b2e
Revises: c7e2a49d1f08
"""

import sqlalchemy as sa
from alembic import op


revision = "e9d91a7c4b2e"
down_revision = "c7e2a49d1f08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="password"))
    op.add_column("users", sa.Column("google_subject", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_google_subject", "users", ["google_subject"], unique=True)
    op.add_column("verification_codes", sa.Column("purpose", sa.String(length=40), nullable=False, server_default="signup_verification"))


def downgrade() -> None:
    op.drop_column("verification_codes", "purpose")
    op.drop_index("ix_users_google_subject", table_name="users")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "google_subject")
    op.drop_column("users", "auth_provider")
