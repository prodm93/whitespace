"""A SaaS-mode Graphiti client and stand-in builders of its two Bedrock clients."""

from __future__ import annotations

from typing import Any

import pytest
from _bedrock_fakes import StandInBedrock
from _graphiti_fakes import CloseRecorder, install_graphiti_fakes

from whitespace.config import Config
from whitespace.graph import graphiti_client as module
from whitespace.graph.graphiti_client import GraphitiClient


def saas_client() -> GraphitiClient:
    config = Config(  # type: ignore[call-arg]
        _env_file=None,
        mode="saas",
        openrouter_api_key="",
        graphiti_bedrock_model="medium-model",
        graphiti_bedrock_small_model="small-model",
        graphiti_rerank_model="rerank-model",
    )
    return GraphitiClient(config, neo4j=None)  # type: ignore[arg-type]


class Builders:
    """Stand-in builders of the two boto3 clients; each records the region it was given."""

    def __init__(self, closes: CloseRecorder, **options: Any) -> None:
        self.regions: list[str] = []
        self.runtime = StandInBedrock({}, name="runtime", closes=closes, **options)
        self.agent = StandInBedrock({}, name="agent runtime", closes=closes)
        self.agent_error: BaseException | None = None

    def runtime_client(self, region: str) -> StandInBedrock:
        self.regions.append(region)
        return self.runtime

    def agent_runtime_client(self, region: str) -> StandInBedrock:
        self.regions.append(region)
        if self.agent_error is not None:
            raise self.agent_error
        return self.agent


def install_bedrock_fakes(
    monkeypatch: pytest.MonkeyPatch, closes: CloseRecorder, **options: Any
) -> tuple[list[dict[str, Any]], Builders]:
    """Install the Graphiti fakes and the two client builders; an OpenAI client fails the test.

    Returns the keyword arguments each fake ``Graphiti`` was built with, and the builders.
    """
    built_with = install_graphiti_fakes(monkeypatch, closes)
    builders = Builders(closes, **options)
    monkeypatch.setattr(module, "runtime_client", builders.runtime_client)
    monkeypatch.setattr(module, "agent_runtime_client", builders.agent_runtime_client)

    def no_openai(**_kwargs: Any) -> Any:
        pytest.fail("an OpenAI client was built in SaaS mode")

    monkeypatch.setattr(module, "AsyncOpenAI", no_openai)
    return built_with, builders
