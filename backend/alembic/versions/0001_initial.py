"""初始表结构

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-27

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nickname", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "lost_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=40), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("location_code", sa.String(length=100), nullable=False),
        sa.Column("location_text", sa.String(length=200), nullable=False),
        sa.Column("lost_at", sa.DateTime(), nullable=True),
        sa.Column("features", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_lost_items_user_id", "lost_items", ["user_id"])
    op.create_index("ix_lost_items_status", "lost_items", ["status"])

    op.create_table(
        "found_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=40), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("location_code", sa.String(length=100), nullable=False),
        sa.Column("location_text", sa.String(length=200), nullable=False),
        sa.Column("found_at", sa.DateTime(), nullable=True),
        sa.Column("features", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_found_items_user_id", "found_items", ["user_id"])
    op.create_index("ix_found_items_status", "found_items", ["status"])

    op.create_table(
        "item_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("item_type", sa.String(length=8), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("object_key", name="uq_item_images_object_key"),
    )
    op.create_index("ix_item_images_type_id", "item_images", ["item_type", "item_id"])

    op.create_table(
        "match_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("initiated_item_type", sa.String(length=8), nullable=False),
        sa.Column("lost_item_id", sa.Integer(), sa.ForeignKey("lost_items.id"), nullable=False),
        sa.Column("found_item_id", sa.Integer(), sa.ForeignKey("found_items.id"), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("initiated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "batch_id", "lost_item_id", "found_item_id", name="uq_match_batch_pair"
        ),
    )
    op.create_index("ix_match_records_batch_id", "match_records", ["batch_id"])
    op.create_index("ix_match_records_lost_item_id", "match_records", ["lost_item_id"])
    op.create_index("ix_match_records_found_item_id", "match_records", ["found_item_id"])
    op.create_index("ix_match_lost_found", "match_records", ["lost_item_id", "found_item_id", "score"])

    op.create_table(
        "claim_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("match_records.id"), nullable=True),
        sa.Column("lost_item_id", sa.Integer(), sa.ForeignKey("lost_items.id"), nullable=True),
        sa.Column("found_item_id", sa.Integer(), sa.ForeignKey("found_items.id"), nullable=True),
        sa.Column("claimant_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("private_evidence", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_claim_requests_review_status", "claim_requests", ["review_status"])
    op.create_index(
        "ix_claim_claimant_target",
        "claim_requests",
        ["claimant_id", "lost_item_id", "found_item_id"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("claim_requests")
    op.drop_table("match_records")
    op.drop_table("item_images")
    op.drop_table("found_items")
    op.drop_table("lost_items")
    op.drop_table("users")