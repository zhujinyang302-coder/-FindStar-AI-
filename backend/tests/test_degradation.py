from __future__ import annotations

from app.ai.provider import AIProvider, AIUnavailableError
from app.db.enums import BatchStatus
from app.db.models import MatchBatch
from app.schemas.ai import ItemFeatures
from app.services import match_orchestrator, semantic_service
from tests.conftest import service_approve, service_create_item

LOST_PAYLOAD = {
    "title": "黑色双肩包",
    "description": "图书馆三楼自习区丢失黑色双肩包，包内有蓝色水杯和一本线性代数教材",
    "category": "钱包箱包",
    "color": "黑色",
    "location_code": "LIB-3F",
    "location_text": "图书馆三楼自习区",
}


class _BrokenProvider(AIProvider):
    name = "broken"

    def extract_features(self, *, description, image_paths) -> ItemFeatures:
        raise AIUnavailableError("broken")

    def explain_match(self, *, context: dict) -> dict:
        raise AIUnavailableError("broken")

    def embed_text(self, texts: list[str]) -> list[list[float]]:
        raise AIUnavailableError("embedding timeout")


def test_keyword_fallback_marks_degraded(db_session):
    result = semantic_service.semantic_recall(
        initiated_item=service_create_item(db_session, _user(db_session), item_type="lost")[0],
        pool=[],
        top_k=10,
        provider=_BrokenProvider(),
    )
    assert result.channel == "keyword"
    assert result.candidates == []


def test_batch_degrades_without_real_ai(db_session, user, other_user, admin):
    found, found_ticket = service_create_item(db_session, other_user, item_type="found")
    service_approve(db_session, admin, found_ticket)
    lost, lost_ticket = service_create_item(
        db_session, user, payload=LOST_PAYLOAD, item_type="lost"
    )
    service_approve(db_session, admin, lost_ticket)
    match_orchestrator.process_processing_batches(db_session)
    batch = (
        db_session.query(MatchBatch)
        .filter(MatchBatch.initiated_item_type == "lost")
        .first()
    )
    assert batch.degraded is True
    assert batch.status in {
        BatchStatus.completed.value,
        BatchStatus.degraded_completed.value,
    }
    assert batch.recall_channel == "keyword"


def _user(db):
    from app.db.enums import UserRole
    from tests.conftest import make_user

    return make_user(db, email="degraded@test.demo", role=UserRole.user.value)