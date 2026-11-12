"""State schema for the gap-analysis LangGraph."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from pydantic import BaseModel

from whitespace.orchestration._research_stage import RunMemory
from whitespace.orchestration._state_codec import Codec, dump_state, load_state
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion, QuestionRecord, UserAnswer


class GapCouncilState(TypedDict, total=False):
    domain: str
    profile: ProfessionalProfile
    doc_paths: list[str]
    keep_findings: bool
    run_id: str
    run_memory: RunMemory
    queries: list[str]
    findings_text: str
    findings_by_role: dict[str, str]
    candidates: list[CandidateGap]
    proposed_questions: list[ProposedQuestion]
    pending_questions: list[QuestionRecord]
    gate_flags: dict[str, str]
    report: CriticReport | None
    revision_round: int
    synthesised_needs: list[UnmetNeed]
    user_answers: list[UserAnswer]
    questions_enabled: bool
    held_discards: list[dict[str, str]]
    final_discards: list[dict[str, str]]


_MODELS: dict[str, type[BaseModel]] = {
    "profile": ProfessionalProfile,
    "report": CriticReport,
}
_MODEL_LISTS: dict[str, type[BaseModel]] = {
    "candidates": CandidateGap,
    "proposed_questions": ProposedQuestion,
    "pending_questions": QuestionRecord,
    "user_answers": UserAnswer,
}


_CUSTOM: dict[str, Codec] = {
    "run_memory": (lambda memory: memory.to_dict(), RunMemory.from_dict),
}


def dump_mid_state(state: GapCouncilState) -> dict[str, Any]:
    """Convert the state between council halves to JSON-compatible data."""
    return dump_state(cast(dict[str, Any], state), _MODELS, _MODEL_LISTS, _CUSTOM)


def load_mid_state(data: dict[str, Any]) -> GapCouncilState:
    """Rebuild the state between council halves from ``dump_mid_state`` output."""
    return cast(GapCouncilState, load_state(data, _MODELS, _MODEL_LISTS, _CUSTOM))


def build_initial_gap_state(
    profile: ProfessionalProfile,
    domain: str,
    doc_paths: list[str] | None,
    *,
    keep_findings: bool,
    run_id: str,
    run_memory: RunMemory,
    questions_enabled: bool,
) -> GapCouncilState:
    """The state a gap council run starts from."""
    return {
        "domain": domain,
        "profile": profile,
        "doc_paths": doc_paths or [],
        "keep_findings": keep_findings,
        "run_id": run_id,
        "run_memory": run_memory,
        "questions_enabled": questions_enabled,
    }
