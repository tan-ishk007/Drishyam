"""Add source-grounded evidence intelligence tables and stage vocabulary.

Purely additive. No existing table, column, index or row is altered, so historic cases, evidence,
reports, receipts and audit entries stay readable exactly as they are.

Revision ID: d1c8f4e7a930
Revises: c4f2d9a8b7e6
"""

from alembic import op
import sqlalchemy as sa


revision = "d1c8f4e7a930"
down_revision = "c4f2d9a8b7e6"
branch_labels = None
depends_on = None


# SQLAlchemy's Enum type persists the member NAME, not its value — the existing members are stored
# as 'UPLOADED', 'QUEUED' and so on. The new members must follow that same convention, otherwise
# assigning one in Python would write a label the database type does not contain.
NEW_EVIDENCE_STATUSES = (
    "RECEIVED",
    "TYPE_DETECTED",
    "OCR_COMPLETED",
    "LOCAL_MODEL_COMPLETED",
    "GROQ_ESCALATED",
    "VALIDATED",
    "REVIEW_REQUIRED",
    "READY",
    "PARTIALLY_PROCESSED",
)


def upgrade() -> None:
    op.create_table(
        "raw_extraction_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_version", sa.String(length=64), nullable=False),
        sa.Column("layer", sa.String(length=48), nullable=False),
        sa.Column("extractor_name", sa.String(length=96), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", "artifact_version", "layer", name="uq_raw_artifact_version_layer"),
    )
    op.create_index("ix_raw_extraction_artifacts_evidence_id", "raw_extraction_artifacts", ["evidence_id"])
    op.create_index("ix_raw_extraction_artifacts_case_id", "raw_extraction_artifacts", ["case_id"])
    op.create_index("ix_raw_artifacts_case_evidence", "raw_extraction_artifacts", ["case_id", "evidence_id"])

    op.create_table(
        "model_inference_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_key", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("parsed_payload", sa.JSON(), nullable=True),
        sa.Column("grounding_report", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", "record_key", "cache_key", name="uq_inference_run_cache"),
    )
    op.create_index("ix_model_inference_runs_evidence_id", "model_inference_runs", ["evidence_id"])
    op.create_index("ix_model_inference_runs_case_id", "model_inference_runs", ["case_id"])
    op.create_index("ix_model_inference_runs_cache_key", "model_inference_runs", ["cache_key"])
    op.create_index("ix_inference_case_evidence", "model_inference_runs", ["case_id", "evidence_id"])

    op.create_table(
        "normalized_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("record_key", sa.String(length=255), nullable=False),
        sa.Column("source_file_name", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("observed_text", sa.Text(), nullable=True),
        sa.Column("normalized_summary", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_time_raw", sa.String(length=160), nullable=True),
        sa.Column("event_time_precision", sa.String(length=24), nullable=False),
        sa.Column("participant_a", sa.String(length=255), nullable=True),
        sa.Column("participant_b", sa.String(length=255), nullable=True),
        sa.Column("sender", sa.String(length=255), nullable=True),
        sa.Column("receiver", sa.String(length=255), nullable=True),
        sa.Column("message_direction", sa.String(length=16), nullable=True),
        sa.Column("chat_participant_identifier", sa.String(length=255), nullable=True),
        sa.Column("phone_numbers", sa.JSON(), nullable=False),
        sa.Column("email_addresses", sa.JSON(), nullable=False),
        sa.Column("account_identifiers", sa.JSON(), nullable=False),
        sa.Column("transaction_reference", sa.String(length=160), nullable=True),
        sa.Column("amount_value", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("amount_currency", sa.String(length=8), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("device_identifier", sa.String(length=160), nullable=True),
        sa.Column("event_attributes", sa.JSON(), nullable=False),
        sa.Column("observation_basis", sa.String(length=24), nullable=False),
        sa.Column("field_provenance", sa.JSON(), nullable=False),
        sa.Column("model_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("validation_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("final_confidence_band", sa.String(length=16), nullable=False),
        sa.Column("validation_status", sa.String(length=24), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("review_state", sa.String(length=24), nullable=False),
        sa.Column("conflict_fields", sa.JSON(), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("raw_extraction_version", sa.String(length=64), nullable=False),
        sa.Column("raw_model_output_version", sa.String(length=64), nullable=True),
        sa.Column("extraction_model_name", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", "record_key", "raw_extraction_version", name="uq_normalized_record_version"),
    )
    op.create_index("ix_normalized_records_evidence_id", "normalized_records", ["evidence_id"])
    op.create_index("ix_normalized_records_case_id", "normalized_records", ["case_id"])
    op.create_index("ix_normalized_records_event_time", "normalized_records", ["event_time"])
    op.create_index("ix_normalized_records_transaction_reference", "normalized_records", ["transaction_reference"])
    op.create_index("ix_normalized_case_review", "normalized_records", ["case_id", "requires_human_review", "final_confidence_band"])
    op.create_index("ix_normalized_case_created", "normalized_records", ["case_id", "created_at"])

    op.create_table(
        "record_relations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("detection_method", sa.String(length=32), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("record_ids", sa.JSON(), nullable=False),
        sa.Column("matching_or_conflicting_fields", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("review_decision", sa.String(length=32), nullable=True),
        sa.Column("reviewed_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_record_relation_idempotency"),
    )
    op.create_index("ix_record_relations_case_id", "record_relations", ["case_id"])
    op.create_index("ix_record_relations_case_type_status", "record_relations", ["case_id", "relation_type", "status"])

    op.create_table(
        "record_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_id", sa.String(length=36), sa.ForeignKey("normalized_records.id", ondelete="CASCADE"), nullable=True),
        sa.Column("relation_id", sa.String(length=36), sa.ForeignKey("record_relations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("field_name", sa.String(length=96), nullable=True),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("audit_log_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_record_reviews_case_id", "record_reviews", ["case_id"])
    op.create_index("ix_record_reviews_record_id", "record_reviews", ["record_id"])
    op.create_index("ix_record_reviews_relation_id", "record_reviews", ["relation_id"])
    op.create_index("ix_record_reviews_case_created", "record_reviews", ["case_id", "created_at"])

    # Enum members are added last so a failure above leaves the type untouched. On PostgreSQL these
    # cannot be removed again, which is why the downgrade deliberately leaves them in place.
    if op.get_bind().dialect.name == "postgresql":
        for value in NEW_EVIDENCE_STATUSES:
            op.execute(f"ALTER TYPE evidence_status ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_table("record_reviews")
    op.drop_table("record_relations")
    op.drop_table("normalized_records")
    op.drop_table("model_inference_runs")
    op.drop_table("raw_extraction_artifacts")
    # The evidence_status members added above are intentionally retained: PostgreSQL cannot drop an
    # enum value, and recreating the type would require rewriting the existing evidence_files rows.
    # Leaving unused members in place is harmless and keeps the downgrade non-destructive.
