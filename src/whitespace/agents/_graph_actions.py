"""Knowledge-graph exploration actions exposed to agents as tools.

Thin judgment-free wrappers over ``GraphTools`` that render results as
text an LLM can read. Which action to call, with what query, and when to
stop is entirely the calling agent's decision.
"""

from __future__ import annotations

import logging
from typing import Any

from whitespace.config import Config
from whitespace.domain import Edge
from whitespace.tools.graph_tools import GraphTools

logger = logging.getLogger(__name__)

_EDGE_LIMIT = 12
_ENTITY_LIMIT = 10
_MAX_RESULT_CHARS = 6000

_NOTHING = "Nothing found. Try different wording."


class GraphActions:
    """LLM-facing graph exploration toolkit built on GraphTools."""

    def __init__(self, config: Config, graph_tools: GraphTools) -> None:
        self._config = config
        self._graph = graph_tools

    def tool_definitions(self) -> list[dict[str, Any]]:
        query_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        name_schema = {
            "type": "object",
            "properties": {"entity_name": {"type": "string"}},
            "required": ["entity_name"],
        }
        return [
            {
                "name": "search_graph",
                "description": (
                    "Semantic search over relationships in the knowledge "
                    "graph. Returns the most relevant facts (entity → "
                    "relationship → entity). Best first move; try multiple "
                    "phrasings — limitations, complaints, technology names."
                ),
                "parameters": query_schema,
            },
            {
                "name": "list_entities",
                "description": (
                    "Find entities in the graph matching a keyword or "
                    "topic. Returns names and one-line summaries. Use to "
                    "discover what the graph knows before inspecting."
                ),
                "parameters": query_schema,
            },
            {
                "name": "inspect_entity",
                "description": (
                    "Fetch every relationship the graph holds for one named "
                    "entity. Use after search_graph or list_entities "
                    "surfaces something worth digging into."
                ),
                "parameters": name_schema,
            },
        ]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "search_graph":
            return await self._search_graph(str(arguments.get("query", "")))
        if name == "list_entities":
            return await self._list_entities(str(arguments.get("query", "")))
        if name == "inspect_entity":
            return await self._inspect_entity(str(arguments.get("entity_name", "")))
        return f"Unknown tool: {name}"

    async def _search_graph(self, query: str) -> str:
        if not query.strip():
            return _NOTHING
        group_id = self._config.graphiti_namespace
        edges = await self._graph.edges.search_edges(
            query=query, group_id=group_id, limit=_EDGE_LIMIT
        )
        return await self._render_edges(edges, group_id)

    async def _list_entities(self, query: str) -> str:
        if not query.strip():
            return _NOTHING
        group_id = self._config.graphiti_namespace
        nodes = await self._graph.nodes.search_nodes(
            query=query, group_id=group_id, limit=_ENTITY_LIMIT
        )
        if not nodes:
            return _NOTHING
        lines = []
        for node in nodes:
            summary = str(node.properties.get("summary", "")).strip()
            lines.append(f"- {node.name}" + (f": {summary}" if summary else ""))
        return "\n".join(lines)[:_MAX_RESULT_CHARS]

    async def _inspect_entity(self, entity_name: str) -> str:
        if not entity_name.strip():
            return _NOTHING
        group_id = self._config.graphiti_namespace
        nodes = await self._graph.nodes.find_entity_by_name(
            entity_name=entity_name, group_id=group_id, limit=1
        )
        if not nodes:
            return f"No entity named '{entity_name}' in the graph."
        edges = await self._graph.edges.fetch_edges(
            node_id=nodes[0].id, group_id=group_id, limit=_EDGE_LIMIT * 2
        )
        return await self._render_edges(edges, group_id)

    async def _render_edges(self, edges: list[Edge], group_id: str) -> str:
        if not edges:
            return _NOTHING
        uuids = list({e.source_id for e in edges} | {e.target_id for e in edges})
        names = await self._graph.nodes.fetch_node_names(uuids=uuids, group_id=group_id)
        lines = []
        for edge in edges:
            props = edge.properties or {}
            src = names.get(edge.source_id) or edge.source_id[:8]
            tgt = names.get(edge.target_id) or edge.target_id[:8]
            fact = str(props.get("fact", "")).strip()
            line = f"- {src} —[{edge.edge_type}]→ {tgt}"
            if fact:
                line += f": {fact}"
            when = props.get("valid_at") or props.get("reference_time")
            if when:
                line += f" [as of {str(when)[:10]}]"
            lines.append(line)
        return "\n".join(lines)[:_MAX_RESULT_CHARS]
