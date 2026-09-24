"""State schema for the gap-analysis LangGraph."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from pydantic import BaseModel

from whitespace.orchestration._research_stage import RunMemory
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion


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
    gate_flags: dict[str, str]
    report: CriticReport | None
    revision_round: int
    synthesised_needs: list[UnmetNeed]


_MODELS: dict[str, type[BaseModel]] = {
    "profile": ProfessionalProfile,
    "report": CriticReport,
}
_MODEL_LISTS: dict[str, type[BaseModel]] = {
    "candidates": CandidateGap,
    "proposed_questions": ProposedQuestion,
}


def dump_mid_state(state: GapCouncilState) -> dict[str, Any]:
    """Convert the state between council halves to JSON-compatible data."""
    data: dict[str, Any] = {}
    for key, value in cast(dict[str, Any], state).items():
        if key == "run_memory":
            data[key] = value.to_dict()
        elif key in _MODEL_LISTS:
            data[key] = [item.model_dump(mode="json") for item in value]
        elif key in _MODELS and value is not None:
            data[key] = value.model_dump(mode="json")
        else:
            data[key] = value
    return data


def load_mid_state(data: dict[str, Any]) -> GapCouncilState:
    """Rebuild the state between council halves from ``dump_mid_state`` output."""
    state: dict[str, Any] = {}
    for key, value in data.items():
        if key == "run_memory":
            state[key] = RunMemory.from_dict(value)
        elif key in _MODEL_LISTS:
            state[key] = [_MODEL_LISTS[key].model_validate(item) for item in value]
        elif key in _MODELS and value is not None:
            state[key] = _MODELS[key].model_validate(value)
        else:
            state[key] = value
    return cast(GapCouncilState, state)
