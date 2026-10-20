"""Aggregations over stored postings.

Stage 1 deliberately pushes aggregation into Python instead of SQL window functions:
the dataset is small, and readable code beats a clever query when you are learning.
When you hit ~10^5 rows, move the counting into SQL (see the homework in docs/stage1.md).
"""

from __future__ import annotations

from collections import Counter
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import JobPosting, Skill


def skill_frequency(session: Session, *, top: int | None = None) -> list[dict]:
    """Return skills ordered by how many postings require them.

    ``share`` is the fraction of postings mentioning the skill at all, which matters
    more than the raw count once the corpus grows past a few dozen postings.
    """
    postings = session.scalars(select(JobPosting)).all()
    total = len(postings)
    counts: Counter[str] = Counter()
    required_counts: Counter[str] = Counter()
    for job in postings:
        for job_skill in job.skills:
            name = job_skill.skill.name
            counts[name] += 1
            if job_skill.required:
                required_counts[name] += 1

    rows = [
        {
            "skill": name,
            "postings": count,
            "required": required_counts[name],
            "share": round(count / total, 4) if total else 0.0,
        }
        for name, count in counts.most_common()
    ]
    return rows[:top] if top else rows


def salary_summary(session: Session) -> dict:
    """Median of (min+max)/2 across postings that disclose a salary range."""
    mids: list[float] = []
    disclosed = 0
    for job in session.scalars(select(JobPosting)):
        if job.salary_min_k and job.salary_max_k:
            mids.append((job.salary_min_k + job.salary_max_k) / 2)
            disclosed += 1
    return {
        "postings_with_salary": disclosed,
        "median_monthly_k": round(median(mids), 1) if mids else None,
    }


def corpus_summary(session: Session) -> dict:
    total_jobs = session.query(JobPosting).count()
    total_skills = session.query(Skill).count()
    return {
        "postings": total_jobs,
        "distinct_skills": total_skills,
        **salary_summary(session),
    }
