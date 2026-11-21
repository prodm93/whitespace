"""Graphiti's language model on Bedrock, driven through Graphiti's own ``generate_response``."""

from __future__ import annotations

from typing import Any

import pytest
from _bedrock_fakes import StandInBedrock, client_error
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize
from graphiti_core.llm_client.errors import RateLimitError
from graphiti_core.prompts.models import Message
from pydantic import BaseModel
from tenacity import wait_none

from whitespace.graph._bedrock_llm import BedrockLLMClient

_MEDIUM = "amazon.nova-pro-v1:0"
_SMALL = "amazon.nova-micro-v1:0"
_CAP = 8192


class Entities(BaseModel):
    names: list[str]


def _tool_answer(found: dict[str, Any], stop: str = "tool_use") -> dict[str, Any]:
    block = {"toolUse": {"toolUseId": "t1", "name": "Entities", "input": found}}
    return {"output": {"message": {"role": "assistant", "content": [block]}}, "stopReason": stop}


def _text_answer(text: str) -> dict[str, Any]:
    content = [{"text": text}]
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": "end_turn",
    }


def _messages() -> list[Message]:
    return [Message(role="system", content="Extract."), Message(role="user", content="Mira Okafor")]


def _llm(client: StandInBedrock, small: str | None = _SMALL) -> BedrockLLMClient:
    config = LLMConfig(model=_MEDIUM, small_model=small)
    return BedrockLLMClient(config, client=client, max_output_tokens=_CAP)


@pytest.fixture()
def no_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LLMClient._generate_response_with_retry.retry, "wait", wait_none())


async def test_a_response_model_is_asked_for_with_one_forced_tool() -> None:
    client = StandInBedrock(_tool_answer({"names": ["Mira Okafor"]}))

    result = await _llm(client).generate_response(_messages(), response_model=Entities)

    assert result == {"names": ["Mira Okafor"]}
    assert len(client.calls) == 1
    operation, request = client.calls[0]
    assert operation == "converse"
    assert request["system"][0]["text"].startswith("Extract.")
    assert [m["role"] for m in request["messages"]] == ["user"]
    assert request["messages"][0]["content"][0]["text"].startswith("Mira Okafor")
    tool = request["toolConfig"]["tools"][0]["toolSpec"]
    assert tool["name"] == "Entities"
    assert tool["inputSchema"] == {"json": Entities.model_json_schema()}
    assert request["toolConfig"]["toolChoice"] == {"tool": {"name": "Entities"}}


async def test_with_no_response_model_no_tool_is_sent_and_the_text_is_parsed() -> None:
    client = StandInBedrock(_text_answer('{"answer": 42}'))

    result = await _llm(client).generate_response(_messages())

    assert result == {"answer": 42}
    assert "toolConfig" not in client.calls[0][1]


@pytest.mark.parametrize(
    ("size", "small", "expected"),
    [
        (ModelSize.small, _SMALL, _SMALL),
        (ModelSize.medium, _SMALL, _MEDIUM),
        (ModelSize.small, None, _MEDIUM),
    ],
    ids=["small call", "medium call", "small call with no small model"],
)
async def test_the_model_is_chosen_by_the_size_of_the_call(
    size: ModelSize, small: str | None, expected: str
) -> None:
    client = StandInBedrock(_tool_answer({"names": []}))

    await _llm(client, small).generate_response(
        _messages(), response_model=Entities, model_size=size
    )

    assert client.calls[0][1]["modelId"] == expected


@pytest.mark.parametrize(("asked", "sent"), [(None, _CAP), (400, 400)], ids=["default", "under"])
async def test_the_output_limit_is_capped(asked: int | None, sent: int) -> None:
    client = StandInBedrock(_tool_answer({"names": []}))

    await _llm(client).generate_response(_messages(), response_model=Entities, max_tokens=asked)

    assert client.calls[0][1]["inferenceConfig"]["maxTokens"] == sent


async def test_an_answer_cut_at_the_limit_is_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = StandInBedrock(_tool_answer({"names": ["Mira"]}, stop="max_tokens"))

    result = await _llm(client).generate_response(_messages(), response_model=Entities)

    assert result == {"names": ["Mira"]}
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert warnings == ["A Graphiti answer was cut at the output limit"]


async def test_a_text_answer_that_is_json_is_returned() -> None:
    client = StandInBedrock(_text_answer('{"names": ["Helix"]}'))

    result = await _llm(client).generate_response(_messages(), response_model=Entities)

    assert result == {"names": ["Helix"]}


@pytest.mark.usefixtures("no_waits")
async def test_a_text_answer_that_is_not_json_is_asked_for_again() -> None:
    client = StandInBedrock(_text_answer("not json"), _text_answer('{"names": ["Helix"]}'))

    result = await _llm(client).generate_response(_messages(), response_model=Entities)

    assert result == {"names": ["Helix"]}
    assert len(client.calls) == 2


@pytest.mark.usefixtures("no_waits")
async def test_a_throttled_call_raises_rate_limit_error_after_the_base_retry() -> None:
    client = StandInBedrock(client_error("ThrottlingException"))

    with pytest.raises(RateLimitError) as raised:
        await _llm(client).generate_response(_messages(), response_model=Entities)

    assert isinstance(raised.value.__cause__, ConnectionError)
    assert len(client.calls) == 4


async def test_access_denied_comes_out_unchanged_after_one_call() -> None:
    error = client_error("AccessDeniedException")
    client = StandInBedrock(error)

    with pytest.raises(type(error)) as raised:
        await _llm(client).generate_response(_messages(), response_model=Entities)

    assert raised.value is error
    assert len(client.calls) == 1
