"""LangGraph for ideation: fan-out → critic → synth → prior art → conditional loop."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_MAX_PRIOR_ART_RETRIES = 3


class IdeationCouncilState(TypedDict):
    selected_needs: list[UnmetNeed]
    profile: ProfessionalProfile
    graph_context: str
    prior_art_context: str
    ideator_results: list[list[CandidateIdea]]
    critiqued_ideas: list[CandidateIdea]
    synthesised_ideas: list[IdeationProposal]
    prior_art_results: list[IdeationProposal]
    prior_art_found: bool
    prior_art_retry_count: int
    final_proposals: list[IdeationProposal]


class IdeationCouncilGraph:
    """Fan-out ideators → critic → synthesiser → prior art → conditional loop."""

    def __init__(
        self,
        ideators: list[IdeaIdeator],
        critic: IdeaCritic,
        synthesiser: IdeaSynthesiser,
        prior_art_agent: PriorArtAgent,
    ) -> None:
        self._ideators = ideators
        self._critic = critic
        self._synthesiser = synthesiser
        self._prior_art_agent = prior_art_agent
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(IdeationCouncilState)
        builder.add_node("fan_out_ideators", self._run_ideators)
        builder.add_node("critic", self._run_critic)
        builder.add_node("synthesiser", self._run_synthesiser)
        builder.add_node("prior_art_check", self._run_prior_art_check)
        builder.add_node("finalise", self._run_finalise)
        builder.set_entry_point("fan_out_ideators")
        builder.add_edge("fan_out_ideators", "critic")
        builder.add_edge("critic", "synthesiser")
        builder.add_edge("synthesiser", "prior_art_check")
        builder.add_conditional_edges(
            "prior_art_check",
            self._should_retry,
            {
                "fan_out_ideators": "fan_out_ideators",
                "finalise": "finalise",
            },
        )
        builder.add_edge("finalise", END)
        return builder.compile()

    async def run(
        self,
        selected_needs: list[UnmetNeed],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[IdeationProposal]:
        """Execute the ideation council and return final proposals."""
        logger.info(
            "IdeationCouncilGraph: starting with %d needs, %d ideators",
            len(selected_needs),
            len(self._ideators),
        )
        initial_state: IdeationCouncilState = {
            "selected_needs": selected_needs,
            "profile": profile,
            "graph_context": graph_context,
            "prior_art_context": "",
            "ideator_results": [],
            "critiqued_ideas": [],
            "synthesised_ideas": [],
            "prior_art_results": [],
            "prior_art_found": False,
            "prior_art_retry_count": 0,
            "final_proposals": [],
        }
        final_state = await self._compiled.ainvoke(initial_state)
        return final_state["final_proposals"]

    async def _run_ideators(
        self,
        state: IdeationCouncilState,
    ) -> dict[str, Any]:
        ctx = state["graph_context"]
        prior_art_ctx = state.get("prior_art_context", "")
        if prior_art_ctx:
            ctx = (
                f"{ctx}\n\n## PRIOR ART TO AVOID\n\n"
                f"The following ideas were flagged as too similar to "
                f"existing prior art. Generate DIFFERENT ideas that "
                f"avoid these overlaps:\n\n{prior_art_ctx}"
            )
        tasks = [
            ideator.run(state["selected_needs"], ctx, state["profile"])
            for ideator in self._ideators
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[list[CandidateIdea]] = []
        for i, outcome in enumerate(raw):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "IdeationCouncilGraph: ideator %d failed: %s",
                    i,
                    outcome,
                )
                continue
            results.append(outcome)
        total = sum(len(g) for g in results)
        logger.info(
            "IdeationCouncilGraph: %d/%d ideators succeeded (%d ideas)",
            len(results),
            len(self._ideators),
            total,
        )
        return {"ideator_results": results}

    async def _run_critic(
        self,
        state: IdeationCouncilState,
    ) -> dict[str, Any]:
        ranked = await self._critic.run(
            state["ideator_results"],
            state["profile"],
        )
        return {"critiqued_ideas": ranked}

    async def _run_synthesiser(
        self,
        state: IdeationCouncilState,
    ) -> dict[str, Any]:
        proposals = await self._synthesiser.run(
            state["critiqued_ideas"],
            state["graph_context"],
            state["profile"],
        )
        return {"synthesised_ideas": proposals}

    async def _run_prior_art_check(
        self,
        state: IdeationCouncilState,
    ) -> dict[str, Any]:
        result = await self._prior_art_agent.run(state["synthesised_ideas"])
        prior_art_ctx = state.get("prior_art_context", "")
        if result.prior_art_found:
            new_notes = [
                f"- **{p.title}**: {p.prior_art_notes}"
                for p in result.proposals
                if p.prior_art_notes
            ]
            if new_notes:
                prior_art_ctx += "\n".join(new_notes) + "\n"
        return {
            "prior_art_results": result.proposals,
            "prior_art_found": result.prior_art_found,
            "prior_art_retry_count": state["prior_art_retry_count"] + 1,
            "prior_art_context": prior_art_ctx,
        }

    def _should_retry(self, state: IdeationCouncilState) -> str:
        """Conditional edge: loop back if prior art found and retries remain."""
        if state.get("prior_art_found") and state["prior_art_retry_count"] < _MAX_PRIOR_ART_RETRIES:
            logger.info(
                "IdeationCouncilGraph: prior art found, retrying (%d/%d)",
                state["prior_art_retry_count"],
                _MAX_PRIOR_ART_RETRIES,
            )
            return "fan_out_ideators"
        return "finalise"

    async def _run_finalise(
        self,
        state: IdeationCouncilState,
    ) -> dict[str, Any]:
        proposals = state.get("prior_art_results") or state.get(
            "synthesised_ideas",
            [],
        )
        logger.info(
            "IdeationCouncilGraph: finalised %d proposals after %d pass%s",
            len(proposals),
            state["prior_art_retry_count"],
            "es" if state["prior_art_retry_count"] != 1 else "",
        )
        return {"final_proposals": proposals}
