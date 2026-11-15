"""Questions on a real pipeline: wiring by mode, and one run ID through checkpoint and store."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from _pipeline_questions_helpers import _NEEDS, _PROPOSAL, _pipeline
from _question_gate_helpers import FakeDedup, FakeRouter, gate_response, selection

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
from whitespace.orchestration._question_pause import QuestionPauseShell
from whitespace.orchestration._question_runs import QuestionRuns
from whitespace.orchestration._question_types import PausedForQuestions
from whitespace.orchestration._research_stage import ResearchStage
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.orchestration.pipeline import Pipeline
from whitespace.schemas.critique import CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap, GapExploration
from whitespace.schemas.idea import CandidateIdea, IdeaExploration, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion, UserAnswer
from whitespace.store.sqlite_store import SqliteSessionStore


@pytest.mark.parametrize(
    "mode,with_store,wired",
    [("byok", True, True), ("byok", False, False), ("saas", True, False)],
)
def test_questions_are_wired_in_byok_with_a_store_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, with_store: bool, wired: bool
) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    store = SqliteSessionStore(tmp_path / "s.db") if with_store else None
    namespace = "user_a" if mode == "saas" else "default"
    config = Config(_env_file=None, mode=mode, graphiti_namespace=namespace)  # type: ignore[call-arg]

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
