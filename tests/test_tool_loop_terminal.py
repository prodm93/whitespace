"""A terminal tool error ends the tool loop; any other tool error is reported to the model."""

from __future__ import annotations

from typing import Any

import pytest

from whitespace.agents._tool_loop import TerminalToolError, run_tool_loop


class Toolkit:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.dispatched: list[str] = []

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [{"name": n, "description": n, "parameters": {"type": "object"}} for n in "ab"]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        self.dispatched.append(name)
        if name == "a":
            raise self.error
        return "ok"


class Router:
    def __init__(self) -> None:
        self.calls = 0

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls > 1:
            return {"content": "done", "tool_calls": []}
        calls = [
            {"id": "1", "name": "a", "arguments": {}},
            {"id": "2", "name": "b", "arguments": {}},
        ]
        return {"content": "", "tool_calls": calls}


async def _loop(toolkit: Toolkit) -> str:
    return await run_tool_loop(
        Router(),  # type: ignore[arg-type]
        role="orchestrator",
        system_prompt="s",
        user_prompt="u",
        toolkit=toolkit,
        max_tool_calls=5,
    )


async def test_a_terminal_tool_error_ends_the_loop_before_the_next_call() -> None:
    toolkit = Toolkit(TerminalToolError("second half failed"))

    with pytest.raises(TerminalToolError, match="second half failed"):
        await _loop(toolkit)

    assert toolkit.dispatched == ["a"]


async def test_any_other_tool_error_is_reported_to_the_model() -> None:
    toolkit = Toolkit(RuntimeError("boom"))

    transcript = await _loop(toolkit)

    assert toolkit.dispatched == ["a", "b"]
    assert "Tool a failed; try a different call." in transcript
