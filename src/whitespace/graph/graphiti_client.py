"""Graphiti instance lifecycle wrapper.

Builds a ``graphiti_core.Graphiti`` with its three model services (language model,
embedder, reranker) explicitly constructed from the session config. In BYOK mode they
are Graphiti's OpenAI-compatible clients pointed at OpenRouter's API. In SaaS mode they
are Bedrock adapters, signed by the function's own AWS role, with no stored model key.
"""

from __future__ import annotations

import asyncio
import functools
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
from whitespace.graph._bedrock_calls import agent_runtime_client, runtime_client
from whitespace.graph._bedrock_embedder import BedrockEmbedder
from whitespace.graph._bedrock_llm import BedrockLLMClient
from whitespace.graph._bedrock_reranker import BedrockReranker
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

        if self._config.mode == "saas":
            llm, embedder, reranker = self._bedrock_components()
            self._start(self._driver(), llm, embedder, reranker)
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

    def _bedrock_components(self) -> tuple[LLMClient, EmbedderClient, CrossEncoderClient]:
        """Build the two Bedrock clients and the three adapters over them.

        Each client's close is recorded as soon as the client is built, so a later failure
        of ``initialise`` still leaves it for ``close``.
        """
        config = self._config
        region = config.aws_region
        runtime = runtime_client(region)
        self._http_closers.append(
            ("Graphiti Bedrock runtime client", functools.partial(asyncio.to_thread, runtime.close))
        )
        agent_runtime = agent_runtime_client(region)
        self._http_closers.append(
            (
                "Graphiti Bedrock agent runtime client",
                functools.partial(asyncio.to_thread, agent_runtime.close),
            )
        )
        llm = BedrockLLMClient(
            LLMConfig(
                model=config.graphiti_bedrock_model,
                small_model=config.graphiti_bedrock_small_model,
            ),
            client=runtime,
            max_output_tokens=config.graphiti_bedrock_max_tokens,
        )
        embedder = BedrockEmbedder(runtime, config.graphiti_embedding_model)
        rerank_arn = f"arn:aws:bedrock:{region}::foundation-model/{config.graphiti_rerank_model}"
        return llm, embedder, BedrockReranker(agent_runtime, rerank_arn)

    async def ensure_indices_and_constraints(self) -> None:
        if self._graphiti is None:
            raise RuntimeError(
                "GraphitiClient.ensure_indices_and_constraints called before initialise"
            )
        await self._graphiti.build_indices_and_constraints()

    async def close(self) -> None:
        """Close Graphiti, then the clients this object built, in the order they were built.

        The handles are cleared first, so a second close closes nothing. The clients are
        closed also when there is no Graphiti, after a failed ``initialise``. Every close is
        attempted, each within its time limit; an interruption of one is raised after the
        others.
        """
        graphiti, http_closers = self._graphiti, self._http_closers
        self._graphiti = None
        self._http_closers = []
        closers: list[Closer] = [] if graphiti is None else [("Graphiti", graphiti.close)]
        await close_all([*closers, *http_closers])

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
