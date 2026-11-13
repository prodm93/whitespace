"""Tests for the kept clients and the pipelines built on them."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from neo4j import AsyncDriver
from neo4j.exceptions import ServiceUnavailable

from whitespace.config import Config
from whitespace.orchestration import _wiring
from whitespace.orchestration._shared_clients import SharedClients
from whitespace.orchestration.pipeline import Pipeline


class _FakeNeo4j:
    def __init__(self, config: Config, calls: list[str]) -> None:
        self.config = config
        self._calls = calls

    async def connect(self) -> None:
        self._calls.append("neo4j.connect")

    async def close(self) -> None:
        self._calls.append("neo4j.close")


class _FakeGraphiti:
    def __init__(self, config: Config, neo4j: _FakeNeo4j, calls: list[str]) -> None:
        self.config = config
        self.neo4j = neo4j
        self._calls = calls

    async def initialise(self) -> None:
        self._calls.append("graphiti.initialise")

    async def close(self) -> None:
        self._calls.append("graphiti.close")


@pytest.fixture()
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the two network clients in the wiring with fakes that record calls."""
    recorded: list[str] = []
    monkeypatch.setattr(_wiring, "Neo4jClient", lambda config: _FakeNeo4j(config, recorded))
    monkeypatch.setattr(
        _wiring,
        "GraphitiClient",
        lambda config, neo4j: _FakeGraphiti(config, neo4j, recorded),
    )
    return recorded


def _config(**overrides: Any) -> Config:
    return Config(_env_file=None, **overrides)  # type: ignore[call-arg]


async def test_from_config_pipeline_connects_and_closes_its_own_clients(
    calls: list[str],
) -> None:
    pipeline = Pipeline.from_config(_config(mode="byok"))

    await pipeline.initialise()
    await pipeline.close()

    assert calls == ["neo4j.connect", "graphiti.initialise", "graphiti.close", "neo4j.close"]


def _checked_clients() -> tuple[SharedClients, AsyncMock, AsyncMock]:
    neo4j_driver = AsyncMock(spec=AsyncDriver)
    graphiti_driver = AsyncMock(spec=Neo4jDriver)
    shared = SharedClients(
        neo4j=SimpleNamespace(driver=neo4j_driver),  # type: ignore[arg-type]
        graphiti=SimpleNamespace(graphiti=SimpleNamespace(driver=graphiti_driver)),  # type: ignore[arg-type]
        provider_factory=object(),  # type: ignore[arg-type]
    )
    return shared, neo4j_driver, graphiti_driver


async def test_check_asks_both_drivers() -> None:
    shared, neo4j_driver, graphiti_driver = _checked_clients()

    await shared.check()

    neo4j_driver.verify_connectivity.assert_awaited_once()
    graphiti_driver.health_check.assert_awaited_once()


@pytest.mark.parametrize("failing", ["neo4j", "graphiti"])
async def test_check_raises_when_either_driver_fails(failing: str) -> None:
    shared, neo4j_driver, graphiti_driver = _checked_clients()
    if failing == "neo4j":
        neo4j_driver.verify_connectivity.side_effect = ServiceUnavailable("down")
    else:
        graphiti_driver.health_check.side_effect = ServiceUnavailable("down")

    with pytest.raises(ServiceUnavailable):
        await shared.check()


def test_graphiti_neo4j_driver_has_health_check() -> None:
    assert callable(getattr(Neo4jDriver, "health_check", None))


def _run_pipelines(monkeypatch: pytest.MonkeyPatch) -> tuple[SharedClients, Pipeline, Pipeline]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    shared = _wiring.build_shared(_config(mode="saas"))
    pipeline_a = Pipeline.from_shared(shared, _config(mode="saas", graphiti_namespace="user_a"))
    pipeline_b = Pipeline.from_shared(shared, _config(mode="saas", graphiti_namespace="user_b"))
    return shared, pipeline_a, pipeline_b


def test_run_pipelines_hold_their_own_namespace_and_share_only_the_kept_clients(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shared, pipeline_a, pipeline_b = _run_pipelines(monkeypatch)

    for pipeline, owner in ((pipeline_a, "user_a"), (pipeline_b, "user_b")):
        assert pipeline._context_agent._config.graphiti_namespace == owner
        assert pipeline._ingest._graph_agent._config.graphiti_namespace == owner
    assert pipeline_a._neo4j is shared.neo4j
    assert pipeline_b._neo4j is shared.neo4j
    assert pipeline_a._router is not pipeline_b._router
    assert pipeline_a._router._registry is not pipeline_b._router._registry
    assert pipeline_a._dedup is not pipeline_b._dedup


async def test_run_pipelines_do_not_open_or_close_the_kept_clients(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, pipeline_a, pipeline_b = _run_pipelines(monkeypatch)

    for pipeline in (pipeline_a, pipeline_b):
        await pipeline.initialise()
        await pipeline.close()

    assert calls == []


async def test_neo4j_driver_tests_idle_connections_before_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from whitespace.graph import neo4j_client

    factory = MagicMock(return_value=AsyncMock(spec=AsyncDriver))
    monkeypatch.setattr(neo4j_client.AsyncGraphDatabase, "driver", factory)

    await neo4j_client.Neo4jClient(_config(mode="byok")).connect()

    assert factory.call_args.kwargs["liveness_check_timeout"] == 30
