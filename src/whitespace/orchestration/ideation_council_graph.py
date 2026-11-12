"""LangGraph for ideation in two halves: ideas and questions, then answers and judgment."""

from __future__ import annotations

import logging
from typing import Any, cast

from langgraph.graph import END, StateGraph

from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._council_common import should_revise
from whitespace.orchestration._ideation_answer_stage import run_ideation_refine_node
from whitespace.orchestration._ideation_council_state import (
    IdeationCouncilState,
    build_initial_ideation_state,
)
from whitespace.orchestration._ideation_critique_phase import (
    run_ideation_critic_node,
    run_ideation_revision_node,
    run_ideation_synth_node,
)
from whitespace.orchestration._ideation_generation_phase import (
    run_ideation_question_gate_node,
    run_ideators_node,
    run_novelty_node,
)
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import UserAnswer
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)


class IdeationCouncilGraph:
    """Fan-out ideators, ideator-driven novelty check, critic and synthesis.

    Novelty is checked by the ideators themselves: each hunts duplicates
    of its own ideas via the prior-art agent and decides modify or drop,
    with automatic discard of remaining (semi-)duplicates after the cap.
    The first half can end with questions for the user; the second half
    starts from their answers.
    """

    def __init__(
        self,
        ideators: list[IdeaIdeator],
        critic: IdeaCritic,
        synthesiser: IdeaSynthesiser,
        prior_art_agent: PriorArtAgent,
        dedup: SemanticDeduplicator,
        question_gate: QuestionGate | None = None,
    ) -> None:
        self._ideators = {i.role_name: i for i in ideators}
        self._critic = critic
        self._synthesiser = synthesiser
        self._prior_art = prior_art_agent
        self._dedup = dedup
        self._question_gate = question_gate
        self._first_half = self._build_first_half()
        self._second_half = self._build_second_half()

    def _build_first_half(self) -> Any:
        builder = StateGraph(IdeationCouncilState)
        builder.add_node("fan_out_ideators", self._run_ideators)
        builder.add_node("novelty", self._run_novelty)
        builder.add_node("question_gate_node", self._run_question_gate)
        builder.set_entry_point("fan_out_ideators")
        builder.add_edge("fan_out_ideators", "novelty")
        builder.add_edge("novelty", "question_gate_node")
        builder.add_edge("question_gate_node", END)
        return builder.compile()

    def _build_second_half(self) -> Any:
        builder = StateGraph(IdeationCouncilState)
        builder.add_node("refine_with_answers", self._run_refine)
        builder.add_node("critic", self._run_critic)
        builder.add_node("revise", self._run_revision)
        builder.add_node("synthesiser", self._run_synthesiser)
        builder.set_entry_point("refine_with_answers")
        builder.add_edge("refine_with_answers", "critic")
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
        selected_needs: list[UnmetNeed],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> tuple[list[IdeationProposal], list[dict[str, str]]]:
        """Execute the council with questions off; returns (proposals, discarded candidates)."""
        logger.info(
            "IdeationCouncilGraph: starting with %d needs, %d ideators",
            len(selected_needs),
            len(self._ideators),
        )
        initial = build_initial_ideation_state(
            selected_needs,
            profile,
            graph_context,
            run_id="",
            gap_run_id="",
            domain="",
            questions_enabled=False,
            prior_idea_texts=[],
        )
        return await self.run_second_half(await self.run_first_half(initial))

    async def run_first_half(self, initial: IdeationCouncilState) -> IdeationCouncilState:
        """Generate and novelty-check ideas; return them with any questions to ask."""
        return cast(IdeationCouncilState, await self._first_half.ainvoke(initial))

    async def run_second_half(
        self, state: IdeationCouncilState, answers: list[UserAnswer] | None = None
    ) -> tuple[list[IdeationProposal], list[dict[str, str]]]:
        """Refine with the answers, then critique, revise and synthesise the pool."""
        if answers is not None:
            state = {**state, "user_answers": answers}
        final_state = await self._second_half.ainvoke(state)
        proposals = cast(list[IdeationProposal], final_state.get("final_proposals", []))
        return proposals, cast(list[dict[str, str]], final_state.get("discards", []))

    async def _run_ideators(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_ideators_node(self._ideators, state)

    async def _run_novelty(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_novelty_node(self._ideators, self._prior_art, state)

    async def _run_question_gate(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_ideation_question_gate_node(self._question_gate, state)

    async def _run_refine(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_ideation_refine_node(self._ideators, self._dedup, self._prior_art, state)

    def _route_after_critic(self, state: IdeationCouncilState) -> str:
        """Conditional edge driven by the critic's own verdicts."""
        if should_revise(state["report"], state["revision_round"]):
            return "revise"
        return "synthesiser"

    async def _run_critic(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_ideation_critic_node(self._critic, state)

    async def _run_revision(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_ideation_revision_node(self._ideators, state)

    async def _run_synthesiser(self, state: IdeationCouncilState) -> dict[str, Any]:
        return await run_ideation_synth_node(self._synthesiser, state)
