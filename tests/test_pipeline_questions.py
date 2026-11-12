"""Pipeline entry points for runs with questions on, and their run identity."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from _question_gate_helpers import FakeDedup, FakeRouter, gate_response, selection
from _question_runs_helpers import NEED, make_record

from whitespace.agents.council._answer_refinement import Refined
from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.config import Config
from whitespace.orchestration._council_halves import GapHalves, IdeationHalves
from whitespace.orchestration._question_pause import PauseOutcome, QuestionPauseShell
from whitespace.orchestration._question_runs import QuestionRuns
from whitespace.orchestration._question_types import NoPendingPause, PausedForQuestions
from whitespace.orchestration._research_stage import ResearchStage
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.orchestration.pipeline import Pipeline
from whitespace.schemas.critique import CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap, GapExploration, UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeaExploration, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion, UserAnswer
from whitespace.store.sqlite_store import SqliteSessionStore


class FakeRuns:
    def __init__(self, outcome: PauseOutcome) -> None:
        self.outcome = outcome
        self.started: list[tuple[str, str, dict[str, Any]]] = []

    async def start(self, stage: str, job_id: str, initial: dict[str, Any]) -> PauseOutcome:
        self.started.append((stage, job_id, initial))
        return self.outcome


def _pipeline(question_runs: Any = None, store: Any = None) -> Pipeline:
    gap_council = MagicMock()
    gap_council.run = AsyncMock(return_value=([UnmetNeed.model_validate(NEED)], []))
    ideation_council = MagicMock()
    ideation_council.run = AsyncMock(return_value=([], []))
    context_agent = MagicMock()
    context_agent.run = AsyncMock(return_value="Graph context")
    return Pipeline(
        config=MagicMock(),
        neo4j=MagicMock(),
        graphiti=MagicMock(),
        context_agent=context_agent,
        profile_agent=MagicMock(),
        ingest_graph=MagicMock(),
        gap_council=gap_council,
        ideation_council=ideation_council,
        query_graph=MagicMock(),
        router=MagicMock(),
        dedup=MagicMock(),
        session_store=store,
        question_runs=question_runs,
    )


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
_PROPOSAL = {
    "title": "Acoustic monitor",
    "problem_statement": "p",
    "technical_approach": "t",
    "why_this_person": "w",
    "differentiation_from_prior_art": "d",
    "limitations": "l",
}
_DONE_IDEA = PauseOutcome(result={"proposals": [_PROPOSAL], "discards": []})
_NEEDS = [UnmetNeed.model_validate(NEED)]


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


@pytest.mark.parametrize(
    "mode,with_store,wired",
    [("byok", True, True), ("byok", False, False), ("saas", True, False)],
)
def test_questions_are_wired_in_byok_with_a_store_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, with_store: bool, wired: bool
) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    store = SqliteSessionStore(tmp_path / "s.db") if with_store else None
    config = Config(_env_file=None, mode=mode)  # type: ignore[call-arg]

    pipeline = Pipeline.from_config(config, session_store=store)

    assert (pipeline._question_runs is not None) is wired
    assert (pipeline._gap_council._question_gate is not None) is wired
    assert (pipeline._ideation_council._question_gate is not None) is wired


class _Dedup(FakeDedup):
    async def dedup(self, findings: list[Any]) -> list[Any]:
        return findings


def _clarify(role: str) -> ProposedQuestion:
    return ProposedQuestion(
        question="Which packs?", purpose="clarify", rationale="r", hypothesis="h", asker_role=role
    )


async def _real_pipeline(tmp_path: Path) -> tuple[Pipeline, SqliteSessionStore, QuestionRuns]:
    store = SqliteSessionStore(tmp_path / "s.db")
    dedup = _Dedup()
    router = FakeRouter(gate_response(ask=True, selected=[selection("P1")], ranking=["P1"]))
    gate = QuestionGate(MagicMock(), router, dedup, store)  # type: ignore[arg-type]
    ideator = MagicMock(spec=IdeaIdeator)
    ideator.role_name = "idea_ideator_1"
    idea = CandidateIdea(title="Acoustic monitor", description="d", source_model="m")
    ideator.run = AsyncMock(
        return_value=IdeaExploration(ideas=[idea], proposed_questions=[_clarify("idea_ideator_1")])
    )
    ideator.novelty_filter = AsyncMock(side_effect=lambda own, _pa: (own, []))
    ideator.refine = AsyncMock(side_effect=lambda own, *_a, **_kw: Refined(revised=own))
    idea_critic = MagicMock(spec=IdeaCritic)
    idea_critic.run = AsyncMock(side_effect=lambda pool, *_a, **_kw: _keep(pool))
    idea_synth = MagicMock(spec=IdeaSynthesiser)
    idea_synth.run = AsyncMock(return_value=[IdeationProposal.model_validate(_PROPOSAL)])
    ideation = IdeationCouncilGraph(
        [ideator],
        idea_critic,
        idea_synth,
        MagicMock(),
        dedup,
        question_gate=gate,  # type: ignore[arg-type]
    )
    identifier = MagicMock(spec=GapIdentifier)
    identifier.role_name = "gap_identifier_1"
    identifier.craft_queries = AsyncMock(return_value=["heat recovery"])
    gap = CandidateGap(title="Heat recovery", description="d", source_model="m")
    identifier.run = AsyncMock(
        return_value=GapExploration(
            gaps=[gap], findings="Graph", proposed_questions=[_clarify("gap_identifier_1")]
        )
    )
    identifier.refine = AsyncMock(side_effect=lambda own, *_a, **_kw: Refined(revised=own))
    gap_critic = MagicMock(spec=GapCritic)
    gap_critic.run = AsyncMock(side_effect=lambda pool, *_a, **_kw: _keep(pool))
    gap_synth = MagicMock(spec=GapSynthesiser)
    gap_synth.run = AsyncMock(return_value=_NEEDS)
    research = ResearchStage(
        MagicMock(research=AsyncMock(return_value=[])),
        dedup,  # type: ignore[arg-type]
        MagicMock(),
        MagicMock(run=AsyncMock()),
        store,
    )
    gap_council = GapCouncilGraph([identifier], gap_critic, gap_synth, research, gate)
    runs = QuestionRuns(
        store,
        QuestionPauseShell(str(tmp_path / "cp.db")),
        GapHalves(gap_council),
        IdeationHalves(ideation),
    )
    pipeline = _pipeline(runs, store)
    pipeline._gap_council = gap_council
    pipeline._ideation_council = ideation
    return pipeline, store, runs


def _keep(pool: list[Any]) -> CriticReport:
    ids = [c.candidate_id for c in pool]
    return CriticReport(
        assessments=[
            CriticAssessment(candidate_id=i, verdict="keep", scores={"specificity": 8}) for i in ids
        ],
        ranking=ids,
    )


async def _check_pause(store: SqliteSessionStore, runs: QuestionRuns, stage: str) -> str:
    records = await store.list_question_records()
    assert records and all(r.run_id == "job-1" for r in records)
    pause = await store.get_pending_pause()
    assert pause is not None and (pause.job_id, pause.thread_id) == ("job-1", "job-1")
    assert await runs._shell.status("job-1", runs._halves[stage]) == "awaiting"
    return pause.questions[0].question_id


async def test_a_paused_ideation_run_keeps_one_id_through_checkpoint_and_store(
    tmp_path: Path,
) -> None:
    pipeline, store, runs = await _real_pipeline(tmp_path)

    paused = await pipeline.ideate_with_questions(
        _NEEDS, ProfessionalProfile(), run_id="job-1", gap_run_id="gap-1"
    )
    assert isinstance(paused, PausedForQuestions)
    question_id = await _check_pause(store, runs, "ideation")
    await pipeline.resume_questions(
        [UserAnswer(question_id=question_id, status="answered", answer="Pouch cells")]
    )

    stored = await store.get_idea_run("job-1")
    assert stored is not None and stored.gap_run_id == "gap-1"
    assert await store.get_pending_pause() is None


async def test_a_paused_gap_run_keeps_one_id_through_checkpoint_and_store(tmp_path: Path) -> None:
    pipeline, store, runs = await _real_pipeline(tmp_path)

    paused = await pipeline.analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", run_id="job-1", fresh_start=True
    )
    assert isinstance(paused, PausedForQuestions)
    question_id = await _check_pause(store, runs, "gap")
    await pipeline.resume_questions(
        [UserAnswer(question_id=question_id, status="answered", answer="Pouch cells")]
    )

    assert await store.get_gap_run("job-1") is not None
    assert await store.get_pending_pause() is None
