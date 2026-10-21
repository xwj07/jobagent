"""Data contracts for collection, matching and independent human evaluation."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .schemas import ResumeExtraction

Source = Literal["boss", "zhilian", "manual"]
Category = Literal["skills", "projects", "experience", "education"]
Role = Literal["python", "ai_application", "java", "frontend", "data", "ml"]
City = Literal["hangzhou", "beijing", "shanghai", "shenzhen", "guangzhou", "chengdu"]


class JobCandidate(BaseModel):
    title: str
    company: str
    city: str
    salary: str
    source: Source
    url: str | None
    raw_text: str = Field(min_length=10)


class CollectionRequest(BaseModel):
    role: Role
    city: City
    source: Literal["boss", "zhilian", "both"] = "both"


class SourceResult(BaseModel):
    source: Source
    status: Literal["success", "blocked", "error"]
    count: int
    message: str


class CollectionResult(BaseModel):
    jobs: list[JobCandidate]
    sources: list[SourceResult]


class MatchRequest(BaseModel):
    resume: ResumeExtraction
    job: JobCandidate


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


class HumanAnnotation(BaseModel):
    annotator: str = Field(min_length=1)
    dimensions: list[HumanDimension] = Field(min_length=1)
    skill_gaps: list[str]
    notes: str = ""

    @model_validator(mode="after")
    def distinct_dimensions(self) -> "HumanAnnotation":
        categories = [item.category for item in self.dimensions]
        if len(categories) != len(set(categories)):
            raise ValueError("同一评分维度不能重复")
        if any(not name.strip() for name in self.skill_gaps):
            raise ValueError("技能名称不能为空")
        return self
