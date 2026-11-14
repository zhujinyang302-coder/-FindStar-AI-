"""公开聚合统计（唯一允许的公开口径）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PublicStatsOut(BaseModel):
    completed_total: int
    generated_at: datetime
    disclaimer: str = "仅提供聚合完成数量，不提供任何可反推的个人信息"