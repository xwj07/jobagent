"""Pydantic schemas: the contract between the LLM and the database."""

from pydantic import BaseModel, Field, model_validator


class RawPosting(BaseModel):
    """One line of import input. Company/title are optional hints from the collector."""

    raw_text: str = Field(min_length=10)
    company: str | None = None
    title: str | None = None
    source: str = "manual"
    url: str | None = None


class SkillMention(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    required: bool = True


class JobExtraction(BaseModel):
    """What we ask the LLM to produce. Validation here is the first line of defense:
    a malformed extraction never reaches the database."""

    title: str = "unknown"
    company: str = "unknown"
    city: str | None = None
    salary_min_k: int | None = Field(default=None, ge=0, le=1000)
    salary_max_k: int | None = Field(default=None, ge=0, le=1000)
    years_min: int | None = Field(default=None, ge=0, le=40)
    education: str | None = None
    skills: list[SkillMention] = Field(default_factory=list)

    @model_validator(mode="after")
    def _order_salary(self) -> "JobExtraction":
        # LLMs occasionally swap min/max. Fix silently rather than failing the row.
        if (
            self.salary_min_k is not None
            and self.salary_max_k is not None
            and self.salary_min_k > self.salary_max_k
        ):
            self.salary_min_k, self.salary_max_k = self.salary_max_k, self.salary_min_k
        return self
