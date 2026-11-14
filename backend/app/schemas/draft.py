"""先匹配后发布 DTO（草稿 / 预览 / 发布）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DraftCreatedOut(BaseModel):
    draft_id: str
    status: str
    preview_batch_id: str | None = None
    expires_at: datetime
    created_at: datetime
    idempotent_replay: bool = False


class DraftImageOut(BaseModel):
    object_key: str
    url: str
    mime_type: str
    size_bytes: int


class DraftCandidateOut(BaseModel):
    candidate_public_id: str
    item_type: str = "found"
    category: str
    color: str | None = None
    brand: str | None = None
    area_name: str
    occurred_on: str | None = None
    title_excerpt: str
    description_excerpt: str
    thumb_url: str | None = None
    score: float
    score_breakdown: dict[str, Any]
    differences: list[Any] = Field(default_factory=list)
    requires_offline_verification: bool = False
    explanation_status: str = "ready"
    reasons: list[str] = Field(default_factory=list)
    low_similar: bool = False
    threshold: float = 0.0
    threshold_source: str = ""


class DraftPreviewOut(BaseModel):
    draft_id: str
    batch_id: str | None = None
    status: str
    candidate_count: int
    degraded: bool = False
    degraded_reason: str | None = None
    threshold: float
    threshold_source: str
    sort_note: str = "按相似度降序展示"
    disclaimer: str = "匹配分数由后端算法计算，仅用于推荐候选，不代表物品归属或找回概率"
    candidates: list[DraftCandidateOut] = Field(default_factory=list)
    expires_at: datetime | None = None


class DraftDetailOut(BaseModel):
    draft_id: str
    title: str
    description: str
    category: str
    color: str | None = None
    brand: str | None = None
    location_code: str | None = None
    location_text: str
    occurred_at: datetime | None = None
    status: str
    expires_at: datetime
    created_at: datetime
    preview_batch_id: str | None = None
    candidate_count: int = 0
    can_publish: bool = False
    images: list[DraftImageOut] = Field(default_factory=list)


class DraftListItem(BaseModel):
    draft_id: str
    title: str
    status: str
    created_at: datetime
    expires_at: datetime
    remaining_seconds: int
    candidate_count: int
    can_publish: bool


class DraftListOut(BaseModel):
    items: list[DraftListItem]
    total: int


class PublishOut(BaseModel):
    item_id: int
    item_type: str
    status: str
    review_ticket_no: str | None = None
    data_version: int = 1
    batch_id: str | None = None
    preview_reused: bool = False
    publish_flow: str


class AbandonOut(BaseModel):
    draft_id: str
    status: str


class PublishModeOut(BaseModel):
    publish_mode: str