"""The clients that own a network connection and outlive a single run.

These objects hold connections and credentials only. They never hold a tenant ID, a
graph namespace or a session store, so one set can serve the runs of different
tenants in turn. Everything bound to a tenant is built for each run on top of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.models.providers import ProviderFactory

if TYPE_CHECKING:
    from graphiti_core.driver.neo4j_driver import Neo4jDriver


@dataclass(frozen=True)
class SharedClients:
    """Neo4j client, Graphiti client and model provider factory, kept together."""

    neo4j: Neo4jClient
    graphiti: GraphitiClient
    provider_factory: ProviderFactory

    async def initialise(self) -> None:
        """Connect Neo4j, then initialise Graphiti on top of it."""
        await self.neo4j.connect()
        await self.graphiti.initialise()

    async def close(self) -> None:
        """Close Graphiti, then Neo4j."""
        await self.graphiti.close()
        await self.neo4j.close()

    async def check(self) -> None:
        """Ask both drivers for an answer; raise the driver's error when either fails.

        Graphiti's ``Neo4jDriver`` has ``health_check`` and no ``verify_connectivity``;
        ``GraphitiClient`` always builds that driver.
        """
        await self.neo4j.driver.verify_connectivity()
        await cast("Neo4jDriver", self.graphiti.graphiti.driver).health_check()
