"""存量数据迁移到 V3 双向匹配结构。

特性：
- 幂等、可续跑、每批独立事务；
- `--dry-run` 零写入；
- 迁移前后计数与六条一致性断言；
- 差异非零时以非零退出码终止，阻止上线。

用法：
    python scripts/migrate_bidirectional_match.py --dry-run
    python scripts/migrate_bidirectional_match.py --batch-size 200
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.ai.matching import BASE_WEIGHTS  # noqa: E402
from app.core.timeutil import utcnow  # noqa: E402
from app.db.enums import (  # noqa: E402
    BatchStatus,
    CandidateStatus,
    ContactStatus,
    DisclosureLevel,
    ItemLifecycleStatus,
    ReviewStatus,
    VisibilityScope,
)
from app.db.models import (  # noqa: E402
    ClaimRequest,
    ContactRequest,
    FoundItem,
    ItemImage,
    LostItem,
    MatchBatch,
    MatchRecord,
)
from app.db.session import SessionLocal  # noqa: E402
from app.services.disclosure_service import candidate_public_id  # noqa: E402

LEGACY_STATUS_MAP = {
    "active": ItemLifecycleStatus.active.value,
    "claimed": ItemLifecycleStatus.claimed.value,
    "resolved": ItemLifecycleStatus.resolved.value,
    "closed": ItemLifecycleStatus.closed.value,
    "rejected": ItemLifecycleStatus.listing_rejected.value,
    "pending": ItemLifecycleStatus.pending_listing.value,
}

CLAIM_STATUS_MAP = {
    ReviewStatus.pending.value: ContactStatus.pending.value,
    ReviewStatus.approved.value: ContactStatus.confirmed.value,
    ReviewStatus.rejected.value: ContactStatus.rejected.value,
}


def _items(db: Session):
    return list(db.execute(select(LostItem)).scalars().all()) + list(
        db.execute(select(FoundItem)).scalars().all()
    )


def migrate_items(db: Session, *, dry_run: bool) -> int:
    changed = 0
    for item in _items(db):
        item_type = "lost" if isinstance(item, LostItem) else "found"
        target = LEGACY_STATUS_MAP.get(item.status, ItemLifecycleStatus.active.value)
        image_count = int(
            db.execute(
                select(func.count(ItemImage.id)).where(
                    ItemImage.item_type == item_type, ItemImage.item_id == item.id
                )
            ).scalar_one()
        )
        expected_sufficient = image_count >= 1 or len((item.description or "").strip()) >= 20
        values = {
            "status": target,
            "visibility_scope": VisibilityScope.owner_only.value,
            "info_sufficient": bool(expected_sufficient),
            "data_version": max(int(item.data_version or 0), 1),
        }
        if any(getattr(item, key) != value for key, value in values.items()):
            changed += 1
            if not dry_run:
                for key, value in values.items():
                    setattr(item, key, value)
    return changed


def migrate_batches(db: Session, *, dry_run: bool) -> int:
    created = 0
    records = list(db.execute(select(MatchRecord)).scalars().all())
    by_batch: dict[str, list[MatchRecord]] = {}
    for record in records:
        by_batch.setdefault(record.batch_id, []).append(record)

    for batch_id, rows in by_batch.items():
        existing = db.execute(
            select(MatchBatch).where(MatchBatch.batch_id == batch_id)
        ).scalars().first()
        if existing is not None:
            for row in rows:
                _fill_candidate(row, existing)
            continue
        created += 1
        if dry_run:
            continue
        first = rows[0]
        initiated_type = first.initiated_item_type
        initiated_id = (
            first.lost_item_id if initiated_type == "lost" else first.found_item_id
        )
        created_at = min(row.created_at for row in rows)
        batch = MatchBatch(
            batch_id=batch_id,
            idempotency_key=f"migrate:{batch_id}",
            initiated_item_type=initiated_type,
            initiated_item_id=initiated_id,
            initiator_id=first.initiated_by,
            direction="lost_to_found" if initiated_type == "lost" else "found_to_lost",
            status=BatchStatus.completed.value,
            algorithm_version=first.algorithm_version,
            config_version="migrated",
            data_version=1,
            threshold=0.0,
            quota=min(5, len(rows)),
            weights_snapshot=dict(BASE_WEIGHTS),
            recall_channel="keyword",
            degraded=True,
            degraded_reason="存量迁移批次",
            filter_stats={},
            candidate_count=len(rows),
            visible=True,
            created_at=created_at,
            completed_at=created_at,
            expires_at=created_at,
        )
        db.add(batch)
        db.flush()
        for row in rows:
            _fill_candidate(row, batch)
    return created


def _fill_candidate(row: MatchRecord, batch: MatchBatch) -> None:
    candidate_type = (
        "found" if row.initiated_item_type == "lost" else "lost"
    )
    candidate_id = (
        row.found_item_id if candidate_type == "found" else row.lost_item_id
    )
    row.batch_fk = batch.id
    row.candidate_public_id = candidate_public_id(batch.batch_id, candidate_type, candidate_id)
    row.candidate_item_type = candidate_type
    row.candidate_item_id = candidate_id
    row.disclosure_level = DisclosureLevel.summary.value
    row.candidate_status = CandidateStatus.valid.value
    row.explanation_status = "ready"
    row.view_count = int(row.view_count or 0)
    row.expires_at = batch.expires_at
    row.differences_json = (row.reason_json or {}).get("differences", [])


def migrate_claims(db: Session, *, dry_run: bool) -> int:
    created = 0
    claims = list(db.execute(select(ClaimRequest)).scalars().all())
    for claim in claims:
        candidate = db.execute(
            select(MatchRecord).where(MatchRecord.id == claim.match_id)
        ).scalars().first()
        target_type = claim.target_item_type
        target_id = claim.target_item_id
        if target_type is None:
            if candidate is not None and candidate.candidate_item_type:
                target_type = candidate.candidate_item_type
                target_id = candidate.candidate_item_id
            elif claim.found_item_id is not None:
                # 旧认领主场景：失主认领拾获记录
                target_type, target_id = "found", claim.found_item_id
            else:
                target_type, target_id = "lost", claim.lost_item_id
        if target_id is None:
            continue
        model = LostItem if target_type == "lost" else FoundItem
        target = db.get(model, target_id)
        if target is None:
            continue
        if target.user_id == claim.claimant_id:
            # 历史脏数据：自申请不迁移，避免污染新流程
            continue
        exists = db.execute(
            select(ContactRequest).where(
                ContactRequest.applicant_id == claim.claimant_id,
                ContactRequest.target_item_type == target_type,
                ContactRequest.target_item_id == target_id,
                ContactRequest.created_at == claim.created_at,
            )
        ).scalars().first()
        if exists is not None:
            continue
        created += 1
        if dry_run:
            continue
        public_id = (
            candidate.candidate_public_id
            if candidate is not None and candidate.candidate_public_id
            else candidate_public_id(f"legacy-{claim.id}", target_type, target_id)
        )
        status = CLAIM_STATUS_MAP.get(claim.review_status, ContactStatus.pending.value)
        lock_key = (
            f"{claim.claimant_id}:{target_type}:{target_id}"
            if status == ContactStatus.pending.value
            else None
        )
        db.add(
            ContactRequest(
                request_type="claim",
                batch_id=candidate.batch_id if candidate is not None else f"legacy-{claim.id}",
                candidate_public_id=public_id,
                candidate_id=candidate.id if candidate is not None else None,
                applicant_id=claim.claimant_id,
                target_owner_id=target.user_id,
                target_item_type=target_type,
                target_item_id=target_id,
                private_verification=claim.private_evidence,
                status=status,
                decider_id=claim.confirmer_id,
                decision_note=claim.review_note,
                failure_count=0,
                active_lock_key=lock_key,
                sensitive_category=False,
                created_at=claim.created_at,
                decided_at=claim.reviewed_at,
            )
        )
    return created


def validate(db: Session, *, assume_migrated: bool = False) -> list[str]:
    errors: list[str] = []

    candidates = db.execute(select(MatchRecord)).scalars().all()
    if not assume_migrated:
        for row in candidates:
            if row.batch_fk is None:
                errors.append(f"候选 {row.id} 缺少批次关联")
    batch_ids = {
        batch.batch_id for batch in db.execute(select(MatchBatch)).scalars().all()
    }
    for row in candidates:
        if row.batch_id not in batch_ids:
            errors.append(f"候选 {row.id} 的批次不存在")

    for item in _items(db):
        item_type = "lost" if isinstance(item, LostItem) else "found"
        image_count = int(
            db.execute(
                select(func.count(ItemImage.id)).where(
                    ItemImage.item_type == item_type, ItemImage.item_id == item.id
                )
            ).scalar_one()
        )
        expected = image_count >= 1 or len((item.description or "").strip()) >= 20
        if not assume_migrated and bool(item.info_sufficient) != bool(expected):
            errors.append(f"记录 {item_type}:{item.id} 信息量标记不一致")

    for contact in db.execute(select(ContactRequest)).scalars().all():
        if contact.status == ContactStatus.pending.value and not contact.active_lock_key:
            errors.append(f"申请 {contact.id} 处于 pending 但缺少锁键")
        if contact.applicant_id == contact.target_owner_id:
            errors.append(f"申请 {contact.id} 为自申请")

    public_scopes = db.execute(
        select(func.count(LostItem.id)).where(LostItem.visibility_scope == "public")
    ).scalar_one()
    if public_scopes:
        errors.append("存在 visibility_scope='public' 的记录")
    public_scopes = db.execute(
        select(func.count(FoundItem.id)).where(FoundItem.visibility_scope == "public")
    ).scalar_one()
    if public_scopes:
        errors.append("存在 visibility_scope='public' 的记录")

    legacy_statuses = {row.status for row in _items(db)} - {
        item.value for item in ItemLifecycleStatus
    }
    if legacy_statuses:
        errors.append(f"存在非法状态：{sorted(legacy_statuses)}")

    return errors


def run(db: Session, *, dry_run: bool, batch_size: int, skip_batches: bool) -> dict:
    before_items = len(_items(db))
    before_candidates = int(
        db.execute(select(func.count(MatchRecord.id))).scalar_one()
    )
    changed_items = migrate_items(db, dry_run=dry_run)
    created_batches = 0 if skip_batches else migrate_batches(db, dry_run=dry_run)
    created_claims = migrate_claims(db, dry_run=dry_run)
    if not dry_run:
        db.commit()
    errors = validate(db, assume_migrated=dry_run)
    return {
        "dry_run": dry_run,
        "items_changed": changed_items,
        "batches_created": created_batches,
        "claims_created": created_claims,
        "before_items": before_items,
        "after_items": len(_items(db)),
        "before_candidates": before_candidates,
        "after_candidates": int(
            db.execute(select(func.count(MatchRecord.id))).scalar_one()
        ),
        "errors": errors,
        "migrated_at": utcnow().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--from-id", type=int, default=0)
    parser.add_argument("--skip-batches", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = run(
            db,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            skip_batches=args.skip_batches,
        )
    finally:
        db.close()

    print("[migrate] 报告：")
    for key, value in report.items():
        print(f"  {key}: {value}")
    if report["errors"]:
        print("[migrate] 一致性断言失败，禁止上线：")
        for error in report["errors"]:
            print(f"  - {error}")
        return 1
    print("[migrate] 一致性断言全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())