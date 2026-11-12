"""Refine step that opens the ideation council's second half with the user's answers."""

from __future__ import annotations

import logging
from typing import Any

from whitespace.agents.council._answer_prompts import (
    answered_keys,
    answers_section,
    refine_targets,
)
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.orchestration._council_common import collect_batches
from whitespace.orchestration._ideation_council_state import IdeationCouncilState
from whitespace.orchestration._ideation_generation_phase import novelty_discard
from whitespace.orchestration._prior_output_gate import gate_against_prior
from whitespace.schemas.idea import CandidateIdea
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)


async def run_ideation_refine_node(
    ideators: dict[str, IdeaIdeator],
    dedup: SemanticDeduplicator,
    prior_art: PriorArtAgent,
    state: IdeationCouncilState,
) -> dict[str, Any]:
    """Let the ideators revise and extend their ideas from the answers."""
    records = state.get("pending_questions", [])
    answers = state.get("user_answers", [])
    valid = answered_keys(records, answers)
    if not valid:
        return {}
    pool = state["candidates"]
    targets = refine_targets(records, answers, pool, list(ideators))
    by_role: dict[str, list[CandidateIdea]] = {}
    for candidate in pool:
        by_role.setdefault(candidate.source_role, []).append(candidate)
    answers_text = answers_section(state)
    tasks = [
        ideators[role].refine(
            by_role.get(role, []),
            answers_text,
            state["graph_context"],
            state["profile"],
            allow_queries=False,
            valid_keys=valid,
        )
        for role in targets
    ]
    refined = dict(await collect_batches(targets, tasks, "IdeationCouncilGraph.refine"))
    added = [idea for result in refined.values() for idea in result.added]
    kept_added, flags, gate_kills = await gate_against_prior(
        dedup, added, state.get("prior_idea_texts", [])
    )
    originals = {c.candidate_id: c for c in pool}
    to_check: dict[str, list[CandidateIdea]] = {}
    for role, result in refined.items():
        changed = [idea for idea in result.revised if _differs(idea, originals)]
        new = [idea for idea in kept_added if idea.source_role == role]
        if changed or new:
            to_check[role] = changed + new
    checked = await _recheck_novelty(ideators, prior_art, to_check)
    revised = {idea.candidate_id: idea for result in refined.values() for idea in result.revised}
    survivors: dict[str, CandidateIdea] = {}
    dropped: list[CandidateIdea] = []
    for role, ideas in to_check.items():
        if role not in checked:
            for idea in ideas:
                revised.pop(idea.candidate_id, None)
            continue
        kept, gone = checked[role]
        survivors.update({idea.candidate_id: idea for idea in kept})
        dropped.extend(gone)
    dropped_ids = {idea.candidate_id for idea in dropped}
    new_pool = [
        survivors.get(c.candidate_id) or revised.get(c.candidate_id, c)
        for c in pool
        if c.candidate_id not in dropped_ids
    ]
    new_pool += [survivors[a.candidate_id] for a in kept_added if a.candidate_id in survivors]
    return {
        "candidates": new_pool,
        "gate_flags": {**state.get("gate_flags", {}), **flags},
        "discards": state.get("discards", []) + gate_kills + [novelty_discard(d) for d in dropped],
    }


def _differs(idea: CandidateIdea, originals: dict[str, CandidateIdea]) -> bool:
    before = originals.get(idea.candidate_id)
    return before is None or (idea.title, idea.description) != (before.title, before.description)


async def _recheck_novelty(
    ideators: dict[str, IdeaIdeator],
    prior_art: PriorArtAgent,
    to_check: dict[str, list[CandidateIdea]],
) -> dict[str, tuple[list[CandidateIdea], list[CandidateIdea]]]:
    """The existing two-round novelty check, only on ideas that refine changed or added.

    A role whose check fails is absent from the result: its ideas stay as
    they were before the refine and its added ideas are not admitted.
    """
    roles = list(to_check)
    tasks = [ideators[role].novelty_filter(to_check[role], prior_art) for role in roles]
    return dict(await collect_batches(roles, tasks, "IdeationCouncilGraph.recheck"))
