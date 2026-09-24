"""LangGraph for gap analysis: research → ingest → two-channel council."""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from langgraph.graph import END, StateGraph

from whitespace.agents.council._question_proposals import resolve_question_candidate_ids
from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._council_common import (
    assign_candidate_ids,
    collect_batches,
    should_revise,
)
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._gap_critique_phase import (
    run_critic_node,
    run_revision_node,
    run_synth_node,
)
from whitespace.orchestration._gap_question_stage import run_question_gate_node
from whitespace.orchestration._research_stage import (
    ResearchStage,
    RunMemory,
    format_findings,
)
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile

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
    ) -> None:
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
            ("critic", self._run_critic),
            ("revise", self._run_revision),
            ("synthesiser", self._run_synthesiser),
        ]:
            builder.add_node(name, fn)
        builder.set_entry_point("critic")
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
    ) -> list[UnmetNeed]:
        initial_state: GapCouncilState = {
            "domain": domain,
            "profile": profile,
            "doc_paths": doc_paths or [],
            "keep_findings": keep_findings,
            "run_id": run_id or str(uuid.uuid4()),
            "run_memory": run_memory or RunMemory(),
        }
        mid_state = await self.run_first_half(initial_state)
        if mid_state.get("pending_questions"):
            raise RuntimeError("run() cannot pause for questions; call the halves directly")
        return await self.run_second_half(mid_state)

    async def run_first_half(self, initial: GapCouncilState) -> GapCouncilState:
        """Research the domain and return candidates, evidence and any questions to ask."""
        return cast(GapCouncilState, await self._first_half.ainvoke(initial))

    async def run_second_half(self, state: GapCouncilState) -> list[UnmetNeed]:
        """Critique, revise, and synthesise an existing candidate pool."""
        final_state = await self._second_half.ainvoke(state)
        return cast(list[UnmetNeed], final_state.get("synthesised_needs", []))

    async def _run_craft_queries(self, state: GapCouncilState) -> dict[str, Any]:
        roles = list(self._identifiers)
        memory = state["run_memory"]
        tasks = [
            self._identifiers[role].craft_queries(
                state["domain"], state["profile"], memory.prior_queries, memory.neighbours
            )
            for role in roles
        ]
        batches = await collect_batches(roles, tasks, "GapCouncilGraph.queries")
        queries: list[str] = []
        for _, batch in batches:
            queries.extend(q for q in batch if q not in queries)
        return {"queries": queries}

    async def _run_research(self, state: GapCouncilState) -> dict[str, Any]:
        findings = await self._research.research(
            state["queries"],
            domain=state["domain"],
            keep_findings=state["keep_findings"],
            run_id=state["run_id"],
            prior_queries=state["run_memory"].prior_queries,
            prior_findings=state["run_memory"].prior_findings,
        )
        await self._research.ingest(state["doc_paths"], findings)
        return {"findings_text": format_findings(findings)}

    async def _run_identifiers(self, state: GapCouncilState) -> dict[str, Any]:
        roles = list(self._identifiers)
        mem = state["run_memory"]
        tasks = [
            self._identifiers[role].run(
                state["profile"], state["findings_text"], mem.memory, mem.neighbours
            )
            for role in roles
        ]
        batches = await collect_batches(roles, tasks, "GapCouncilGraph")
        pool = assign_candidate_ids([(role, out.gaps) for role, out in batches])
        pool, flags = await self._research.gate_pool(
            pool, state["run_memory"].prior_texts, state["run_id"], "gap", state["domain"]
        )
        proposals = resolve_question_candidate_ids(
            [question for _, output in batches for question in output.proposed_questions],
            pool,
        )
        logger.info("GapCouncilGraph: %d candidates after gate", len(pool))
        return {
            "candidates": pool,
            "proposed_questions": proposals,
            "gate_flags": flags,
            "findings_by_role": {role: out.findings for role, out in batches},
            "report": None,
            "revision_round": 0,
        }

    async def _run_question_gate(self, state: GapCouncilState) -> dict[str, Any]:
        dedup = self._research.deduplicator
        return await run_question_gate_node(self._question_gate, dedup, state)

    def _route_after_critic(self, state: GapCouncilState) -> str:
        rd, rr = state["report"], state["revision_round"]
        return "revise" if should_revise(rd, rr) else "synthesiser"

    async def _run_critic(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_critic_node(self._identifiers, self._critic, self._research, state)

    async def _run_revision(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_revision_node(self._identifiers, self._research, state)

    async def _run_synthesiser(self, state: GapCouncilState) -> dict[str, Any]:
        return await run_synth_node(self._synthesiser, self._research, state)
