"""Neo4j async driver lifecycle wrapper.

A small adapter over ``neo4j.AsyncGraphDatabase.driver`` that gives us
lifecycle methods (``connect``/``close``) matching the per-request resource
model, plus an async context manager to prevent leaks.
"""

from __future__ import annotations

import logging
from typing import Self

from neo4j import AsyncDriver, AsyncGraphDatabase

from whitespace.config import Config

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Owns the neo4j async driver for a single request/session."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Open the driver connection. Idempotent."""
        if self._driver is not None:
            return
        logger.info("Neo4jClient: connecting to %s", self._config.neo4j_uri)
        self._driver = AsyncGraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_username, self._config.neo4j_password),
        )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        """Close the driver. Errors are logged, never re-raised."""
        if self._driver is None:
            return
        try:
            await self._driver.close()
        except Exception:
            logger.exception("Neo4jClient: error closing driver")
        finally:
            self._driver = None

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected — call connect() first")
        return self._driver

    @property
    def database(self) -> str:
        return self._config.neo4j_database or "neo4j"

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
