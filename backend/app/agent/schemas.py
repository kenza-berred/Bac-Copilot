from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..concepts import CONCEPTS


def _concept_or_none(v):
    return v if v in CONCEPTS else None


class RouteDecision(BaseModel):
    intent: Literal["ask", "quiz", "grade", "progress"] = "ask"
    language: str = "fr"
    search_query: str = ""
    concept: str | None = None

    @field_validator("concept", mode="before")
    @classmethod
    def check_concept(cls, v):
        return _concept_or_none(v)


class VerifyResult(BaseModel):
    supported: bool = True
    unsupported_claims: list[str] = Field(default_factory=list)
    better_query: str | None = None


class RubricItem(BaseModel):
    criterion: str
    points: float


class Question(BaseModel):
    question: str
    type: Literal["qcm", "short", "analysis"] = "short"
    options: list[str] = Field(default_factory=list)
    answer: str
    rubric: list[RubricItem] = Field(default_factory=list)
    concept: str | None = None
    difficulty: str = "moyen"
    source_ids: list[int] = Field(default_factory=list)

    @field_validator("concept", mode="before")
    @classmethod
    def check_concept(cls, v):
        return _concept_or_none(v)

    @property
    def max_points(self) -> float:
        return sum(r.points for r in self.rubric) or 1.0


class QuizOut(BaseModel):
    questions: list[Question]


class Verdict(BaseModel):
    index: int
    valid: bool
    reason: str = ""


class Verdicts(BaseModel):
    verdicts: list[Verdict]


class CriterionGrade(BaseModel):
    criterion: str
    max_points: float
    awarded: float
    comment: str = ""


class GradeOut(BaseModel):
    criteria: list[CriterionGrade] = Field(default_factory=list)
    score: float = 0.0
    max_score: float = 0.0
    feedback: str = ""
    misconceptions: list[str] = Field(default_factory=list)
    concept: str | None = None

    @field_validator("concept", mode="before")
    @classmethod
    def check_concept(cls, v):
        return _concept_or_none(v)

    def normalized(self) -> "GradeOut":
        """Clamp per-criterion points and recompute totals (never trust the LLM's arithmetic)."""
        for c in self.criteria:
            c.awarded = round(min(max(c.awarded, 0.0), c.max_points) * 4) / 4
        if self.criteria:
            self.score = sum(c.awarded for c in self.criteria)
            self.max_score = sum(c.max_points for c in self.criteria)
        return self


class RubricOut(BaseModel):
    rubric: list[RubricItem]
    reference: str = ""


class Flashcard(BaseModel):
    front: str
    back: str
    concept: str | None = None
    source_ids: list[int] = Field(default_factory=list)

    @field_validator("concept", mode="before")
    @classmethod
    def check_concept(cls, v):
        return _concept_or_none(v)


class FlashcardsOut(BaseModel):
    cards: list[Flashcard]
