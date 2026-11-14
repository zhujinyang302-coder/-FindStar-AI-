"""语义召回（匹配第 2 层）。

向量通道优先；无向量能力或 embedding 失败时回退关键词/字符相似度，
并标记 recall_channel="keyword"、degraded=True。模型排序建议不采用自报分数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.ai.provider import AIUnavailableError, AIProvider
from app.ai.text_similarity import rule_based_similarity
from app.core.config import settings


@dataclass
class SemanticResult:
    candidates: list[tuple[str, Any]] = field(default_factory=list)
    channel: str = "keyword"
    degraded: bool = False


def combined_text(item: Any) -> str:
    parts = [item.title or "", item.description or ""]
    features = item.features or {}
    description = features.get("description") if isinstance(features, dict) else None
    if isinstance(description, str):
        parts.append(description)
    visible = features.get("visible_features") if isinstance(features, dict) else None
    if isinstance(visible, list):
        parts.extend(str(x) for x in visible)
    return " ".join(part for part in parts if part)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def semantic_recall(
    *,
    initiated_item: Any,
    pool: list[tuple[str, Any]],
    top_k: int,
    provider: AIProvider | None = None,
) -> SemanticResult:
    if not pool:
        return SemanticResult(candidates=[], channel="keyword", degraded=False)

    query = combined_text(initiated_item)
    candidate_texts = [combined_text(item) for _, item in pool]

    if provider is not None and settings.ai_is_live and settings.ai_embedding_model:
        try:
            vectors = provider.embed_text([query, *candidate_texts])
            if len(vectors) == len(candidate_texts) + 1:
                scored = [
                    (cosine(vectors[0], vectors[index + 1]), pair)
                    for index, pair in enumerate(pool)
                ]
                scored.sort(key=lambda item: (-item[0], item[1][1].id))
                return SemanticResult(
                    candidates=[pair for _, pair in scored[:top_k]],
                    channel="vector",
                    degraded=False,
                )
        except AIUnavailableError:
            pass

    scored = [
        (rule_based_similarity(query, text), pair)
        for text, pair in zip(candidate_texts, pool)
    ]
    scored.sort(key=lambda item: (-item[0], item[1][1].id))
    return SemanticResult(
        candidates=[pair for _, pair in scored[:top_k]],
        channel="keyword",
        degraded=True,
    )