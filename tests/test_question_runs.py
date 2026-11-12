"""Starting, continuing and discarding a run that pauses for the user's answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _question_runs_helpers import DISCARD, make_record, make_runs

from whitespace.orchestration._question_types import AnswersDoNotMatch, NoPendingPause
from whitespace.schemas.question import QuestionRecord, UserAnswer
from whitespace.store.sqlite_store import SqliteSessionStore


async def test_a_paused_start_saves_one_pending_row(tmp_path: Path) -> None:
    runs, store, _, _ = await make_runs(tmp_path, [make_record("q-1")])

    outcome = await runs.start("gap", "job-1", {"run_id": "job-1"})

    pause = await store.get_pending_pause()
    assert pause is not None
    assert (pause.job_id, pause.thread_id, pause.stage) == ("job-1", "job-1", "gap")
    assert [q.question_id for q in pause.questions] == ["q-1"]
    assert [q["question_id"] for q in outcome.questions] == ["q-1"]


def _answer(question_id: str, answer: str = "", status: str = "answered") -> UserAnswer:
    return UserAnswer(question_id=question_id, status=status, answer=answer)  # type: ignore[arg-type]


async def _records(store: SqliteSessionStore) -> dict[str, QuestionRecord]:
    return {r.question_id: r for r in await store.list_question_records()}


async def test_a_continue_scores_the_answers_stores_the_run_and_clears_the_row(
    tmp_path: Path,
) -> None:
    runs, store, halves, _ = await make_runs(
        tmp_path, [make_record("q-1"), make_record("q-2")], discards=[DISCARD]
    )
    await runs.start("gap", "job-1", {"run_id": "job-1"})

    resumed = await runs.resume([_answer("q-1", "Pouch cells"), _answer("q-2", status="skipped")])

    records = await _records(store)
    assert [
        (records[q].status, records[q].answer, records[q].outcome_score) for q in ("q-1", "q-2")
    ] == [
        ("answered", "Pouch cells", 0.0),
        ("skipped", "", -0.3),
    ]
    assert [n.title for n in resumed.needs] == ["Heat recovery"]
    stored = await store.get_gap_run("job-1")
    assert stored is not None
    assert [d["title"] for d in await store.list_discards("gap")] == ["Kill A"]
    assert await store.get_pending_pause() is None
    assert halves.second_answers == [
        [
            {"question_id": "q-1", "status": "answered", "answer": "Pouch cells"},
            {"question_id": "q-2", "status": "skipped", "answer": ""},
        ]
    ]


def _sent(halves: Any) -> list[tuple[str, str, str]]:
    return [(a["question_id"], a["status"], a["answer"]) for a in halves.second_answers[-1]]


async def test_a_partial_submission_skips_the_rest_and_a_blank_answer_is_skipped(
    tmp_path: Path,
) -> None:
    runs, _, halves, _ = await make_runs(
        tmp_path, [make_record("q-1"), make_record("q-2"), make_record("q-3")]
    )
    await runs.start("gap", "job-1", {"run_id": "job-1"})

    await runs.resume([_answer("q-1", "Pouch cells"), _answer("q-2", "   ")])

    assert _sent(halves) == [
        ("q-1", "answered", "Pouch cells"),
        ("q-2", "skipped", ""),
        ("q-3", "skipped", ""),
    ]


async def test_a_fully_skipped_submission_still_completes(tmp_path: Path) -> None:
    runs, store, _, _ = await make_runs(tmp_path, [make_record("q-1")])
    await runs.start("gap", "job-1", {"run_id": "job-1"})

    await runs.resume([_answer("q-1", status="skipped")])

    assert await store.get_gap_run("job-1") is not None
    assert await store.get_pending_pause() is None


async def test_a_continue_with_no_pending_row_is_refused(tmp_path: Path) -> None:
    runs, _, _, _ = await make_runs(tmp_path, [make_record("q-1")])

    with pytest.raises(NoPendingPause):
        await runs.resume([_answer("q-1", "Yes")])


async def test_answers_that_match_no_question_are_refused_and_change_nothing(
    tmp_path: Path,
) -> None:
    runs, store, halves, _ = await make_runs(tmp_path, [make_record("q-1")])
    await runs.start("gap", "job-1", {"run_id": "job-1"})

    with pytest.raises(AnswersDoNotMatch):
        await runs.resume([_answer("other", "Yes")])

    assert (await _records(store))["q-1"].status == "pending"
    assert await store.get_pending_pause() is not None
    assert halves.second_answers == []


async def test_a_row_whose_thread_is_gone_is_cleared_and_its_questions_expire(
    tmp_path: Path,
) -> None:
    runs, store, _, shell = await make_runs(tmp_path, [make_record("q-1")])
    await runs.start("gap", "job-1", {"run_id": "job-1"})
    await shell.discard("job-1")

    with pytest.raises(NoPendingPause):
        await runs.resume([_answer("q-1", "Yes")])

    record = (await _records(store))["q-1"]
    assert (record.status, record.outcome_score) == ("expired", 0.0)
    assert await store.get_pending_pause() is None


async def test_discarding_a_pause_clears_the_row_expires_the_questions_and_the_thread(
    tmp_path: Path,
) -> None:
    runs, store, halves, shell = await make_runs(tmp_path, [make_record("q-1")])
    await runs.start("gap", "job-1", {"run_id": "job-1"})

    assert await runs.discard_pending() is True

    assert await store.get_pending_pause() is None
    assert (await _records(store))["q-1"].status == "expired"
    assert await shell.status("job-1", halves) == "missing"
    assert await runs.discard_pending() is False


async def test_a_start_that_asks_nothing_stores_the_run_and_its_discards(tmp_path: Path) -> None:
    runs, store, halves, _ = await make_runs(tmp_path, [], discards=[DISCARD])

    outcome = await runs.start("gap", "job-1", {"run_id": "job-1"})

    assert outcome.questions == []
    assert await store.get_pending_pause() is None
    assert await store.get_gap_run("job-1") is not None
    assert [d["title"] for d in await store.list_discards("gap")] == ["Kill A"]
