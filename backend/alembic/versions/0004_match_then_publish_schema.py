"""先匹配后发布增量结构（草稿 / 预览批次 / 预览候选）

Revision ID: 0004_match_then_publish_schema
Revises: 0003_bidirectional_match_schema
Create Date: 2026-11-07

纯增量：不改记录表、不改八态枚举、不改 match_records 既有结构。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_match_then_publish_schema"
down_revision = "0003_bidirectional_match_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("match_batches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "batch_kind",
                sa.String(length=16),
                nullable=False,
                server_default="formal",
            )
        )
        batch_op.add_column(
            sa.Column(
                "threshold_source",
                sa.String(length=16),
                nullable=False,
                server_default="formal",
            )
        )
        batch_op.add_column(sa.Column("draft_id", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_match_batches_draft_id", ["draft_id"])

    op.create_table(
        "match_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column(
            "owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("item_type", sa.String(length=8), nullable=False, server_default="lost"),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="matching"
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=40), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("location_code", sa.String(length=100), nullable=True),
        sa.Column("location_text", sa.String(length=200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column(
            "info_sufficient", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("data_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preview_batch_id", sa.String(length=64), nullable=True),
        sa.Column("published_item_type", sa.String(length=8), nullable=True),
        sa.Column("published_item_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "matching_notice_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_match_drafts_idempotency"),
    )
    op.create_index(
        "ix_match_drafts_draft_id", "match_drafts", ["draft_id"], unique=True
    )
    op.create_index("ix_match_drafts_owner_id", "match_drafts", ["owner_id"])
    op.create_index("ix_match_drafts_status", "match_drafts", ["status"])
    op.create_index(
        "ix_match_drafts_preview_batch_id", "match_drafts", ["preview_batch_id"]
    )
    op.create_index("ix_match_drafts_expires_at", "match_drafts", ["expires_at"])

    op.create_table(
        "match_draft_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("thumb_key", sa.String(length=500), nullable=True),
        sa.Column("watermark_key", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("draft_id", "object_key", name="uq_draft_image"),
    )
    op.create_index(
        "ix_match_draft_images_draft_id", "match_draft_images", ["draft_id"]
    )

    op.create_table(
        "match_preview_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column(
            "batch_fk",
            sa.Integer(),
            sa.ForeignKey("match_batches.id"),
            nullable=True,
        ),
        sa.Column("candidate_public_id", sa.String(length=64), nullable=False),
        sa.Column(
            "candidate_item_type",
            sa.String(length=8),
            nullable=False,
            server_default="found",
        ),
        sa.Column("candidate_item_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=False),
        sa.Column("differences_json", sa.JSON(), nullable=True),
        sa.Column(
            "explanation_status",
            sa.String(length=16),
            nullable=False,
            server_default="ready",
        ),
        sa.Column(
            "requires_offline_verification",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "low_similar", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "disclosure_level",
            sa.String(length=16),
            nullable=False,
            server_default="summary",
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="valid"
        ),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "candidate_public_id", name="uq_preview_candidate_public_id"
        ),
    )
    op.create_index(
        "ix_match_preview_candidates_batch_id",
        "match_preview_candidates",
        ["batch_id"],
    )
    op.create_index(
        "ix_match_preview_candidates_batch_fk",
        "match_preview_candidates",
        ["batch_fk"],
    )
    op.create_index(
        "ix_match_preview_candidates_draft_id",
        "match_preview_candidates",
        ["draft_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_match_preview_candidates_draft_id",
        table_name="match_preview_candidates",
    )
    op.drop_index(
        "ix_match_preview_candidates_batch_fk",
        table_name="match_preview_candidates",
    )
    op.drop_index(
        "ix_match_preview_candidates_batch_id",
        table_name="match_preview_candidates",
    )
    op.drop_table("match_preview_candidates")

    op.drop_index("ix_match_draft_images_draft_id", table_name="match_draft_images")
    op.drop_table("match_draft_images")

    op.drop_index("ix_match_drafts_expires_at", table_name="match_drafts")
    op.drop_index("ix_match_drafts_preview_batch_id", table_name="match_drafts")
    op.drop_index("ix_match_drafts_status", table_name="match_drafts")
    op.drop_index("ix_match_drafts_owner_id", table_name="match_drafts")
    op.drop_index("ix_match_drafts_draft_id", table_name="match_drafts")
    op.drop_table("match_drafts")

    with op.batch_alter_table("match_batches") as batch_op:
        batch_op.drop_index("ix_match_batches_draft_id")
        batch_op.drop_column("draft_id")
        batch_op.drop_column("threshold_source")
        batch_op.drop_column("batch_kind")