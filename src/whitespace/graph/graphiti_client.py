"""Graphiti instance lifecycle wrapper.

Builds a ``graphiti_core.Graphiti`` with all three OpenAI-compatible
components (LLM client, embedder, cross-encoder) explicitly constructed
from the session config. In BYOK mode these point at OpenRouter's
API; in SaaS mode they point at a Bedrock-compatible endpoint.
"""

from __future__ import annotations

import logging
from typing import Self

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from openai import AsyncOpenAI

from whitespace.closing import Closer, close_all
from whitespace.config import Config
from whitespace.graph.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class GraphitiClient:
    """Owns a Graphiti instance bound to the current session credentials."""

    def __init__(self, config: Config, neo4j: Neo4jClient) -> None:
        self._config = config
        self._neo4j = neo4j
        self._graphiti: Graphiti | None = None
        self._http_closers: list[Closer] = []

    async def initialise(self) -> None:
        if self._graphiti is not None:
            return

        api_key = self._config.openrouter_api_key
        if not api_key:
            raise RuntimeError("OpenRouter API key is not configured")

        driver = self._driver()
        model_http = AsyncOpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)
        embedder_http = AsyncOpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)
        reranker_http = AsyncOpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)
        llm_client = OpenAIClient(
            config=LLMConfig(
                api_key=api_key,
                model=self._config.graphiti_model,
                base_url=_OPENROUTER_BASE_URL,
            ),
            client=model_http,
        )
        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=api_key,
                base_url=_OPENROUTER_BASE_URL,
            ),
            client=embedder_http,
        )
        cross_encoder = OpenAIRerankerClient(
            config=LLMConfig(
                api_key=api_key,
                base_url=_OPENROUTER_BASE_URL,
            ),
            client=reranker_http,
        )

        self._start(driver, llm_client, embedder, cross_encoder)
        self._http_closers = [
            ("Graphiti model client", model_http.close),
            ("Graphiti embedder client", embedder_http.close),
            ("Graphiti reranker client", reranker_http.close),
        ]

    def _driver(self) -> Neo4jDriver:
        return Neo4jDriver(
            uri=self._config.neo4j_uri,
            user=self._config.neo4j_username,
            password=self._config.neo4j_password,
            database=self._config.neo4j_database or "neo4j",
        )

    def _start(
        self,
        driver: Neo4jDriver,
        llm_client: LLMClient,
        embedder: EmbedderClient,
        cross_encoder: CrossEncoderClient,
    ) -> None:
        logger.info("GraphitiClient: initialising")
        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

    async def ensure_indices_and_constraints(self) -> None:
        if self._graphiti is None:
            raise RuntimeError(
                "GraphitiClient.ensure_indices_and_constraints called before initialise"
            )
        await self._graphiti.build_indices_and_constraints()

    async def close(self) -> None:
        """Close Graphiti, then its model, embedder and reranker HTTP clients.

        The handles are cleared first. Every close is attempted, each within its time
        limit; an interruption of one is raised after the others.
        """
        if self._graphiti is None:
            return
        graphiti, http_closers = self._graphiti, self._http_closers
        self._graphiti = None
        self._http_closers = []
        await close_all([("Graphiti", graphiti.close), *http_closers])

    @property
    def graphiti(self) -> Graphiti:
        if self._graphiti is None:
            raise RuntimeError("GraphitiClient is not initialised — call initialise() first")
        return self._graphiti

    async def __aenter__(self) -> Self:
        await self.initialise()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
