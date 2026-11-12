"""Pause shell: first half, a LangGraph interrupt for the answers, second half; checkpointed."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from whitespace.orchestration._council_halves import CouncilHalves
from whitespace.orchestration._question_types import NoPendingPause

ThreadStatus = Literal["awaiting", "second_half_pending", "complete", "missing"]


class _ShellState(TypedDict, total=False):
    mid: dict[str, Any]
    answers: list[dict[str, Any]]
    result: dict[str, Any]


@dataclass
class PauseOutcome:
    questions: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None


def _build(halves: CouncilHalves, saver: AsyncSqliteSaver) -> Any:
    async def first_half(state: _ShellState) -> dict[str, Any]:
        return {"mid": await halves.first(state["mid"])}

    def route(state: _ShellState) -> str:
        return "ask_user" if state["mid"].get("pending_questions") else "second_half"

    def ask_user(state: _ShellState) -> dict[str, Any]:
        answers = interrupt(state["mid"]["pending_questions"])
        return {"answers": answers}

    async def second_half(state: _ShellState) -> dict[str, Any]:
        return {"result": await halves.second(state["mid"], state.get("answers", []))}

    builder = StateGraph(_ShellState)
    builder.add_node("first_half", first_half)
    builder.add_node("ask_user", ask_user)
    builder.add_node("second_half", second_half)
    builder.set_entry_point("first_half")
    builder.add_conditional_edges(
        "first_half", route, {"ask_user": "ask_user", "second_half": "second_half"}
    )
    builder.add_edge("ask_user", "second_half")
    builder.add_edge("second_half", END)
    return builder.compile(checkpointer=saver)


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


class QuestionPauseShell:
    """Runs a council's halves around one interrupt, with every step in a checkpoint file.

    The ask step only calls ``interrupt``, because a continue runs that node
    again from its top. A second half that failed is retried by replacing the
    stored answers and invoking with no input; ``Command(resume=...)`` is
    never sent then, because LangGraph would run the old answers.
    """

    def __init__(self, checkpoint_path: str) -> None:
        self._path = checkpoint_path

    @asynccontextmanager
    async def _graph(self, halves: CouncilHalves) -> AsyncIterator[Any]:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(self._path) as saver:
            yield _build(halves, saver)

    async def run(
        self, thread_id: str, halves: CouncilHalves, initial: dict[str, Any]
    ) -> PauseOutcome:
        async with self._graph(halves) as graph:
            out = await graph.ainvoke({"mid": initial}, _config(thread_id))
        return _outcome(out)

    async def status(self, thread_id: str, halves: CouncilHalves) -> ThreadStatus:
        async with self._graph(halves) as graph:
            return await _status(graph, thread_id)

    async def resume(
        self, thread_id: str, halves: CouncilHalves, answers: list[dict[str, Any]]
    ) -> PauseOutcome:
        config = _config(thread_id)
        async with self._graph(halves) as graph:
            status = await _status(graph, thread_id)
            if status == "missing":
                raise NoPendingPause(f"no paused run for thread {thread_id}")
            if status == "complete":
                snapshot = await graph.aget_state(config)
                return PauseOutcome(result=snapshot.values.get("result"))
            if status == "awaiting":
                out = await graph.ainvoke(Command(resume=answers), config)
            else:
                await graph.aupdate_state(config, {"answers": answers}, as_node="ask_user")
                out = await graph.ainvoke(None, config)
        return _outcome(out)

    async def discard(self, thread_id: str) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(self._path) as saver:
            await saver.adelete_thread(thread_id)


async def _status(graph: Any, thread_id: str) -> ThreadStatus:
    snapshot = await graph.aget_state(_config(thread_id))
    if not snapshot.values:
        return "missing"
    if snapshot.interrupts:
        return "awaiting"
    if snapshot.next == ("second_half",):
        return "second_half_pending"
    if not snapshot.next:
        return "complete"
    raise RuntimeError(f"thread {thread_id} stopped before {snapshot.next}; it cannot continue")


def _outcome(out: dict[str, Any]) -> PauseOutcome:
    if "__interrupt__" in out:
        return PauseOutcome(questions=list(out["__interrupt__"][0].value))
    return PauseOutcome(result=out.get("result"))
