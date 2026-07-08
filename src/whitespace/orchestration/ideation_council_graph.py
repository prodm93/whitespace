"""LangGraph for ideation: fan-out → novelty filter → critic loop → synthesis."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.orchestration._council_common import (
    assign_candidate_ids,
    collect_batches,
    resolve_final,
    run_targeted_revision,
    should_revise,
)
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)


class IdeationCouncilState(TypedDict, total=False):
    selected_needs: list[UnmetNeed]
    profile: ProfessionalProfile
    graph_context: str
    candidates: list[CandidateIdea]
    report: CriticReport | None
    revision_round: int
    final_proposals: list[IdeationProposal]
    discards: list[dict[str, str]]


class IdeationCouncilGraph:
    """Fan-out ideators → ideator-driven novelty filter → critic → synthesis.

    Novelty is checked by the ideators themselves: each hunts duplicates
    of its own ideas via the prior-art agent and decides modify or drop,
    with automatic discard of remaining (semi-)duplicates after the cap.
    """

    def __init__(
        self,
        ideators: list[IdeaIdeator],
        critic: IdeaCritic,
        synthesiser: IdeaSynthesiser,
        prior_art_agent: PriorArtAgent,
    ) -> None:
        self._ideators = {i.role_name: i for i in ideators}
        self._critic = critic
        self._synthesiser = synthesiser
        self._prior_art = prior_art_agent
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(IdeationCouncilState)
        builder.add_node("fan_out_ideators", self._run_ideators)
        builder.add_node("novelty", self._run_novelty)
        builder.add_node("revise", self._run_revision)
        builder.add_node("critic", self._run_critic)
        builder.add_node("synthesiser", self._run_synthesiser)
        builder.set_entry_point("fan_out_ideators")
        builder.add_edge("fan_out_ideators", "novelty")
        builder.add_edge("novelty", "critic")
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
        """Execute the council; returns (proposals, discarded candidates)."""
        logger.info(
            "IdeationCouncilGraph: starting with %d needs, %d ideators",
            len(selected_needs),
            len(self._ideators),
        )
        initial_state: IdeationCouncilState = {
            "selected_needs": selected_needs,
            "profile": profile,
            "graph_context": graph_context,
        }
        final_state = await self._compiled.ainvoke(initial_state)
        proposals: list[IdeationProposal] = final_state.get("final_proposals", [])
        return proposals, final_state.get("discards", [])

    async def _run_ideators(self, state: IdeationCouncilState) -> dict[str, Any]:
        roles = list(self._ideators)
        tasks = [
            self._ideators[role].run(
                state["selected_needs"], state["graph_context"], state["profile"]
            )
            for role in roles
        ]
        batches = await collect_batches(roles, tasks, "IdeationCouncilGraph")
        pool = assign_candidate_ids(batches)
        logger.info(
            "IdeationCouncilGraph: %d/%d ideators succeeded (%d candidates)",
            len(batches),
            len(roles),
            len(pool),
        )
        return {"candidates": pool, "report": None, "revision_round": 0}

    async def _run_novelty(self, state: IdeationCouncilState) -> dict[str, Any]:
        """Each ideator novelty-checks its own ideas and prunes duplicates."""
        by_role: dict[str, list[CandidateIdea]] = {}
        for candidate in state["candidates"]:
            by_role.setdefault(candidate.source_role, []).append(candidate)
        roles = [role for role in by_role if role in self._ideators]
        tasks = [
            self._ideators[role].novelty_filter(by_role[role], self._prior_art) for role in roles
        ]
        batches = await collect_batches(roles, tasks, "IdeationCouncilGraph.novelty")
        survivors = [c for _, (kept, _) in batches for c in kept]
        discards = [
            {
                "title": c.title,
                "description": c.description,
                "reason": "identified (semi-)duplicate during novelty check",
            }
            for _, (_, dropped) in batches
            for c in dropped
        ]
        logger.info(
            "IdeationCouncilGraph: novelty filter kept %d/%d candidates",
            len(survivors),
            len(state["candidates"]),
        )
        return {"candidates": survivors, "discards": discards}

    def _route_after_critic(self, state: IdeationCouncilState) -> str:
        """Conditional edge driven by the critic's own verdicts."""
        if should_revise(state["report"], state["revision_round"]):
            return "revise"
        return "synthesiser"

    async def _run_critic(self, state: IdeationCouncilState) -> dict[str, Any]:
        report = await self._critic.run(
            state["candidates"], state["profile"], evidence=state["graph_context"]
        )
        return {"report": report}

    async def _run_revision(self, state: IdeationCouncilState) -> dict[str, Any]:
        report = state["report"]
        assert report is not None  # only reachable via _route_after_critic
        contexts = {role: state["graph_context"] for role in self._ideators}
        pool = await run_targeted_revision(
            {role: agent.revise for role, agent in self._ideators.items()},
            report,
            state["candidates"],
            contexts,
            state["profile"],
            "IdeationCouncilGraph",
        )
        return {"candidates": pool, "revision_round": state["revision_round"] + 1}

    async def _run_synthesiser(self, state: IdeationCouncilState) -> dict[str, Any]:
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
        proposals = await self._synthesiser.run(
            state["candidates"], resolved, state["graph_context"], state["profile"]
        )
        return {
            "final_proposals": proposals,
            "discards": state.get("discards", []) + kills,
        }
