"""Composition of the focused graph query tools.

Bundles ``GraphEdgeTools``, ``GraphNodeTools`` and ``GraphEpisodeTools``
behind a single object so agents can hold one dependency. Each sub-tool
is reachable as ``.edges``, ``.nodes`` and ``.episodes`` respectively.
"""

from __future__ import annotations

from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.tools.graph.edges import GraphEdgeTools
from whitespace.tools.graph.episodes import GraphEpisodeTools
from whitespace.tools.graph.nodes import GraphNodeTools


class GraphTools:
    """Aggregate of edge, node and episode query tools."""

    def __init__(self, graphiti: GraphitiClient, neo4j: Neo4jClient) -> None:
        self.edges = GraphEdgeTools(graphiti, neo4j)
        self.nodes = GraphNodeTools(graphiti, neo4j)
        self.episodes = GraphEpisodeTools(neo4j)
