"""The user's answers reach the gap critic, the revising identifier and the synthesiser."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from _gap_council_helpers import (
    ROLES,
    RefineRouter,
    ScoreDedup,
    keep_all,
    make_council,
    make_gap,
    make_mid_state,
    make_record,
)

from whitespace.orchestration._research_stage import ResearchStage
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.schemas.critique import CandidateLike, CriticAssessment, CriticReport
from whitespace.schemas.gap import GapExploration
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import UserAnswer
from whitespace.store.sqlite_store import SqliteSessionStore

_ANSWERS_SECTION = (
    "## USER ANSWERS (this run)\n\n"
    "- [Q1] Question: Question q-1?\n"
    "  Our hypothesis: Hypothesis q-1\n"
    "  Answer: Exhaust is 400C"
)
_ANSWERS = [UserAnswer(question_id="q-1", status="answered", answer="Exhaust is 400C")]


async def test_critic_evidence_ends_with_the_answers_when_findings_are_long() -> None:
    council = make_council(RefineRouter())
    state = {**make_mid_state([make_record("q-1")]), "findings_text": "x" * 50000}

    await council.graph.run_second_half(state, _ANSWERS)

    assert council.critic.run.await_args is not None
    evidence = council.critic.run.await_args.kwargs["evidence"]
    assert evidence.endswith(_ANSWERS_SECTION)
    assert evidence.startswith("x" * 40000)


def _delegate_once() -> Any:
    calls = {"n": 0}

    def report(candidates: list[CandidateLike], *args: Any, **kwargs: Any) -> CriticReport:
        calls["n"] += 1
        if calls["n"] > 1:
            return keep_all(candidates)
        first = candidates[0].candidate_id
        return CriticReport(
            assessments=[
                CriticAssessment(
                    candidate_id=first,
                    verdict="delegate_back",
                    scores={"specificity": 4},
                    feedback_for_originator="Name the heat exchanger",
                )
            ],
            ranking=[first],
        )

    return report


def _revision_messages(router: RefineRouter) -> list[str]:
    return [
        call["messages"][1]["content"]
        for call in router.calls
        if call["response_format"]["json_schema"]["name"] == "RevisedCandidateGaps"
    ]


async def test_answers_reach_the_revision_and_the_synthesiser() -> None:
    council = make_council(RefineRouter())
    council.critic.run.side_effect = _delegate_once()

    await council.graph.run_second_half(make_mid_state([make_record("q-1")]), _ANSWERS)

    revisions = _revision_messages(council.router)
    assert len(revisions) == 1
    assert "- [Q1] Question: Question q-1?" in revisions[0]
    assert "  Answer: Exhaust is 400C" in revisions[0]
    assert council.synthesiser.run.await_args is not None
    assert council.synthesiser.run.await_args.args[2].endswith(_ANSWERS_SECTION)


async def test_without_answers_no_message_carries_an_answers_section() -> None:
    council = make_council(RefineRouter())
    council.critic.run.side_effect = _delegate_once()

    await council.graph.run_second_half(make_mid_state([make_record("q-1")]))

    assert council.critic.run.await_args is not None
    assert "USER ANSWERS" not in council.critic.run.await_args.kwargs["evidence"]
    revisions = _revision_messages(council.router)
    assert len(revisions) == 1
    assert "USER ANSWERS" not in revisions[0]
    assert council.synthesiser.run.await_args is not None
    assert "USER ANSWERS" not in council.synthesiser.run.await_args.args[2]


class CountingStore(SqliteSessionStore):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self.discard_saves = 0

    async def save_discards(self, run_id: str, kind: str, items: list[dict[str, str]]) -> None:
        self.discard_saves += 1
        await super().save_discards(run_id, kind, items)


class _Dedup(ScoreDedup):
    async def dedup(self, findings: list[Any]) -> list[Any]:
        return findings


_HELD = {
    "title": "Old gap",
    "description": "Seen before",
    "reason": "near-duplicate of a previous run's output",
    "domain": "energy",
}
_KILL_X = {
    "title": "Kiln sealing",
    "description": "Kiln sealing description",
    "reason": "Covered by US1234567",
    "domain": "energy",
}


def _kill_second(candidates: list[CandidateLike], *args: Any, **kwargs: Any) -> CriticReport:
    keep, kill = candidates[0].candidate_id, candidates[1].candidate_id
    return CriticReport(
        assessments=[
            CriticAssessment(candidate_id=keep, verdict="keep", scores={"specificity": 8}),
            CriticAssessment(
                candidate_id=kill,
                verdict="kill",
                scores={"specificity": 2},
                objections="Covered by US1234567",
            ),
        ],
        ranking=[keep],
    )


def _real_research_council(tmp_path: Path) -> tuple[GapCouncilGraph, Any, CountingStore]:
    store = CountingStore(tmp_path / "s.db")
    research = ResearchStage(
        MagicMock(research=AsyncMock(return_value=[])),
        _Dedup(),  # type: ignore[arg-type]
        MagicMock(),
        MagicMock(run=AsyncMock()),
        store,
    )
    council = make_council(RefineRouter())
    council.critic.run.side_effect = _kill_second
    graph = GapCouncilGraph(
        list(council.graph._identifiers.values()), council.critic, council.synthesiser, research
    )
    return graph, council, store


async def test_second_half_returns_the_final_discards_and_writes_none(tmp_path: Path) -> None:
    graph, council, store = _real_research_council(tmp_path)
    state = {**make_mid_state([]), "held_discards": [_HELD]}

    needs, discards = await graph.run_second_half(state)

    assert needs == [council.need]
    assert discards == [_KILL_X, _HELD]
    assert store.discard_saves == 0
    assert await store.list_discards() == []


async def test_a_failed_synthesis_in_the_second_half_writes_no_discard(tmp_path: Path) -> None:
    graph, council, store = _real_research_council(tmp_path)
    council.synthesiser.run.side_effect = RuntimeError("synthesis failed")
    state = {**make_mid_state([]), "held_discards": [_HELD]}

    with pytest.raises(RuntimeError):
        await graph.run_second_half(state)

    assert store.discard_saves == 0


def _stub_first_half(graph: GapCouncilGraph) -> None:
    for role, identifier in graph._identifiers.items():
        identifier.craft_queries = AsyncMock(return_value=[f"{role} query"])  # type: ignore[method-assign]
        gap = make_gap(role, 1, "Heat recovery" if role == ROLES[0] else "Kiln sealing")
        identifier.run = AsyncMock(  # type: ignore[method-assign]
            return_value=GapExploration(gaps=[gap], findings="Graph evidence")
        )


async def test_run_with_questions_off_returns_kills_and_writes_none(tmp_path: Path) -> None:
    graph, council, store = _real_research_council(tmp_path)
    _stub_first_half(graph)

    needs, discards = await graph.run(ProfessionalProfile(), "energy", run_id="run-1")

    assert needs == [council.need]
    assert discards == [_KILL_X]
    assert store.discard_saves == 0


async def test_run_with_a_failed_synthesis_writes_no_discard(tmp_path: Path) -> None:
    graph, council, store = _real_research_council(tmp_path)
    _stub_first_half(graph)
    council.synthesiser.run.side_effect = RuntimeError("synthesis failed")

    with pytest.raises(RuntimeError):
        await graph.run(ProfessionalProfile(), "energy", run_id="run-1")

    assert store.discard_saves == 0
