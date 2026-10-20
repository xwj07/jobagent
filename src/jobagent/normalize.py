"""Skill-name canonicalization.

This is intentionally a small alias dictionary, not a semantic matcher.
Stage 1 wants deterministic, explainable merges; embedding-based clustering of
near-duplicate skill names comes in stage 2 once we have real data to tune it.
"""

from __future__ import annotations

ALIASES: dict[str, str] = {
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "pg": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "golang": "go",
    "spring-boot": "spring boot",
    "springcloud": "spring cloud",
    "es": "elasticsearch",
    "消息队列": "message queue",
    "大模型": "大语言模型",
    "llm": "大语言模型",
    "large language model": "大语言模型",
    "检索增强生成": "rag",
    "retrieval augmented generation": "rag",
    "vector database": "向量数据库",
    "prompt engineering": "提示词工程",
    "machine learning": "机器学习",
    "deep learning": "深度学习",
    "natural language processing": "nlp",
    "microservices": "微服务",
}


def canonical(name: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation, then apply aliases.

    Chinese names pass through unchanged except for stripping; `.lower()` is a no-op there.
    """
    s = " ".join(name.strip().lower().split())
    s = s.rstrip(".;,，。；")
    return ALIASES.get(s, s)
