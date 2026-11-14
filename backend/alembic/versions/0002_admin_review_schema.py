"""V2 审核结构承接

Revision ID: 0002_admin_review_schema
Revises: 0001_initial
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_admin_review_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_ITEM_TABLES = ("lost_items", "found_items")


def upgrade() -> None:
    for table in _ITEM_TABLES:
        op.add_column(table, sa.Column("review_round", sa.Integer(), nullable=False, server_default="1"))
        op.add_column(table, sa.Column("latest_ticket_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("delist_reason", sa.String(length=500), nullable=True))
        op.add_column(table, sa.Column("delisted_at", sa.DateTime(), nullable=True))

    op.add_column(
        "users",
        sa.Column("migration_notice_seen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "review_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticket_no", sa.String(length=40), nullable=False),
        sa.Column("review_type", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="owner_request"),
        sa.Column("item_type", sa.String(length=8), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("applicant_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("opinion", sa.String(length=500), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ticket_no", name="uq_review_ticket_no"),
    )
    op.create_index("ix_review_queue", "review_tickets", ["review_type", "status", "created_at"])
    op.create_index("ix_review_tickets_status", "review_tickets", ["status"])
    op.create_index("ix_review_tickets_item", "review_tickets", ["item_type", "item_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("ref_type", sa.String(length=40), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivery_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_notification_user", "notifications", ["user_id", "is_read", "created_at"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),
    )

    op.add_column("audit_logs", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("actor_role", sa.String(length=16), nullable=True))
    op.add_column("audit_logs", sa.Column("before_status", sa.String(length=24), nullable=True))
    op.add_column("audit_logs", sa.Column("after_status", sa.String(length=24), nullable=True))
    op.add_column("audit_logs", sa.Column("reason", sa.String(length=500), nullable=True))
    op.add_column("audit_logs", sa.Column("batch_id", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("candidate_id", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("disclosure_level", sa.String(length=16), nullable=True))
    op.create_index("ix_audit_batch", "audit_logs", ["batch_id"])
    op.create_index("ix_audit_request", "audit_logs", ["request_id"])

    with op.batch_alter_table("claim_requests") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("target_item_type", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("target_item_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("active_lock_key", sa.String(length=128), nullable=True))
        batch.alter_column("reviewer_id", new_column_name="confirmer_id")
        batch.create_unique_constraint("uq_claim_active_lock", ["active_lock_key"])


def downgrade() -> None:
    with op.batch_alter_table("claim_requests") as batch:
        batch.drop_constraint("uq_claim_active_lock", type_="unique")
        batch.alter_column("confirmer_id", new_column_name="reviewer_id")
        batch.drop_column("active_lock_key")
        batch.drop_column("target_item_id")
        batch.drop_column("target_item_type")
        batch.drop_column("owner_id")

    op.drop_index("ix_audit_request", table_name="audit_logs")
    op.drop_index("ix_audit_batch", table_name="audit_logs")
    for column in (
        "disclosure_level",
        "candidate_id",
        "batch_id",
        "reason",
        "after_status",
        "before_status",
        "actor_role",
        "request_id",
    ):
        op.drop_column("audit_logs", column)

    op.drop_table("idempotency_keys")
    op.drop_index("ix_notification_user", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_review_tickets_item", table_name="review_tickets")
    op.drop_index("ix_review_tickets_status", table_name="review_tickets")
    op.drop_index("ix_review_queue", table_name="review_tickets")
    op.drop_table("review_tickets")

    op.drop_column("users", "migration_notice_seen")
    for table in _ITEM_TABLES:
        op.drop_column(table, "delisted_at")
        op.drop_column(table, "delist_reason")
        op.drop_column(table, "latest_ticket_id")
        op.drop_column(table, "review_round")