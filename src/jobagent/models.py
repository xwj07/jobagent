"""ORM models: a posting is the unit of ingestion; skills are normalized and shared."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # sha256(company|title|normalized raw text). The UNIQUE constraint is what makes
    # re-running an import idempotent instead of duplicating rows.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200), default="unknown")
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salary_min_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="manual")
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    skills: Mapped[list["JobSkill"]] = relationship(
        back_populates="posting", cascade="all, delete-orphan"
    )


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Canonical lowercase form, e.g. "kubernetes" and "k8s" both land here as "kubernetes".
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    postings: Mapped[list["JobSkill"]] = relationship(back_populates="skill")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id", name="uq_job_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)

    posting: Mapped[JobPosting] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="postings", lazy="joined")
