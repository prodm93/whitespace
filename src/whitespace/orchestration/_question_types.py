"""Results, refusals and the pending view of runs that pause for the user's answers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.question import QuestionRecord
from whitespace.store.base import SessionStore

Stage = Literal["gap", "ideation"]


@dataclass
class PausedForQuestions:
    stage: Stage
    questions: list[QuestionRecord]


@dataclass
class ResumedRun:
    stage: Stage
    needs: list[UnmetNeed] = field(default_factory=list)
    proposals: list[IdeationProposal] = field(default_factory=list)


@dataclass
class PendingView:
    stage: Stage
    questions: list[QuestionRecord]
    editable: bool


class NoPendingPause(RuntimeError):
    """No run is waiting for answers."""


class AnswersDoNotMatch(RuntimeError):
    """None of the submitted answers names a question of the pending run."""


class AnswersLocked(RuntimeError):
    """The run already finished with earlier answers; different answers are refused."""


class QuestionRunBusy(RuntimeError):
    """Another start, continue or discard of a paused run is in progress."""


class PauseAlreadyPending(RuntimeError):
    """A run is already waiting for answers, so a new one cannot pause."""


async def pending_view(store: SessionStore) -> PendingView | None:
    """The waiting run's stage and each asked question as its current stored record."""
    pause = await store.get_pending_pause()
    if pause is None:
        return None
    asked = {q.question_id for q in pause.questions}
    current = {
        r.question_id: r for r in await store.list_question_records() if r.question_id in asked
    }
    questions = [current.get(q.question_id, q) for q in pause.questions]
    return PendingView(stage=pause.stage, questions=questions, editable=not pause.computed)
