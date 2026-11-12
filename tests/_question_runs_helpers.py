"""Fixtures for QuestionRuns tests: a real store and shell on disk, fake council halves."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from whitespace.orchestration._pipeline_questions import PipelineQuestionsMixin
from whitespace.orchestration._question_pause import QuestionPauseShell
from whitespace.orchestration._question_runs import QuestionRuns
from whitespace.schemas.question import QuestionRecord
from whitespace.store.sqlite_store import SqliteSessionStore

NEED = {
    "title": "Heat recovery",
    "description": "d",
    "current_state": "s",
    "why_unmet": "w",
}
DISCARD = {"title": "Kill A", "description": "d", "reason": "Covered by US1", "domain": "energy"}


def make_record(question_id: str, run_id: str = "job-1") -> QuestionRecord:
    return QuestionRecord(
        question_id=question_id,
        run_id=run_id,
        stage="gap",
        purpose="clarify",
        question=f"Question {question_id}?",
        hypothesis="h",
        rationale="r",
        asker_role="gap_identifier_1",
        asked=True,
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


class FakeGapHalves:
    """Asks the given records; the second half returns one need and the given discards."""

    stage: Literal["gap", "ideation"] = "gap"

    def __init__(
        self,
        records: list[QuestionRecord],
        *,
        discards: list[dict[str, str]] | None = None,
        failures: int = 0,
    ) -> None:
        self.records = records
        self.discards = discards or []
        self.failures = failures
        self.second_answers: list[list[dict[str, Any]]] = []

    async def first(self, state: dict[str, Any]) -> dict[str, Any]:
        pending = [r.model_dump(mode="json") for r in self.records]
        return {**state, "pending_questions": pending}

    async def second(self, state: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
        self.second_answers.append(answers)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("second half failed")
        return {
            "needs": [NEED],
            "discards": self.discards,
            "run_id": state["run_id"],
            "domain": "energy",
        }


async def make_runs(
    tmp_path: Path,
    records: list[QuestionRecord],
    store: SqliteSessionStore | None = None,
    **halves_kwargs: Any,
) -> tuple[QuestionRuns, SqliteSessionStore, FakeGapHalves, QuestionPauseShell]:
    store = store or SqliteSessionStore(tmp_path / "s.db")
    await store.save_question_records(records)
    shell = QuestionPauseShell(str(tmp_path / "checkpoints.db"))
    halves = FakeGapHalves(records, **halves_kwargs)
    return QuestionRuns(store, shell, halves, halves), store, halves, shell  # type: ignore[arg-type]


class QuestionsOnlyPipeline(PipelineQuestionsMixin):
    """A pipeline whose question runs are real and whose other parts are absent."""

    def __init__(
        self,
        runs: QuestionRuns,
        store: SqliteSessionStore,
        *,
        router: Any = None,
        key: str = "",
        halves: FakeGapHalves | None = None,
    ) -> None:
        self._question_runs = runs
        self._store = store
        self.router = router
        self.key = key
        self.halves = halves
        self.closed = False

    async def initialise(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True
