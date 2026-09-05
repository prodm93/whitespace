"""State schema for the gap-analysis LangGraph."""

from __future__ import annotations

from typing import TypedDict

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
