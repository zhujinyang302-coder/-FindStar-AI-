"""后端匹配评分算法。

综合分数（基线权重）：
    S = 0.35·S_text + 0.25·S_image + 0.20·S_location + 0.15·S_time + 0.05·S_attribute

规则：
- 各分项归一化到 0–1，最终分数显示为 0–100。
- 无可靠图像向量时，视觉项替换为结构化视觉特征一致性并标记为不可用（available=False），
  随后重新归一化权重。
- 地点未知返回中性分；时间未知返回中性分；品牌未知不扣分。
- 类别明确冲突触发惩罚。
- 分数只由本算法计算，不采用模型自报分数。评分可重复。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.ai.text_similarity import text_similarity
from app.db.enums import UNKNOWN

BASE_WEIGHTS: dict[str, float] = {
    "text": 0.35,
    "image": 0.25,
    "location": 0.20,
    "time": 0.15,
    "attribute": 0.05,
}

# 校园地点层级/邻近关系（前缀越相似视为越接近）
_NEUTRAL = 0.5


@dataclass
class ItemSide:
    """参与评分的单侧记录快照。"""

    title: str
    description: str
    category: str
    color: str | None
    brand: str | None
    location_code: str
    location_text: str
    occurred_at: datetime | None
    features: dict | None = None
    text_embedding: list[float] | None = None
    image_similarity: float | None = None

    def combined_text(self) -> str:
        parts = [self.title, self.description]
        if self.features:
            desc = self.features.get("description")
            if isinstance(desc, str):
                parts.append(desc)
            vf = self.features.get("visible_features")
            if isinstance(vf, list):
                parts.extend(str(x) for x in vf)
        return " ".join(p for p in parts if p)


@dataclass
class ScoreResult:
    total: float
    breakdown: dict[str, dict]
    reasons: list[str] = field(default_factory=list)
    differences: list[dict] = field(default_factory=list)
    category_conflict: bool = False


def _is_known(value: str | None) -> bool:
    return bool(value) and value != UNKNOWN


def score_text(a: ItemSide, b: ItemSide) -> tuple[float, bool, str | None]:
    embeddings = None
    if a.text_embedding and b.text_embedding:
        embeddings = (a.text_embedding, b.text_embedding)
    score = text_similarity(a.combined_text(), b.combined_text(), embeddings)
    note = None if embeddings else "未启用文本向量，使用规则相似度"
    return score, True, note


def score_image(a: ItemSide, b: ItemSide) -> tuple[float, bool, str | None]:
    """视觉项：优先使用图像向量相似度；否则使用结构化视觉特征一致性。"""
    if a.image_similarity is not None and b.image_similarity is not None:
        # 由服务层在具备向量能力时计算好的相似度（此处直接使用 a 侧携带的结果）
        return a.image_similarity, True, None
    score = _visual_feature_consistency(a, b)
    return score, False, "未提供图像向量，视觉项降级为结构化视觉特征一致性"


def _visual_feature_consistency(a: ItemSide, b: ItemSide) -> float:
    signals: list[float] = []
    if _is_known(a.category) and _is_known(b.category):
        signals.append(1.0 if a.category == b.category else 0.0)
    if _is_known(a.color) and _is_known(b.color):
        signals.append(1.0 if _same_text(a.color, b.color) else 0.0)
    if _is_known(a.brand) and _is_known(b.brand):
        signals.append(1.0 if _same_text(a.brand, b.brand) else 0.0)
    feat_a = set(a.features.get("visible_features", [])) if a.features else set()
    feat_b = set(b.features.get("visible_features", [])) if b.features else set()
    if feat_a and feat_b:
        overlap = len(feat_a & feat_b) / max(1, min(len(feat_a), len(feat_b)))
        signals.append(overlap)
    if not signals:
        return _NEUTRAL
    return sum(signals) / len(signals)


def _same_text(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def score_location(a: ItemSide, b: ItemSide) -> tuple[float, bool, str | None]:
    code_a, code_b = (a.location_code or "").strip(), (b.location_code or "").strip()
    if not _is_known(code_a) or not _is_known(code_b):
        return _NEUTRAL, True, "地点未知，使用中性分"
    if code_a == code_b:
        return 1.0, True, None
    if code_a in code_b or code_b in code_a:
        return 0.8, True, None
    common = _common_prefix_ratio(code_a, code_b)
    if common >= 0.5:
        return 0.6, True, None
    # 文本层面存在共同地点关键词
    if _share_keyword(code_a, code_b):
        return 0.5, True, None
    return 0.2, True, None


def _common_prefix_ratio(a: str, b: str) -> float:
    prefix = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        prefix += 1
    return prefix / max(len(a), len(b))


def _share_keyword(a: str, b: str) -> bool:
    keywords = ["教学楼", "图书馆", "食堂", "宿舍", "操场", "体育馆", "校门", "实验室", "办公室"]
    for kw in keywords:
        if kw in a and kw in b:
            return True
    return False


def score_time(
    a: ItemSide, b: ItemSide, *, window_days: int = 30
) -> tuple[float, bool, str | None]:
    if a.occurred_at is None or b.occurred_at is None:
        return _NEUTRAL, True, "时间未知，使用中性分"
    diff_days = abs((a.occurred_at - b.occurred_at).total_seconds()) / 86400.0
    if diff_days <= 3:
        score = 1.0
    elif diff_days <= 7:
        score = 0.85
    elif diff_days <= 15:
        score = 0.6
    elif diff_days <= window_days:
        score = 0.35
    else:
        score = 0.1
    return score, True, None


def score_attribute(a: ItemSide, b: ItemSide) -> tuple[float, bool, str | None, bool]:
    """返回 (分数, 可用, 说明, 类别是否冲突)。"""
    conflict = _is_known(a.category) and _is_known(b.category) and a.category != b.category

    components: list[float] = []
    weights: list[float] = []

    if _is_known(a.category) and _is_known(b.category):
        components.append(1.0 if a.category == b.category else 0.0)
        weights.append(0.5)

    if _is_known(a.color) and _is_known(b.color):
        components.append(1.0 if _same_text(a.color, b.color) else 0.0)
        weights.append(0.3)
    elif _is_known(a.color) or _is_known(b.color):
        weights.append(0.0)  # 一方未知不扣分也不加分

    if _is_known(a.brand) and _is_known(b.brand):
        components.append(1.0 if _same_text(a.brand, b.brand) else 0.0)
        weights.append(0.2)
    # 品牌未知时不参与，天然不扣分

    if not weights or sum(weights) == 0:
        return _NEUTRAL, True, "结构化属性不足，使用中性分", conflict

    score = sum(c * w for c, w in zip(components, weights)) / sum(weights)
    note = "类别明确冲突" if conflict else None
    return score, True, note, conflict


def _weighted_total(parts: dict[str, tuple[float, bool]]) -> tuple[float, dict[str, float]]:
    """按可用性重新归一化权重后加权求和，返回 (总分0–1, 有效权重)。"""
    effective = {k: BASE_WEIGHTS[k] for k, (_, available) in parts.items() if available}
    if not effective:
        return 0.0, {}
    total_weight = sum(effective.values())
    total = sum(parts[k][0] * w for k, w in effective.items()) / total_weight
    return total, effective


def score_pair(
    a: ItemSide,
    b: ItemSide,
    *,
    window_days: int = 30,
) -> ScoreResult:
    """计算两个记录侧之间的综合分数（0–100）与分项明细。"""
    text_score, text_avail, text_note = score_text(a, b)
    image_score, image_avail, image_note = score_image(a, b)
    loc_score, loc_avail, loc_note = score_location(a, b)
    time_score, time_avail, time_note = score_time(a, b, window_days=window_days)
    attr_score, attr_avail, attr_note, category_conflict = score_attribute(a, b)

    parts_raw = {
        "text": (text_score, text_avail),
        "image": (image_score, image_avail),
        "location": (loc_score, loc_avail),
        "time": (time_score, time_avail),
        "attribute": (attr_score, attr_avail),
    }
    total_01, effective = _weighted_total(parts_raw)

    notes = {
        "text": text_note,
        "image": image_note,
        "location": loc_note,
        "time": time_note,
        "attribute": attr_note,
    }
    raw_scores = {
        "text": text_score,
        "image": image_score,
        "location": loc_score,
        "time": time_score,
        "attribute": attr_score,
    }
    available = {
        "text": text_avail,
        "image": image_avail,
        "location": loc_avail,
        "time": time_avail,
        "attribute": attr_avail,
    }
    total_weight = sum(effective.values()) or 1.0

    breakdown: dict[str, dict] = {}
    for key in BASE_WEIGHTS:
        breakdown[key] = {
            "score": round(raw_scores[key], 4),
            "weight": round(effective.get(key, 0.0) / total_weight, 4),
            "available": available[key],
            "note": notes[key],
        }

    # 类别明确冲突：显著降分（不因地点相近进入高排名）
    if category_conflict:
        total_01 *= 0.5

    result = ScoreResult(
        total=round(total_01 * 100, 2),
        breakdown=breakdown,
        category_conflict=category_conflict,
    )
    result.reasons, result.differences = _build_reasons(a, b, raw_scores, notes, category_conflict)
    return result


def _build_reasons(
    a: ItemSide,
    b: ItemSide,
    raw: dict[str, float],
    notes: dict[str, str | None],
    conflict: bool,
) -> tuple[list[str], list[dict]]:
    reasons: list[str] = []
    differences: list[dict] = []

    if _is_known(a.category) and a.category == b.category:
        reasons.append(f"类别一致：{a.category}")
    if _is_known(a.color) and b.color and _same_text(a.color, b.color):
        reasons.append(f"颜色一致：{a.color}")
    if _is_known(a.brand) and b.brand and _same_text(a.brand, b.brand):
        reasons.append(f"品牌一致：{a.brand}")
    if raw["location"] >= 0.8:
        reasons.append(f"地点相近：{a.location_text} / {b.location_text}")
    if raw["time"] >= 0.85 and a.occurred_at and b.occurred_at:
        reasons.append("时间接近")
    if raw["text"] >= 0.4:
        reasons.append("文本描述语义相近")
    if notes["image"]:
        reasons.append("视觉依据为结构化特征一致性（图像向量不可用）")

    if conflict:
        differences.append(
            {"field": "category", "self_value": a.category, "candidate_value": b.category, "note": "类别冲突，已降分"}
        )
    if _is_known(a.color) and _is_known(b.color) and not _same_text(a.color, b.color):
        differences.append(
            {"field": "color", "self_value": a.color, "candidate_value": b.color, "note": "颜色不一致，需人工核验"}
        )
    if _is_known(a.brand) and _is_known(b.brand) and not _same_text(a.brand, b.brand):
        differences.append(
            {"field": "brand", "self_value": a.brand, "candidate_value": b.brand, "note": "品牌不一致，需人工核验"}
        )
    if a.occurred_at and b.occurred_at and abs((a.occurred_at - b.occurred_at).days) > 7:
        differences.append(
            {
                "field": "time",
                "self_value": a.occurred_at.isoformat(),
                "candidate_value": b.occurred_at.isoformat(),
                "note": "时间间隔较大，需人工核验",
            }
        )
    if not _is_known(a.location_code) or not _is_known(b.location_code):
        differences.append(
            {"field": "location", "self_value": a.location_text, "candidate_value": b.location_text, "note": "地点信息不足"}
        )
    return reasons, differences