"""The two halves of each council as JSON-in, JSON-out steps for the pause shell."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from whitespace.orchestration._gap_council_state import dump_mid_state, load_mid_state
from whitespace.orchestration._ideation_council_state import (
    dump_ideation_state,
    load_ideation_state,
)
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.schemas.question import UserAnswer


class CouncilHalves(Protocol):
    stage: Literal["gap", "ideation"]

    async def first(self, state: dict[str, Any]) -> dict[str, Any]: ...

    async def second(
        self, state: dict[str, Any], answers: list[dict[str, Any]]
    ) -> dict[str, Any]: ...


def _answers(answers: list[dict[str, Any]]) -> list[UserAnswer]:
    return [UserAnswer.model_validate(a) for a in answers]


class GapHalves:
    stage: Literal["gap", "ideation"] = "gap"

    def __init__(self, gap_council: GapCouncilGraph) -> None:
        self._council = gap_council

    async def first(self, state: dict[str, Any]) -> dict[str, Any]:
        return dump_mid_state(await self._council.run_first_half(load_mid_state(state)))

    async def second(self, state: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
        needs, discards = await self._council.run_second_half(
            load_mid_state(state), _answers(answers)
        )
        return {
            "needs": [n.model_dump(mode="json") for n in needs],
            "discards": discards,
            "run_id": state["run_id"],
            "domain": state["domain"],
        }


class IdeationHalves:
    stage: Literal["gap", "ideation"] = "ideation"

    def __init__(self, ideation_council: IdeationCouncilGraph) -> None:
        self._council = ideation_council

    async def first(self, state: dict[str, Any]) -> dict[str, Any]:
        return dump_ideation_state(await self._council.run_first_half(load_ideation_state(state)))

    async def second(self, state: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
        proposals, discards = await self._council.run_second_half(
            load_ideation_state(state), _answers(answers)
        )
        return {
            "proposals": [p.model_dump(mode="json") for p in proposals],
            "discards": discards,
            "run_id": state["run_id"],
            "gap_run_id": state["gap_run_id"],
            "selected_need_titles": [n["title"] for n in state["selected_needs"]],
        }
