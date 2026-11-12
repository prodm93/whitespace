"""The pause shell on the real SQLite checkpointer: pause, continue, retry, discard."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pytest

from whitespace.orchestration._question_pause import QuestionPauseShell
from whitespace.orchestration._question_types import NoPendingPause

_QUESTION = {"question_id": "q-1", "question": "Which packs?"}


class FakeHalves:
    """Counts each half; the second half can fail a set number of times."""

    stage: Literal["gap", "ideation"] = "gap"

    def __init__(self, *, questions: bool = True, failures: int = 0) -> None:
        self.questions = questions
        self.failures = failures
        self.first_calls = 0
        self.second_answers: list[list[dict[str, Any]]] = []

    async def first(self, state: dict[str, Any]) -> dict[str, Any]:
        self.first_calls += 1
        return {**state, "pending_questions": [_QUESTION] if self.questions else []}

    async def second(self, state: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
        self.second_answers.append(answers)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("second half failed")
        return {"needs": [state["run_id"]], "answers": answers}


def _shell(tmp_path: Path) -> QuestionPauseShell:
    return QuestionPauseShell(str(tmp_path / "checkpoints" / "q.db"))


async def test_a_run_with_no_questions_completes_at_once(tmp_path: Path) -> None:
    halves = FakeHalves(questions=False)

    outcome = await _shell(tmp_path).run("job-1", halves, {"run_id": "job-1"})

    assert outcome.questions == []
    assert outcome.result == {"needs": ["job-1"], "answers": []}
    assert halves.first_calls == 1
    assert len(halves.second_answers) == 1


_ANSWERS = [{"question_id": "q-1", "status": "answered", "answer": "Pouch cells"}]
_OTHER = [{"question_id": "q-1", "status": "answered", "answer": "Prismatic cells"}]


async def test_a_run_with_questions_pauses_before_the_second_half(tmp_path: Path) -> None:
    halves = FakeHalves()
    shell = _shell(tmp_path)

    outcome = await shell.run("job-1", halves, {"run_id": "job-1"})

    assert outcome.questions == [_QUESTION]
    assert outcome.result is None
    assert halves.second_answers == []
    assert await shell.status("job-1", halves) == "awaiting"


async def test_a_new_shell_on_the_same_file_continues_the_run(tmp_path: Path) -> None:
    halves = FakeHalves()
    await _shell(tmp_path).run("job-1", halves, {"run_id": "job-1"})

    restarted = _shell(tmp_path)
    outcome = await restarted.resume("job-1", halves, _ANSWERS)

    assert outcome.result == {"needs": ["job-1"], "answers": _ANSWERS}
    assert halves.first_calls == 1
    assert halves.second_answers == [_ANSWERS]
    assert await restarted.status("job-1", halves) == "complete"


async def test_a_second_continue_returns_the_stored_result_and_runs_nothing(
    tmp_path: Path,
) -> None:
    halves = FakeHalves()
    shell = _shell(tmp_path)
    await shell.run("job-1", halves, {"run_id": "job-1"})
    first = await shell.resume("job-1", halves, _ANSWERS)

    again = await shell.resume("job-1", halves, _OTHER)

    assert again.result == first.result
    assert halves.second_answers == [_ANSWERS]


async def test_a_discarded_thread_is_missing(tmp_path: Path) -> None:
    halves = FakeHalves()
    shell = _shell(tmp_path)
    await shell.run("job-1", halves, {"run_id": "job-1"})

    await shell.discard("job-1")

    assert await shell.status("job-1", halves) == "missing"
    with pytest.raises(NoPendingPause):
        await shell.resume("job-1", halves, _ANSWERS)


async def test_a_failed_second_half_is_retried_with_replaced_answers(tmp_path: Path) -> None:
    halves = FakeHalves(failures=1)
    shell = _shell(tmp_path)
    await shell.run("job-1", halves, {"run_id": "job-1"})
    with pytest.raises(RuntimeError, match="second half failed"):
        await shell.resume("job-1", halves, _ANSWERS)
    assert await shell.status("job-1", halves) == "second_half_pending"

    outcome = await _shell(tmp_path).resume("job-1", halves, _OTHER)

    assert outcome.result == {"needs": ["job-1"], "answers": _OTHER}
    assert halves.second_answers == [_ANSWERS, _OTHER]
    assert halves.first_calls == 1


async def test_two_failed_second_halves_then_a_success(tmp_path: Path) -> None:
    halves = FakeHalves(failures=2)
    shell = _shell(tmp_path)
    await shell.run("job-1", halves, {"run_id": "job-1"})
    for _ in range(2):
        with pytest.raises(RuntimeError, match="second half failed"):
            await shell.resume("job-1", halves, _ANSWERS)

    outcome = await shell.resume("job-1", halves, _ANSWERS)

    assert outcome.result == {"needs": ["job-1"], "answers": _ANSWERS}
    assert len(halves.second_answers) == 3
    assert halves.first_calls == 1
