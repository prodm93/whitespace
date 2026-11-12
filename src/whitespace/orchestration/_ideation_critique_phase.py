"""Ideation judgment phase: critic, revision and synthesis nodes for IdeationCouncilGraph."""

from __future__ import annotations

from typing import Any

from whitespace.agents.council._answer_prompts import with_answers
from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.orchestration._council_common import (
    build_flag_evidence,
    resolve_final,
    run_targeted_revision,
)
from whitespace.orchestration._ideation_council_state import IdeationCouncilState


async def run_ideation_critic_node(
    critic: IdeaCritic, state: IdeationCouncilState
) -> dict[str, Any]:
    """Score and route the idea pool against the graph context, flags and answers."""
    evidence = with_answers(
        state["graph_context"] + build_flag_evidence(state.get("gate_flags", {})), state
    )
    report = await critic.run(state["candidates"], state["profile"], evidence=evidence)
    return {"report": report}


async def run_ideation_revision_node(
    ideators: dict[str, IdeaIdeator], state: IdeationCouncilState
) -> dict[str, Any]:
    """Re-invoke flagged ideators and swap their revisions into the pool."""
    report = state["report"]
    assert report is not None  # only reachable after the critic
    context = with_answers(state["graph_context"], state)
    pool = await run_targeted_revision(
        {role: agent.revise for role, agent in ideators.items()},
        report,
        state["candidates"],
        {role: context for role in ideators},
        state["profile"],
        "IdeationCouncilGraph",
    )
    return {"candidates": pool, "revision_round": state["revision_round"] + 1}


async def run_ideation_synth_node(
    synthesiser: IdeaSynthesiser, state: IdeationCouncilState
) -> dict[str, Any]:
    """Write up the survivors; the critic's kills join the run's discards."""
    report = state["report"]
    assert report is not None  # critic always precedes synthesis
    resolved = resolve_final(report)
    by_id = {c.candidate_id: c for c in state["candidates"]}
    kills = [
        {
            "title": by_id[a.candidate_id].title,
            "description": by_id[a.candidate_id].description,
            "reason": a.objections or "killed by council critic",
        }
        for a in resolved.assessments
        if a.verdict == "kill" and a.candidate_id in by_id
    ]
    proposals = await synthesiser.run(
        state["candidates"], resolved, with_answers(state["graph_context"], state), state["profile"]
    )
    return {"final_proposals": proposals, "discards": state.get("discards", []) + kills}
