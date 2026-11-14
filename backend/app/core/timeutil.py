"""时间工具：统一使用 UTC 的 naive 时间，避免时区歧义。"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)