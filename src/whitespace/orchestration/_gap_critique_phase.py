"""Council judgment phase: critic, revision, and synthesis nodes for GapCouncilGraph."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.orchestration._council_common import (
    build_flag_evidence,
    resolve_final,
    run_targeted_revision,
)
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._research_stage import ResearchStage
from whitespace.orchestration._trail_rendering import (
    build_exploration_context,
    build_gap_references,
    render_trail,
)
from whitespace.schemas.critique import CandidateLike

logger = logging.getLogger(__name__)

_MAX_EVIDENCE_CHARS = 40000


async def run_critic_node(
    identifiers: dict[str, GapIdentifier],
    critic: GapCritic,
    research: ResearchStage,
    state: GapCouncilState,
) -> dict[str, Any]:
    """Score and route the candidate pool; returns an updated critic report."""
    by_role: dict[str, list[CandidateLike]] = {}
    for c in state["candidates"]:
        by_role.setdefault(c.source_role, []).append(c)
    exploration = await build_exploration_context(
        set(identifiers),
        state.get("findings_by_role", {}),
        by_role,
        research.deduplicator,
    )
    evidence = (
        state["findings_text"] + build_flag_evidence(state.get("gate_flags", {})) + exploration
    )[:_MAX_EVIDENCE_CHARS]
    report = await critic.run(state["candidates"], state["profile"], evidence=evidence)
    return {"report": report}


async def run_revision_node(
    identifiers: dict[str, GapIdentifier],
    research: ResearchStage,
    state: GapCouncilState,
) -> dict[str, Any]:
    """Re-invoke flagged originators and swap revisions into the pool."""
    assert (report := state["report"]) is not None
    findings_prefix = state["findings_text"] + "\n\n"
    by_role: dict[str, list[CandidateLike]] = {}
    for c in state["candidates"]:
        by_role.setdefault(c.source_role, []).append(c)
    roles = list(identifiers)
    fbr = state.get("findings_by_role", {})
    trails = await asyncio.gather(
        *[
            render_trail(
                fbr.get(r, ""),
                build_gap_references(by_role.get(r, [])),
                research.deduplicator,
            )
            for r in roles
        ]
    )
    contexts = {r: findings_prefix + t for r, t in zip(roles, trails, strict=True)}
    pool = await run_targeted_revision(
        {role: agent.revise for role, agent in identifiers.items()},
        report,
        state["candidates"],
        contexts,
        state["profile"],
        "GapCouncilGraph",
    )
    return {"candidates": pool, "revision_round": state["revision_round"] + 1}


async def run_synth_node(
    synthesiser: GapSynthesiser,
    research: ResearchStage,
    state: GapCouncilState,
) -> dict[str, Any]:
    """Write up the surviving candidates as UnmetNeed reports."""
    assert (report := state["report"]) is not None
    resolved = resolve_final(report)
    await research.record_kills(
        resolved, state["candidates"], state["run_id"], "gap", state["domain"]
    )
    surviving_ids = set(resolved.ranking)
    surv: list[CandidateLike] = [c for c in state["candidates"] if c.candidate_id in surviving_ids]
    surv_roles = {c.source_role for c in surv}
    exploration = await build_exploration_context(
        surv_roles,
        state.get("findings_by_role", {}),
        {role: surv for role in surv_roles},
        research.deduplicator,
    )
    evidence = (state["findings_text"] + exploration)[:_MAX_EVIDENCE_CHARS]
    needs = await synthesiser.run(state["candidates"], resolved, evidence, state["profile"])
    return {"synthesised_needs": needs}
