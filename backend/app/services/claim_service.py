"""认领申请与管理员审核服务。

- 认领申请幂等：同一用户对同一目标重复提交返回既有申请。
- 私密核验信息仅用于审核，不进入公开响应或普通日志。
- 审核在事务中执行：更新目标记录状态、处理冲突申请并写入审计日志。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import utcnow
from app.db.enums import ItemStatus, ItemType, MatchStatus, ReviewStatus
from app.db.models import ClaimRequest, MatchRecord, User
from app.schemas.claim import ClaimListOut, ClaimOut
from app.schemas.admin import ClaimReviewOut
from app.services import audit
from app.services.item_service import _model  # noqa: PLC2701
from app.services.state_machine import assert_transition

# 审核通过后目标记录的目标状态
_APPROVED_TARGET_STATUS = ItemStatus.claimed.value


def _resolve_target(
    db: Session, *, match_id: int | None, lost_item_id: int | None, found_item_id: int | None
) -> tuple[str, int]:
    """确定认领目标记录（type, id）。"""
    if lost_item_id is not None:
        return ItemType.lost.value, lost_item_id
    if found_item_id is not None:
        return ItemType.found.value, found_item_id
    if match_id is not None:
        record = db.get(MatchRecord, match_id)
        if record is None:
            raise NotFoundError("匹配结果不存在")
        # 认领主场景：失主认领拾获记录
        return ItemType.found.value, record.found_item_id
    raise ConflictError("无法确定认领目标", code="CLAIM_TARGET_REQUIRED")


def create_claim(
    db: Session,
    *,
    user: User,
    match_id: int | None,
    lost_item_id: int | None,
    found_item_id: int | None,
    private_evidence: str,
) -> ClaimOut:
    target_type, target_id = _resolve_target(
        db, match_id=match_id, lost_item_id=lost_item_id, found_item_id=found_item_id
    )
    model = _model(target_type)
    target = db.get(model, target_id)
    if target is None:
        raise NotFoundError("目标记录不存在")
    if target.status != ItemStatus.active.value or target.is_removed:
        raise ConflictError("该记录当前不接受认领申请", code="CLAIM_NOT_ALLOWED")

    # 幂等：同一用户对同一目标已存在有效申请则返回既有
    existing = db.execute(
        select(ClaimRequest).where(
            ClaimRequest.claimant_id == user.id,
            ClaimRequest.review_status.in_(
                [ReviewStatus.pending.value, ReviewStatus.approved.value]
            ),
        )
    ).scalars().all()
    for claim in existing:
        existing_target_id = (
            claim.lost_item_id if target_type == ItemType.lost.value else claim.found_item_id
        )
        if existing_target_id == target_id:
            return _serialize(db, claim, target_type, target)

    claim = ClaimRequest(
        match_id=match_id,
        lost_item_id=target_id if target_type == ItemType.lost.value else None,
        found_item_id=target_id if target_type == ItemType.found.value else None,
        claimant_id=user.id,
        private_evidence=private_evidence,
        review_status=ReviewStatus.pending.value,
    )
    db.add(claim)
    db.flush()
    audit.record_audit(
        db,
        actor_id=user.id,
        action="claim_submit",
        entity_type="claim_request",
        entity_id=claim.id,
        details={"target_type": target_type, "target_id": target_id},
    )
    db.commit()
    db.refresh(claim)
    return _serialize(db, claim, target_type, target)


def list_my_claims(db: Session, user: User) -> ClaimListOut:
    claims = db.execute(
        select(ClaimRequest)
        .where(ClaimRequest.claimant_id == user.id)
        .order_by(ClaimRequest.created_at.desc())
    ).scalars().all()
    items = [serialize_claim(db, claim) for claim in claims]
    return ClaimListOut(items=items, total=len(items))


def _serialize(db: Session, claim: ClaimRequest, target_type: str, target) -> ClaimOut:
    return ClaimOut(
        id=claim.id,
        match_id=claim.match_id,
        target_type=target_type,
        target_item_id=target.id,
        target_title=target.title,
        review_status=claim.review_status,
        review_note=claim.review_note,
        created_at=claim.created_at,
        reviewed_at=claim.reviewed_at,
    )


def serialize_claim(db: Session, claim: ClaimRequest) -> ClaimOut:
    if claim.lost_item_id is not None:
        target_type, target_id = ItemType.lost.value, claim.lost_item_id
    elif claim.found_item_id is not None:
        target_type, target_id = ItemType.found.value, claim.found_item_id
    else:
        target_type, target_id = ItemType.found.value, 0
    model = _model(target_type)
    target = db.get(model, target_id)
    title = target.title if target else "（记录已删除）"
    return ClaimOut(
        id=claim.id,
        match_id=claim.match_id,
        target_type=target_type,
        target_item_id=target_id,
        target_title=title,
        review_status=claim.review_status,
        review_note=claim.review_note,
        created_at=claim.created_at,
        reviewed_at=claim.reviewed_at,
    )


# ---------------- 管理员审核 ----------------
def review_claim(
    db: Session, *, admin: User, claim_id: int, action: str, review_note: str | None
) -> ClaimReviewOut:
    if admin.role != "admin":
        raise ForbiddenError("需要管理员权限")

    claim = db.execute(
        select(ClaimRequest).where(ClaimRequest.id == claim_id).with_for_update()
    ).scalars().first()
    if claim is None:
        raise NotFoundError("认领申请不存在")
    if claim.review_status != ReviewStatus.pending.value:
        raise ConflictError("该申请已被处理", code="CLAIM_ALREADY_REVIEWED")

    target_type = ItemType.lost.value if claim.lost_item_id else ItemType.found.value
    target_id = claim.lost_item_id or claim.found_item_id
    model = _model(target_type)
    target = db.execute(
        select(model).where(model.id == target_id).with_for_update()
    ).scalars().first()
    if target is None:
        raise NotFoundError("目标记录不存在")
    if target.status != ItemStatus.active.value:
        raise ConflictError("目标记录状态已变化，请刷新后重试", code="TARGET_STATE_CHANGED")

    item_status: str | None = None
    if action == "approve":
        assert_transition(target.status, _APPROVED_TARGET_STATUS)
        target.status = _APPROVED_TARGET_STATUS
        item_status = target.status
        claim.review_status = ReviewStatus.approved.value
        # 关联匹配结果置为已确认
        if claim.match_id:
            match = db.get(MatchRecord, claim.match_id)
            if match:
                match.status = MatchStatus.confirmed.value
        # 同一目标的其他待处理申请进入拒绝态
        conflicts = db.execute(
            select(ClaimRequest).where(
                ClaimRequest.id != claim.id,
                ClaimRequest.review_status == ReviewStatus.pending.value,
            )
        ).scalars().all()
        for other in conflicts:
            other_target_id = other.lost_item_id if target_type == ItemType.lost.value else other.found_item_id
            if other_target_id == target_id:
                other.review_status = ReviewStatus.rejected.value
                other.review_note = "已有其他申请被通过"
                other.confirmer_id = admin.id
                other.reviewed_at = utcnow()
    else:
        claim.review_status = ReviewStatus.rejected.value

    claim.confirmer_id = admin.id
    claim.review_note = review_note
    claim.reviewed_at = utcnow()

    audit.record_audit(
        db,
        actor_id=admin.id,
        action=f"claim_{action}",
        entity_type="claim_request",
        entity_id=claim.id,
        details={"target_type": target_type, "target_id": target_id, "item_status": item_status},
    )
    if item_status:
        audit.record_audit(
            db,
            actor_id=admin.id,
            action="item_status_change",
            entity_type=f"{target_type}_item",
            entity_id=target_id,
            details={"from": ItemStatus.active.value, "to": item_status, "reason": "claim_approved"},
        )
    db.commit()
    db.refresh(claim)
    return ClaimReviewOut(
        claim_id=claim.id,
        review_status=claim.review_status,
        reviewed_at=claim.reviewed_at,
        item_status=item_status,
    )


def list_pending_claims(db: Session) -> list[ClaimRequest]:
    return list(
        db.execute(
            select(ClaimRequest)
            .where(ClaimRequest.review_status == ReviewStatus.pending.value)
            .order_by(ClaimRequest.created_at.asc())
        ).scalars().all()
    )