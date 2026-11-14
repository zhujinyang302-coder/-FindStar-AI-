"""审计日志服务（只追加）。

审计字段来源 design 2.1.3(8)；私密核验正文不进入审计与日志。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.db.models import AuditLog

_SENSITIVE_KEYS = {
    "password",
    "token",
    "api_key",
    "private_evidence",
    "private_verification",
    "secret",
    "handover_note",
}


def _sanitize(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return details
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if key.lower() in _SENSITIVE_KEYS:
            cleaned[key] = "[REDACTED]"
        else:
            cleaned[key] = value
    return cleaned


def record_audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int,
    details: dict[str, Any] | None = None,
    actor_role: str | None = None,
    request_id: str | None = None,
    batch_id: str | None = None,
    candidate_id: str | None = None,
    disclosure_level: str | None = None,
    before_status: str | None = None,
    after_status: str | None = None,
    reason: str | None = None,
) -> AuditLog:
    log = AuditLog(
        request_id=request_id or request_id_var.get() or None,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        batch_id=batch_id,
        candidate_id=candidate_id,
        disclosure_level=disclosure_level,
        before_status=before_status,
        after_status=after_status,
        reason=reason,
        details=_sanitize(details),
    )
    db.add(log)
    return log