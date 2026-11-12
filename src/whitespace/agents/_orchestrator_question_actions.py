"""Orchestrator actions for runs that pause for the user's answers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from whitespace.agents._orchestrator_session import AnalysisSession
from whitespace.agents._tool_loop import TerminalToolError
from whitespace.orchestration._question_types import (
    AnswersDoNotMatch,
    AnswersLocked,
    NoPendingPause,
    PauseAlreadyPending,
    PausedForQuestions,
    QuestionRunBusy,
)

if TYPE_CHECKING:
    from whitespace.orchestration.pipeline import Pipeline
    from whitespace.schemas.gap import UnmetNeed

logger = logging.getLogger(__name__)

ANSWERS_ARRIVED_TWICE = "These questions already have answers. The analysis continues."
NO_QUESTIONS_WAITING = "No questions are waiting for an answer."
RUN_WAITING = "A run is waiting for your answers. Answer or skip the questions first."
RUN_IN_PROGRESS = "Another run is in progress. Wait for it to finish, then try again."
ANSWERS_LOCKED = (
    "The analysis already finished with your earlier answers. Reload the page to continue."
)
NO_SUBMISSION = "No answers were submitted by the user. Stop and report."


def _blocked(session: AnalysisSession, reason: str) -> str:
    session.blocked_reason = reason
    return reason


async def submit_answers(pipeline: Pipeline, session: AnalysisSession) -> str:
    """Continue the paused run with the user's submission; each submission is used once.

    A refusal becomes the job's blocked reason. Any other failure ends the job.
    """
    if not session.question_answers:
        return NO_SUBMISSION
    submission = session.question_answers
    session.question_answers = None
    try:
        resumed = await pipeline.resume_questions(submission)
    except (NoPendingPause, AnswersDoNotMatch):
        return _blocked(session, NO_QUESTIONS_WAITING)
    except QuestionRunBusy:
        return _blocked(session, ANSWERS_ARRIVED_TWICE)
    except AnswersLocked:
        return _blocked(session, ANSWERS_LOCKED)
    except Exception as exc:
        logger.exception("submit_question_answers: continuing the paused run failed")
        raise TerminalToolError(str(exc)) from exc
    session.pending_questions = []
    session.blocked_reason = None
    if resumed.stage == "gap":
        session.needs = resumed.needs
        titles = "; ".join(n.title for n in session.needs)
        return f"Gap analysis complete. {len(session.needs)} gaps found: {titles}"
    session.proposals = resumed.proposals
    titles = "; ".join(p.title for p in session.proposals)
    return f"Ideation complete. {len(session.proposals)} proposals: {titles}"


async def guard_new_run(pipeline: Pipeline, session: AnalysisSession) -> str | None:
    """Refuse a new run while a pause is pending; a fresh start discards the pause first."""
    if await pipeline.pending_questions() is None:
        return None
    if not session.fresh_start:
        return _blocked(session, RUN_WAITING)
    try:
        await pipeline.discard_pending_questions()
    except QuestionRunBusy:
        return _blocked(session, RUN_IN_PROGRESS)
    return None


def record_pause(session: AnalysisSession, paused: PausedForQuestions) -> str:
    """Keep the asked questions in the session; tell the model to stop."""
    session.pending_questions = paused.questions
    session.pending_stage = paused.stage
    return f"Analysis paused: {len(paused.questions)} question(s) for the user. Stop and report."


def refuse_run(session: AnalysisSession, error: PauseAlreadyPending | QuestionRunBusy) -> str:
    """The blocked reason for a question-enabled run that could not start."""
    reason = RUN_WAITING if isinstance(error, PauseAlreadyPending) else RUN_IN_PROGRESS
    return _blocked(session, reason)


async def run_gap_stage(pipeline: Pipeline, s: AnalysisSession) -> str | None:
    """Run the gap analysis into the session; a pause or a refusal returns its text."""
    assert s.profile is not None
    if not s.ask_questions:
        s.needs = await pipeline.analyse_gaps(
            s.profile,
            s.domain,
            s.doc_paths,
            keep_findings=s.keep_findings,
            run_id=s.run_id or None,
            fresh_start=s.fresh_start,
        )
        return None
    try:
        result = await pipeline.analyse_gaps_with_questions(
            s.profile,
            s.domain,
            s.doc_paths,
            keep_findings=s.keep_findings,
            run_id=s.run_id or None,
            fresh_start=s.fresh_start,
        )
    except (PauseAlreadyPending, QuestionRunBusy) as error:
        return refuse_run(s, error)
    if isinstance(result, PausedForQuestions):
        return record_pause(s, result)
    s.needs = result
    return None


async def run_ideation_stage(
    pipeline: Pipeline, s: AnalysisSession, chosen: list[UnmetNeed]
) -> str | None:
    """Run ideation on the chosen needs into the session; a pause or a refusal returns its text."""
    assert s.profile is not None
    if not s.ask_questions:
        s.proposals = await pipeline.ideate(
            chosen, s.profile, gap_run_id=s.gap_run_id, fresh_start=s.fresh_start
        )
        return None
    try:
        result = await pipeline.ideate_with_questions(
            chosen,
            s.profile,
            run_id=s.run_id or None,
            gap_run_id=s.gap_run_id,
            fresh_start=s.fresh_start,
            domain=s.domain,
        )
    except (PauseAlreadyPending, QuestionRunBusy) as error:
        return refuse_run(s, error)
    if isinstance(result, PausedForQuestions):
        return record_pause(s, result)
    s.proposals = result
    return None
