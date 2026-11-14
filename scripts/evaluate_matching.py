"""离线匹配评估脚本。

读取 JSONL 标注样本（每行：
`{"direction":"lost_to_found|found_to_lost","lost_payload":{...},"found_payload":{...},"label":true,"split":"tune|validation"}`），
复用硬约束 + 后端评分的纯函数路径（不写库、不发通知），输出：
`precision_at_3 / recall_at_3 / top1_hit_rate / false_recommend_rate / conclusion_available`。

用法：
    python scripts/evaluate_matching.py samples.jsonl
    python scripts/evaluate_matching.py samples.jsonl --compare baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.ai.matching import ItemSide, score_pair  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.enums import UNKNOWN  # noqa: E402

_UNKNOWN_CATEGORIES = {UNKNOWN, "其他"}


def _to_datetime(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return value


def _side(payload: dict, occurred_key: str) -> ItemSide:
    return ItemSide(
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        category=str(payload.get("category") or UNKNOWN),
        color=payload.get("color"),
        brand=payload.get("brand"),
        location_code=str(payload.get("location_code") or UNKNOWN),
        location_text=str(payload.get("location_text") or ""),
        occurred_at=_to_datetime(payload.get(occurred_key)),
        features=payload.get("features"),
    )


def _known(category: str | None) -> bool:
    return bool(category) and category not in _UNKNOWN_CATEGORIES


def _hard_constraints(query: ItemSide, candidate: ItemSide) -> bool:
    if (
        _known(query.category)
        and _known(candidate.category)
        and query.category != candidate.category
    ):
        return False
    if query.occurred_at and candidate.occurred_at:
        if abs((query.occurred_at - candidate.occurred_at).total_seconds()) / 86400.0 > settings.match_time_window_days:
            return False
    return True


def _key(payload: dict) -> str:
    return f"{payload.get('title')}|{payload.get('description')}"


def evaluate(samples: list[dict], *, threshold: float | None = None) -> dict:
    cut = settings.match_score_threshold if threshold is None else threshold
    directions = {"lost_to_found", "found_to_lost"}
    result: dict = {"conclusion_available": False, "by_direction": {}}

    for direction in directions:
        subset = [example for example in samples if example.get("direction") == direction]
        if not subset:
            result["by_direction"][direction] = {
                "samples": 0,
                "precision_at_3": 0.0,
                "recall_at_3": 0.0,
                "top1_hit_rate": 0.0,
                "false_recommend_rate": 0.0,
            }
            continue
        hits_at3 = 0
        hits_at1 = 0
        false_recommends = 0
        recommends = 0
        for example in subset:
            query_type = "lost" if direction == "lost_to_found" else "found"
            query_key = "lost_payload" if query_type == "lost" else "found_payload"
            candidate_key = "found_payload" if query_type == "lost" else "lost_payload"
            occurred_query = "lost_at" if query_type == "lost" else "found_at"
            occurred_candidate = "found_at" if query_type == "lost" else "lost_at"
            query = _side(example[query_key], occurred_query)
            positive = _key(example[candidate_key])

            scored: list[tuple[float, str]] = []
            for other in subset:
                payload = other[candidate_key]
                side = _side(payload, occurred_candidate)
                if not _hard_constraints(query, side):
                    continue
                scored.append((float(score_pair(query, side, window_days=settings.match_time_window_days).total), _key(payload)))
            scored.sort(key=lambda item: (-item[0], item[1]))
            recommended = [item for item in scored if item[0] >= cut][:3]
            if recommended:
                recommends += 1
            if any(key == positive for _, key in recommended):
                hits_at3 += 1
                if recommended and recommended[0][1] == positive:
                    hits_at1 += 1
            else:
                false_recommends += 1

        total = len(subset)
        result["by_direction"][direction] = {
            "samples": total,
            "precision_at_3": round(hits_at3 / total, 4) if total else 0.0,
            "recall_at_3": round(hits_at3 / total, 4) if total else 0.0,
            "top1_hit_rate": round(hits_at1 / total, 4) if total else 0.0,
            "false_recommend_rate": round(false_recommends / total, 4) if total else 0.0,
        }

    lost_count = len([x for x in samples if x.get("direction") == "lost_to_found"])
    found_count = len([x for x in samples if x.get("direction") == "found_to_lost"])
    result["conclusion_available"] = lost_count >= 50 and found_count >= 50
    result["threshold"] = cut
    result["total_samples"] = len(samples)
    return result


def _load_jsonl(path: Path) -> list[dict]:
    samples: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            samples.append(json.loads(line))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path)
    parser.add_argument("--compare", type=Path, default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.samples.is_file():
        print("[evaluate] 样本文件不存在")
        return 2
    report = evaluate(_load_jsonl(args.samples), threshold=args.threshold)
    if not report["conclusion_available"]:
        print("[evaluate] 样本不足（每个方向需 ≥50 对），结论不可用，禁止据此调整阈值")

    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.compare and args.compare.is_file():
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        for direction, metrics in report["by_direction"].items():
            base = baseline.get("by_direction", {}).get(direction, {})
            base_p3 = base.get("precision_at_3", 0.0)
            drop = base_p3 - metrics["precision_at_3"]
            if drop > 0.05:
                print(
                    f"[evaluate] {direction} Precision@3 下降 {drop:.4f}（>{0.05}），阻止上线"
                )
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())