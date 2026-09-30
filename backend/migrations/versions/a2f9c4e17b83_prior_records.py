"""The national record of registered cases, as this deployment holds it.

A different source from the shared ledger and a different question. The ledger says another force
is working a live case that touches an identity, and holds nothing else on purpose. This says a
case was registered before and comes from a store entitled to hold the details.

Disposal is not nullable for a reason: a record that showed convictions and omitted acquittals
would be a lie told by arithmetic.

Revision ID: a2f9c4e17b83
Revises: f4c81e50b6d3
"""

from alembic import op
import sqlalchemy as sa

revision = "a2f9c4e17b83"
down_revision = "f4c81e50b6d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prior_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identifier_type", sa.String(32), nullable=False),
        sa.Column("identifier_value", sa.String(512), nullable=False),
        sa.Column("subject_name", sa.String(160)),
        sa.Column("record_reference", sa.String(96), nullable=False),
        sa.Column("police_station", sa.String(160), nullable=False),
        sa.Column("district", sa.String(160)),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("registered_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disposal", sa.String(32), nullable=False),
        sa.Column("disposal_on", sa.DateTime(timezone=True)),
        sa.Column("contact_officer", sa.String(320)),
        sa.Column("source", sa.String(96), nullable=False, server_default="synthetic-national-dataset"),
        sa.UniqueConstraint("record_reference", "identifier_type", "identifier_value", name="uq_prior_record_identity"),
    )
    op.create_index("ix_prior_records_identifier_value", "prior_records", ["identifier_value"])
    op.create_index("ix_prior_records_identifier", "prior_records", ["identifier_type", "identifier_value"])


def downgrade() -> None:
    op.drop_index("ix_prior_records_identifier", table_name="prior_records")
    op.drop_index("ix_prior_records_identifier_value", table_name="prior_records")
    op.drop_table("prior_records")
