"""The orchestrator with questions: pausing, submitting answers, refusals, run identity."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from whitespace.agents._orchestrator_actions import OrchestratorActions
from whitespace.agents._orchestrator_session import AnalysisSession
from whitespace.agents._tool_loop import TerminalToolError
from whitespace.agents.orchestrator_agent import OrchestratorAgent
from whitespace.orchestration._question_types import (
    AnswersDoNotMatch,
    AnswersLocked,
    NoPendingPause,
    PauseAlreadyPending,
    PausedForQuestions,
    QuestionRunBusy,
    ResumedRun,
)
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import QuestionRecord, UserAnswer
from whitespace.store.base import PendingPause

STRING_15 = "These questions already have answers. The analysis continues."
STRING_16 = "No questions are waiting for an answer."
STRING_17 = "A run is waiting for your answers. Answer or skip the questions first."
STRING_18 = "Another run is in progress. Wait for it to finish, then try again."
STRING_19 = "The analysis already finished with your earlier answers. Reload the page to continue."
NO_SUBMISSION = "No answers were submitted by the user. Stop and report."

_RECORD = QuestionRecord(
    question_id="q-1",
    run_id="job-1",
    stage="gap",
    purpose="clarify",
    question="Which packs?",
    hypothesis="h",
    rationale="r",
    asker_role="gap_identifier_1",
    asked=True,
    created_at=datetime(2026, 11, 11, tzinfo=UTC),
)
_NEED = UnmetNeed(title="Gap A", description="d", current_state="c", why_unmet="w")
_ANSWERS = [UserAnswer(question_id="q-1", status="answered", answer="Pouch cells")]


class QuestionPipeline:
    def __init__(self) -> None:
        self.pending: PendingPause | None = None
        self.resume_result: ResumedRun | Exception = ResumedRun("gap", needs=[_NEED])
        self.resume_calls = 0
        self.gap_result: Any = PausedForQuestions("gap", [_RECORD])
        self.calls: dict[str, list[dict[str, Any]]] = {}
        self.discard_result: bool | Exception = True

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.setdefault(name, []).append(kwargs)

    async def pending_questions(self) -> PendingPause | None:
        return self.pending

    async def discard_pending_questions(self) -> bool:
        if isinstance(self.discard_result, Exception):
            raise self.discard_result
        self.pending = None
        return self.discard_result

    async def resume_questions(self, submission: list[UserAnswer]) -> ResumedRun:
        self.resume_calls += 1
        if isinstance(self.resume_result, Exception):
            raise self.resume_result
        return self.resume_result

    async def analyse_gaps(self, *args: Any, **kwargs: Any) -> list[UnmetNeed]:
        self._record("analyse_gaps", kwargs)
        return [_NEED]

    async def analyse_gaps_with_questions(self, *args: Any, **kwargs: Any) -> Any:
        self._record("analyse_gaps_with_questions", kwargs)
        if isinstance(self.gap_result, Exception):
            raise self.gap_result
        return self.gap_result

    async def ideate(self, *args: Any, **kwargs: Any) -> list[Any]:
        self._record("ideate", kwargs)
        return []

    async def ideate_with_questions(self, *args: Any, **kwargs: Any) -> list[Any]:
        self._record("ideate_with_questions", kwargs)
        return []


def _pause() -> PendingPause:
    return PendingPause(
        pause_id="p",
        job_id="job-0",
        thread_id="job-0",
        stage="gap",
        questions=[_RECORD],
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


def _actions(pipeline: QuestionPipeline, **session: Any) -> OrchestratorActions:
    defaults: dict[str, Any] = {"profile": ProfessionalProfile(), "domain": "energy"}
    return OrchestratorActions(pipeline, AnalysisSession(**{**defaults, **session}))  # type: ignore[arg-type]


async def test_a_submission_continues_the_run_and_fills_the_needs() -> None:
    pipeline = QuestionPipeline()
    actions = _actions(pipeline, question_answers=_ANSWERS, pending_questions=[_RECORD])

    result = await actions.dispatch("submit_question_answers", {})

    assert result == "Gap analysis complete. 1 gaps found: Gap A"
    assert actions.session.needs == [_NEED]
    assert actions.session.pending_questions == []


@pytest.mark.parametrize("answers", [None, []])
async def test_no_submission_returns_the_fixed_text_and_changes_nothing(answers: Any) -> None:
    pipeline = QuestionPipeline()
    actions = _actions(pipeline, question_answers=answers)

    assert await actions.dispatch("submit_question_answers", {}) == NO_SUBMISSION
    assert pipeline.resume_calls == 0


async def test_a_submission_is_used_once_per_job() -> None:
    pipeline = QuestionPipeline()
    actions = _actions(pipeline, question_answers=_ANSWERS)

    await actions.dispatch("submit_question_answers", {})
    second = await actions.dispatch("submit_question_answers", {})

    assert second == NO_SUBMISSION
    assert pipeline.resume_calls == 1


@pytest.mark.parametrize(
    "error,reason",
    [
        (NoPendingPause(), STRING_16),
        (AnswersDoNotMatch(), STRING_16),
        (QuestionRunBusy(), STRING_15),
        (AnswersLocked(), STRING_19),
    ],
)
async def test_each_refusal_of_a_submission_shows_its_string(error: Exception, reason: str) -> None:
    pipeline = QuestionPipeline()
    pipeline.resume_result = error
    actions = _actions(pipeline, question_answers=_ANSWERS)

    assert await actions.dispatch("submit_question_answers", {}) == reason
    assert actions.session.blocked_reason == reason


class _Router:
    def __init__(self, names: list[str]) -> None:
        self.replies = [
            {"content": "", "tool_calls": [{"id": str(i), "name": n, "arguments": {}}]}
            for i, n in enumerate(names)
        ] + [{"content": "done", "tool_calls": []}]

    async def call(self, **_kw: Any) -> dict[str, Any]:
        return self.replies.pop(0)


async def test_a_failed_continue_fails_the_job_and_stops_the_tools() -> None:
    pipeline = QuestionPipeline()
    pipeline.resume_result = RuntimeError("second half failed")
    actions = _actions(pipeline, question_answers=_ANSWERS)
    agent = OrchestratorAgent(_Router(["submit_question_answers", "get_status"]))  # type: ignore[arg-type]

    with pytest.raises(TerminalToolError, match="second half failed"):
        await agent.run("Continue the analysis with my answers.", actions)

    assert pipeline.resume_calls == 1


async def test_status_shows_waiting_questions_and_ready_answers() -> None:
    actions = _actions(QuestionPipeline(), pending_questions=[_RECORD], question_answers=_ANSWERS)
    empty = _actions(QuestionPipeline())

    status = await actions.dispatch("get_status", {})
    status_empty = await empty.dispatch("get_status", {})

    assert "questions waiting for the user: 1" in status
    assert "answers ready to submit: 1" in status
    assert "answers ready to submit: 0" in status_empty


async def test_a_paused_gap_run_ends_the_job_awaiting_answers() -> None:
    actions = _actions(QuestionPipeline(), ask_questions=True, run_id="job-1")
    agent = OrchestratorAgent(_Router(["run_gap_analysis"]))  # type: ignore[arg-type]

    result = await agent.run("Find gaps", actions)

    assert result.status == "awaiting_answers"
    assert result.questions == [_RECORD]
    assert result.stage == "gap"


async def test_a_selection_while_a_pause_is_pending_does_not_continue_it() -> None:
    pipeline = QuestionPipeline()
    pipeline.pending = _pause()
    actions = _actions(pipeline, user_selected_titles=["Gap A"], needs=[_NEED])

    result = await actions.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert result == STRING_17
    assert pipeline.resume_calls == 0
    assert "ideate" not in pipeline.calls


async def test_a_new_run_while_a_pause_is_pending_is_refused() -> None:
    pipeline = QuestionPipeline()
    pipeline.pending = _pause()

    result = await _actions(pipeline).dispatch("run_gap_analysis", {})

    assert result == STRING_17
    assert pipeline.calls == {}


@pytest.mark.parametrize(
    "error,reason", [(PauseAlreadyPending(), STRING_17), (QuestionRunBusy(), STRING_18)]
)
async def test_a_refused_question_run_shows_its_string(error: Exception, reason: str) -> None:
    pipeline = QuestionPipeline()
    pipeline.gap_result = error
    actions = _actions(pipeline, ask_questions=True)

    assert await actions.dispatch("run_gap_analysis", {}) == reason
    assert actions.session.blocked_reason == reason


async def test_a_fresh_start_while_another_run_works_is_refused() -> None:
    pipeline = QuestionPipeline()
    pipeline.pending = _pause()
    pipeline.discard_result = QuestionRunBusy()

    result = await _actions(pipeline, fresh_start=True).dispatch("run_gap_analysis", {})

    assert result == STRING_18


async def test_a_fresh_start_discards_the_pause_and_runs() -> None:
    pipeline = QuestionPipeline()
    pipeline.pending = _pause()

    await _actions(pipeline, fresh_start=True).dispatch("run_gap_analysis", {})

    assert pipeline.pending is None
    assert len(pipeline.calls["analyse_gaps"]) == 1


async def test_questions_on_sends_the_job_id_to_both_question_runs() -> None:
    pipeline = QuestionPipeline()
    pipeline.gap_result = [_NEED]
    gap = _actions(pipeline, ask_questions=True, run_id="job-1")
    idea = _actions(
        pipeline,
        ask_questions=True,
        run_id="job-1",
        gap_run_id="gap-1",
        needs=[_NEED],
        user_selected_titles=["Gap A"],
    )

    await gap.dispatch("run_gap_analysis", {})
    await idea.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert pipeline.calls["analyse_gaps_with_questions"][0]["run_id"] == "job-1"
    sent = pipeline.calls["ideate_with_questions"][0]
    assert (sent["run_id"], sent["gap_run_id"], sent["domain"]) == ("job-1", "gap-1", "energy")
    assert "ideate" not in pipeline.calls


async def test_questions_off_calls_ideate_exactly_as_before() -> None:
    pipeline = QuestionPipeline()
    actions = _actions(
        pipeline, run_id="job-1", gap_run_id="gap-1", needs=[_NEED], user_selected_titles=["Gap A"]
    )

    await actions.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert pipeline.calls["ideate"] == [{"gap_run_id": "gap-1", "fresh_start": False}]
    assert "ideate_with_questions" not in pipeline.calls
