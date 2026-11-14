from __future__ import annotations

from app.schemas.admin import ReviewTicketDetailOut
from app.schemas.item import MyItemListItem, MyItemOut
from app.schemas.match import CandidateSummaryOut, CandidateVerifiedOut
from app.services.disclosure_policy import FORBIDDEN_FIELDS

_FORBIDDEN = {
    "owner_id",
    "owner_nickname",
    "user_id",
    "phone",
    "email",
    "full_description",
    "original_url",
    "private_verification",
    "private_evidence",
    "candidate",
    "score_detail",
}


def test_candidate_summary_has_no_forbidden_fields():
    fields = set(CandidateSummaryOut.model_fields)
    assert not fields & _FORBIDDEN
    assert "candidate_public_id" in fields
    assert "thumb_url" in fields


def test_verified_candidate_has_no_forbidden_fields():
    fields = set(CandidateVerifiedOut.model_fields)
    assert not fields & _FORBIDDEN


def test_review_ticket_detail_has_no_match_fields():
    fields = set(ReviewTicketDetailOut.model_fields)
    assert not fields & {"candidate", "candidates", "score", "candidate_public_id"}
    assert not fields & {"private_verification", "private_evidence", "applicant_id"}
    assert "disclaimer" in fields


def test_my_item_has_no_counterparty_fields():
    for model in (MyItemOut, MyItemListItem):
        fields = set(model.model_fields)
        assert not fields & {"owner_nickname", "owner_id", "phone", "email"}


def test_forbidden_field_list_covers_design():
    assert "owner_id" in FORBIDDEN_FIELDS
    assert "original_url" in FORBIDDEN_FIELDS
    assert "full_description" in FORBIDDEN_FIELDS