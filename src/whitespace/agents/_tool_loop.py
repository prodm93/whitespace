"""Generic tool-use loop for agents that explore before concluding.

An agent hands the router a toolkit (tool schemas + a dispatcher), the
model decides which tools to call and when it has enough evidence, and
the loop returns a plain-text findings transcript. The agent then makes
its own final structured call on the findings — keeping structured
output separate from tool use, which not every provider combines well.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from whitespace.models.router import ModelRouter

logger = logging.getLogger(__name__)


class Toolkit(Protocol):
    """Anything that can describe its tools and execute a call."""

    def tool_definitions(self) -> list[dict[str, Any]]: ...

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str: ...


class CombinedToolkit:
    """Union of several toolkits presented to the model as one."""

    def __init__(self, *toolkits: Toolkit) -> None:
        self._toolkits = toolkits
        self._owner: dict[str, Toolkit] = {}
        for kit in toolkits:
            for definition in kit.tool_definitions():
                self._owner[definition["name"]] = kit

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [d for kit in self._toolkits for d in kit.tool_definitions()]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        kit = self._owner.get(name)
        if kit is None:
            return f"Unknown tool: {name}"
        return await kit.dispatch(name, arguments)


async def run_tool_loop(
    router: ModelRouter,
    *,
    role: str,
    system_prompt: str,
    user_prompt: str,
    toolkit: Toolkit,
    max_tool_calls: int,
    temperature: float = 0.0,
) -> str:
    """Let the model drive the toolkit; return a findings transcript.

    The transcript records every call and its result, plus the model's
    closing text. The model stops the loop itself by not calling tools;
    the cap is a guard, not the expected exit.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tools = toolkit.tool_definitions()
    findings: list[str] = []
    calls_made = 0

    while calls_made < max_tool_calls:
        result = await router.call(
            role=role,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )
        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            if result.get("content"):
                findings.append(result["content"])
            break

        messages.append(
            {
                "role": "assistant",
                "content": result.get("content", ""),
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            calls_made += 1
            try:
                output = await toolkit.dispatch(call["name"], call["arguments"])
            except Exception:
                logger.exception("Tool %s failed for role=%s", call["name"], role)
                output = f"Tool {call['name']} failed; try a different call."
            findings.append(f"### {call['name']}({call['arguments']})\n{output}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": output,
                }
            )
    else:
        logger.info("run_tool_loop: cap of %d tool calls reached for %s", max_tool_calls, role)

    logger.info("run_tool_loop: role=%s used %d tool calls", role, calls_made)
    return "\n\n".join(findings) if findings else "(no findings gathered)"
