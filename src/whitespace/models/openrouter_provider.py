"""OpenRouter (OpenAI-compatible) chat call with normalised tool support."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from whitespace.models.registry import ModelEntry

logger = logging.getLogger(__name__)


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate normalised messages into OpenAI chat-completion shape."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg["role"] == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
            )
        elif msg["role"] == "assistant" and msg.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            },
                        }
                        for call in msg["tool_calls"]
                    ],
                }
            )
        else:
            out.append({"role": msg["role"], "content": msg["content"]})
    return out


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate normalised tool definitions into OpenAI function specs."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


def to_openai_tool_choice(tool_choice: str) -> str | dict[str, Any]:
    if tool_choice in ("auto", "required"):
        return tool_choice
    return {"type": "function", "function": {"name": tool_choice}}


def parse_tool_calls(message: Any) -> list[dict[str, Any]]:
    """Normalise OpenAI tool calls; malformed argument JSON degrades to {}."""
    calls: list[dict[str, Any]] = []
    for call in message.tool_calls or []:
        try:
            arguments = json.loads(call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "openrouter_provider: malformed tool arguments for %s",
                call.function.name,
            )
            arguments = {}
        calls.append({"id": call.id, "name": call.function.name, "arguments": arguments})
    return calls


async def call_openrouter(
    client: AsyncOpenAI,
    model_id: str,
    entry: ModelEntry,
    messages: list[dict[str, Any]],
    temperature: float,
    response_format: dict[str, Any] | None,
    tools: list[dict[str, Any]] | None,
    tool_choice: str | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": to_openai_messages(messages),
        "temperature": temperature,
        "timeout": entry.timeout_seconds,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = to_openai_tools(tools)
        if tool_choice is not None:
            kwargs["tool_choice"] = to_openai_tool_choice(tool_choice)

    response = await client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    usage = response.usage
    tool_calls = parse_tool_calls(choice.message) if tools else []

    return {
        "content": choice.message.content or "",
        "model_id": entry.model_id,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "tool_calls": tool_calls,
        "stop_reason": "tool_use" if tool_calls else "end",
    }
