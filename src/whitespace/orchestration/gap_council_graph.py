"""LangGraph for gap analysis: research, then ingest, then a two-channel council."""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from langgraph.graph import END, StateGraph

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._council_common import should_revise
from whitespace.orchestration._gap_answer_stage import run_refine_node
from whitespace.orchestration._gap_council_state import (
    GapCouncilState,
    build_initial_gap_state,
)
from whitespace.orchestration._gap_critique_phase import (
    run_critic_node,
    run_revision_node,
    run_synth_node,
)
from whitespace.orchestration._gap_question_stage import run_question_gate_node
from whitespace.orchestration._gap_research_phase import (
    run_craft_queries_node,
    run_identifiers_node,
    run_research_node,
)
from whitespace.orchestration._gap_snapshot import GapSnapshotWriter
from whitespace.orchestration._research_stage import ResearchStage, RunMemory
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import UserAnswer

logger = logging.getLogger(__name__)


class GapCouncilGraph:
    """Research first, ingest once, then a two-channel council."""

    def __init__(
        self,
        identifiers: list[GapIdentifier],
        critic: GapCritic,
        synthesiser: GapSynthesiser,
        research_stage: ResearchStage,
        question_gate: QuestionGate | None = None,
        snapshot_writer: GapSnapshotWriter | None = None,
    ) -> None:
        self._snapshot_writer = snapshot_writer
        self._identifiers = {i.role_name: i for i in identifiers}
        self._critic = critic
        self._synthesiser = synthesiser
        self._research = research_stage
        self._question_gate = question_gate
        self._first_half = self._build_first_half()
        self._second_half = self._build_second_half()

    def _build_first_half(self) -> Any:
        builder = StateGraph(GapCouncilState)
        builder.add_node("craft_queries", self._run_craft_queries)
        builder.add_node("research", self._run_research)
        builder.add_node("fan_out_identifiers", self._run_identifiers)
        builder.add_node("question_gate_node", self._run_question_gate)
        builder.set_entry_point("craft_queries")
        builder.add_edge("craft_queries", "research")
        builder.add_edge("research", "fan_out_identifiers")
        builder.add_edge("fan_out_identifiers", "question_gate_node")
        builder.add_edge("question_gate_node", END)
        return builder.compile()

    def _build_second_half(self) -> Any:
        builder = StateGraph(GapCouncilState)
        for name, fn in [
            ("refine_with_answers", self._run_refine),
            ("critic", self._run_critic),
            ("revise", self._run_revision),
            ("synthesiser", self._run_synthesiser),
        ]:
            builder.add_node(name, fn)
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
        profile: ProfessionalProfile,
        domain: str,
        doc_paths: list[str] | None = None,
        *,
        keep_findings: bool = False,
        run_id: str | None = None,
        run_memory: RunMemory | None = None,
    ) -> tuple[list[UnmetNeed], list[dict[str, str]]]:
        initial = build_initial_gap_state(
            profile,
            domain,
            doc_paths,
            keep_findings=keep_findings,
            run_id=run_id or str(uuid.uuid4()),
            run_memory=run_memory or RunMemory(),
            questions_enabled=False,
        )
        return await self.run_second_half(await self.run_first_half(initial))

    async def run_first_half(self, initial: GapCouncilState) -> GapCouncilState:
        """Research the domain and return candidates, evidence and any questions to ask."""
        mid_state = cast(GapCouncilState, await self._first_half.ainvoke(initial))
        if self._snapshot_writer is not None:
            await self._snapshot_writer.save(mid_state)
        return mid_state

    async def run_second_half(
        self, state: GapCouncilState, answers: list[UserAnswer] | None = None
    ) -> tuple[list[UnmetNeed], list[dict[str, str]]]:
        """Refine with the answers, critique, revise and synthesise; store nothing.

        Returns the needs and the final discards (the critic's kills plus the
        held discards). Storing them is the caller's job.
        """
        if answers is not None:
            state = {**state, "user_answers": answers}
        final_state = await self._second_half.ainvoke(state)
        needs = cast(list[UnmetNeed], final_state.get("synthesised_needs", []))
        discards = cast(list[dict[str, str]], final_state.get("final_discards", []))
        return needs, discards

    async def _run_craft_queries(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_craft_queries_node(self._identifiers, state)

    async def _run_research(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_research_node(self._research, state)

    async def _run_identifiers(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_identifiers_node(self._identifiers, self._research, state)

    async def _run_question_gate(self, state: GapCouncilState) -> dict[str, Any]:
        if state.get("questions_enabled") is not True:
            return {"pending_questions": []}
        dedup = self._research.deduplicator
        return await run_question_gate_node(self._question_gate, dedup, state)

    def _route_after_critic(self, state: GapCouncilState) -> str:
        rd, rr = state["report"], state["revision_round"]
        return "revise" if should_revise(rd, rr) else "synthesiser"

    async def _run_refine(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_refine_node(self._identifiers, self._research, state)

    async def _run_critic(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_critic_node(self._identifiers, self._critic, self._research, state)

    async def _run_revision(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_revision_node(self._identifiers, self._research, state)

    async def _run_synthesiser(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_synth_node(self._synthesiser, self._research, state)
