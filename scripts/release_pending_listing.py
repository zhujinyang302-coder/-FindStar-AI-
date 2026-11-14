"""存量待上架记录自动放行脚本（发布免审核切换）。

特性：
- 默认即演练（零写入）；正式放行需同时提供 --release-pending 且配置
  AUTO_APPROVE_LEGACY_PENDING=true；
- 幂等、按批提交、--from-id 续跑；
- 不触碰下架审核单与既有终态记录；
- 输出六项一致性断言与回执报告。

用法：
    python scripts/release_pending_listing.py
    python scripts/release_pending_listing.py --release-pending --batch-size 200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.listing_modes import (  # noqa: E402
    AUDIT_ITEM_AUTO_APPROVED,
    LEGACY_REJECT_OPINION,
    LEGACY_RELEASE_OPINION,
    LEGACY_RELEASE_SOURCE,
    NOTIFICATION_LISTING_AUTO_APPROVED,
)
from app.core.timeutil import utcnow  # noqa: E402
from app.db.enums import (  # noqa: E402
    ItemLifecycleStatus as S,
    ReviewTicketStatus,
    ReviewType,
    VisibilityScope,
)
from app.db.models import FoundItem, LostItem, ReviewTicket, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import audit, notification_service, review_service  # noqa: E402

SCRIPT_VERSION = "1.0.0"
_MODELS = (("lost", LostItem), ("found", FoundItem))


def _count(db, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int(db.execute(stmt).scalar_one())


def _pending_items(db, from_id: int | None) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = []
    for item_type, model in _MODELS:
        stmt = select(model).where(model.status == S.pending_listing.value)
        if from_id is not None:
            stmt = stmt.where(model.id > from_id)
        rows.extend((item_type, item) for item in db.execute(stmt).scalars().all())
    return rows


def _reject_reason(db, item) -> str | None:
    if item.is_removed:
        return "记录已移除"
    if not item.info_sufficient:
        return "信息量不足"
    owner = db.get(User, item.user_id)
    if owner is None or owner.status != "active":
        return "归属账号不可用"
    return None


def _pending_listing_tickets(db, item_type: str, item_id: int) -> list[ReviewTicket]:
    return list(
        db.execute(
            select(ReviewTicket).where(
                ReviewTicket.review_type == ReviewType.listing.value,
                ReviewTicket.item_type == item_type,
                ReviewTicket.item_id == item_id,
                ReviewTicket.status == ReviewTicketStatus.pending.value,
            )
        )
        .scalars()
        .all()
    )


def _converge_tickets(db, item_type: str, item, *, approved: bool, now) -> int:
    tickets = _pending_listing_tickets(db, item_type, item.id)
    for ticket in tickets:
        ticket.status = (
            ReviewTicketStatus.approved.value
            if approved
            else ReviewTicketStatus.rejected.value
        )
        ticket.source = LEGACY_RELEASE_SOURCE if approved else ticket.source
        ticket.opinion = (
            LEGACY_RELEASE_OPINION if approved else LEGACY_REJECT_OPINION
        )
        ticket.decided_by = None
        ticket.decided_at = now
        ticket.deadline_at = None
    if approved and not tickets:
        ticket = review_service.create_ticket(
            db,
            review_type=ReviewType.listing.value,
            item_type=item_type,
            item_id=item.id,
            applicant_id=item.user_id,
            review_round=int(item.review_round or 1),
            source=LEGACY_RELEASE_SOURCE,
            status=ReviewTicketStatus.approved.value,
            opinion=LEGACY_RELEASE_OPINION,
            decided_at=now,
        )
        tickets = [ticket]
    if tickets:
        item.latest_ticket_id = tickets[0].id
    return len(tickets)


def _release(db, item_type: str, item, now) -> None:
    before = item.status
    item.status = S.active.value
    item.visibility_scope = VisibilityScope.match_disclosure.value
    item.is_removed = False

    _converge_tickets(db, item_type, item, approved=True, now=now)

    audit.record_audit(
        db,
        actor_id=None,
        actor_role="system",
        action=AUDIT_ITEM_AUTO_APPROVED,
        entity_type=f"{item_type}_item",
        entity_id=item.id,
        before_status=before,
        after_status=item.status,
        reason=LEGACY_RELEASE_OPINION,
        details={
            "review_mode": "auto",
            "legacy_release": True,
            "ticket_no": None,
        },
    )
    notification_service.notify(
        db,
        user_id=item.user_id,
        event_type=NOTIFICATION_LISTING_AUTO_APPROVED,
        ref_type="review_ticket",
        ref_id=item.latest_ticket_id,
    )
    if settings.auto_match_on_approve and item.info_sufficient:
        from app.services.match_orchestrator import enqueue_auto_match

        enqueue_auto_match(
            db,
            item_type=item_type,
            item=item,
            initiator_id=item.user_id,
        )


def _reject(db, item_type: str, item, now) -> None:
    item.status = S.listing_rejected.value
    item.delist_reason = LEGACY_REJECT_OPINION
    _converge_tickets(db, item_type, item, approved=False, now=now)
    notification_service.notify(
        db,
        user_id=item.user_id,
        event_type="review_result",
        ref_type="review_ticket",
        ref_id=item.latest_ticket_id,
        body="存量迁移：记录不满足自动上架条件，请修改后重新提交。",
    )


def _assertions(db, *, total_before: int, released: list[tuple[str, int]]) -> dict:
    pending_tickets = _count(
        db,
        ReviewTicket,
        ReviewTicket.review_type == ReviewType.listing.value,
        ReviewTicket.status == ReviewTicketStatus.pending.value,
    )
    pending_items = 0
    for _, model in _MODELS:
        pending_items += _count(db, model, model.status == S.pending_listing.value)

    missing_visibility = 0
    missing_ticket = 0
    for item_type, item_id in released:
        model = dict(_MODELS)[item_type]
        item = db.get(model, item_id)
        if item is None:
            continue
        if item.visibility_scope != VisibilityScope.match_disclosure.value:
            missing_visibility += 1
        ticket = db.execute(
            select(ReviewTicket).where(
                ReviewTicket.id == item.latest_ticket_id,
                ReviewTicket.status == ReviewTicketStatus.approved.value,
            )
        ).scalars().first()
        if ticket is None:
            missing_ticket += 1

    total_after = sum(_count(db, model) for _, model in _MODELS)

    return {
        "no_pending_listing_tickets": pending_tickets == 0,
        "no_pending_listing_items": pending_items == 0,
        "released_visibility_ok": missing_visibility == 0,
        "released_ticket_ok": missing_ticket == 0,
        "item_total_unchanged": total_after == total_before,
        "details": {
            "pending_listing_tickets": pending_tickets,
            "pending_listing_items": pending_items,
            "missing_visibility": missing_visibility,
            "missing_ticket": missing_ticket,
            "total_before": total_before,
            "total_after": total_after,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="存量待上架记录自动放行")
    parser.add_argument("--dry-run", action="store_true", help="只读演练（默认行为）")
    parser.add_argument(
        "--release-pending", action="store_true", help="正式放行（需二次保险）"
    )
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--from-id", type=int, default=None)
    parser.add_argument("--report", type=str, default=None)
    args = parser.parse_args()

    execute = bool(args.release_pending and not args.dry_run)
    if execute and not settings.auto_approve_legacy_pending:
        print("缺少 AUTO_APPROVE_LEGACY_PENDING=true，自动降级为演练模式")
        execute = False

    db = SessionLocal()
    now = utcnow()
    total_before = sum(_count(db, model) for _, model in _MODELS)
    released: list[tuple[str, int]] = []
    rejected: list[tuple[str, int]] = []
    skipped: list[dict] = []
    released_count = 0

    try:
        rows = _pending_items(db, args.from_id)
        for index, (item_type, item) in enumerate(rows):
            reason = _reject_reason(db, item)
            if reason:
                skipped.append(
                    {"item_type": item_type, "item_id": item.id, "reason": reason}
                )
                if execute:
                    _reject(db, item_type, item, now)
                    rejected.append((item_type, item.id))
                continue
            if execute:
                _release(db, item_type, item, now)
                released.append((item_type, item.id))
                released_count += 1
            if execute and (index + 1) % max(args.batch_size, 1) == 0:
                db.commit()

        if execute:
            db.commit()
        else:
            db.rollback()

        assertions = _assertions(db, total_before=total_before, released=released)
    finally:
        db.close()

    differences = len(skipped)
    assertions_ok = all(
        value for key, value in assertions.items() if key != "details"
    )
    report = {
        "script_version": SCRIPT_VERSION,
        "mode": "release" if execute else "dry-run",
        "from_id": args.from_id,
        "batch_size": args.batch_size,
        "candidates": len(rows),
        "released": released_count,
        "rejected": len(rejected),
        "skipped": skipped,
        "assertions": assertions,
        "assertions_ok": assertions_ok,
        "executed_at": now.isoformat(),
    }
    output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(output)
    if args.report:
        Path(args.report).write_text(output, encoding="utf-8")

    if differences or not assertions_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())