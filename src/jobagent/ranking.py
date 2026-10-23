"""Explainable skill-keyword coverage for ordering a large collected job list."""

import re

from .match_schemas import RankedJob, RankRequest
from .normalize import ALIASES, canonical

SKILLS = {
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "c",
    "c++",
    "c#",
    ".net",
    "php",
    "rust",
    "sql",
    "mysql",
    "postgresql",
    "redis",
    "mongodb",
    "elasticsearch",
    "sqlite",
    "oracle",
    "fastapi",
    "django",
    "flask",
    "spring",
    "spring boot",
    "spring cloud",
    "react",
    "vue",
    "node.js",
    "html",
    "css",
    "linux",
    "git",
    "github",
    "docker",
    "kubernetes",
    "kafka",
    "rabbitmq",
    "spark",
    "hadoop",
    "hive",
    "flink",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "pandas",
    "numpy",
    "大语言模型",
    "rag",
    "微调",
    "embedding",
    "langchain",
    "langgraph",
    "agent",
    "向量数据库",
    "milvus",
    "pgvector",
    "机器学习",
    "深度学习",
    "nlp",
    "提示词工程",
    "微服务",
    "message queue",
    "webrtc",
    "ffmpeg",
    "asyncio",
    "kotlin",
    "swift",
    "运筹优化",
}


def mentions(text: str, term: str) -> bool:
    return (
        re.search(r"(?<![a-z0-9_+#])" + re.escape(term) + r"(?![a-z0-9_+#])", text, re.I)
        is not None
    )


def rank_jobs(request: RankRequest) -> list[RankedJob]:
    resume_skills = {canonical(skill.name) for skill in request.resume.skills}
    resume_skills.update(
        canonical(name) for project in request.resume.projects for name in project.technologies
    )
    resume_skills.discard("")
    terms = {name: name for name in SKILLS | resume_skills}
    terms.update(ALIASES)
    ranked = []
    for job in request.jobs:
        # Only the JD is scanned, excluding company and publisher metadata.
        found = {
            canonical(name)
            for term, name in terms.items()
            if mentions(job.description or job.raw_text, term)
        }
        matched = sorted(found & resume_skills)
        missing = sorted(found - resume_skills)
        ranked.append(
            RankedJob(
                job=job,
                score=round(100 * len(matched) / len(found), 1) if found else None,
                matched_skills=matched,
                missing_skills=missing,
            )
        )
    return sorted(
        ranked,
        key=lambda item: (
            -(item.score if item.score is not None else -1),
            -len(item.matched_skills),
        ),
    )
