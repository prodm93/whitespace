"""Prior-art agent — the council's shared research executor.

Callers (gap identifiers at research time, ideators at novelty-check
time) craft their own queries; this agent executes them across USPTO,
Semantic Scholar, and the web, returning dated findings. Judgment about
the results stays with the caller.
"""

from __future__ import annotations

import logging

from whitespace.config import Config
from whitespace.schemas.research import RawFinding
from whitespace.tools.search.research_executor import ResearchExecutor

logger = logging.getLogger(__name__)


class PriorArtAgent:
    """Executes research queries for the councils."""

    def __init__(self, config: Config, executor: ResearchExecutor) -> None:
        self._config = config
        self._executor = executor

    async def research(
        self,
        queries: list[str],
        *,
        per_query: int = 8,
    ) -> list[RawFinding]:
        """Run the given queries across all three search surfaces."""
        if not queries:
            return []
        logger.info("PriorArtAgent: executing %d queries", len(queries))
        return await self._executor.run(queries, per_query=per_query)
