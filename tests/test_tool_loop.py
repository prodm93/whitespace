"""Tests for the generic agent tool loop."""

from __future__ import annotations

from typing import Any

import pytest

from whitespace.agents._tool_loop import run_tool_loop


class FakeToolkit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "probe",
                "description": "probe something",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        if name == "explode":
            raise RuntimeError("boom")
        return f"result for {arguments.get('query')}"


class FakeRouter:
    """Feeds scripted responses; records the messages it was called with."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.seen_messages: list[list[dict[str, Any]]] = []
        self.index = 0

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.seen_messages.append(kwargs["messages"])
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response


def _tool_response(*names: str) -> dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [
            {"id": f"t{i}", "name": n, "arguments": {"query": f"q{i}"}} for i, n in enumerate(names)
        ],
        "stop_reason": "tool_use",
    }


_DONE = {"content": "conclusions", "tool_calls": [], "stop_reason": "end"}


@pytest.mark.asyncio
async def test_loop_runs_tools_then_stops_on_no_calls() -> None:
    toolkit = FakeToolkit()
    router = FakeRouter([_tool_response("probe"), _DONE])
    findings = await run_tool_loop(
        router,  # type: ignore[arg-type]
        role="r",
        system_prompt="s",
        user_prompt="u",
        toolkit=toolkit,
        max_tool_calls=5,
    )
    assert toolkit.calls == [("probe", {"query": "q0"})]
    assert "result for q0" in findings
    assert "conclusions" in findings
    final_messages = router.seen_messages[-1]
    assert final_messages[-1]["role"] == "tool"
    assert final_messages[-1]["content"] == "result for q0"


@pytest.mark.asyncio
async def test_loop_respects_tool_call_cap() -> None:
    toolkit = FakeToolkit()
    router = FakeRouter([_tool_response("probe")])  # always asks for more
    await run_tool_loop(
        router,  # type: ignore[arg-type]
        role="r",
        system_prompt="s",
        user_prompt="u",
        toolkit=toolkit,
        max_tool_calls=3,
    )
    assert len(toolkit.calls) == 3


@pytest.mark.asyncio
async def test_loop_reports_tool_failure_and_continues() -> None:
    toolkit = FakeToolkit()
    router = FakeRouter([_tool_response("explode"), _DONE])
    findings = await run_tool_loop(
        router,  # type: ignore[arg-type]
        role="r",
        system_prompt="s",
        user_prompt="u",
        toolkit=toolkit,
        max_tool_calls=5,
    )
    assert "failed" in findings
    tool_message = router.seen_messages[-1][-1]
    assert tool_message["role"] == "tool"
    assert "failed" in tool_message["content"]
