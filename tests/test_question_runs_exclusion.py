"""One question operation at a time: a second one is refused at once, never queued."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from _question_runs_helpers import FakeGapHalves, make_record, make_runs

from whitespace.orchestration._question_types import PauseAlreadyPending, QuestionRunBusy
from whitespace.schemas.question import UserAnswer

_ANSWER = [UserAnswer(question_id="q-1", status="answered", answer="Pouch cells")]


class HeldHalves(FakeGapHalves):
    """Each half waits on an event, so a test can act while it is running."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.hold_first = False
        self.hold_second = False
        self.first_calls = 0

    async def first(self, state: dict[str, Any]) -> dict[str, Any]:
        self.first_calls += 1
        if self.hold_first:
            self.entered.set()
            await self.release.wait()
        return await super().first(state)

    async def second(self, state: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
        if self.hold_second:
            self.entered.set()
            await self.release.wait()
        return await super().second(state, answers)


async def _runs(tmp_path: Path) -> tuple[Any, Any, HeldHalves]:
    runs, store, _, _ = await make_runs(tmp_path, [make_record("q-1")])
    halves = HeldHalves([make_record("q-1")])
    runs._halves = {"gap": halves, "ideation": halves}
    return runs, store, halves


async def test_two_starts_at_once_give_one_pause_and_one_refusal(tmp_path: Path) -> None:
    runs, store, halves = await _runs(tmp_path)
    halves.hold_first = True
    first = asyncio.create_task(runs.start("gap", "job-1", {"run_id": "job-1"}))
    await halves.entered.wait()

    with pytest.raises(QuestionRunBusy):
        await runs.start("gap", "job-2", {"run_id": "job-2"})
    halves.release.set()
    await first

    pause = await store.get_pending_pause()
    assert pause is not None and pause.job_id == "job-1"
    assert halves.first_calls == 1


async def test_a_start_while_a_pause_is_pending_runs_nothing(tmp_path: Path) -> None:
    runs, _, halves = await _runs(tmp_path)
    await runs.start("gap", "job-1", {"run_id": "job-1"})

    with pytest.raises(PauseAlreadyPending):
        await runs.start("gap", "job-2", {"run_id": "job-2"})

    assert halves.first_calls == 1


async def _resume_in_flight(runs: Any, halves: HeldHalves) -> asyncio.Task[Any]:
    await runs.start("gap", "job-1", {"run_id": "job-1"})
    halves.hold_second = True
    task = asyncio.create_task(runs.resume(_ANSWER))
    await halves.entered.wait()
    return task


async def test_a_discard_during_a_continue_is_refused(tmp_path: Path) -> None:
    runs, store, halves = await _runs(tmp_path)
    task = await _resume_in_flight(runs, halves)

    with pytest.raises(QuestionRunBusy):
        await runs.discard_pending()
    halves.release.set()
    await task

    assert await store.get_gap_run("job-1") is not None


async def test_a_second_continue_during_a_continue_is_refused(tmp_path: Path) -> None:
    runs, _, halves = await _runs(tmp_path)
    task = await _resume_in_flight(runs, halves)

    with pytest.raises(QuestionRunBusy):
        await runs.resume(_ANSWER)
    halves.release.set()
    await task


async def test_the_lock_is_free_after_an_operation_that_raised(tmp_path: Path) -> None:
    runs, _, _ = await _runs(tmp_path)
    await runs.start("gap", "job-1", {"run_id": "job-1"})
    with pytest.raises(PauseAlreadyPending):
        await runs.start("gap", "job-2", {"run_id": "job-2"})

    assert await runs.discard_pending() is True
