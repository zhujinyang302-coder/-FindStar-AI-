"""匹配与候选披露 Schema（V3）。

候选 DTO 结构上不存在身份、账号、联系方式、完整描述、原图字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ScorePart(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    available: bool = True
    note: str | None = None


class ScoreBreakdown(BaseModel):
    text: ScorePart
    image: ScorePart
    location: ScorePart
    time: ScorePart
    attribute: ScorePart


class DifferenceItem(BaseModel):
    field: str
    self_value: str | None = None
    candidate_value: str | None = None
    note: str


class MatchCreateRequest(BaseModel):
    lost_item_id: int | None = None
    found_item_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "MatchCreateRequest":
        provided = [x for x in (self.lost_item_id, self.found_item_id) if x is not None]
        if len(provided) != 1:
            raise ValueError("必须且只能提供一个 lost_item_id 或 found_item_id")
        return self


class MatchAcceptedOut(BaseModel):
    batch_id: str
    status: str
    reused: bool
    accepted_at: datetime


class MatchBatchOut(BaseModel):
    batch_id: str
    initiated_item_type: str
    initiated_item_id: int
    status: str
    candidate_count: int = 0
    degraded: bool = False
    degraded_reason: str | None = None
    recall_channel: str | None = None
    threshold: float | None = None
    quota: int | None = None
    algorithm_version: str | None = None
    config_version: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    message: str | None = None


class MyBatchItem(BaseModel):
    batch_id: str
    initiated_item_id: int
    initiated_item_type: str
    status: str
    candidate_count: int
    degraded: bool
    created_at: datetime
    expires_at: datetime | None = None
    can_rematch: bool = False


class MyBatchListOut(BaseModel):
    items: list[MyBatchItem] = Field(default_factory=list)
    total: int = 0


class CandidateSummaryOut(BaseModel):
    candidate_public_id: str
    item_type: str
    category: str
    color: str | None = None
    brand: str | None = None
    area_name: str
    occurred_on: str | None = None
    title_excerpt: str
    description_excerpt: str
    thumb_url: str | None = None
    score: float
    score_breakdown: ScoreBreakdown
    differences: list[DifferenceItem] = Field(default_factory=list)
    requires_offline_verification: bool = False
    explanation_status: str = "ready"
    reasons: list[str] = Field(default_factory=list)


class CandidateVerifiedOut(CandidateSummaryOut):
    occurred_window: str | None = None
    location_text: str | None = None
    visible_features: list[str] = Field(default_factory=list)


class CandidateHandoverOut(CandidateVerifiedOut):
    handover_location_code: str | None = None
    handover_window_start: datetime | None = None
    handover_window_end: datetime | None = None
    handover_note: str | None = None


class CandidateSummaryListOut(BaseModel):
    batch_id: str
    disclosure_level: str = "summary"
    candidates: list[CandidateSummaryOut] = Field(default_factory=list)
    filtered_total: int = 0
    total: int = 0
    sort_note: str = "分数降序 → 时间接近度 → 地点接近度 → candidate_id"
    disclaimer: str = "候选基于相似度匹配，交接前请线下核验物品真伪"


class ExplanationOut(BaseModel):
    candidate_public_id: str
    score: float
    score_breakdown: ScoreBreakdown
    reasons: list[str] = Field(default_factory=list)
    differences: list[DifferenceItem] = Field(default_factory=list)
    explanation_status: str = "ready"
    disclaimer: str = "解释仅依据公开字段与已计算分项"


class FeedbackRequest(BaseModel):
    feedback_type: Literal["not_mine", "not_target", "inaccurate", "suspected_impersonation"]
    note: str | None = Field(default=None, max_length=200)


class FeedbackOut(BaseModel):
    feedback_id: int
    recorded: bool = True