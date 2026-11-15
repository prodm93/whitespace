"""Closing the kept clients and a pipeline's own clients: every close runs, within limits."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from _graphiti_fakes import CloseRecorder, install_graphiti_fakes
from _loop_helpers import Stubborn, drive, drive_timed

from whitespace.closing import close_all
from whitespace.config import Config
from whitespace.graph import neo4j_client as neo4j_module
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.orchestration._shared_clients import SharedClients
from whitespace.orchestration.pipeline import Pipeline


class _FakeNeo4j:
    def __init__(self, closes: CloseRecorder) -> None:
        self._closes = closes

    async def close(self) -> None:
        await self._closes.close("neo4j")


class _FakeGraphitiClient:
    def __init__(self, closes: CloseRecorder) -> None:
        self._closes = closes

    async def close(self) -> None:
        await self._closes.close("graphiti-client")


def _config() -> Config:
    return Config(_env_file=None, mode="byok", openrouter_api_key="k")  # type: ignore[call-arg]


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_a_cancelled_graphiti_close_still_closes_neo4j_then_raises() -> None:
    closes = CloseRecorder({"graphiti-client": asyncio.CancelledError()})
    shared = SharedClients(
        neo4j=_FakeNeo4j(closes),  # type: ignore[arg-type]
        graphiti=_FakeGraphitiClient(closes),  # type: ignore[arg-type]
        provider_factory=None,  # type: ignore[arg-type]
    )

    with pytest.raises(asyncio.CancelledError):
        drive(shared.close)

    assert closes.names == ["graphiti-client", "neo4j"]


def _real_graphiti(monkeypatch: Any, closes: CloseRecorder) -> GraphitiClient:
    install_graphiti_fakes(monkeypatch, closes)
    graphiti = GraphitiClient(_config(), neo4j=None)  # type: ignore[arg-type]
    drive(graphiti.initialise)
    return graphiti


_EVERY_CLOSE = ["graphiti", "model", "embedder", "reranker", "neo4j"]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit(1)], ids=repr)
@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interrupted_graphiti_close_still_closes_every_kept_client(
    monkeypatch: Any, interruption: BaseException
) -> None:
    closes = CloseRecorder({"graphiti": interruption})
    shared = SharedClients(
        neo4j=_FakeNeo4j(closes),  # type: ignore[arg-type]
        graphiti=_real_graphiti(monkeypatch, closes),
        provider_factory=None,  # type: ignore[arg-type]
    )

    with pytest.raises(type(interruption)):
        drive(shared.close)

    assert closes.names == _EVERY_CLOSE


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit(1)], ids=repr)
@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interrupted_graphiti_close_still_closes_every_pipeline_client(
    monkeypatch: Any, interruption: BaseException
) -> None:
    closes = CloseRecorder({"graphiti": interruption})
    install_graphiti_fakes(monkeypatch, closes)
    pipeline = Pipeline.from_config(_config())
    drive(pipeline._graphiti.initialise)
    pipeline._neo4j = _FakeNeo4j(closes)  # type: ignore[assignment]

    with pytest.raises(type(interruption)):
        drive(pipeline.close)

    assert closes.names == _EVERY_CLOSE


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_a_neo4j_driver_close_that_never_ends_is_left_at_the_limit(monkeypatch: Any) -> None:
    work = Stubborn()

    class StuckDriver:
        async def close(self) -> None:
            await work.run()

    monkeypatch.setattr(
        neo4j_module, "close_all", lambda closers, **_kw: close_all(closers, seconds=0.05)
    )
    client = Neo4jClient(_config())
    client._driver = StuckDriver()  # type: ignore[assignment]

    elapsed = drive_timed(client.close, work)

    assert elapsed < 1.0
    with pytest.raises(RuntimeError):
        _ = client.driver
