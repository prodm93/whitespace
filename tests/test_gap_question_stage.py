"""Question gate step at the end of the gap council's first half."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._gap_question_stage import (
    build_run_summary,
    find_corroboration,
    run_question_gate_node,
)
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.question import GateDecision, ProposedQuestion, QuestionRecord
from whitespace.tools.dedup import SemanticDeduplicator


class PairDedup:
    """Scores listed title pairs as near matches and everything else as distinct."""

    def __init__(self, matching: set[frozenset[str]], *, fail: bool = False) -> None:
        self.matching = matching
        self.fail = fail
        self.calls = 0

    async def similarity_matrix(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding service unreachable")
        titles = [_title(text) for text in texts]
        return [
            [1.0 if a == b or frozenset((a, b)) in self.matching else 0.1 for b in titles]
            for a in titles
        ]


def _title(text: str) -> str:
    return text.split(":", 1)[0]


def _candidate(role: str, index: int, title: str) -> CandidateGap:
    return CandidateGap(
        title=title,
        description=f"{title} detail",
        source_model="m",
        candidate_id=f"{role}-{index}",
        source_role=role,
    )


def _pool() -> list[CandidateGap]:
    return [
        _candidate("gap_identifier_1", 1, "Heat recovery"),
        _candidate("gap_identifier_1", 2, "Kiln sensor drift"),
        _candidate("gap_identifier_2", 1, "Waste heat capture"),
        _candidate("gap_identifier_3", 1, "Glaze defects"),
    ]


def _dedup(matching: set[frozenset[str]]) -> SemanticDeduplicator:
    return cast(SemanticDeduplicator, PairDedup(matching))


def _proposal() -> ProposedQuestion:
    return ProposedQuestion(
        question="Is waste heat available?",
        purpose="unlock",
        rationale="Determines whether recovery is possible",
        hypothesis="Heat is available",
        asker_role="gap_identifier_1",
        related_candidate_id="gap_identifier_1-1",
    )


def _record() -> QuestionRecord:
    return QuestionRecord(
        question_id="q-1",
        run_id="run-1",
        stage="gap",
        purpose="unlock",
        question="Is waste heat available?",
        hypothesis="Heat is available",
        rationale="Determines whether recovery is possible",
        asker_role="gap_identifier_1",
        related_candidate_id="gap_identifier_1-1",
        asked=True,
        created_at=datetime(2026, 9, 24, tzinfo=UTC),
    )


def _state(**overrides: Any) -> GapCouncilState:
    state: dict[str, Any] = {
        "domain": "energy",
        "run_id": "run-1",
        "candidates": _pool(),
        "proposed_questions": [_proposal()],
        "gate_flags": {},
    }
    state.update(overrides)
    return cast(GapCouncilState, state)


async def test_corroboration_names_every_other_identifier_with_a_near_match() -> None:
    dedup = PairDedup({frozenset(("Heat recovery", "Waste heat capture"))})

    found = await find_corroboration(cast(SemanticDeduplicator, dedup), _pool())

    assert found == {
        "gap_identifier_1-1": ["gap_identifier_2"],
        "gap_identifier_1-2": [],
        "gap_identifier_2-1": ["gap_identifier_1"],
        "gap_identifier_3-1": [],
    }
    assert dedup.calls == 1


def test_run_summary_matches_approved_wording() -> None:
    corroboration = {
        "gap_identifier_1-1": ["gap_identifier_2"],
        "gap_identifier_1-2": [],
        "gap_identifier_2-1": ["gap_identifier_1"],
        "gap_identifier_3-1": [],
    }
    flags = {"gap_identifier_3-1": "resembles prior work (score 0.88): Glaze crazing"}

    summary = build_run_summary(_pool(), corroboration, flags)

    assert summary == (
        "Candidates: 4 (gap_identifier_1: 2, gap_identifier_2: 1, gap_identifier_3: 1)\n"
        "Contest level: 2 of 4 candidates were found by only one identifier.\n"
        "- [gap_identifier_1-1] Heat recovery (also found by gap_identifier_2)\n"
        "- [gap_identifier_1-2] Kiln sensor drift (only found by gap_identifier_1)\n"
        "- [gap_identifier_2-1] Waste heat capture (also found by gap_identifier_1)\n"
        "- [gap_identifier_3-1] Glaze defects (only found by gap_identifier_3)\n"
        "Candidates resembling earlier runs' output: 1\n"
        "- [gap_identifier_3-1] resembles prior work (score 0.88): Glaze crazing"
    )


async def test_corroboration_lists_both_other_identifiers_when_all_three_agree() -> None:
    dedup = _dedup(
        {
            frozenset(("Heat recovery", "Waste heat capture")),
            frozenset(("Heat recovery", "Glaze defects")),
        }
    )

    found = await find_corroboration(dedup, _pool())

    assert found is not None
    assert found["gap_identifier_1-1"] == ["gap_identifier_2", "gap_identifier_3"]
    line = build_run_summary(_pool(), found, {}).splitlines()[2]
    assert line == (
        "- [gap_identifier_1-1] Heat recovery (also found by gap_identifier_2, gap_identifier_3)"
    )


async def test_failed_similarity_check_reports_contest_level_unavailable() -> None:
    dedup = PairDedup(set(), fail=True)

    found = await find_corroboration(cast(SemanticDeduplicator, dedup), _pool())
    summary = build_run_summary(_pool()[:2], found, {})

    assert found is None
    assert summary == (
        "Candidates: 2 (gap_identifier_1: 2)\n"
        "Contest level: unavailable (similarity check failed).\n"
        "- [gap_identifier_1-1] Heat recovery\n"
        "- [gap_identifier_1-2] Kiln sensor drift\n"
        "Candidates resembling earlier runs' output: 0"
    )


def test_run_summary_without_flags_lists_none() -> None:
    summary = build_run_summary(_pool()[:1], {}, {})

    assert summary.endswith("Candidates resembling earlier runs' output: 0")


async def test_without_gate_no_similarity_or_model_calls() -> None:
    dedup = PairDedup(set())

    update = await run_question_gate_node(None, cast(SemanticDeduplicator, dedup), _state())

    assert update == {"pending_questions": []}
    assert dedup.calls == 0


async def test_without_proposals_gate_is_not_consulted() -> None:
    gate = MagicMock(spec=QuestionGate)
    gate.judge = AsyncMock()

    update = await run_question_gate_node(gate, _dedup(set()), _state(proposed_questions=[]))

    assert update == {"pending_questions": []}
    gate.judge.assert_not_awaited()


@pytest.mark.parametrize("ask", [True, False])
async def test_gate_receives_summary_and_its_questions_become_pending(ask: bool) -> None:
    questions = [_record()] if ask else []
    gate = MagicMock(spec=QuestionGate)
    gate.judge = AsyncMock(return_value=GateDecision(ask=ask, questions=questions, reasoning=""))

    update = await run_question_gate_node(gate, _dedup(set()), _state())

    assert update == {"pending_questions": questions}
    proposals, summary, stage, run_id, domain = gate.judge.call_args.args
    assert proposals == [_proposal()]
    assert summary.startswith("Candidates: 4 ")
    assert "Contest level: 4 of 4 candidates" in summary
    assert (stage, run_id, domain) == ("gap", "run-1", "energy")
