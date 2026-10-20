"""Extraction service: raw text in, deduplicated posting out.

The transaction boundary is per-posting on purpose. One malformed JD should not roll
back an entire import batch; it should be reported and skipped.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .llm import Provider, ProviderError
from .models import JobPosting, JobSkill, Skill
from .normalize import canonical
from .schemas import RawPosting


def content_hash(raw_text: str, company: str | None, title: str | None) -> str:
    normalized = re.sub(r"\s+", " ", raw_text).strip().lower()
    payload = f"{company or ''}|{title or ''}|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class IngestResult:
    inserted: int = 0
    skipped: int = 0
    failed: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"inserted": self.inserted, "skipped": self.skipped, "failed": self.failed}


def _get_or_create_skill(session: Session, name: str) -> Skill:
    skill = session.scalar(select(Skill).where(Skill.name == name))
    if skill is None:
        skill = Skill(name=name)
        session.add(skill)
        session.flush()  # assign id without ending the transaction
    return skill


def ingest_one(session: Session, posting: RawPosting, provider: Provider) -> str:
    """Persist one posting. Returns "inserted" or "skipped"; raises ProviderError."""
    h = content_hash(posting.raw_text, posting.company, posting.title)
    exists = session.scalar(select(JobPosting.id).where(JobPosting.content_hash == h))
    if exists:
        return "skipped"

    extraction = provider.extract(
        posting.raw_text, company=posting.company, title=posting.title
    )

    job = JobPosting(
        content_hash=h,
        title=posting.title or extraction.title,
        company=posting.company or extraction.company,
        city=extraction.city,
        salary_min_k=extraction.salary_min_k,
        salary_max_k=extraction.salary_max_k,
        years_min=extraction.years_min,
        education=extraction.education,
        source=posting.source,
        url=posting.url,
        raw_text=posting.raw_text,
    )
    session.add(job)
    session.flush()

    # Dedupe skills within one posting after canonicalization: "K8s" and "Kubernetes"
    # must not produce two rows for the same job.
    merged: dict[str, bool] = {}
    for mention in extraction.skills:
        name = canonical(mention.name)
        if not name:
            continue
        merged[name] = merged.get(name, False) or mention.required

    for name, required in merged.items():
        job.skills.append(JobSkill(skill=_get_or_create_skill(session, name), required=required))

    return "inserted"


def ingest_many(
    session_factory: sessionmaker[Session],
    postings: list[RawPosting],
    provider: Provider,
) -> IngestResult:
    result = IngestResult()
    for idx, posting in enumerate(postings):
        session = session_factory()
        try:
            outcome = ingest_one(session, posting, provider)
            session.commit()
            if outcome == "inserted":
                result.inserted += 1
            else:
                result.skipped += 1
        except ProviderError as exc:
            session.rollback()
            result.failed.append({"index": idx, "error": str(exc)})
        except Exception as exc:  # defensive: never let one row kill the batch
            session.rollback()
            result.failed.append({"index": idx, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            session.close()
    return result
