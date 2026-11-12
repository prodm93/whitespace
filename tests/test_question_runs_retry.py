"""Retries of a paused run: the second half failed, or storing its result failed."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from _question_runs_helpers import DISCARD, make_record, make_runs

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._council_halves import GapHalves
from whitespace.orchestration._gap_council_state import build_initial_gap_state, dump_mid_state
from whitespace.orchestration._question_pause import QuestionPauseShell
from whitespace.orchestration._question_runs import QuestionRuns
from whitespace.orchestration._question_types import AnswersLocked, pending_view
from whitespace.orchestration._research_stage import ResearchStage, RunMemory
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.schemas.critique import CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap, GapExploration, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import GateDecision, ProposedQuestion, UserAnswer
from whitespace.store.sqlite_store import SqliteSessionStore

_FIRST = [UserAnswer(question_id="q-1", status="answered", answer="Pouch cells")]
_OTHER = [UserAnswer(question_id="q-1", status="answered", answer="Prismatic cells")]
_DISCARD_B = {**DISCARD, "title": "Kill B"}


class FailOnce(SqliteSessionStore):
    """Raises once, on the ``nth`` call of the named method."""

    def __init__(self, db_path: Path, method: str, nth: int = 1) -> None:
        super().__init__(db_path)
        self.method, self.nth, self.calls = method, nth, 0

    def _maybe_fail(self, name: str) -> None:
        if name == self.method:
            self.calls += 1
            if self.calls == self.nth:
                raise OSError(f"{name} failed")

    async def save_gap_run(self, run: Any) -> None:
        self._maybe_fail("save_gap_run")
        await super().save_gap_run(run)

    async def save_discards(self, run_id: str, kind: str, items: list[dict[str, str]]) -> None:
        self._maybe_fail("save_discards")
        await super().save_discards(run_id, kind, items)

    async def delete_pending_pause(self, pause_id: str) -> None:
        self._maybe_fail("delete_pending_pause")
        await super().delete_pending_pause(pause_id)

    async def save_pending_pause(self, pause: Any) -> None:
        self._maybe_fail("save_pending_pause")
        await super().save_pending_pause(pause)


async def _answer_of(store: SqliteSessionStore) -> str:
    return {r.question_id: r for r in await store.list_question_records()}["q-1"].answer


async def test_a_failed_second_half_accepts_edited_answers_on_retry(tmp_path: Path) -> None:
    runs, store, halves, _ = await make_runs(tmp_path, [make_record("q-1")], failures=1)
    await runs.start("gap", "job-1", {"run_id": "job-1"})
    with pytest.raises(RuntimeError, match="second half failed"):
        await runs.resume(_FIRST)
    assert await store.get_pending_pause() is not None
    assert await _answer_of(store) == "Pouch cells"

    await runs.resume(_OTHER)

    assert await _answer_of(store) == "Prismatic cells"
    assert halves.second_answers[-1][0]["answer"] == "Prismatic cells"


async def _failed_finalisation(tmp_path: Path, method: str, **kwargs: Any) -> Any:
    store = FailOnce(tmp_path / "s.db", method, kwargs.pop("nth", 1))
    runs, store, halves, shell = await make_runs(
        tmp_path, [make_record("q-1")], store=store, **kwargs
    )
    await runs.start("gap", "job-1", {"run_id": "job-1"})
    with pytest.raises(OSError, match=f"{method} failed"):
        await runs.resume(_FIRST)
    return runs, store, halves


async def test_a_failed_run_save_completes_on_a_retry_with_the_same_answers(
    tmp_path: Path,
) -> None:
    runs, store, halves = await _failed_finalisation(tmp_path, "save_gap_run")

    await runs.resume(_FIRST)

    assert await store.get_gap_run("job-1") is not None
    assert await store.get_pending_pause() is None
    assert len(halves.second_answers) == 1


async def test_a_failed_run_save_refuses_edited_answers(tmp_path: Path) -> None:
    runs, store, halves = await _failed_finalisation(tmp_path, "save_gap_run")

    with pytest.raises(AnswersLocked):
        await runs.resume(_OTHER)

    assert await _answer_of(store) == "Pouch cells"
    assert len(halves.second_answers) == 1
    await runs.resume(_FIRST)
    assert await store.get_gap_run("job-1") is not None


async def test_a_failed_row_delete_completes_without_duplicates(tmp_path: Path) -> None:
    runs, store, _ = await _failed_finalisation(
        tmp_path, "delete_pending_pause", discards=[DISCARD]
    )

    await runs.resume(_FIRST)

    assert await store.get_pending_pause() is None
    assert len(await store.list_gap_runs()) == 1
    assert [d["title"] for d in await store.list_discards("gap")] == ["Kill A"]


async def test_a_failed_computed_flag_still_locks_answers_on_the_next_retry(
    tmp_path: Path,
) -> None:
    runs, store, _ = await _failed_finalisation(tmp_path, "save_pending_pause", nth=2)
    view = await pending_view(store)
    assert view is not None and view.editable is True

    with pytest.raises(AnswersLocked):
        await runs.resume(_OTHER)

    view = await pending_view(store)
    assert view is not None and view.editable is False


async def test_a_failed_discard_save_stores_nothing_then_completes_once(tmp_path: Path) -> None:
    runs, store, halves = await _failed_finalisation(
        tmp_path, "save_discards", discards=[DISCARD, _DISCARD_B]
    )
    assert await store.get_pending_pause() is not None
    assert await store.list_discards() == []
    assert await store.get_gap_run("job-1") is None

    await runs.resume(_FIRST)

    assert sorted(d["title"] for d in await store.list_discards("gap")) == ["Kill A", "Kill B"]
    assert len(await store.list_gap_runs()) == 1
    assert await store.get_pending_pause() is None
    assert len(halves.second_answers) == 1


async def test_a_failed_discard_save_refuses_edited_answers(tmp_path: Path) -> None:
    runs, store, halves = await _failed_finalisation(
        tmp_path, "save_discards", discards=[DISCARD, _DISCARD_B]
    )

    with pytest.raises(AnswersLocked):
        await runs.resume(_OTHER)

    assert len(halves.second_answers) == 1
    assert await _answer_of(store) == "Pouch cells"
    assert await store.list_discards() == []
    await runs.resume(_FIRST)
    assert sorted(d["title"] for d in await store.list_discards("gap")) == ["Kill A", "Kill B"]


async def test_a_failed_run_save_after_stored_discards_keeps_them_single(tmp_path: Path) -> None:
    runs, store, _ = await _failed_finalisation(tmp_path, "save_gap_run", discards=[DISCARD])

    with pytest.raises(AnswersLocked):
        await runs.resume(_OTHER)
    await runs.resume(_FIRST)

    assert [d["title"] for d in await store.list_discards("gap")] == ["Kill A"]
    assert await store.get_gap_run("job-1") is not None


def _kill_x_then(keep_after: bool) -> Any:
    calls = {"n": 0}

    def report(candidates: list[Any], *_a: Any, **_kw: Any) -> CriticReport:
        calls["n"] += 1
        kill_x = not (keep_after and calls["n"] > 1)
        assessments = [
            CriticAssessment(
                candidate_id=c.candidate_id,
                verdict="kill" if kill_x and c.title == "Kiln sealing" else "keep",
                scores={"specificity": 8},
                objections="Covered by US1234567" if c.title == "Kiln sealing" else "",
            )
            for c in candidates
        ]
        ranking = [c.candidate_id for c in candidates if not (kill_x and c.title == "Kiln sealing")]
        return CriticReport(assessments=assessments, ranking=ranking)

    return report


async def _real_council_runs(tmp_path: Path, store: SqliteSessionStore, critic_report: Any) -> Any:
    record = make_record("q-1")
    await store.save_question_records([record])
    identifiers = []
    for role, title in (
        ("gap_identifier_1", "Heat recovery"),
        ("gap_identifier_2", "Kiln sealing"),
    ):
        identifier = MagicMock(spec=GapIdentifier)
        identifier.role_name = role
        identifier.craft_queries = AsyncMock(return_value=[f"{role} query"])
        identifier.run = AsyncMock(
            return_value=GapExploration(
                gaps=[CandidateGap(title=title, description="d", source_model="m")],
                findings="Graph evidence",
                proposed_questions=[
                    ProposedQuestion(
                        question="Which packs?",
                        purpose="clarify",
                        rationale="r",
                        hypothesis="h",
                        asker_role=role,
                    )
                ],
            )
        )
        identifiers.append(identifier)
    critic = MagicMock(spec=GapCritic)
    critic.run = AsyncMock(side_effect=critic_report)
    synthesiser = MagicMock(spec=GapSynthesiser)
    synthesiser.run = AsyncMock(
        return_value=[
            UnmetNeed(title="Heat recovery", description="d", current_state="s", why_unmet="w")
        ]
    )
    gate = MagicMock(spec=QuestionGate)
    gate.judge = AsyncMock(return_value=GateDecision(ask=True, questions=[record], reasoning=""))
    dedup = MagicMock()
    dedup.dedup = AsyncMock(side_effect=lambda findings: findings)
    dedup.similarity_matrix = AsyncMock(return_value=[[1.0, 0.0], [0.0, 1.0]])
    research = ResearchStage(
        MagicMock(research=AsyncMock(return_value=[])),
        dedup,
        MagicMock(),
        MagicMock(run=AsyncMock()),
        store,
    )
    council = GapCouncilGraph(identifiers, critic, synthesiser, research, gate)
    halves = GapHalves(council)
    runs = QuestionRuns(store, QuestionPauseShell(str(tmp_path / "cp.db")), halves, halves)
    initial = build_initial_gap_state(
        ProfessionalProfile(),
        "energy",
        [],
        keep_findings=False,
        run_id="job-1",
        run_memory=RunMemory(),
        questions_enabled=True,
    )
    await runs.start("gap", "job-1", dump_mid_state(initial))
    return runs, critic, synthesiser


async def test_a_kill_from_a_failed_attempt_is_never_stored(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    runs, _, synthesiser = await _real_council_runs(tmp_path, store, _kill_x_then(keep_after=True))
    synthesiser.run.side_effect = [RuntimeError("synthesis failed"), synthesiser.run.return_value]
    with pytest.raises(RuntimeError, match="synthesis failed"):
        await runs.resume(_FIRST)
    assert await store.list_discards() == []

    await runs.resume(_OTHER)

    assert await store.get_gap_run("job-1") is not None
    assert await store.list_discards() == []


async def test_a_kill_is_stored_once_and_edited_answers_are_refused_after_compute(
    tmp_path: Path,
) -> None:
    store = FailOnce(tmp_path / "s.db", "save_discards")
    runs, critic, _ = await _real_council_runs(tmp_path, store, _kill_x_then(keep_after=False))
    with pytest.raises(OSError, match="save_discards failed"):
        await runs.resume(_FIRST)

    with pytest.raises(AnswersLocked):
        await runs.resume(_OTHER)
    assert critic.run.await_count == 1
    await runs.resume(_FIRST)

    discards = await store.list_discards("gap")
    assert [(d["title"], d["reason"]) for d in discards] == [
        ("Kiln sealing", "Covered by US1234567")
    ]
    assert len(await store.list_gap_runs()) == 1
