"""Contracts for the handwritten interview loop."""

from typing import Literal

from pydantic import BaseModel, Field

from .match_schemas import MatchRequest


class Topic(BaseModel):
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    questions: list[str] = Field(min_length=3, max_length=3)
    expected_points: list[str] = Field(min_length=1)


class InterviewPlan(BaseModel):
    topics: list[Topic] = Field(min_length=3, max_length=3)


class AnswerScores(BaseModel):
    technical: int = Field(ge=0, le=100)
    reasoning: int = Field(ge=0, le=100)
    practice: int = Field(ge=0, le=100)
    communication: int = Field(ge=0, le=100)


class AssessmentFields(BaseModel):
    scores: AnswerScores
    strengths: list[str]
    improvements: list[str] = Field(min_length=1)
    reflection: str = Field(min_length=1)
    action: Literal["follow_up", "next"]
    follow_up: str | None


class AnswerEvaluation(AssessmentFields):
    evidence_turns: list[int]


class Assessment(AssessmentFields):
    evidence: list[str]


class AudioEvaluation(AnswerEvaluation):
    transcript: str


class AnswerInput(BaseModel):
    answer: str = Field(min_length=1)


class StartInterview(MatchRequest):
    pass
