"""Opening and closing the pipeline's graph connections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from whitespace.closing import close_all

if TYPE_CHECKING:
    from whitespace.graph.graphiti_client import GraphitiClient
    from whitespace.graph.neo4j_client import Neo4jClient


class PipelineLifecycleMixin:
    """Connects and closes the graph clients, but only when the pipeline owns them.

    A pipeline built on kept clients does not own them: whoever keeps the clients
    opens and closes them, so ``initialise`` and ``close`` return at once.
    """

    _neo4j: Neo4jClient
    _graphiti: GraphitiClient
    _owns_shared: bool

    async def initialise(self) -> None:
        """Connect Neo4j and initialise Graphiti. Call before any run."""
        if not self._owns_shared:
            return
        await self._neo4j.connect()
        await self._graphiti.initialise()

    async def close(self) -> None:
        """Close Graphiti, then Neo4j; an interruption of one does not skip the other."""
        if not self._owns_shared:
            return
        await close_all(
            [("Graphiti client", self._graphiti.close), ("Neo4j client", self._neo4j.close)],
            seconds=None,
        )

    async def __aenter__(self) -> Self:
        await self.initialise()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
