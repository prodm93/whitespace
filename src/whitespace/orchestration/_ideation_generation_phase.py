"""Ideation first half: ideator fan-out, novelty check and question gate nodes."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from whitespace.agents.council._question_proposals import resolve_question_candidate_ids
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._council_common import assign_candidate_ids, collect_batches
from whitespace.orchestration._ideation_council_state import IdeationCouncilState
from whitespace.schemas.idea import CandidateIdea

logger = logging.getLogger(__name__)

NOVELTY_DROP_REASON = "identified (semi-)duplicate during novelty check"


async def run_ideators_node(
    ideators: dict[str, IdeaIdeator], state: IdeationCouncilState
) -> dict[str, Any]:
    """Each ideator proposes ideas and questions for the selected needs."""
    roles = list(ideators)
    tasks = [
        ideators[role].run(state["selected_needs"], state["graph_context"], state["profile"])
        for role in roles
    ]
    batches = await collect_batches(roles, tasks, "IdeationCouncilGraph")
    pool = assign_candidate_ids([(role, output.ideas) for role, output in batches])
    logger.info(
        "IdeationCouncilGraph: %d/%d ideators succeeded (%d candidates)",
        len(batches),
        len(roles),
        len(pool),
    )
    return {
        "candidates": pool,
        "proposed_questions": resolve_question_candidate_ids(
            [question for _, output in batches for question in output.proposed_questions],
            pool,
        ),
        "report": None,
        "revision_round": 0,
    }


def novelty_discard(idea: CandidateIdea) -> dict[str, str]:
    return {"title": idea.title, "description": idea.description, "reason": NOVELTY_DROP_REASON}


async def run_novelty_node(
    ideators: dict[str, IdeaIdeator], prior_art: PriorArtAgent, state: IdeationCouncilState
) -> dict[str, Any]:
    """Each ideator novelty-checks its own ideas and prunes duplicates."""
    by_role: dict[str, list[CandidateIdea]] = {}
    for candidate in state["candidates"]:
        by_role.setdefault(candidate.source_role, []).append(candidate)
    roles = [role for role in by_role if role in ideators]
    tasks = [ideators[role].novelty_filter(by_role[role], prior_art) for role in roles]
    batches = await collect_batches(roles, tasks, "IdeationCouncilGraph.novelty")
    survivors = [c for _, (kept, _) in batches for c in kept]
    discards = [novelty_discard(c) for _, (_, dropped) in batches for c in dropped]
    logger.info(
        "IdeationCouncilGraph: novelty filter kept %d/%d candidates",
        len(survivors),
        len(state["candidates"]),
    )
    return {"candidates": survivors, "discards": discards}


def build_ideation_summary(pool: list[CandidateIdea], removed: int) -> str:
    """The run summary the question gate reads at the end of the ideation first half."""
    counts = Counter(c.source_role for c in pool)
    per_role = ", ".join(f"{role}: {n}" for role, n in counts.items())
    lines = [
        f"Candidates: {len(pool)} ({per_role})",
        f"Removed as duplicates of existing work before this point: {removed}",
    ]
    lines += [f"- [{c.candidate_id}] {c.title}" for c in pool]
    return "\n".join(lines)


async def run_ideation_question_gate_node(
    gate: QuestionGate | None, state: IdeationCouncilState
) -> dict[str, Any]:
    """Let the question gate decide whether this ideation run pauses to ask the user."""
    proposals = state.get("proposed_questions", [])
    if state.get("questions_enabled") is not True or gate is None or not proposals:
        return {"pending_questions": []}
    pool = state.get("candidates", [])
    ids = {c.candidate_id for c in pool}
    proposals = [p for p in proposals if p.purpose != "unlock" or p.related_candidate_id in ids]
    summary = build_ideation_summary(pool, len(state.get("discards", [])))
    decision = await gate.judge(proposals, summary, "ideation", state["run_id"], state["domain"])
    return {"pending_questions": decision.questions}
