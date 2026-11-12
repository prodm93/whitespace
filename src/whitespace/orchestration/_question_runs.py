"""Start, continue and discard runs that pause for the user's answers; one at a time."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from whitespace.orchestration._council_halves import CouncilHalves
from whitespace.orchestration._question_pause import PauseOutcome, QuestionPauseShell
from whitespace.orchestration._question_types import (
    AnswersDoNotMatch,
    AnswersLocked,
    NoPendingPause,
    PauseAlreadyPending,
    QuestionRunBusy,
    ResumedRun,
    Stage,
)
from whitespace.orchestration._run_records import save_gap_result, save_idea_result
from whitespace.schemas._question_scoring import compute_outcome_score
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.question import QuestionRecord, UserAnswer
from whitespace.store.base import PendingPause, SessionStore


class QuestionRuns:
    """The one place that starts, continues and discards a paused run.

    One lock covers every operation. A second operation while one runs is
    refused at once with ``QuestionRunBusy``; it never waits.
    """

    def __init__(
        self,
        store: SessionStore,
        shell: QuestionPauseShell,
        gap_halves: CouncilHalves,
        ideation_halves: CouncilHalves,
    ) -> None:
        self._store = store
        self._shell = shell
        self._halves = {"gap": gap_halves, "ideation": ideation_halves}
        self._lock = asyncio.Lock()

    def _claim(self) -> asyncio.Lock:
        if self._lock.locked():
            raise QuestionRunBusy("another question operation is running")
        return self._lock

    async def start(self, stage: Stage, job_id: str, initial: dict[str, Any]) -> PauseOutcome:
        """Run the first half; save a pending row when it asks questions, else the result."""
        async with self._claim():
            if await self._store.get_pending_pause() is not None:
                raise PauseAlreadyPending("a run is already waiting for answers")
            outcome = await self._shell.run(job_id, self._halves[stage], initial)
            if outcome.questions:
                await self._store.save_pending_pause(
                    PendingPause(
                        pause_id=uuid.uuid4().hex,
                        job_id=job_id,
                        thread_id=job_id,
                        stage=stage,
                        questions=[QuestionRecord.model_validate(q) for q in outcome.questions],
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                await self._save_result(stage, outcome.result or {})
            return outcome

    async def resume(self, submission: list[UserAnswer]) -> ResumedRun:
        """Continue the paused run with the user's submission and store its result."""
        async with self._claim():
            pause = await self._store.get_pending_pause()
            if pause is None:
                raise NoPendingPause("no run is waiting for answers")
            answers = _normalise(pause, submission)
            halves = self._halves[pause.stage]
            status = await self._shell.status(pause.thread_id, halves)
            if status == "missing":
                await self._store.delete_pending_pause(pause.pause_id)
                await self._expire(pause)
                raise NoPendingPause("the paused run is gone; its questions have expired")
            sent = [a.model_dump(mode="json") for a in answers]
            if status == "complete":
                if not await self._matches_saved(answers):
                    await self._mark_computed(pause)
                    raise AnswersLocked("the run already finished with earlier answers")
                if not pause.computed:
                    await self._mark_computed(pause)
            else:
                await self._write_answers(pause, answers)
            outcome = await self._shell.resume(pause.thread_id, halves, sent)
            if status != "complete":
                await self._mark_computed(pause)
            return await self._finalise(pause, outcome.result or {})

    async def _mark_computed(self, pause: PendingPause) -> None:
        await self._store.save_pending_pause(pause.model_copy(update={"computed": True}))

    async def _matches_saved(self, answers: list[UserAnswer]) -> bool:
        saved = {r.question_id: r for r in await self._store.list_question_records()}
        return all(
            (saved[a.question_id].status, saved[a.question_id].answer) == (a.status, a.answer)
            for a in answers
            if a.question_id in saved
        )

    async def discard_pending(self) -> bool:
        """Drop the paused run: its row, its thread, and its questions as expired."""
        async with self._claim():
            pause = await self._store.get_pending_pause()
            if pause is None:
                return False
            await self._store.delete_pending_pause(pause.pause_id)
            await self._expire(pause)
            await self._shell.discard(pause.thread_id)
            return True

    async def _expire(self, pause: PendingPause) -> None:
        for question in pause.questions:
            await self._store.update_question_record(
                question.question_id, status="expired", outcome_score=0.0
            )

    async def _write_answers(self, pause: PendingPause, answers: list[UserAnswer]) -> None:
        current = {r.question_id: r for r in await self._store.list_question_records()}
        for answer in answers:
            record = current.get(answer.question_id)
            if record is None:
                continue
            updated = record.model_copy(update={"status": answer.status, "answer": answer.answer})
            await self._store.update_question_record(
                answer.question_id,
                status=answer.status,
                answer=answer.answer,
                outcome_score=compute_outcome_score(updated),
            )

    async def _finalise(self, pause: PendingPause, result: dict[str, Any]) -> ResumedRun:
        """Store the result, then clear the row; every write is safe to repeat."""
        await self._save_result(pause.stage, result)
        await self._store.delete_pending_pause(pause.pause_id)
        return ResumedRun(
            stage=pause.stage,
            needs=[UnmetNeed.model_validate(n) for n in result.get("needs", [])],
            proposals=[IdeationProposal.model_validate(p) for p in result.get("proposals", [])],
        )

    async def _save_result(self, stage: Stage, result: dict[str, Any]) -> None:
        if stage == "gap":
            await save_gap_result(
                self._store,
                result["run_id"],
                result["domain"],
                [UnmetNeed.model_validate(n) for n in result["needs"]],
                result["discards"],
            )
        else:
            await save_idea_result(
                self._store,
                result["run_id"],
                result["gap_run_id"],
                result["selected_need_titles"],
                [IdeationProposal.model_validate(p) for p in result["proposals"]],
                result["discards"],
            )


def _normalise(pause: PendingPause, submission: list[UserAnswer]) -> list[UserAnswer]:
    """One answer for each asked question: a missing entry or a blank answer is skipped."""
    by_id = {a.question_id: a for a in submission}
    if not any(q.question_id in by_id for q in pause.questions):
        raise AnswersDoNotMatch("the answers name no question of the waiting run")
    normalised: list[UserAnswer] = []
    for question in pause.questions:
        entry = by_id.get(question.question_id)
        if entry is None or (entry.status == "answered" and not entry.answer.strip()):
            normalised.append(UserAnswer(question_id=question.question_id, status="skipped"))
        else:
            normalised.append(entry)
    return normalised
