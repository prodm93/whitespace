from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from whitespace.schemas.question import QuestionRecord
from whitespace.store.base import PendingPause
from whitespace.store.noop_store import NoopSessionStore
from whitespace.store.sqlite_store import SqliteSessionStore

_CREATED_AT = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _question(question_id: str, *, seconds_later: int = 0) -> QuestionRecord:
    return QuestionRecord(
        question_id=question_id,
        run_id="r1",
        stage="gap",
        purpose="clarify",
        question="Which operating temperature is required?",
        hypothesis="Below 80 C",
        rationale="This determines which materials remain viable.",
        asker_role="gap_identifier_1",
        asked=True,
        created_at=_CREATED_AT + timedelta(seconds=seconds_later),
    )


async def test_question_records_save_list_and_limit(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "questions.db")
    older = _question("q1")
    newer = _question("q2", seconds_later=1)

    await store.save_question_records([older, newer])

    assert await store.list_question_records() == [newer, older]
    assert await store.list_question_records(limit=1) == [newer]
    assert await store.list_question_records(limit=0) == []


async def test_question_record_update_round_trip(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "questions.db")
    await store.save_question_records([_question("q1")])

    await store.update_question_record(
        "q1",
        status="answered",
        answer="The requirement is 70 C.",
        outcome_score=1.25,
        survival_bonus=0.25,
    )

    records = await store.list_question_records()
    assert len(records) == 1
    assert records[0].status == "answered"
    assert records[0].answer == "The requirement is 70 C."
    assert records[0].outcome_score == 1.25
    assert records[0].survival_bonus == 0.25


async def test_missing_question_update_is_a_no_op(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "questions.db")

    await store.update_question_record("missing", status="expired")

    assert await store.list_question_records() == []


async def test_pending_pause_save_get_delete(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "questions.db")
    pause = PendingPause(
        pause_id="pause-1",
        job_id="job-1",
        thread_id="thread-1",
        stage="gap",
        questions=[_question("q1")],
        created_at=_CREATED_AT,
    )

    await store.save_pending_pause(pause)
    assert await store.get_pending_pause() == pause

    await store.delete_pending_pause(pause.pause_id)
    assert await store.get_pending_pause() is None


async def test_noop_store_uses_question_defaults() -> None:
    store = NoopSessionStore()
    pause = PendingPause(
        pause_id="pause-1",
        job_id="job-1",
        thread_id="thread-1",
        stage="gap",
        questions=[_question("q1")],
        created_at=_CREATED_AT,
    )

    await store.save_question_records(pause.questions)
    await store.update_question_record("q1", status="answered")
    await store.save_pending_pause(pause)
    await store.delete_pending_pause(pause.pause_id)

    assert await store.list_question_records() == []
    assert await store.get_pending_pause() is None
