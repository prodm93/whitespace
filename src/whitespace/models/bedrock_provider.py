"""AWS Bedrock Converse API call with normalised tool support.

boto3 is never imported here — ProviderFactory constructs the runtime
client lazily and passes it in, keeping this module import-safe in BYOK
mode.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from whitespace.models.registry import ModelEntry

logger = logging.getLogger(__name__)


def to_converse_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate normalised messages into Converse system + conversation lists.

    Consecutive tool results merge into a single user turn — Converse
    requires alternating roles, with toolResult blocks inside user messages.
    """
    system_parts: list[dict[str, Any]] = []
    conversation: list[dict[str, Any]] = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append({"text": msg["content"]})
        elif msg["role"] == "tool":
            block = {
                "toolResult": {
                    "toolUseId": msg["tool_call_id"],
                    "content": [{"text": msg["content"]}],
                }
            }
            last = conversation[-1] if conversation else None
            if last is not None and last["role"] == "user" and "toolResult" in last["content"][-1]:
                last["content"].append(block)
            else:
                conversation.append({"role": "user", "content": [block]})
        elif msg["role"] == "assistant" and msg.get("tool_calls"):
            content: list[dict[str, Any]] = []
            if msg.get("content"):
                content.append({"text": msg["content"]})
            content.extend(
                {
                    "toolUse": {
                        "toolUseId": call["id"],
                        "name": call["name"],
                        "input": call["arguments"],
                    }
                }
                for call in msg["tool_calls"]
            )
            conversation.append({"role": "assistant", "content": content})
        else:
            conversation.append({"role": msg["role"], "content": [{"text": msg["content"]}]})
    return system_parts, conversation


def to_tool_config(
    tools: list[dict[str, Any]],
    tool_choice: str | None,
) -> dict[str, Any]:
    """Translate normalised tool definitions into a Converse toolConfig."""
    config: dict[str, Any] = {
        "tools": [
            {
                "toolSpec": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": {"json": tool["parameters"]},
                }
            }
            for tool in tools
        ]
    }
    if tool_choice == "required":
        config["toolChoice"] = {"any": {}}
    elif tool_choice not in (None, "auto"):
        config["toolChoice"] = {"tool": {"name": tool_choice}}
    return config


def parse_converse_output(response: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Extract text content and normalised tool calls from a Converse response."""
    content = ""
    tool_calls: list[dict[str, Any]] = []
    message = response.get("output", {}).get("message", {})
    for block in message.get("content", []):
        if "text" in block:
            content += block["text"]
        elif "toolUse" in block:
            use = block["toolUse"]
            tool_calls.append(
                {"id": use["toolUseId"], "name": use["name"], "arguments": use["input"]}
            )
    return content, tool_calls


async def call_bedrock(
    client: Any,
    entry: ModelEntry,
    messages: list[dict[str, Any]],
    temperature: float,
    response_format: dict[str, Any] | None,
    tools: list[dict[str, Any]] | None,
    tool_choice: str | None,
) -> dict[str, Any]:
    """Invoke a model through the Converse API.

    Structured output (response_format) is prompt-driven on Bedrock —
    the Converse API has no JSON-schema enforcement parameter, so the
    argument is accepted for interface parity and intentionally unused.
    """
    system_parts, conversation = to_converse_messages(messages)
    kwargs: dict[str, Any] = {
        "modelId": entry.model_id,
        "messages": conversation,
        "inferenceConfig": {"temperature": temperature},
    }
    if system_parts:
        kwargs["system"] = system_parts
    if tools:
        kwargs["toolConfig"] = to_tool_config(tools, tool_choice)

    response = await asyncio.to_thread(client.converse, **kwargs)

    content, tool_calls = parse_converse_output(response)
    usage = response.get("usage", {})
    return {
        "content": content,
        "model_id": entry.model_id,
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        "tool_calls": tool_calls,
        "stop_reason": "tool_use" if response.get("stopReason") == "tool_use" else "end",
    }
