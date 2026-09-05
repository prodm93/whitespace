from __future__ import annotations

from typing import Any


class FakeRouter:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return next(self._responses)


class EmptyToolkit:
    def tool_definitions(self) -> list[dict[str, Any]]:
        return []

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        raise AssertionError("No tool calls expected")


def proposal(
    *,
    question: str = "Do you have access to a pilot kiln?",
    purpose: str = "unlock",
    title: str = "Adaptive kiln control",
) -> dict[str, str]:
    return {
        "question": question,
        "purpose": purpose,
        "rationale": "[F2] Access determines whether the control loop is testable.",
        "hypothesis": "You have access through an industry partner.",
        "related_candidate_title": title,
    }
