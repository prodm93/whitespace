"""One Bedrock call from async code: transient errors become ``ConnectionError``, bodies close."""

from __future__ import annotations

import asyncio
import functools
import json
import threading
from typing import Any

import pytest
from _bedrock_fakes import StandInBedrock, StandInBody, client_error
from _runtime_helpers import record_waits
from botocore.exceptions import (
    EndpointConnectionError,
    IncompleteReadError,
    ReadTimeoutError,
    ResponseStreamingError,
)

from whitespace.graph import _bedrock_calls as calls

_GOOD = {"embedding": [0.5, 0.25]}


def _invoke(client: StandInBedrock) -> Any:
    return functools.partial(calls.invoke_model_json, client)


async def test_a_good_answer_is_parsed_in_a_worker_thread_and_its_body_closed() -> None:
    body = StandInBody(json.dumps(_GOOD).encode())
    client = StandInBedrock(body)

    payload = await calls.call(_invoke(client), modelId="m")

    assert payload == _GOOD
    assert body.read_threads and body.read_threads[0] != threading.get_ident()
    assert body.closes == 1


async def test_a_slow_body_does_not_block_the_event_loop() -> None:
    body = StandInBody(json.dumps(_GOOD).encode(), delay=0.2)
    client = StandInBedrock(body)
    passes = 0
    done = asyncio.Event()

    async def tick() -> None:
        nonlocal passes
        while not done.is_set():
            await asyncio.sleep(0.01)
            passes += 1

    ticker = asyncio.create_task(tick())
    await calls.call(_invoke(client), modelId="m")
    passes_before_return = passes
    done.set()
    await ticker

    assert passes_before_return >= 5
    assert body.closes == 1


@pytest.mark.parametrize(
    "fault",
    [
        ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"),
        ResponseStreamingError(error="the connection broke"),
        IncompleteReadError(actual_bytes=1, expected_bytes=20),
    ],
    ids=["read timeout", "broken stream", "short body"],
)
async def test_a_body_that_fails_while_read_is_tried_again(
    monkeypatch: pytest.MonkeyPatch, fault: BaseException
) -> None:
    record_waits(monkeypatch)
    first, second = StandInBody(fault), StandInBody(json.dumps(_GOOD).encode())
    client = StandInBedrock(first, second)

    payload = await calls.call_with_retry(_invoke(client), modelId="m")

    assert payload == _GOOD
    assert len(client.calls) == 2
    assert (first.closes, second.closes) == (1, 1)


async def test_a_body_that_is_not_json_fails_at_once_and_is_closed() -> None:
    body = StandInBody(b"not json")
    client = StandInBedrock(body)

    with pytest.raises(json.JSONDecodeError):
        await calls.call_with_retry(_invoke(client), modelId="m")

    assert len(client.calls) == 1
    assert body.closes == 1


async def test_three_timed_out_reads_raise_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_waits(monkeypatch)
    bodies = [StandInBody(ReadTimeoutError(endpoint_url="https://x")) for _ in range(3)]
    client = StandInBedrock(*bodies)

    with pytest.raises(ConnectionError):
        await calls.call_with_retry(_invoke(client), modelId="m")

    assert len(client.calls) == 3
    assert [body.closes for body in bodies] == [1, 1, 1]


async def test_a_good_call_returns_the_answer() -> None:
    client = StandInBedrock({"results": []})

    assert await calls.call(client.rerank, queries=[]) == {"results": []}


async def test_throttling_comes_out_as_connection_error() -> None:
    client = StandInBedrock(client_error("ThrottlingException"))

    with pytest.raises(ConnectionError) as raised:
        await calls.call(client.converse, modelId="m")

    assert raised.value.__cause__ is not None


async def test_access_denied_comes_out_unchanged() -> None:
    error = client_error("AccessDeniedException")
    client = StandInBedrock(error)

    with pytest.raises(type(error)) as raised:
        await calls.call(client.converse, modelId="m")

    assert raised.value is error


async def test_an_unreachable_endpoint_comes_out_as_connection_error() -> None:
    client = StandInBedrock(EndpointConnectionError(endpoint_url="https://x"))

    with pytest.raises(ConnectionError):
        await calls.call(client.converse, modelId="m")


async def test_two_transient_failures_then_an_answer_give_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_waits(monkeypatch)
    throttled = client_error("ThrottlingException")
    client = StandInBedrock(throttled, throttled, {"results": []})

    assert await calls.call_with_retry(client.rerank) == {"results": []}
    assert len(client.calls) == 3


async def test_three_transient_failures_raise_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_waits(monkeypatch)
    client = StandInBedrock(client_error("ServiceUnavailableException"))

    with pytest.raises(ConnectionError):
        await calls.call_with_retry(client.rerank)

    assert len(client.calls) == 3


async def test_access_denied_is_not_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    record_waits(monkeypatch)
    client = StandInBedrock(client_error("AccessDeniedException"))

    with pytest.raises(Exception, match="AccessDeniedException"):
        await calls.call_with_retry(client.rerank)

    assert len(client.calls) == 1
