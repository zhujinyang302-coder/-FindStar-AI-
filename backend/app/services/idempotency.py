"""幂等键服务：同一用户同一 (scope, key) 24 小时内返回首次结果。"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import ConflictError
from app.core.timeutil import utcnow
from app.db.models import IdempotencyKey

_TTL_HOURS = 24


def payload_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def begin(
    db: Session, *, user_id: int, scope: str, key: str | None, payload: Any
) -> tuple[IdempotencyKey | None, bool]:
    """返回 (记录, 是否首次)。命中同键同载荷返回既有记录且 is_new=False。"""
    if not key:
        return None, True
    digest = payload_hash(payload)
    existing = db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.scope == scope,
            IdempotencyKey.key == key,
        )
    ).scalars().first()
    if existing is not None:
        if existing.payload_hash != digest:
            raise ConflictError(
                "相同幂等键提交了不同内容", code="DUPLICATE_SUBMISSION"
            )
        if existing.created_at < utcnow() - timedelta(hours=_TTL_HOURS):
            existing.payload_hash = digest
            existing.response_json = None
            existing.created_at = utcnow()
            return existing, True
        return existing, False
    record = IdempotencyKey(
        user_id=user_id,
        scope=scope,
        key=key,
        payload_hash=digest,
        created_at=utcnow(),
    )
    db.add(record)
    db.flush()
    return record, True


def save_response(db: Session, record: IdempotencyKey | None, response: dict) -> None:
    if record is None:
        return
    record.response_json = response
    db.flush()


def cached_response(record: IdempotencyKey | None) -> dict | None:
    if record is None or not record.response_json:
        return None
    return dict(record.response_json)