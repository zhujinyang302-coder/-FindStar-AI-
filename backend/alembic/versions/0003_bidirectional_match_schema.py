"""V3 双向匹配增量结构

Revision ID: 0003_bidirectional_match_schema
Revises: 0002_admin_review_schema
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_bidirectional_match_schema"
down_revision = "0002_admin_review_schema"
branch_labels = None
depends_on = None

_ITEM_TABLES = ("lost_items", "found_items")
_APPEND_ONLY = ("audit_logs", "disclosure_access_logs")


def upgrade() -> None:
    for table in _ITEM_TABLES:
        op.add_column(table, sa.Column("visibility_scope", sa.String(length=24), nullable=False, server_default="owner_only"))
        op.add_column(table, sa.Column("info_sufficient", sa.Boolean(), nullable=False, server_default=sa.true()))
        op.add_column(table, sa.Column("data_version", sa.Integer(), nullable=False, server_default="1"))
        op.add_column(table, sa.Column("claimed_at", sa.DateTime(), nullable=True))
        op.add_column(table, sa.Column("matched_at", sa.DateTime(), nullable=True))

    op.add_column("item_images", sa.Column("thumb_key", sa.String(length=500), nullable=True))
    op.add_column("item_images", sa.Column("watermark_key", sa.String(length=500), nullable=True))
    op.add_column(
        "item_images",
        sa.Column("sensitive_masked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "match_batches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("initiated_item_type", sa.String(length=8), nullable=False),
        sa.Column("initiated_item_id", sa.Integer(), nullable=False),
        sa.Column("initiator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("direction", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="processing"),
        sa.Column("algorithm_version", sa.String(length=40), nullable=False),
        sa.Column("config_version", sa.String(length=40), nullable=False),
        sa.Column("data_version", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("quota", sa.Integer(), nullable=False),
        sa.Column("weights_snapshot", sa.JSON(), nullable=True),
        sa.Column("recall_channel", sa.String(length=16), nullable=False, server_default="keyword"),
        sa.Column("recall_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("degraded_reason", sa.String(length=255), nullable=True),
        sa.Column("filter_stats", sa.JSON(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("batch_id", name="uq_match_batches_batch_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_match_batches_idempotency"),
    )
    op.create_index("ix_match_batches_status", "match_batches", ["status"])
    op.create_index("ix_match_batches_initiator", "match_batches", ["initiator_id"])
    op.create_index("ix_match_batches_item", "match_batches", ["initiated_item_type", "initiated_item_id"])

    with op.batch_alter_table("match_records") as batch:
        batch.add_column(sa.Column("batch_fk", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("candidate_public_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("candidate_item_type", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("candidate_item_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("disclosure_level", sa.String(length=16), nullable=False, server_default="summary"))
        batch.add_column(sa.Column("candidate_status", sa.String(length=24), nullable=False, server_default="valid"))
        batch.add_column(sa.Column("explanation_status", sa.String(length=16), nullable=False, server_default="ready"))
        batch.add_column(sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("differences_json", sa.JSON(), nullable=True))
        batch.create_unique_constraint("uq_match_candidate_public_id", ["candidate_public_id"])
    op.create_index("ix_match_records_batch_fk", "match_records", ["batch_fk"])
    op.create_index("ix_match_records_candidate", "match_records", ["candidate_public_id"])

    op.create_table(
        "contact_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_type", sa.String(length=24), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_public_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=True),
        sa.Column("applicant_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_item_type", sa.String(length=8), nullable=False),
        sa.Column("target_item_id", sa.Integer(), nullable=False),
        sa.Column("private_verification", sa.Text(), nullable=True),
        sa.Column("handover_location_code", sa.String(length=100), nullable=True),
        sa.Column("handover_window_start", sa.DateTime(), nullable=True),
        sa.Column("handover_window_end", sa.DateTime(), nullable=True),
        sa.Column("handover_note", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("decider_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_note", sa.String(length=200), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("active_lock_key", sa.String(length=128), nullable=True),
        sa.Column("sensitive_category", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("active_lock_key", name="uq_contact_active_lock"),
    )
    op.create_index("ix_contact_applicant", "contact_requests", ["applicant_id", "created_at"])
    op.create_index("ix_contact_target_owner", "contact_requests", ["target_owner_id", "status"])
    op.create_index("ix_contact_requests_batch", "contact_requests", ["batch_id"])
    op.create_index("ix_contact_requests_status", "contact_requests", ["status"])

    op.create_table(
        "disclosure_access_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_public_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("disclosure_level", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_disclosure_batch", "disclosure_access_logs", ["batch_id", "created_at"])

    op.create_table(
        "match_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_public_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=True),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("candidate_public_id", "reporter_id", name="uq_feedback_candidate_reporter"),
    )
    op.create_index("ix_match_feedback_candidate", "match_feedback", ["candidate_public_id"])

    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.String(length=10), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "subject_type", "subject_id", "action", "window_start",
            name="uq_rate_limit_subject_window",
        ),
    )

    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("handled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "item_semantic_index",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("item_type", sa.String(length=8), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("item_type", "item_id", "model_version", name="uq_semantic_item_model"),
    )

    op.create_table(
        "match_config_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("quota", sa.Integer(), nullable=False),
        sa.Column("time_window_days", sa.Integer(), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=True),
        sa.Column("recall_strategy", sa.String(length=40), nullable=False, server_default="vector_first"),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("version", name="uq_match_config_version"),
    )

    _create_append_only_triggers()


def _create_append_only_triggers() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    for table in _APPEND_ONLY:
        if dialect == "sqlite":
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_update "
                f"BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
            )
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_delete "
                f"BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
            )
        elif dialect in {"mysql", "mariadb"}:
            op.execute(
                f"CREATE TRIGGER trg_{table}_no_update BEFORE UPDATE ON {table} FOR EACH ROW "
                f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{table} is append-only'"
            )
            op.execute(
                f"CREATE TRIGGER trg_{table}_no_delete BEFORE DELETE ON {table} FOR EACH ROW "
                f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{table} is append-only'"
            )


def _drop_append_only_triggers() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    for table in _APPEND_ONLY:
        if dialect == "sqlite":
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_update")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_delete")
        elif dialect in {"mysql", "mariadb"}:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_update")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_delete")


def downgrade() -> None:
    _drop_append_only_triggers()
    op.drop_table("match_config_versions")
    op.drop_table("item_semantic_index")
    op.drop_table("security_events")
    op.drop_table("rate_limit_counters")
    op.drop_index("ix_match_feedback_candidate", table_name="match_feedback")
    op.drop_table("match_feedback")
    op.drop_index("ix_disclosure_batch", table_name="disclosure_access_logs")
    op.drop_table("disclosure_access_logs")
    op.drop_index("ix_contact_requests_status", table_name="contact_requests")
    op.drop_index("ix_contact_requests_batch", table_name="contact_requests")
    op.drop_index("ix_contact_target_owner", table_name="contact_requests")
    op.drop_index("ix_contact_applicant", table_name="contact_requests")
    op.drop_table("contact_requests")

    op.drop_index("ix_match_records_candidate", table_name="match_records")
    op.drop_index("ix_match_records_batch_fk", table_name="match_records")
    with op.batch_alter_table("match_records") as batch:
        batch.drop_constraint("uq_match_candidate_public_id", type_="unique")
        for column in (
            "differences_json",
            "expires_at",
            "view_count",
            "explanation_status",
            "candidate_status",
            "disclosure_level",
            "candidate_item_id",
            "candidate_item_type",
            "candidate_public_id",
            "batch_fk",
        ):
            batch.drop_column(column)

    op.drop_index("ix_match_batches_item", table_name="match_batches")
    op.drop_index("ix_match_batches_initiator", table_name="match_batches")
    op.drop_index("ix_match_batches_status", table_name="match_batches")
    op.drop_table("match_batches")

    for column in ("sensitive_masked", "watermark_key", "thumb_key"):
        op.drop_column("item_images", column)

    for table in _ITEM_TABLES:
        for column in ("matched_at", "claimed_at", "data_version", "info_sufficient", "visibility_scope"):
            op.drop_column(table, column)