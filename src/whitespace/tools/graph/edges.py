"""Edge queries over Graphiti + Neo4j.

Pure I/O. ``search_edges`` wraps Graphiti's ``search()`` (BM25 + cosine
over fact text, optionally reranked by graph distance from a centre
node). ``fetch_edges`` enumerates every ``RELATES_TO`` edge incident on
a given entity via a direct Cypher query against the Neo4j driver.
"""

from __future__ import annotations

import logging
from typing import Any

from whitespace.domain import Edge
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


_FETCH_EDGES_CYPHER = """
MATCH (n {uuid: $uuid, group_id: $group_id})-[r:RELATES_TO]-(m)
WHERE r.group_id = $group_id
  AND ($edge_type IS NULL OR r.name = $edge_type)
RETURN
  r.uuid AS uuid,
  r.name AS edge_type,
  startNode(r).uuid AS source_id,
  endNode(r).uuid AS target_id,
  r.fact AS fact,
  r.attributes AS attributes,
  r.episodes AS episodes
LIMIT $limit
"""


class GraphEdgeTools:
    """Edge-side reads against the knowledge graph."""

    def __init__(self, graphiti: GraphitiClient, neo4j: Neo4jClient) -> None:
        self._graphiti = graphiti
        self._neo4j = neo4j

    async def fetch_edges(
        self,
        node_id: str,
        group_id: str,
        edge_type: str | None = None,
        limit: int = 25,
    ) -> list[Edge]:
        """Fetch every ``RELATES_TO`` edge incident on ``node_id`` within ``group_id``."""
        try:
            async with self._neo4j.driver.session(database=self._neo4j.database) as session:
                records = await session.run(
                    _FETCH_EDGES_CYPHER,
                    uuid=node_id,
                    group_id=group_id,
                    edge_type=edge_type,
                    limit=limit,
                )
                rows = [record.data() async for record in records]
        except Exception:
            logger.exception("fetch_edges failed for node=%s group=%s", node_id, group_id)
            return []

        edges: list[Edge] = []
        for row in rows:
            attrs: dict[str, Any] = {}
            raw_attrs = row.get("attributes")
            if isinstance(raw_attrs, dict):
                attrs.update(raw_attrs)
            fact = row.get("fact")
            if fact:
                attrs["fact"] = fact
            episodes = row.get("episodes")
            if isinstance(episodes, list):
                attrs["episodes"] = list(episodes)
            edges.append(
                Edge(
                    id=row["uuid"],
                    edge_type=row.get("edge_type") or "RELATES_TO",
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    properties=attrs,
                )
            )
        return edges

    async def search_edges(
        self,
        query: str,
        group_id: str,
        limit: int = 20,
        center_node_uuid: str | None = None,
    ) -> list[Edge]:
        """Hybrid search for fact edges, optionally reranked by graph distance."""
        try:
            results = await self._graphiti.graphiti.search(
                query=query,
                group_ids=[group_id],
                num_results=limit,
                center_node_uuid=center_node_uuid,
            )
        except Exception:
            logger.exception(
                "search_edges failed for query=%r group=%s center=%s",
                query,
                group_id,
                center_node_uuid,
            )
            return []

        return _entity_edges_to_domain(results)


def _entity_edges_to_domain(results: list[Any]) -> list[Edge]:
    edges: list[Edge] = []
    for entity_edge in results:
        attrs: dict[str, Any] = {}
        raw_attrs = getattr(entity_edge, "attributes", None)
        if isinstance(raw_attrs, dict):
            attrs.update(raw_attrs)
        if entity_edge.fact:
            attrs["fact"] = entity_edge.fact
        episodes = getattr(entity_edge, "episodes", None)
        if isinstance(episodes, list):
            attrs["episodes"] = list(episodes)
        for tkey in ("valid_at", "invalid_at", "reference_time", "created_at"):
            tval = getattr(entity_edge, tkey, None)
            if tval is not None:
                attrs[tkey] = tval.isoformat() if hasattr(tval, "isoformat") else str(tval)
        edges.append(
            Edge(
                id=entity_edge.uuid,
                edge_type=entity_edge.name or "RELATES_TO",
                source_id=entity_edge.source_node_uuid,
                target_id=entity_edge.target_node_uuid,
                properties=attrs,
            )
        )
    return edges
