"""Refine step that opens the gap council's second half with the user's answers."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from whitespace.agents.council._answer_prompts import (
    answered_keys,
    answers_section,
    refine_targets,
)
from whitespace.agents.council._answer_refinement import Refined
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.orchestration._council_common import collect_batches, replace_candidates
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._prior_output_gate import gate_against_prior
from whitespace.orchestration._research_stage import ResearchStage, format_finding_line
from whitespace.orchestration._trail_rendering import build_gap_references, render_trail
from whitespace.schemas.gap import CandidateGap

logger = logging.getLogger(__name__)


async def run_refine_node(
    identifiers: dict[str, GapIdentifier],
    research: ResearchStage,
    state: GapCouncilState,
) -> dict[str, Any]:
    """Let the members revise and extend their candidates from the answers."""
    records = state.get("pending_questions", [])
    answers = state.get("user_answers", [])
    valid = answered_keys(records, answers)
    if not valid:
        return {}
    pool = state["candidates"]
    targets = refine_targets(records, answers, pool, list(identifiers))
    answers_text = answers_section(state)
    by_role: dict[str, list[CandidateGap]] = {}
    for candidate in pool:
        by_role.setdefault(candidate.source_role, []).append(candidate)
    fbr = state.get("findings_by_role", {})
    trails = await asyncio.gather(
        *[
            render_trail(
                fbr.get(role, ""),
                build_gap_references([c for c in by_role.get(role, [])]),
                research.deduplicator,
            )
            for role in targets
        ]
    )
    trail_by_role = dict(zip(targets, trails, strict=True))
    contexts = {role: state["findings_text"] + "\n\n" + trail_by_role[role] for role in targets}
    profile = state["profile"]

    async def refine_all(roles: list[str], allow_queries: bool) -> dict[str, Refined[CandidateGap]]:
        tasks = [
            identifiers[role].refine(
                by_role.get(role, []),
                answers_text,
                contexts[role],
                profile,
                allow_queries=allow_queries,
                valid_keys=valid,
            )
            for role in roles
        ]
        return dict(await collect_batches(roles, tasks, "GapCouncilGraph.refine"))

    refined = await refine_all(targets, True)
    queries: list[str] = []
    for role in targets:
        for query in refined[role].queries if role in refined else []:
            if query not in queries:
                queries.append(query)
    findings_text = state["findings_text"]
    if queries:
        new_lines = await _follow_up_findings(research, state, queries)
        if new_lines:
            findings_text = findings_text + "\n" + new_lines
            askers = [role for role in targets if role in refined and refined[role].queries]
            for role in askers:
                contexts[role] = findings_text + "\n\n" + trail_by_role[role]
            refined.update(await refine_all(askers, False))
    revised = [gap for result in refined.values() for gap in result.revised]
    added = [gap for result in refined.values() for gap in result.added]
    kept, flags, kills = await gate_against_prior(
        research.deduplicator, added, state["run_memory"].prior_texts
    )
    return {
        "candidates": replace_candidates(pool, revised) + kept,
        "gate_flags": {**state.get("gate_flags", {}), **flags},
        "findings_text": findings_text,
        "queries": state["queries"] + queries,
        "held_discards": [{**kill, "domain": state["domain"]} for kill in kills],
    }


async def _follow_up_findings(
    research: ResearchStage, state: GapCouncilState, queries: list[str]
) -> str:
    """Search the follow-up queries once; the new findings keyed after the last [F{N}]."""
    memory = state["run_memory"]
    try:
        found = await research.research(
            queries,
            domain=state["domain"],
            keep_findings=state["keep_findings"],
            run_id=state["run_id"],
            prior_queries=state["queries"] + memory.prior_queries,
            prior_findings=[],
        )
    except Exception:
        logger.exception("GapCouncilGraph.refine: follow-up search failed; no findings added")
        return ""
    keys = [int(n) for n in re.findall(r"\[F(\d+)\]", state["findings_text"])]
    start = max(keys, default=0) + 1
    return "\n".join(format_finding_line(start + i, f) for i, f in enumerate(found))
