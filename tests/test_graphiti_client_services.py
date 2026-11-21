"""In SaaS mode Graphiti's three model services are Bedrock adapters, and their clients close."""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any

import pytest
from _graphiti_fakes import CloseRecorder
from _graphiti_services_helpers import install_bedrock_fakes, saas_client

from whitespace.closing import close_all
from whitespace.graph import graphiti_client as module
from whitespace.graph._bedrock_embedder import BedrockEmbedder
from whitespace.graph._bedrock_llm import BedrockLLMClient
from whitespace.graph._bedrock_reranker import BedrockReranker


@pytest.mark.protects("saas-graphiti-calls-stay-in-aws")
async def test_saas_mode_builds_the_bedrock_adapters_with_no_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built_with, _ = install_bedrock_fakes(monkeypatch, CloseRecorder())

    await saas_client().initialise()

    (arguments,) = built_with
    assert type(arguments["llm_client"]) is BedrockLLMClient
    assert type(arguments["embedder"]) is BedrockEmbedder
    assert type(arguments["cross_encoder"]) is BedrockReranker


async def test_the_language_model_gets_the_medium_and_the_small_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built_with, _ = install_bedrock_fakes(monkeypatch, CloseRecorder())

    await saas_client().initialise()

    llm = built_with[0]["llm_client"]
    assert (llm.model, llm.small_model) == ("medium-model", "small-model")


async def test_the_reranker_arn_and_the_clients_use_the_configured_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built_with, builders = install_bedrock_fakes(monkeypatch, CloseRecorder())

    await saas_client().initialise()

    reranker = built_with[0]["cross_encoder"]
    assert reranker._model_arn == "arn:aws:bedrock:us-east-1::foundation-model/rerank-model"
    assert builders.regions == ["us-east-1", "us-east-1"]


async def test_close_closes_graphiti_then_both_clients_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = CloseRecorder()
    _, builders = install_bedrock_fakes(monkeypatch, closes)
    client = saas_client()
    await client.initialise()

    await client.close()
    await client.close()

    assert closes.names == ["graphiti", "runtime", "agent runtime"]
    assert (builders.runtime.close_count, builders.agent.close_count) == (1, 1)


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
async def test_a_failed_close_does_not_stop_the_other_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = CloseRecorder({"graphiti": RuntimeError("driver broke")})
    _, builders = install_bedrock_fakes(monkeypatch, closes, close_error=OSError("socket"))
    client = saas_client()
    await client.initialise()

    await client.close()

    assert closes.names == ["graphiti", "runtime", "agent runtime"]


@pytest.mark.parametrize(
    "interruption",
    [asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(1)],
    ids=["cancelled", "keyboard-interrupt", "system-exit"],
)
async def test_an_interrupted_graphiti_close_still_closes_both_clients_then_raises(
    monkeypatch: pytest.MonkeyPatch, interruption: BaseException
) -> None:
    closes = CloseRecorder({"graphiti": interruption})
    install_bedrock_fakes(monkeypatch, closes)
    client = saas_client()
    await client.initialise()

    with pytest.raises(type(interruption)):
        await client.close()

    assert closes.names == ["graphiti", "runtime", "agent runtime"]


async def test_a_failed_graphiti_build_still_lets_close_close_both_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = CloseRecorder()
    install_bedrock_fakes(monkeypatch, closes)

    def broken(**_kwargs: Any) -> Any:
        raise RuntimeError("graphiti would not build")

    monkeypatch.setattr(module, "Graphiti", broken)
    client = saas_client()

    with pytest.raises(RuntimeError):
        await client.initialise()
    await client.close()

    assert closes.names == ["runtime", "agent runtime"]


async def test_a_failed_agent_runtime_build_lets_close_close_the_runtime_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = CloseRecorder()
    _, builders = install_bedrock_fakes(monkeypatch, closes)
    builders.agent_error = RuntimeError("no endpoint")
    client = saas_client()

    with pytest.raises(RuntimeError):
        await client.initialise()
    await client.close()

    assert closes.names == ["runtime"]


async def test_a_client_close_that_hangs_is_left_behind_at_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = CloseRecorder()
    install_bedrock_fakes(monkeypatch, closes, close_delay=0.5)
    monkeypatch.setattr(module, "close_all", functools.partial(close_all, seconds=0.05))
    client = saas_client()
    await client.initialise()

    started = time.monotonic()
    await client.close()

    assert time.monotonic() - started < 0.4
    assert "agent runtime" in closes.names
