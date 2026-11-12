"""Council judgment phase: critic, revision, and synthesis nodes for GapCouncilGraph."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from whitespace.agents.council._answer_prompts import with_answers
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
from whitespace.schemas.critique import CandidateLike, CriticReport

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
    evidence = with_answers(
        (state["findings_text"] + build_flag_evidence(state.get("gate_flags", {})) + exploration)[
            :_MAX_EVIDENCE_CHARS
        ],
        state,
    )
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
    contexts = {
        r: with_answers(findings_prefix + t, state) for r, t in zip(roles, trails, strict=True)
    }
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
    """Write up the surviving candidates; return them with every rejection, storing nothing.

    The final discards are the critic's kills plus the held discards of the
    refine step. They are built only after the synthesis succeeded.
    """
    assert (report := state["report"]) is not None
    resolved = resolve_final(report)
    surviving_ids = set(resolved.ranking)
    surv: list[CandidateLike] = [c for c in state["candidates"] if c.candidate_id in surviving_ids]
    surv_roles = {c.source_role for c in surv}
    exploration = await build_exploration_context(
        surv_roles,
        state.get("findings_by_role", {}),
        {role: surv for role in surv_roles},
        research.deduplicator,
    )
    evidence = with_answers((state["findings_text"] + exploration)[:_MAX_EVIDENCE_CHARS], state)
    needs = await synthesiser.run(state["candidates"], resolved, evidence, state["profile"])
    kills = build_kill_items(resolved, state["candidates"], state["domain"])
    return {
        "synthesised_needs": needs,
        "final_discards": kills + state.get("held_discards", []),
    }


def build_kill_items(
    report: CriticReport, pool: Sequence[CandidateLike], domain: str
) -> list[dict[str, str]]:
    """One discard item for each candidate in the pool that the critic killed."""
    by_id = {c.candidate_id: c for c in pool}
    return [
        {
            "title": by_id[a.candidate_id].title,
            "description": by_id[a.candidate_id].description,
            "reason": a.objections or "killed by council critic",
            "domain": domain,
        }
        for a in report.assessments
        if a.verdict == "kill" and a.candidate_id in by_id
    ]
