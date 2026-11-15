"""Pipeline entry points for runs with questions on, and their run identity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _pipeline_questions_helpers import _NEEDS, _PROPOSAL, _pipeline
from _question_runs_helpers import NEED, make_record

from whitespace.orchestration._question_pause import PauseOutcome
from whitespace.orchestration._question_types import NoPendingPause, PausedForQuestions
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.sqlite_store import SqliteSessionStore


class FakeRuns:
    def __init__(self, outcome: PauseOutcome) -> None:
        self.outcome = outcome
        self.started: list[tuple[str, str, dict[str, Any]]] = []

    async def start(self, stage: str, job_id: str, initial: dict[str, Any]) -> PauseOutcome:
        self.started.append((stage, job_id, initial))
        return self.outcome


_PAUSED = PauseOutcome(questions=[make_record("q-1").model_dump(mode="json")])


async def test_a_gap_run_that_pauses_returns_its_questions() -> None:
    pipeline = _pipeline(FakeRuns(_PAUSED))

    result = await pipeline.analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", run_id="job-1", fresh_start=True
    )

    assert isinstance(result, PausedForQuestions)
    assert result.stage == "gap"
    assert [q.question_id for q in result.questions] == ["q-1"]


_DONE_GAP = PauseOutcome(result={"needs": [NEED], "discards": [], "run_id": "job-1"})
_DONE_IDEA = PauseOutcome(result={"proposals": [_PROPOSAL], "discards": []})


async def test_a_gap_run_that_does_not_pause_returns_its_needs() -> None:
    result = await _pipeline(FakeRuns(_DONE_GAP)).analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", fresh_start=True
    )

    assert result == _NEEDS


async def test_without_question_runs_a_gap_run_is_the_plain_run() -> None:
    pipeline = _pipeline()

    result = await pipeline.analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", fresh_start=True
    )

    assert result == _NEEDS
    pipeline._gap_council.run.assert_awaited_once()  # type: ignore[attr-defined]


async def test_ideation_pauses_completes_or_falls_back_to_the_plain_run() -> None:
    paused = await _pipeline(FakeRuns(_PAUSED)).ideate_with_questions(_NEEDS, ProfessionalProfile())
    done = await _pipeline(FakeRuns(_DONE_IDEA)).ideate_with_questions(
        _NEEDS, ProfessionalProfile()
    )
    plain_pipeline = _pipeline()
    plain = await plain_pipeline.ideate_with_questions(_NEEDS, ProfessionalProfile())

    assert isinstance(paused, PausedForQuestions) and paused.stage == "ideation"
    assert [p.title for p in done] == ["Acoustic monitor"]  # type: ignore[union-attr]
    assert plain == []
    plain_pipeline._ideation_council.run.assert_awaited_once()  # type: ignore[attr-defined]


async def test_without_question_runs_the_question_methods_report_nothing() -> None:
    pipeline = _pipeline()

    with pytest.raises(NoPendingPause):
        await pipeline.resume_questions([])
    assert await pipeline.discard_pending_questions() is False
    assert await pipeline.pending_questions() is None


@pytest.mark.protects("gap-and-idea-runs-saved")
async def test_ideate_still_stores_its_discards_and_run(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    pipeline = _pipeline(store=store)
    pipeline._ideation_council.run.return_value = (  # type: ignore[attr-defined]
        [IdeationProposal.model_validate(_PROPOSAL)],
        [{"title": "Gas sniffer", "description": "d", "reason": "dup"}],
    )

    await pipeline.ideate(_NEEDS, ProfessionalProfile(), run_id="idea-1", gap_run_id="gap-1")
    await pipeline.ideate(_NEEDS, ProfessionalProfile(), run_id="idea-2", fresh_start=True)
    await pipeline.ideate(_NEEDS, ProfessionalProfile(), run_id="idea-3")

    stored = await store.get_idea_run("idea-1")
    assert stored is not None and stored.gap_run_id == "gap-1"
    assert len(await store.list_discards("idea")) == 3
    assert pipeline._context_agent.run.await_count == 3  # type: ignore[attr-defined]
    council_run = pipeline._ideation_council.run  # type: ignore[attr-defined]
    contexts = [call.args[1] for call in council_run.await_args_list]
    negatives = "ALREADY GENERATED OR REJECTED IDEAS"
    assert [negatives in c for c in contexts] == [False, False, True]


async def test_ideation_with_questions_carries_one_run_id_everywhere() -> None:
    runs = FakeRuns(_PAUSED)
    pipeline = _pipeline(runs)

    await pipeline.ideate_with_questions(
        _NEEDS, ProfessionalProfile(), run_id="job-1", gap_run_id="gap-1", domain="d"
    )

    stage, job_id, state = runs.started[0]
    assert (stage, job_id) == ("ideation", "job-1")
    assert (state["run_id"], state["gap_run_id"], state["domain"]) == ("job-1", "gap-1", "d")
    assert state["questions_enabled"] is True


async def test_a_missing_run_id_is_made_once_and_used_everywhere() -> None:
    idea_runs, gap_runs = FakeRuns(_PAUSED), FakeRuns(_PAUSED)

    await _pipeline(idea_runs).ideate_with_questions(_NEEDS, ProfessionalProfile())
    await _pipeline(gap_runs).analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", fresh_start=True
    )

    for runs in (idea_runs, gap_runs):
        _, job_id, state = runs.started[0]
        assert isinstance(job_id, str) and job_id
        assert state["run_id"] == job_id


async def test_gap_analysis_with_questions_carries_the_given_run_id() -> None:
    runs = FakeRuns(_PAUSED)

    await _pipeline(runs).analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", run_id="job-1", fresh_start=True
    )

    stage, job_id, state = runs.started[0]
    assert (stage, job_id, state["run_id"]) == ("gap", "job-1", "job-1")
    assert state["questions_enabled"] is True
