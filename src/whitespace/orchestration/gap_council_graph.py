"""LangGraph for gap analysis: research → ingest → two-channel council."""

from __future__ import annotations

import logging
import uuid
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
from whitespace.orchestration._research_stage import (
    ResearchStage,
    RunMemory,
    format_findings,
)
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import CandidateGap, GapExploration, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_MAX_EVIDENCE_CHARS = 40000


class GapCouncilState(TypedDict, total=False):
    domain: str
    profile: ProfessionalProfile
    doc_paths: list[str]
    keep_findings: bool
    run_id: str
    run_memory: RunMemory
    queries: list[str]
    findings_text: str
    findings_by_role: dict[str, str]
    candidates: list[CandidateGap]
    report: CriticReport | None
    revision_round: int
    synthesised_needs: list[UnmetNeed]


class GapCouncilGraph:
    """Research first, ingest once, then a two-channel council."""

    def __init__(
        self,
        identifiers: list[GapIdentifier],
        critic: GapCritic,
        synthesiser: GapSynthesiser,
        research_stage: ResearchStage,
    ) -> None:
        self._identifiers = {i.role_name: i for i in identifiers}
        self._critic = critic
        self._synthesiser = synthesiser
        self._research = research_stage
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(GapCouncilState)
        for name, fn in [
            ("craft_queries", self._run_craft_queries),
            ("research", self._run_research),
            ("fan_out_identifiers", self._run_identifiers),
            ("critic", self._run_critic),
            ("revise", self._run_revision),
            ("synthesiser", self._run_synthesiser),
        ]:
            builder.add_node(name, fn)
        builder.set_entry_point("craft_queries")
        builder.add_edge("craft_queries", "research")
        builder.add_edge("research", "fan_out_identifiers")
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
        final_state = await self._compiled.ainvoke(initial_state)
        needs: list[UnmetNeed] = final_state.get("synthesised_needs", [])
        return needs

    async def _run_craft_queries(self, state: GapCouncilState) -> dict[str, Any]:
        roles = list(self._identifiers)
        memory = state["run_memory"]
        tasks = [
            self._identifiers[role].craft_queries(
                state["domain"], state["profile"], memory.prior_queries
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
            keep_findings=state["keep_findings"],
            run_id=state["run_id"],
            prior_queries=state["run_memory"].prior_queries,
            prior_findings=state["run_memory"].prior_findings,
        )
        await self._research.ingest(state["doc_paths"], findings)
        return {"findings_text": format_findings(findings)}

    async def _run_identifiers(self, state: GapCouncilState) -> dict[str, Any]:
        roles = list(self._identifiers)
        tasks = [
            self._identifiers[role].run(
                state["profile"], state["findings_text"], state["run_memory"].memory
            )
            for role in roles
        ]
        batches: list[tuple[str, GapExploration]] = await collect_batches(
            roles, tasks, "GapCouncilGraph"
        )
        pool = assign_candidate_ids([(role, out.gaps) for role, out in batches])
        pool = await self._research.gate_pool(
            pool, state["run_memory"].prior_texts, state["run_id"], "gap"
        )
        logger.info("GapCouncilGraph: %d candidates after gate", len(pool))
        return {
            "candidates": pool,
            "findings_by_role": {role: out.findings for role, out in batches},
            "report": None,
            "revision_round": 0,
        }

    async def _run_critic(self, state: GapCouncilState) -> dict[str, Any]:
        report = await self._critic.run(
            state["candidates"], state["profile"], evidence=state["findings_text"]
        )
        return {"report": report}

    def _route_after_critic(self, state: GapCouncilState) -> str:
        return (
            "revise" if should_revise(state["report"], state["revision_round"]) else "synthesiser"
        )

    async def _run_revision(self, state: GapCouncilState) -> dict[str, Any]:
        report = state["report"]
        assert report is not None
        pool = await run_targeted_revision(
            {role: agent.revise for role, agent in self._identifiers.items()},
            report,
            state["candidates"],
            state["findings_by_role"],
            state["profile"],
            "GapCouncilGraph",
        )
        return {"candidates": pool, "revision_round": state["revision_round"] + 1}

    async def _run_synthesiser(self, state: GapCouncilState) -> dict[str, Any]:
        report = state["report"]
        assert report is not None
        resolved = resolve_final(report)
        await self._research.record_kills(resolved, state["candidates"], state["run_id"], "gap")
        roles = {c.source_role for c in state["candidates"] if c.candidate_id in report.ranking}
        evidence = state["findings_text"] + "".join(
            f"\n\n## Exploration by {r}\n{state['findings_by_role'].get(r, '')}"
            for r in sorted(roles)
        )
        needs = await self._synthesiser.run(
            state["candidates"], resolved, evidence[:_MAX_EVIDENCE_CHARS], state["profile"]
        )
        return {"synthesised_needs": needs}
