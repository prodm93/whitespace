"""State schema for the ideation LangGraph."""

from __future__ import annotations

from typing import TypedDict

from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion


class IdeationCouncilState(TypedDict, total=False):
    selected_needs: list[UnmetNeed]
    profile: ProfessionalProfile
    graph_context: str
    candidates: list[CandidateIdea]
    proposed_questions: list[ProposedQuestion]
    report: CriticReport | None
    revision_round: int
    final_proposals: list[IdeationProposal]
    discards: list[dict[str, str]]
