"""Tests for provider-format translation of the normalised tool interface."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from botocore.exceptions import ClientError

from whitespace.models.bedrock_provider import (
    call_bedrock,
    parse_converse_output,
    to_converse_messages,
    to_tool_config,
)
from whitespace.models.openrouter_provider import (
    parse_tool_calls,
    to_openai_messages,
    to_openai_tool_choice,
    to_openai_tools,
)

_TOOL = {
    "name": "search_graph",
    "description": "Search the knowledge graph",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
}


def test_converse_messages_split_system_and_merge_tool_results() -> None:
    system, conversation = to_converse_messages(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "checking",
                "tool_calls": [{"id": "t1", "name": "search_graph", "arguments": {"query": "x"}}],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "result-1"},
            {"role": "tool", "tool_call_id": "t2", "content": "result-2"},
        ]
    )
    assert system == [{"text": "be brief"}]
    assert conversation[1]["content"] == [
        {"text": "checking"},
        {"toolUse": {"toolUseId": "t1", "name": "search_graph", "input": {"query": "x"}}},
    ]
    tool_turn = conversation[2]
    assert tool_turn["role"] == "user"
    assert [b["toolResult"]["toolUseId"] for b in tool_turn["content"]] == ["t1", "t2"]


def test_tool_config_shapes_and_tool_choice() -> None:
    config = to_tool_config([_TOOL], None)
    assert config["tools"][0]["toolSpec"]["inputSchema"] == {"json": _TOOL["parameters"]}
    assert "toolChoice" not in config
    assert to_tool_config([_TOOL], "required")["toolChoice"] == {"any": {}}
    assert to_tool_config([_TOOL], "search_graph")["toolChoice"] == {
        "tool": {"name": "search_graph"}
    }


def test_parse_converse_output_extracts_text_and_tool_calls() -> None:
    content, calls = parse_converse_output(
        {
            "output": {
                "message": {
                    "content": [
                        {"text": "thinking"},
                        {
                            "toolUse": {
                                "toolUseId": "t1",
                                "name": "search_graph",
                                "input": {"query": "x"},
                            }
                        },
                    ]
                }
            }
        }
    )
    assert content == "thinking"
    assert calls == [{"id": "t1", "name": "search_graph", "arguments": {"query": "x"}}]


def test_openai_messages_encode_tool_calls_and_results() -> None:
    out = to_openai_messages(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "t1", "name": "search_graph", "arguments": {"query": "x"}}],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "result-1"},
        ]
    )
    assert out[0]["content"] is None
    assert out[0]["tool_calls"][0]["function"]["arguments"] == '{"query": "x"}'
    assert out[1] == {"role": "tool", "tool_call_id": "t1", "content": "result-1"}


def test_openai_tools_and_tool_choice() -> None:
    assert to_openai_tools([_TOOL])[0]["function"]["name"] == "search_graph"
    assert to_openai_tool_choice("auto") == "auto"
    assert to_openai_tool_choice("search_graph") == {
        "type": "function",
        "function": {"name": "search_graph"},
    }


def test_parse_tool_calls_degrades_malformed_arguments() -> None:
    message = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                id="t1",
                function=SimpleNamespace(name="search_graph", arguments="{not json"),
            )
        ]
    )
    assert parse_tool_calls(message) == [{"id": "t1", "name": "search_graph", "arguments": {}}]


class _FakeConverseClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: dict[str, Any] = {}

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.sent = kwargs
        if self.error is not None:
            raise self.error
        return {"output": {"message": {"content": [{"text": "hi"}]}}, "usage": {}}


def _entry() -> Any:
    return SimpleNamespace(model_id="anthropic.claude-opus-4-8")


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


async def test_call_bedrock_sends_the_model_argument_and_reports_the_registry_id() -> None:
    client = _FakeConverseClient()

    result = await call_bedrock(
        client, "us.anthropic.claude-opus-4-8", _entry(), [], 0.0, None, None, None
    )

    assert client.sent["modelId"] == "us.anthropic.claude-opus-4-8"
    assert result["model_id"] == "anthropic.claude-opus-4-8"


async def test_bedrock_throttling_comes_out_as_a_connection_error() -> None:
    client = _FakeConverseClient(_client_error("ThrottlingException"))

    with pytest.raises(ConnectionError):
        await call_bedrock(client, "m", _entry(), [], 0.0, None, None, None)


async def test_bedrock_validation_error_comes_out_unchanged() -> None:
    error = _client_error("ValidationException")
    client = _FakeConverseClient(error)

    with pytest.raises(ClientError) as raised:
        await call_bedrock(client, "m", _entry(), [], 0.0, None, None, None)

    assert raised.value is error
