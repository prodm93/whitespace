"""Critic assessment schemas shared by the gap and ideation councils."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

Verdict = Literal["keep", "kill", "delegate_back", "develop_self"]


class CandidateLike(Protocol):
    """Structural type for anything the critics can assess."""

    candidate_id: str
    title: str
    description: str
    source_model: str
    source_role: str


class CriticAssessment(BaseModel):
    candidate_id: str = Field(..., description="ID of the candidate being assessed")
    verdict: Verdict = Field(
        ...,
        description=(
            "keep = strong as-is; kill = discard; delegate_back = the "
            "originating model should develop it further; develop_self = "
            "the critic elaborates it itself"
        ),
    )
    scores: dict[str, int] = Field(
        default_factory=dict,
        description="Per-criterion scores (1-10), criteria set by the council",
    )
    objections: str | None = Field(
        default=None,
        description="Specific weaknesses; required for kill and delegate_back",
    )
    feedback_for_originator: str | None = Field(
        default=None,
        description="Concrete revision instructions; only for delegate_back",
    )
    developed_description: str | None = Field(
        default=None,
        description="The critic's elaborated version; only for develop_self",
    )
    merge_with: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of complementary candidates from other models to combine "
            "with this one during synthesis"
        ),
    )


class CriticReport(BaseModel):
    assessments: list[CriticAssessment] = Field(
        ..., description="One assessment per candidate, referenced by ID"
    )
    ranking: list[str] = Field(
        ...,
        description="Candidate IDs of survivors, best-first",
    )

    def assessment_for(self, candidate_id: str) -> CriticAssessment | None:
        for assessment in self.assessments:
            if assessment.candidate_id == candidate_id:
                return assessment
        return None

    def delegations(self) -> list[CriticAssessment]:
        return [a for a in self.assessments if a.verdict == "delegate_back"]
