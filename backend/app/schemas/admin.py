"""管理端 Schema：上下架审核与质量配置。

结构约束：审核 DTO 中不存在候选、分数、对侧记录、申请人身份与私密核验字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.item import ImageOut


class ReviewQueueItem(BaseModel):
    ticket_no: str
    review_type: str
    source: str
    item_type: str
    item_id: int
    item_title: str
    status: str
    waiting_minutes: int
    overdue: bool
    created_at: datetime


class ReviewQueueOut(BaseModel):
    items: list[ReviewQueueItem] = Field(default_factory=list)
    total: int = 0


class ComplianceCheckOut(BaseModel):
    key: str
    passed: bool
    note: str | None = None


class ReviewHistoryItem(BaseModel):
    review_round: int
    status: str
    opinion: str | None = None
    decided_at: datetime | None = None


class ReviewTicketDetailOut(BaseModel):
    ticket_no: str
    review_type: str
    source: str
    status: str
    item_type: str
    item_id: int
    item_title: str
    item_category: str
    item_description: str
    location_text: str
    occurred_at: datetime | None = None
    images: list[ImageOut] = Field(default_factory=list)
    compliance_checks: list[ComplianceCheckOut] = Field(default_factory=list)
    history: list[ReviewHistoryItem] = Field(default_factory=list)
    disclaimer: str = "匹配结果不参与审核结论"


class ReviewDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    opinion: str | None = Field(default=None, max_length=500)

    @field_validator("opinion")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v else v

    @model_validator(mode="after")
    def _reject_requires_opinion(self) -> "ReviewDecisionRequest":
        if self.decision == "reject":
            if not self.opinion or len(self.opinion.strip()) < 5:
                raise ValueError("驳回必须填写不少于 5 字的理由")
        return self


class ReviewDecisionOut(BaseModel):
    ticket_no: str
    status: str
    item_status: str
    decided_at: datetime
    match_task_created: bool = False
    impact: dict = Field(default_factory=dict)


class DelistApplyRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class WeightsOut(BaseModel):
    text: float
    image: float
    location: float
    time: float
    attribute: float


class MatchConfigVersionOut(BaseModel):
    version: str
    threshold: float
    quota: int
    time_window_days: int
    weights: dict | None = None
    recall_strategy: str
    changed_by: int | None = None
    reason: str | None = None
    active: bool
    created_at: datetime


class MatchConfigVersionListOut(BaseModel):
    items: list[MatchConfigVersionOut] = Field(default_factory=list)


class MatchConfigCreateRequest(BaseModel):
    threshold: float = Field(ge=0.0, le=100.0)
    quota: int = Field(ge=1, le=5)
    time_window_days: int = Field(ge=1, le=365)
    weights: WeightsOut | None = None
    reason: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def _weights_sum(self) -> "MatchConfigCreateRequest":
        if self.weights is not None:
            total = (
                self.weights.text
                + self.weights.image
                + self.weights.location
                + self.weights.time
                + self.weights.attribute
            )
            if abs(total - 1.0) > 0.01:
                raise ValueError("权重之和必须为 1（允许 0.01 容差）")
        return self


class QualityMetricsOut(BaseModel):
    match_requests: int
    no_candidate_rate: float
    top3_hit_rate: float
    user_false_positive_rate: float
    degraded_rate: float
    candidate_p95_ms: float
    period_label: str
    generated_at: datetime
    note: str = "聚合口径，不含任何候选内容与用户身份"