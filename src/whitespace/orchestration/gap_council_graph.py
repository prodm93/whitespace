"""LangGraph for gap analysis: fan-out → critic-routed revision loop → synthesis."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.orchestration._council_common import (
    assign_candidate_ids,
    collect_batches,
    resolve_final,
    run_targeted_revision,
    should_revise,
)
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)


class GapCouncilState(TypedDict):
    graph_context: str
    profile: ProfessionalProfile
    candidates: list[CandidateGap]
    report: CriticReport | None
    revision_round: int
    synthesised_needs: list[UnmetNeed]


class GapCouncilGraph:
    """Fan-out identifiers → critic → (targeted revision ↔ critic) → synthesis.

    The critic's verdicts drive the routing: a revision round only runs
    when it flags candidates for delegation back to their originators.
    """

    def __init__(
        self,
        identifiers: list[GapIdentifier],
        critic: GapCritic,
        synthesiser: GapSynthesiser,
    ) -> None:
        self._identifiers = {i.role_name: i for i in identifiers}
        self._critic = critic
        self._synthesiser = synthesiser
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(GapCouncilState)
        builder.add_node("fan_out_identifiers", self._run_identifiers)
        builder.add_node("critic", self._run_critic)
        builder.add_node("revise", self._run_revision)
        builder.add_node("synthesiser", self._run_synthesiser)
        builder.set_entry_point("fan_out_identifiers")
        builder.add_edge("fan_out_identifiers", "critic")
        builder.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {"revise": "revise", "synthesiser": "synthesiser"},
        )
        builder.add_edge("revise", "critic")
        builder.add_edge("synthesiser", END)
        return builder.compile()

    async def run(
        self,
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[UnmetNeed]:
        """Execute the full gap council and return fleshed-out unmet needs."""
        logger.info(
            "GapCouncilGraph: starting with %d identifiers",
            len(self._identifiers),
        )
        initial_state: GapCouncilState = {
            "graph_context": graph_context,
            "profile": profile,
            "candidates": [],
            "report": None,
            "revision_round": 0,
            "synthesised_needs": [],
        }
        final_state = await self._compiled.ainvoke(initial_state)
        result: list[UnmetNeed] = final_state["synthesised_needs"]
        return result

    async def _run_identifiers(self, state: GapCouncilState) -> dict[str, Any]:
        roles = list(self._identifiers)
        tasks = [
            self._identifiers[role].run(state["graph_context"], state["profile"]) for role in roles
        ]
        batches = await collect_batches(roles, tasks, "GapCouncilGraph")
        pool = assign_candidate_ids(batches)
        logger.info(
            "GapCouncilGraph: %d/%d identifiers succeeded (%d candidates)",
            len(batches),
            len(roles),
            len(pool),
        )
        return {"candidates": pool, "report": None, "revision_round": 0}

    async def _run_critic(self, state: GapCouncilState) -> dict[str, Any]:
        report = await self._critic.run(state["candidates"], state["profile"])
        return {"report": report}

    def _route_after_critic(self, state: GapCouncilState) -> str:
        """Conditional edge driven by the critic's own verdicts."""
        if should_revise(state["report"], state["revision_round"]):
            return "revise"
        return "synthesiser"

    async def _run_revision(self, state: GapCouncilState) -> dict[str, Any]:
        report = state["report"]
        assert report is not None  # only reachable via _route_after_critic
        pool = await run_targeted_revision(
            {role: agent.revise for role, agent in self._identifiers.items()},
            report,
            state["candidates"],
            state["graph_context"],
            state["profile"],
            "GapCouncilGraph",
        )
        return {"candidates": pool, "revision_round": state["revision_round"] + 1}

    async def _run_synthesiser(self, state: GapCouncilState) -> dict[str, Any]:
        report = state["report"]
        assert report is not None  # critic always precedes synthesis
        needs = await self._synthesiser.run(
            state["candidates"],
            resolve_final(report),
            state["graph_context"],
            state["profile"],
        )
        return {"synthesised_needs": needs}
