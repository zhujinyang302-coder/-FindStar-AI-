"""候选披露抽检脚本。

随机抽取 ≥20 条候选，校验：白名单字段、水印缩略图存在、时间/地点模糊化。
输出可归档的抽检记录。不修改业务数据。

用法：
    python scripts/audit_disclosure_sample.py --sample-size 20 --out audit_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import select  # noqa: E402

from app.core.timeutil import utcnow  # noqa: E402
from app.db.models import MatchRecord  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import disclosure_policy, disclosure_service  # noqa: E402
from app.services.item_service import _model  # noqa: E402


def _check_candidate(db, record: MatchRecord) -> dict:
    issues: list[str] = []
    item_type = record.candidate_item_type
    item_id = record.candidate_item_id
    item = db.get(_model(item_type), item_id) if item_type and item_id else None
    if item is None:
        return {"candidate_id": record.id, "issues": ["候选记录不存在"], "passed": False}

    summary = disclosure_service.build_summary(db, record, item, item_type).model_dump()
    forbidden = set(summary) & disclosure_policy.FORBIDDEN_FIELDS
    if forbidden:
        issues.append(f"出现禁披露字段：{sorted(forbidden)}")
    if set(summary) - disclosure_policy.SUMMARY_FIELDS:
        issues.append("出现白名单外字段")

    if summary.get("occurred_on") and "T" in str(summary["occurred_on"]):
        issues.append("时间未模糊到日")
    if not summary.get("area_name"):
        issues.append("地点区域缺失")

    images = getattr(item, "images", []) or []
    if images and not images[0].thumb_key:
        issues.append("缺少水印缩略图")
    if summary.get("thumb_url") and "thumb_" not in summary["thumb_url"]:
        issues.append("候选返回了非缩略图地址")

    return {
        "candidate_id": record.id,
        "candidate_public_id": record.candidate_public_id,
        "batch_id": record.batch_id,
        "has_thumb": bool(images and images[0].thumb_key),
        "fields": sorted(summary),
        "issues": issues,
        "passed": not issues,
    }


def audit(db, *, sample_size: int = 20) -> dict:
    records = list(db.execute(select(MatchRecord)).scalars().all())
    sample = random.sample(records, min(sample_size, len(records))) if records else []
    checks = [_check_candidate(db, record) for record in sample]
    passed = len([item for item in checks if item["passed"]])
    return {
        "generated_at": utcnow().isoformat(),
        "requested_size": sample_size,
        "actual_size": len(sample),
        "passed": passed,
        "failed": len(checks) - passed,
        "items": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = audit(db, sample_size=max(20, args.sample_size))
    finally:
        db.close()

    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[audit] 抽检报告已写入 {args.out}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())