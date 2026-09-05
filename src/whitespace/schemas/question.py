from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProposedQuestion(BaseModel):
    question: str
    purpose: Literal["clarify", "unlock"]
    rationale: str
    hypothesis: str
    asker_role: str
    related_candidate_id: str = ""
    related_candidate_title: str = Field(default="", exclude=True)


class UserAnswer(BaseModel):
    question_id: str
    status: Literal["answered", "skipped", "expired"]
    answer: str = ""


class QuestionRecord(BaseModel):
    question_id: str
    run_id: str
    stage: Literal["gap", "ideation"]
    purpose: Literal["clarify", "unlock"]
    question: str
    hypothesis: str
    rationale: str
    asker_role: str
    related_candidate_id: str = ""
    asked: bool
    status: Literal["pending", "answered", "skipped", "expired"] = "pending"
    answer: str = ""
    domain: str = ""
    created_at: datetime
    outcome_score: float = 0.0
    survival_bonus: float = 0.0
    selection_bonus: float = 0.0
    rerun_penalty: float = 0.0


class GateDecision(BaseModel):
    ask: bool
    questions: list[QuestionRecord]
    reasoning: str
