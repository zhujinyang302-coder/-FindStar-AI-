"""AI 能力包。

- provider：AIProvider 抽象与实现（OpenAI 兼容 + 本地降级）。
- matching：后端评分算法（候选排序的唯一依据）。
- text_similarity：文本语义相似度（embedding 优先，规则降级）。
"""

from app.ai.matching import score_pair
from app.ai.text_similarity import text_similarity

__all__ = ["score_pair", "text_similarity"]