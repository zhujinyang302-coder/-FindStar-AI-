from __future__ import annotations

import importlib.util
from pathlib import Path

from app.db.enums import ItemLifecycleStatus
from app.db.models import ClaimRequest, FoundItem, LostItem, MatchRecord
from app.db.models import MatchBatch
from app.services.disclosure_service import candidate_public_id


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "migrate_bidirectional_match.py"
    spec = importlib.util.spec_from_file_location("migrate_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed_legacy(db, user, other_user):
    lost = LostItem(
        user_id=user.id,
        title="旧寻物记录",
        description="一条足够长的旧寻物记录描述，用于验证信息量迁移判断逻辑",
        category="钱包箱包",
        location_code="LIB",
        location_text="图书馆",
        status=ItemLifecycleStatus.active.value,
        is_removed=False,
    )
    found = FoundItem(
        user_id=other_user.id,
        title="旧拾获记录",
        description="一条足够长的旧拾获记录描述，用于验证信息量迁移判断逻辑",
        category="钱包箱包",
        location_code="LIB",
        location_text="图书馆",
        status=ItemLifecycleStatus.active.value,
        is_removed=False,
    )
    db.add_all([lost, found])
    db.commit()
    db.refresh(lost)
    db.refresh(found)

    batch_id = "legacy-batch-0001"
    record = MatchRecord(
        batch_id=batch_id,
        initiated_item_type="lost",
        lost_item_id=lost.id,
        found_item_id=found.id,
        score=80,
        score_breakdown={},
        reason_json={"reasons": ["旧数据"], "differences": []},
        algorithm_version="v1.0.0",
        status="proposed",
        initiated_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    claim = ClaimRequest(
        match_id=record.id,
        lost_item_id=lost.id,
        found_item_id=found.id,
        claimant_id=user.id,
        private_evidence="旧认领的私密核验信息",
        review_status="pending",
        active_lock_key=None,
    )
    db.add(claim)
    db.commit()
    return lost, found, record, claim


def test_migration_maps_legacy_rows(db_session, user, other_user):
    module = _load_script()
    lost, found, record, claim = _seed_legacy(db_session, user, other_user)

    report = module.run(
        db_session, dry_run=False, batch_size=200, skip_batches=False
    )
    assert report["errors"] == [], report["errors"]
    assert report["batches_created"] == 1
    assert report["claims_created"] == 1

    batch = db_session.query(MatchBatch).filter_by(batch_id="legacy-batch-0001").one()
    db_session.refresh(record)
    assert record.batch_fk == batch.id
    assert record.candidate_item_type == "found"
    assert record.candidate_item_id == found.id
    assert record.candidate_public_id
    assert record.candidate_public_id.startswith("c_")

    contact = db_session.query(
        __import__("app.db.models", fromlist=["ContactRequest"]).ContactRequest
    ).one()
    assert contact.applicant_id == user.id
    assert contact.target_owner_id == other_user.id
    assert contact.status == "pending"
    assert contact.active_lock_key


def test_migration_is_idempotent(db_session, user, other_user):
    module = _load_script()
    _seed_legacy(db_session, user, other_user)
    module.run(db_session, dry_run=False, batch_size=200, skip_batches=False)
    second = module.run(db_session, dry_run=False, batch_size=200, skip_batches=False)
    assert second["batches_created"] == 0
    assert second["claims_created"] == 0
    assert db_session.query(MatchBatch).count() == 1


def test_dry_run_writes_nothing(db_session, user, other_user):
    module = _load_script()
    _seed_legacy(db_session, user, other_user)
    report = module.run(db_session, dry_run=True, batch_size=200, skip_batches=False)
    assert report["batches_created"] == 1
    assert db_session.query(MatchBatch).count() == 0


def test_validation_detects_dirty_data(db_session, user, other_user):
    module = _load_script()
    _seed_legacy(db_session, user, other_user)
    module.run(db_session, dry_run=False, batch_size=200, skip_batches=False)
    lost = db_session.query(LostItem).first()
    lost.visibility_scope = "public"
    db_session.commit()
    errors = module.validate(db_session)
    assert any("visibility_scope" in error for error in errors)