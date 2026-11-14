"""文本语义相似度。

优先使用可用的文本 embedding 余弦相似度（由 provider 提供）；
资源有限时退化为字符/词元组合相似度，保证评分可重复且不依赖外部服务。
"""

from __future__ import annotations

import math
import re
from collections import Counter

_CJK = re.compile(r"[\u4e00-\u9fff]")
_TOKEN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")

_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "与", "个", "一", "把", "被",
    "很", "可能", "好像", "大概", "然后", "一个", "东西", "物品",
}


def _char_bigrams(text: str) -> Counter[str]:
    chars = [c for c in text if _CJK.match(c)]
    bigrams: list[str] = []
    for i in range(len(chars) - 1):
        bigrams.append(chars[i] + chars[i + 1])
    if not bigrams and chars:
        bigrams = chars
    return Counter(bigrams)


def _tokens(text: str) -> Counter[str]:
    return Counter(
        token
        for token in _TOKEN.findall(text)
        if token not in _STOPWORDS and not (token.isdigit() and len(token) < 2)
    )


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rule_based_similarity(a: str, b: str) -> float:
    """字符 bigram 与词元余弦的加权组合，输出 0–1。"""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return 0.5  # 信息不足时返回中性分，而非判定不匹配
    char_score = _cosine(_char_bigrams(a), _char_bigrams(b))
    token_score = _cosine(_tokens(a), _tokens(b))
    score = 0.6 * char_score + 0.4 * token_score
    if score < 0.05 and set(a) & set(b):
        score = 0.15  # 至少共享字符时给最低限度的正分
    return max(0.0, min(1.0, score))


def text_similarity(a: str, b: str, embeddings: tuple[list[float], list[float]] | None = None) -> float:
    """若提供 embedding 向量则使用余弦相似度，否则回退规则相似度。"""
    if embeddings is not None:
        vec_a, vec_b = embeddings
        score = _cosine_vector(vec_a, vec_b)
        if score > 0:
            return max(0.0, min(1.0, score))
    return rule_based_similarity(a, b)


def _cosine_vector(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)