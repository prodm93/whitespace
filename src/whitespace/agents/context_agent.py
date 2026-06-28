"""Context agent — formulates LLM-ready context from the knowledge graph.

Edge-first retrieval: Graphiti's hybrid search ranks fact edges by
relevance (BM25 + cosine, fused via RRF), then a second pass reranks
by graph distance from the top hit. Endpoint UUIDs are resolved to
entity names, and source episode chunks are pulled so the generator
can ground phrasing back to the corpus.
"""

from __future__ import annotations

import logging

from whitespace.agents._context_helpers import (
    EMPTY_CONTEXT,
    collect_episode_uuids,
    render,
)
from whitespace.agents.retrieval_planner_agent import RetrievalPlannerAgent
from whitespace.config import Config
from whitespace.domain import Edge
from whitespace.schemas.retrieval_plan import RetrievalPlan
from whitespace.tools.graph_tools import GraphTools

logger = logging.getLogger(__name__)

_EDGE_LIMIT = 20
_MAX_CHUNKS = 8
_MAX_CONTEXT_CHARS = 24000


class ContextAgent:
    """Builds a structured context string for the generator from the graph."""

    def __init__(
        self,
        config: Config,
        graph_tools: GraphTools,
        planner_agent: RetrievalPlannerAgent | None = None,
    ) -> None:
        self._config = config
        self._graph_tools = graph_tools
        self._planner_agent = planner_agent

    async def run(self, query: str) -> str:
        logger.info("ContextAgent: building context for %d-char query", len(query))
        if not query.strip():
            return EMPTY_CONTEXT
        if self._planner_agent is None:
            return await self._run_edge_hybrid(query)
        try:
            plan = await self._planner_agent.plan(query)
            rendered = await self._run_plan(query, plan)
            if rendered != EMPTY_CONTEXT:
                return rendered
            if plan.strategy == "gap_analysis":
                return rendered
            logger.warning("Planned retrieval returned empty context; falling back")
        except Exception:
            logger.exception("Planned retrieval failed; falling back")
        return await self._run_edge_hybrid(query)

    async def _run_plan(self, query: str, plan: RetrievalPlan) -> str:
        if plan.strategy == "gap_analysis":
            return await self._run_edge_hybrid(query)
        if plan.strategy == "skill_matching":
            return await self._run_centered_rerank(
                query,
                entity_hint=plan.params.entity_name,
            )
        if plan.strategy == "citation_chain":
            return await self._run_entity_lookup(
                plan.params.entity_name or "",
                edge_type=plan.params.edge_type_filter,
            )
        if plan.strategy == "entity_focused":
            return await self._run_entity_lookup(plan.params.entity_name or "")
        raise ValueError(f"Unsupported retrieval strategy: {plan.strategy}")

    async def _run_edge_hybrid(self, query: str) -> str:
        group_id = self._config.graphiti_namespace
        edges = await self._graph_tools.edges.search_edges(
            query=query,
            group_id=group_id,
            limit=_EDGE_LIMIT,
        )
        return await self._render_edges(edges, group_id)

    async def _run_centered_rerank(
        self,
        query: str,
        *,
        entity_hint: str | None = None,
    ) -> str:
        group_id = self._config.graphiti_namespace
        anchor_uuid: str | None = None
        if entity_hint:
            nodes = await self._graph_tools.nodes.find_entity_by_name(
                entity_name=entity_hint,
                group_id=group_id,
                limit=1,
            )
            if nodes:
                anchor_uuid = nodes[0].id
        if anchor_uuid is None:
            edges = await self._graph_tools.edges.search_edges(
                query=query,
                group_id=group_id,
                limit=_EDGE_LIMIT,
            )
            if not edges:
                return EMPTY_CONTEXT
            anchor_uuid = edges[0].source_id
        reranked = await self._graph_tools.edges.search_edges(
            query=query,
            group_id=group_id,
            limit=_EDGE_LIMIT,
            center_node_uuid=anchor_uuid,
        )
        return await self._render_edges(reranked, group_id)

    async def _run_entity_lookup(
        self,
        entity_name: str,
        edge_type: str | None = None,
    ) -> str:
        if not entity_name.strip():
            return EMPTY_CONTEXT
        group_id = self._config.graphiti_namespace
        nodes = await self._graph_tools.nodes.find_entity_by_name(
            entity_name=entity_name,
            group_id=group_id,
            limit=1,
        )
        if not nodes:
            return EMPTY_CONTEXT
        edges = await self._graph_tools.edges.fetch_edges(
            node_id=nodes[0].id,
            group_id=group_id,
            limit=_EDGE_LIMIT,
            edge_type=edge_type,
        )
        return await self._render_edges(edges, group_id)

    async def _render_edges(self, edges: list[Edge], group_id: str) -> str:
        if not edges:
            return EMPTY_CONTEXT

        endpoint_uuids = list({e.source_id for e in edges} | {e.target_id for e in edges})
        name_by_uuid = await self._graph_tools.nodes.fetch_node_names(
            uuids=endpoint_uuids,
            group_id=group_id,
        )

        episode_order = collect_episode_uuids(edges, max_chunks=_MAX_CHUNKS)
        chunks = await self._graph_tools.episodes.fetch_episode_chunks(
            episode_uuids=episode_order,
            group_id=group_id,
        )

        rendered = render(edges, name_by_uuid, episode_order, chunks)
        if len(rendered) > _MAX_CONTEXT_CHARS:
            rendered = rendered[:_MAX_CONTEXT_CHARS].rstrip() + "\n…"
        return rendered
