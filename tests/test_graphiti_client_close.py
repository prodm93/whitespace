"""Closing the Graphiti client closes Graphiti and its three HTTP clients, whatever fails."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from _graphiti_fakes import CloseRecorder, install_graphiti_fakes
from _loop_helpers import drive

from whitespace.config import Config
from whitespace.graph.graphiti_client import GraphitiClient


def _client() -> GraphitiClient:
    config = Config(_env_file=None, openrouter_api_key="k")  # type: ignore[call-arg]
    return GraphitiClient(config, neo4j=None)  # type: ignore[arg-type]


_ALL = ["graphiti", "model", "embedder", "reranker"]


def _initialised(monkeypatch: Any, closes: CloseRecorder) -> GraphitiClient:
    install_graphiti_fakes(monkeypatch, closes)
    client = _client()
    drive(client.initialise)
    return client


def test_close_closes_graphiti_first_then_each_http_client(monkeypatch: Any) -> None:
    closes = CloseRecorder()
    client = _initialised(monkeypatch, closes)

    drive(client.close)

    assert closes.names == _ALL


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_a_failed_graphiti_close_still_closes_the_http_clients(monkeypatch: Any) -> None:
    closes = CloseRecorder({"graphiti": RuntimeError("driver broke")})
    client = _initialised(monkeypatch, closes)

    drive(client.close)

    assert closes.names == _ALL


@pytest.mark.parametrize(
    "interruption",
    [asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(1)],
    ids=["cancelled", "keyboard-interrupt", "system-exit"],
)
@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interrupted_graphiti_close_still_closes_the_rest_then_raises(
    monkeypatch: Any, interruption: BaseException
) -> None:
    closes = CloseRecorder({"graphiti": interruption})
    client = _initialised(monkeypatch, closes)

    with pytest.raises(type(interruption)):
        drive(client.close)

    assert closes.names == _ALL
    with pytest.raises(RuntimeError):
        _ = client.graphiti


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_a_failed_http_client_close_does_not_stop_the_others(monkeypatch: Any) -> None:
    closes = CloseRecorder({"embedder": OSError("socket")})
    client = _initialised(monkeypatch, closes)

    drive(client.close)

    assert closes.names == _ALL


def test_close_before_initialise_and_a_second_close_close_nothing(monkeypatch: Any) -> None:
    closes = CloseRecorder()
    install_graphiti_fakes(monkeypatch, closes)
    client = _client()

    drive(client.close)
    drive(client.initialise)
    drive(client.close)
    drive(client.close)

    assert closes.names == _ALL


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_graphiti_gets_the_real_wrappers_with_the_http_clients_built_here(
    monkeypatch: Any,
) -> None:
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.embedder.openai import OpenAIEmbedder
    from graphiti_core.llm_client.openai_client import OpenAIClient

    closes = CloseRecorder()
    built_with = install_graphiti_fakes(monkeypatch, closes, real_wrappers=True)
    client = _client()

    drive(client.initialise)
    (arguments,) = built_with
    wrappers = [arguments["llm_client"], arguments["embedder"], arguments["cross_encoder"]]

    assert [type(wrapper) for wrapper in wrappers] == [
        OpenAIClient,
        OpenAIEmbedder,
        OpenAIRerankerClient,
    ]
    assert [wrapper.client.name for wrapper in wrappers] == ["model", "embedder", "reranker"]
    drive(client.close)
    assert closes.names == _ALL
