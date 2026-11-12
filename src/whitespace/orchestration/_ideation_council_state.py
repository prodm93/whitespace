"""State schema for the ideation LangGraph."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from pydantic import BaseModel

from whitespace.orchestration._state_codec import Codec, dump_state, load_state
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion, QuestionRecord, UserAnswer


class IdeationCouncilState(TypedDict, total=False):
    selected_needs: list[UnmetNeed]
    profile: ProfessionalProfile
    graph_context: str
    run_id: str
    gap_run_id: str
    domain: str
    candidates: list[CandidateIdea]
    proposed_questions: list[ProposedQuestion]
    pending_questions: list[QuestionRecord]
    user_answers: list[UserAnswer]
    questions_enabled: bool
    prior_idea_texts: list[str]
    gate_flags: dict[str, str]
    report: CriticReport | None
    revision_round: int
    final_proposals: list[IdeationProposal]
    discards: list[dict[str, str]]


_MODELS: dict[str, type[BaseModel]] = {
    "profile": ProfessionalProfile,
    "report": CriticReport,
}
_MODEL_LISTS: dict[str, type[BaseModel]] = {
    "selected_needs": UnmetNeed,
    "candidates": CandidateIdea,
    "proposed_questions": ProposedQuestion,
    "pending_questions": QuestionRecord,
    "user_answers": UserAnswer,
    "final_proposals": IdeationProposal,
}
_CUSTOM: dict[str, Codec] = {}


def dump_ideation_state(state: IdeationCouncilState) -> dict[str, Any]:
    """Convert the state between council halves to JSON-compatible data."""
    return dump_state(cast(dict[str, Any], state), _MODELS, _MODEL_LISTS, _CUSTOM)


def load_ideation_state(data: dict[str, Any]) -> IdeationCouncilState:
    """Rebuild the state between council halves from ``dump_ideation_state`` output."""
    return cast(IdeationCouncilState, load_state(data, _MODELS, _MODEL_LISTS, _CUSTOM))


def build_initial_ideation_state(
    selected_needs: list[UnmetNeed],
    profile: ProfessionalProfile,
    graph_context: str,
    *,
    run_id: str,
    gap_run_id: str,
    domain: str,
    questions_enabled: bool,
    prior_idea_texts: list[str],
) -> IdeationCouncilState:
    """The state an ideation council run starts from."""
    return {
        "selected_needs": selected_needs,
        "profile": profile,
        "graph_context": graph_context,
        "run_id": run_id,
        "gap_run_id": gap_run_id,
        "domain": domain,
        "questions_enabled": questions_enabled,
        "prior_idea_texts": prior_idea_texts,
    }
