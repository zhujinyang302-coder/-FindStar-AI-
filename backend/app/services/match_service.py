"""智能匹配服务。

流程：权限/状态校验 → 幂等检查 → 召回另一侧有效记录 → 后端评分排序 →
阈值过滤取 Top N → 生成解释（失败降级）→ 持久化 → 返回结果。

候选只来自数据库真实记录；分数只由后端算法计算。
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.matching import score_pair
from app.ai.provider import AIUnavailableError, get_provider
from app.cache import get_cache
from app.core.config import settings
from app.core.logging import get_logger
from app.core.response import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.enums import ItemStatus, ItemType, MatchStatus
from app.db.models import FoundItem, LostItem, MatchRecord, User
from app.schemas.match import (
    DifferenceItem,
    MatchBatchOut,
    MatchCandidate,
    MatchDetailOut,
    ScoreBreakdown,
    ScorePart,
)
from app.services import item_service
from app.services.item_service import _model, _TIME_FIELD, to_side  # noqa: PLC2701

logger = get_logger(__name__)


def _batch_id(initiated_type: str, initiated_id: int, data_version: str, algo: str) -> str:
    raw = f"{initiated_type}:{initiated_id}:{data_version}:{algo}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _data_version(item) -> str:
    return str(int(item.updated_at.timestamp()))


def _breakdown_model(breakdown: dict) -> ScoreBreakdown:
    return ScoreBreakdown(
        text=ScorePart(**breakdown["text"]),
        image=ScorePart(**breakdown["image"]),
        location=ScorePart(**breakdown["location"]),
        time=ScorePart(**breakdown["time"]),
        attribute=ScorePart(**breakdown["attribute"]),
    )


def start_match(
    db: Session,
    *,
    user: User,
    lost_item_id: int | None,
    found_item_id: int | None,
) -> MatchBatchOut:
    if (lost_item_id is None) == (found_item_id is None):
        raise ValidationError("必须且只能提供一个 lost_item_id 或 found_item_id")

    if lost_item_id is not None:
        initiated_type, initiated_id = ItemType.lost.value, lost_item_id
    else:
        initiated_type, initiated_id = ItemType.found.value, int(found_item_id or 0)

    model = _model(initiated_type)
    item = db.get(model, initiated_id)
    if item is None:
        raise NotFoundError("记录不存在")
    if item.user_id != user.id and user.role != "admin":
        raise ForbiddenError("只能对本人记录发起匹配")
    if item.status != ItemStatus.active.value or item.is_removed:
        raise ConflictError("记录当前状态不允许匹配", code="MATCH_NOT_ALLOWED")
    if not (item.title and (item.description or item.category)):
        raise ValidationError("记录信息不足，无法匹配")

    algo = settings.match_algorithm_version
    data_version = _data_version(item)
    batch_id = _batch_id(initiated_type, initiated_id, data_version, algo)

    cache = get_cache()
    cache_key = cache.match_key(initiated_type, initiated_id, algo, data_version)

    # 幂等：同一记录对同一算法版本复用既有批次
    existing = db.execute(
        select(MatchRecord).where(MatchRecord.batch_id == batch_id)
    ).scalars().all()
    if existing:
        return _build_batch_out(db, initiated_type, initiated_id, batch_id, existing, algo)

    cached = cache.get_json(cache_key)
    if cached:
        logger.info("match cache hit", extra={"route": "matches"})
        return MatchBatchOut.model_validate(cached)

    other_type = ItemType.found.value if initiated_type == ItemType.lost.value else ItemType.lost.value
    other_model = _model(other_type)
    rows = db.execute(
        select(other_model).where(
            other_model.is_removed.is_(False),
            other_model.status == ItemStatus.active.value,
        )
    ).scalars().all()

    initiated_side = to_side(item, initiated_type)
    scored: list[tuple[object, object]] = []
    for row in rows:
        side = to_side(row, other_type)
        result = score_pair(initiated_side, side, window_days=settings.match_time_window_days)
        scored.append((row, result))
    scored.sort(key=lambda pair: pair[1].total, reverse=True)  # type: ignore[attr-defined]

    reliable = [pair for pair in scored if pair[1].total >= settings.match_score_threshold]  # type: ignore[attr-defined]
    top = reliable[: settings.match_max_candidates]

    records: list[MatchRecord] = []
    provider = get_provider()
    for row, result in top:
        if initiated_type == ItemType.lost.value:
            lost_id, found_id = initiated_id, row.id
        else:
            lost_id, found_id = row.id, initiated_id
        reason = _build_reason(provider, initiated_side, result)
        record = MatchRecord(
            batch_id=batch_id,
            initiated_item_type=initiated_type,
            lost_item_id=lost_id,
            found_item_id=found_id,
            score=result.total,  # type: ignore[attr-defined]
            score_breakdown=result.breakdown,  # type: ignore[attr-defined]
            reason_json=reason,
            algorithm_version=algo,
            status=MatchStatus.proposed.value,
            initiated_by=user.id,
        )
        db.add(record)
        records.append(record)

    db.commit()
    for record in records:
        db.refresh(record)

    batch_out = _build_batch_out(db, initiated_type, initiated_id, batch_id, records, algo)
    cache.set_json(cache_key, batch_out.model_dump(mode="json"), ttl=settings.cache_match_ttl)
    return batch_out


def _build_reason(provider, initiated_side, result) -> dict:
    context = {
        "score": result.total,
        "breakdown": result.breakdown,
        "computed_reasons": result.reasons,
        "differences": result.differences,
    }
    try:
        explanation = provider.explain_match(context=context)
    except AIUnavailableError as exc:
        logger.warning("explain fallback", extra={"error_category": "AI_EXPLAIN_FAILED"})
        explanation = {
            "summary": f"解释生成不可用（{exc}），已降级为规则化描述。",
            "reasons": result.reasons,
            "differences": [d.get("note", "") for d in result.differences],
        }
    reasons = explanation.get("reasons") or result.reasons
    return {
        "summary": explanation.get("summary", ""),
        "reasons": reasons,
        "differences": result.differences,
        "provider": provider.name,
        "degraded": provider.degraded,
    }


def _build_batch_out(
    db: Session,
    initiated_type: str,
    initiated_id: int,
    batch_id: str,
    records: list[MatchRecord],
    algo: str,
) -> MatchBatchOut:
    other_type = ItemType.found.value if initiated_type == ItemType.lost.value else ItemType.lost.value
    results: list[MatchCandidate] = []
    for record in sorted(records, key=lambda r: float(r.score), reverse=True):
        candidate_id = record.found_item_id if initiated_type == ItemType.lost.value else record.lost_item_id
        candidate = db.get(_model(other_type), candidate_id)
        if candidate is None:
            continue
        reason = record.reason_json or {}
        results.append(
            MatchCandidate(
                match_id=record.id,
                candidate=item_service.serialize_list_item(candidate, other_type),
                score=float(record.score),
                score_breakdown=_breakdown_model(record.score_breakdown),
                reasons=[str(x) for x in reason.get("reasons", [])],
                differences=[DifferenceItem(**d) for d in reason.get("differences", [])],
            )
        )

    reliable = bool(results)
    message = None if reliable else "暂未找到可靠候选"
    return MatchBatchOut(
        batch_id=batch_id,
        algorithm_version=algo,
        initiated_item_type=initiated_type,
        initiated_item_id=initiated_id,
        reliable=reliable,
        message=message,
        results=results,
    )


def get_match(db: Session, match_id: int, viewer: User) -> MatchDetailOut:
    record = db.get(MatchRecord, match_id)
    if record is None:
        raise NotFoundError("匹配结果不存在")
    if record.initiated_by != viewer.id and viewer.role != "admin":
        raise ForbiddenError("无权访问该匹配结果")

    initiated_type = record.initiated_item_type
    candidate_type = (
        ItemType.found.value if initiated_type == ItemType.lost.value else ItemType.lost.value
    )
    initiated_id = record.lost_item_id if initiated_type == ItemType.lost.value else record.found_item_id
    candidate_id = record.found_item_id if initiated_type == ItemType.lost.value else record.lost_item_id
    candidate = db.get(_model(candidate_type), candidate_id)
    if candidate is None:
        raise NotFoundError("候选记录不存在")

    reason = record.reason_json or {}
    siblings = db.execute(
        select(MatchRecord).where(MatchRecord.batch_id == record.batch_id)
    ).scalars().all()
    batch_results = _build_batch_out(
        db,
        initiated_type,
        initiated_id,
        record.batch_id,
        list(siblings),
        record.algorithm_version,
    ).results
    return MatchDetailOut(
        match_id=record.id,
        batch_id=record.batch_id,
        algorithm_version=record.algorithm_version,
        score=float(record.score),
        status=record.status,
        initiated_item_type=initiated_type,
        initiated_item_id=initiated_id,
        candidate_item_type=candidate_type,
        candidate_item_id=candidate_id,
        candidate=item_service.serialize_list_item(candidate, candidate_type),
        score_breakdown=_breakdown_model(record.score_breakdown),
        reasons=[str(x) for x in reason.get("reasons", [])],
        differences=[DifferenceItem(**d) for d in reason.get("differences", [])],
        created_at=record.created_at,
        batch_results=batch_results,
    )