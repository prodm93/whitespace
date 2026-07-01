"""LangGraph for gap analysis: fan-out ideators → critic → synthesiser."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_ideator import GapIdeator
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)


class GapCouncilState(TypedDict):
    graph_context: str
    profile: ProfessionalProfile
    ideator_results: list[list[CandidateGap]]
    critiqued_gaps: list[CandidateGap]
    synthesised_needs: list[UnmetNeed]


class GapCouncilGraph:
    """Fan-out to N gap ideators → critic → synthesiser → END."""

    def __init__(
        self,
        ideators: list[GapIdeator],
        critic: GapCritic,
        synthesiser: GapSynthesiser,
    ) -> None:
        self._ideators = ideators
        self._critic = critic
        self._synthesiser = synthesiser
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(GapCouncilState)
        builder.add_node("fan_out_ideators", self._run_ideators)
        builder.add_node("critic", self._run_critic)
        builder.add_node("synthesiser", self._run_synthesiser)
        builder.set_entry_point("fan_out_ideators")
        builder.add_edge("fan_out_ideators", "critic")
        builder.add_edge("critic", "synthesiser")
        builder.add_edge("synthesiser", END)
        return builder.compile()

    async def run(
        self,
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[UnmetNeed]:
        """Execute the full gap council and return fleshed-out unmet needs."""
        logger.info(
            "GapCouncilGraph: starting with %d ideators",
            len(self._ideators),
        )
        initial_state: GapCouncilState = {
            "graph_context": graph_context,
            "profile": profile,
            "ideator_results": [],
            "critiqued_gaps": [],
            "synthesised_needs": [],
        }
        final_state = await self._compiled.ainvoke(initial_state)
        result: list[UnmetNeed] = final_state["synthesised_needs"]
        return result

    async def _run_ideators(self, state: GapCouncilState) -> dict[str, Any]:
        tasks = [
            ideator.run(state["graph_context"], state["profile"]) for ideator in self._ideators
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[list[CandidateGap]] = []
        for i, outcome in enumerate(raw):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "GapCouncilGraph: ideator %d failed: %s",
                    i,
                    outcome,
                )
                continue
            results.append(outcome)
        total = sum(len(g) for g in results)
        logger.info(
            "GapCouncilGraph: %d/%d ideators succeeded (%d total gaps)",
            len(results),
            len(self._ideators),
            total,
        )
        return {"ideator_results": results}

    async def _run_critic(self, state: GapCouncilState) -> dict[str, Any]:
        ranked = await self._critic.run(
            state["ideator_results"],
            state["profile"],
        )
        return {"critiqued_gaps": ranked}

    async def _run_synthesiser(self, state: GapCouncilState) -> dict[str, Any]:
        needs = await self._synthesiser.run(
            state["critiqued_gaps"],
            state["graph_context"],
            state["profile"],
        )
        return {"synthesised_needs": needs}
