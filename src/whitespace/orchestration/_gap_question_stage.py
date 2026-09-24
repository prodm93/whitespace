"""Question gate step that closes the gap council's first half."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.schemas.gap import CandidateGap
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)

# REVISIT: tune if results suggest
CORROBORATION_THRESHOLD = 0.85


async def run_question_gate_node(
    gate: QuestionGate | None,
    dedup: SemanticDeduplicator,
    state: GapCouncilState,
) -> dict[str, Any]:
    """Let the gate decide whether this run pauses to ask the user."""
    proposals = state.get("proposed_questions", [])
    if gate is None or not proposals:
        return {"pending_questions": []}
    candidates = state.get("candidates", [])
    corroboration = await find_corroboration(dedup, candidates)
    summary = build_run_summary(candidates, corroboration, state.get("gate_flags", {}))
    decision = await gate.judge(proposals, summary, "gap", state["run_id"], state["domain"])
    return {"pending_questions": decision.questions}


async def find_corroboration(
    dedup: SemanticDeduplicator,
    candidates: list[CandidateGap],
) -> dict[str, list[str]] | None:
    """Map each candidate ID to the other identifiers that produced a near match.

    Returns None when the similarity check fails, so the gate is told the
    contest level is unavailable rather than shown a falsely unsettled pool.
    """
    try:
        matrix = await dedup.similarity_matrix([_text(c) for c in candidates])
    except Exception:
        logger.exception("Gap question gate: similarity check failed; contest level unavailable")
        return None
    found: dict[str, list[str]] = {c.candidate_id: [] for c in candidates}
    for candidate, row in zip(candidates, matrix, strict=True):
        others = found[candidate.candidate_id]
        for other, score in zip(candidates, row, strict=True):
            role = other.source_role
            corroborates = role != candidate.source_role and score >= CORROBORATION_THRESHOLD
            if corroborates and role not in others:
                others.append(role)
    return found


def build_run_summary(
    candidates: list[CandidateGap],
    corroboration: dict[str, list[str]] | None,
    flags: dict[str, str],
) -> str:
    """Render candidate counts, contest level and prior-work flags for the gate."""
    counts = Counter(c.source_role for c in candidates)
    per_role = ", ".join(f"{role}: {count}" for role, count in counts.items())
    lines = [f"Candidates: {len(candidates)} ({per_role})" if per_role else "Candidates: 0"]
    if corroboration is None:
        lines.append("Contest level: unavailable (similarity check failed).")
        lines.extend(f"- [{c.candidate_id}] {c.title}" for c in candidates)
    else:
        single = sum(1 for c in candidates if not corroboration.get(c.candidate_id))
        lines.append(
            f"Contest level: {single} of {len(candidates)} candidates were found by only one "
            "identifier."
        )
        lines.extend(_candidate_line(c, corroboration) for c in candidates)
    lines.append(f"Candidates resembling earlier runs' output: {len(flags)}")
    lines.extend(f"- [{candidate_id}] {note}" for candidate_id, note in flags.items())
    return "\n".join(lines)


def _candidate_line(candidate: CandidateGap, corroboration: dict[str, list[str]]) -> str:
    others = corroboration.get(candidate.candidate_id, [])
    note = (
        f"also found by {', '.join(others)}" if others else f"only found by {candidate.source_role}"
    )
    return f"- [{candidate.candidate_id}] {candidate.title} ({note})"


def _text(candidate: CandidateGap) -> str:
    return f"{candidate.title}: {candidate.description}"
