"""Council research phase: query, research and identifier nodes for GapCouncilGraph."""

from __future__ import annotations

import logging
from typing import Any

from whitespace.agents.council._question_proposals import resolve_question_candidate_ids
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.orchestration._council_common import assign_candidate_ids, collect_batches
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._research_stage import ResearchStage, format_findings

logger = logging.getLogger(__name__)


async def run_craft_queries_node(
    identifiers: dict[str, GapIdentifier], state: GapCouncilState
) -> dict[str, Any]:
    """Each identifier writes queries; duplicates across identifiers are dropped."""
    roles = list(identifiers)
    memory = state["run_memory"]
    tasks = [
        identifiers[role].craft_queries(
            state["domain"], state["profile"], memory.prior_queries, memory.neighbours
        )
        for role in roles
    ]
    batches = await collect_batches(roles, tasks, "GapCouncilGraph.queries")
    queries: list[str] = []
    for _, batch in batches:
        queries.extend(q for q in batch if q not in queries)
    return {"queries": queries}


async def run_research_node(research: ResearchStage, state: GapCouncilState) -> dict[str, Any]:
    """Run every query, build the graph once, and render the findings channel."""
    findings = await research.research(
        state["queries"],
        domain=state["domain"],
        keep_findings=state["keep_findings"],
        run_id=state["run_id"],
        prior_queries=state["run_memory"].prior_queries,
        prior_findings=state["run_memory"].prior_findings,
    )
    await research.ingest(state["doc_paths"], findings)
    return {"findings_text": format_findings(findings)}


async def run_identifiers_node(
    identifiers: dict[str, GapIdentifier], research: ResearchStage, state: GapCouncilState
) -> dict[str, Any]:
    """Each identifier analyses both channels; the pool passes the duplicate gate."""
    roles = list(identifiers)
    mem = state["run_memory"]
    tasks = [
        identifiers[role].run(state["profile"], state["findings_text"], mem.memory, mem.neighbours)
        for role in roles
    ]
    batches = await collect_batches(roles, tasks, "GapCouncilGraph")
    pool = assign_candidate_ids([(role, out.gaps) for role, out in batches])
    pool, flags = await research.gate_pool(
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
