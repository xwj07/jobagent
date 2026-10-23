"""Data contracts for collection, matching and independent human evaluation."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .job_catalog import CITIES, ROLES
from .schemas import ResumeExtraction

Source = Literal["liepin", "zhilian", "nowcoder", "manual"]
Category = Literal["skills", "projects", "experience", "education"]


class JobCandidate(BaseModel):
    title: str
    company: str
    city: str
    salary: str
    source: Source
    url: str | None
    raw_text: str = Field(min_length=10)
    education: str = ""
    experience: str = ""
    published_at: str = ""
    description: str = ""
    recruitment_type: str = ""


class CollectionRequest(BaseModel):
    role: str
    city: str
    source: Literal["liepin", "zhilian", "nowcoder", "both"] = "both"
    limit: Literal[20, 50, 100] = 50
    recruitment_type: Literal["all", "campus", "intern", "social"] = "all"

    @field_validator("role")
    @classmethod
    def selected_role(cls, value: str) -> str:
        if value not in ROLES:
            raise ValueError("请选择职位目录中的目标职位")
        return value

    @field_validator("city")
    @classmethod
    def selected_city(cls, value: str) -> str:
        if value not in CITIES:
            raise ValueError("请选择城市目录中的工作城市")
        return value


class SourceResult(BaseModel):
    source: Source
    status: Literal["success", "partial", "blocked", "error"]
    count: int
    message: str
    search_urls: dict[str, str]


class CollectionResult(BaseModel):
    jobs: list[JobCandidate]
    sources: list[SourceResult]


class MatchRequest(BaseModel):
    resume: ResumeExtraction
    job: JobCandidate


class RankRequest(BaseModel):
    resume: ResumeExtraction
    jobs: list[JobCandidate]


class RankedJob(BaseModel):
    job: JobCandidate
    score: float | None
    matched_skills: list[str]
    missing_skills: list[str]


class RequirementFields(BaseModel):
    requirement: str
    category: Category
    skill_name: str | None = Field(
        description="skills 类必须填写通用技术技能名称；沟通协作等通用要求归 experience"
    )
    required: bool
    status: Literal["met", "partial", "missing"]
    explanation: str
    suggestion: str | None


class ReferencedRequirement(RequirementFields):
    jd_evidence_id: int = Field(ge=0)
    resume_evidence_ids: list[int]


class ReferencedAnalysis(BaseModel):
    summary: str
    requirements: list[ReferencedRequirement] = Field(min_length=1)


class RequirementAssessment(RequirementFields):
    jd_evidence: str = Field(min_length=1)
    resume_evidence: list[str]

    @model_validator(mode="after")
    def check_assessment(self) -> "RequirementAssessment":
        if self.category == "skills" and not self.skill_name:
            raise ValueError("技能要求必须提供单一技能名称 skill_name")
        if self.status in ("met", "partial") and not self.resume_evidence:
            raise ValueError("命中或部分命中必须提供简历原文证据")
        if self.status == "missing" and self.resume_evidence:
            raise ValueError("未体现项不能同时提供命中证据")
        if self.status != "met" and not self.suggestion:
            raise ValueError("未满足的要求必须提供具体补足建议")
        return self


class MatchAnalysis(BaseModel):
    summary: str
    requirements: list[RequirementAssessment] = Field(min_length=1)


class DimensionScore(BaseModel):
    category: Category
    label: str
    weight: float
    score: float
    contribution: float


class MatchReport(BaseModel):
    case_id: str
    model: str
    rubric_version: str
    total_score: float
    dimensions: list[DimensionScore]
    summary: str
    requirements: list[RequirementAssessment]
    skill_gaps: list[str]


class HumanDimension(BaseModel):
    category: Category
    score: float = Field(ge=0, le=100)


MAX_SKILL_GAPS = 30
MAX_SKILL_GAP_CHARS = 60
MAX_NOTES_CHARS = 2000


class HumanAnnotation(BaseModel):
    # Bounded so a single annotation cannot bloat the database row or the evaluation page.
    annotator: str = Field(min_length=1, max_length=50)
    dimensions: list[HumanDimension] = Field(min_length=1)
    skill_gaps: list[str] = Field(max_length=MAX_SKILL_GAPS)
    notes: str = Field(default="", max_length=MAX_NOTES_CHARS)

    @model_validator(mode="after")
    def distinct_dimensions(self) -> "HumanAnnotation":
        categories = [item.category for item in self.dimensions]
        if len(categories) != len(set(categories)):
            raise ValueError("同一评分维度不能重复")
        if any(not name.strip() for name in self.skill_gaps):
            raise ValueError("技能名称不能为空")
        if any(len(name) > MAX_SKILL_GAP_CHARS for name in self.skill_gaps):
            raise ValueError(f"单个技能名称不能超过 {MAX_SKILL_GAP_CHARS} 个字符")
        return self
