"""Graphiti's embedder on Bedrock: one Titan call for each text, in the order of the input."""

from __future__ import annotations

import json
from typing import Any

import pytest
from _bedrock_fakes import StandInBedrock, StandInBody, client_error
from _runtime_helpers import record_waits
from botocore.exceptions import ReadTimeoutError

from whitespace.graph._bedrock_embedder import BedrockEmbedder

_MODEL = "amazon.titan-embed-text-v2:0"
_VECTORS = {"one": [1.0, 0.0], "two": [0.0, 1.0], "three": [0.5, 0.5]}


def _text(kwargs: dict[str, Any]) -> str:
    return str(json.loads(kwargs["body"])["inputText"])


def _by_text(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {"embedding": _VECTORS[_text(kwargs)]}


@pytest.mark.parametrize("given", [["one"], "one"], ids=["a list of one", "a text"])
async def test_one_text_makes_one_call_and_gives_its_vector(given: Any) -> None:
    client = StandInBedrock(_by_text)

    vector = await BedrockEmbedder(client, _MODEL).create(given)

    assert vector == [1.0, 0.0]
    assert len(client.calls) == 1
    operation, kwargs = client.calls[0]
    assert operation == "invoke_model"
    assert kwargs["modelId"] == _MODEL
    assert json.loads(kwargs["body"]) == {"inputText": "one", "dimensions": 1024, "normalize": True}


async def test_input_that_is_not_text_is_refused() -> None:
    with pytest.raises(TypeError):
        await BedrockEmbedder(StandInBedrock(_by_text), _MODEL).create([1, 2, 3])


async def test_a_batch_gives_one_vector_for_each_text_in_order() -> None:
    client = StandInBedrock(_by_text)

    vectors = await BedrockEmbedder(client, _MODEL).create_batch(["one", "two", "three"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    assert len(client.calls) == 3
    assert [body.closes for body in client.bodies] == [1, 1, 1]


async def test_an_empty_batch_makes_no_call() -> None:
    client = StandInBedrock(_by_text)

    assert await BedrockEmbedder(client, _MODEL).create_batch([]) == []
    assert client.calls == []


async def test_an_empty_text_gets_a_zero_vector_with_no_call() -> None:
    client = StandInBedrock(_by_text)
    embedder = BedrockEmbedder(client, _MODEL)

    alone = await embedder.create("")
    batch = await embedder.create_batch(["one", "  "])

    assert alone == [0.0] * 1024
    assert batch == [[1.0, 0.0], [0.0] * 1024]
    assert [_text(kwargs) for _, kwargs in client.calls] == ["one"]


async def test_a_throttled_call_is_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    record_waits(monkeypatch)
    client = StandInBedrock(client_error("ThrottlingException", "InvokeModel"), _by_text)

    assert await BedrockEmbedder(client, _MODEL).create("two") == [0.0, 1.0]
    assert len(client.calls) == 2


async def test_a_body_that_times_out_is_tried_again_and_both_are_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_waits(monkeypatch)
    client = StandInBedrock(StandInBody(ReadTimeoutError(endpoint_url="https://x")), _by_text)

    assert await BedrockEmbedder(client, _MODEL).create("three") == [0.5, 0.5]
    assert len(client.calls) == 2
    assert [body.closes for body in client.bodies] == [1, 1]
