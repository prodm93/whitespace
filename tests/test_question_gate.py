"""Tests for the agentic adaptive question gate."""

from __future__ import annotations

from _question_gate_helpers import (
    FakeDedup,
    FakeRouter,
    FakeStore,
    gate_response,
    past_answer,
    proposal,
    selection,
)

from whitespace.agents.council.question_gate import QuestionGate
from whitespace.config import Config


def _gate(router: FakeRouter, dedup: FakeDedup, store: FakeStore) -> QuestionGate:
    return QuestionGate(
        Config(),
        router,  # type: ignore[arg-type]
        dedup,  # type: ignore[arg-type]
        store,
    )


async def test_empty_proposals_skip_model_and_persistence() -> None:
    router = FakeRouter(gate_response(ask=True))
    dedup = FakeDedup()
    store = FakeStore()
    result = await _gate(router, dedup, store).judge([], "summary", "gap", "run-1")
    assert result.ask is False
    assert result.questions == []
    assert router.calls == []
    assert dedup.calls == []
    assert store.saved == []


async def test_exact_duplicate_is_removed_while_near_match_reaches_gate() -> None:
    history = [past_answer()]
    router = FakeRouter(gate_response(ask=False))
    dedup = FakeDedup([(0.96, "Past question?"), (0.60, "Past question?")])
    store = FakeStore(history)
    questions = [proposal(1), proposal(2)]
    result = await _gate(router, dedup, store).judge(questions, "summary", "gap", "run-1")
    assert result.ask is False
    assert len(router.calls) == 1
    prompt = router.calls[0]["messages"][1]["content"]
    assert "[P1]" not in prompt
    assert "[P2]" in prompt
    assert "similarity=0.600" in prompt
    assert "past_answer=Past answer" in prompt
    assert len(store.saved) == 2
    assert not any(record.asked for record in store.saved)


async def test_all_exact_duplicates_skip_model_and_are_recorded() -> None:
    router = FakeRouter(gate_response(ask=True))
    dedup = FakeDedup([(0.99, "Past question?")])
    store = FakeStore([past_answer()])
    result = await _gate(router, dedup, store).judge([proposal(1)], "summary", "gap", "run-1")
    assert result.ask is False
    assert router.calls == []
    assert len(store.saved) == 1
    assert store.saved[0].asked is False


async def test_question_cap_and_unlock_floor_are_enforced_together() -> None:
    selected = [selection(f"P{index}") for index in range(1, 4)]
    router = FakeRouter(
        gate_response(ask=True, selected=selected, ranking=["P4", "P1", "P2", "P3"])
    )
    store = FakeStore()
    questions = [
        proposal(1),
        proposal(2),
        proposal(3),
        proposal(4, purpose="unlock", related_candidate_id="gap_identifier_1-4"),
    ]
    result = await _gate(router, FakeDedup(), store).judge(
        questions, "summary", "gap", "run-1", "ceramics"
    )
    assert result.ask is True
    assert len(result.questions) == 3
    assert [record.purpose for record in result.questions] == [
        "clarify",
        "clarify",
        "unlock",
    ]
    unlock = result.questions[-1]
    assert unlock.question == "Question 4?"
    assert unlock.related_candidate_id == "gap_identifier_1-4"
    assert len(store.saved) == 4
    declined = [record for record in store.saved if not record.asked]
    assert [record.question for record in declined] == ["Question 3?"]


async def test_gate_decline_does_not_trigger_unlock_floor() -> None:
    router = FakeRouter(gate_response(ask=False, ranking=["P1"]))
    store = FakeStore()
    result = await _gate(router, FakeDedup(), store).judge(
        [proposal(1, purpose="unlock", related_candidate_id="gap-1")],
        "summary",
        "gap",
        "run-1",
    )
    assert result.ask is False
    assert len(store.saved) == 1
    assert store.saved[0].asked is False


async def test_router_failure_continues_silently_and_records_proposals() -> None:
    router = FakeRouter(RuntimeError("all gate models failed"))
    store = FakeStore()
    result = await _gate(router, FakeDedup(), store).judge([proposal(1)], "summary", "gap", "run-1")
    assert result.ask is False
    assert result.questions == []
    assert len(store.saved) == 1
    assert store.saved[0].asked is False


async def test_merged_selection_records_one_asked_question_and_remaining_decline() -> None:
    merged = selection("P1")
    merged["source_proposal_ids"] = ["P1", "P2"]
    router = FakeRouter(gate_response(ask=True, selected=[merged], ranking=["P1", "P2"]))
    store = FakeStore()
    result = await _gate(router, FakeDedup(), store).judge(
        [proposal(1), proposal(2), proposal(3)], "summary", "gap", "run-1"
    )
    assert len(result.questions) == 1
    assert len(store.saved) == 2
    assert sum(record.asked for record in store.saved) == 1
    assert [record.question for record in store.saved if not record.asked] == ["Question 3?"]
