"""Gap council second half with the user's answers: refine, follow-up search, new gaps."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from _gap_council_helpers import (
    ROLES,
    RefineRouter,
    ScoreDedup,
    make_council,
    make_gap,
    make_mid_state,
    make_record,
)

from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._gap_answer_stage import run_refine_node
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.schemas.gap import CandidateGap, GapExploration
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion, QuestionRecord, UserAnswer
from whitespace.schemas.research import RawFinding


async def test_no_answered_question_makes_no_refine_call() -> None:
    council = make_council(RefineRouter())
    state = make_mid_state([make_record("q-1")])

    result, _ = await council.graph.run_second_half(
        state, [UserAnswer(question_id="q-1", status="skipped")]
    )

    assert result == [council.need]
    assert council.router.calls == []
    assert council.critic.run.await_args is not None
    assert [c.candidate_id for c in council.critic.run.await_args.args[0]] == [
        "gap_identifier_1-1",
        "gap_identifier_2-1",
    ]


async def test_an_answered_clarify_question_refines_every_identifier() -> None:
    council = make_council(RefineRouter())
    state = make_mid_state([make_record("q-1")])

    await council.graph.run_second_half(
        state, [UserAnswer(question_id="q-1", status="answered", answer="Exhaust is 400C")]
    )

    for role in ROLES:
        messages = council.router.messages_for(role)
        assert len(messages) == 1
        assert (
            "## USER ANSWERS (this run)\n\n"
            "- [Q1] Question: Question q-1?\n"
            "  Our hypothesis: Hypothesis q-1\n"
            "  Answer: Exhaust is 400C"
        ) in messages[0]


async def test_an_answered_unlock_question_refines_only_the_owner() -> None:
    council = make_council(RefineRouter())
    state = make_mid_state([make_record("q-1", purpose="unlock", related="gap_identifier_2-1")])

    await council.graph.run_second_half(
        state, [UserAnswer(question_id="q-1", status="answered", answer="Yes")]
    )

    assert council.router.messages_for("gap_identifier_1") == []
    assert len(council.router.messages_for("gap_identifier_2")) == 1


async def test_follow_up_queries_are_searched_and_keyed_after_the_last_finding() -> None:
    first = {
        "gaps": [{"title": "Heat recovery", "description": "d", "evidence": ["[F1]"]}],
        "new_gaps": [],
        "follow_up_queries": ["q a", "q b", "q c", "q d"],
    }
    router = RefineRouter(replies={"gap_identifier_1": [first]})
    council = make_council(router)
    council.research.research.return_value = [
        RawFinding(
            title="Exhaust recovery trial",
            content="Recovered 30 percent",
            source_type="web",
            source_name="example.org",
            query="q a",
            found_at=datetime(2026, 11, 11, tzinfo=UTC),
        )
    ]
    state = make_mid_state([make_record("q-1")])

    await council.graph.run_second_half(
        state, [UserAnswer(question_id="q-1", status="answered", answer="Yes")]
    )

    call = council.research.research.await_args
    assert call is not None
    assert call.args[0] == ["q a", "q b", "q c"]
    assert call.kwargs["prior_queries"] == ["heat recovery", "old query"]
    assert call.kwargs["prior_findings"] == []
    second = council.router.messages_for("gap_identifier_1")[1]
    assert "- [F3] [web] Exhaust recovery trial (n.d.; found 2026-11-11; query: q a)" in second
    assert len(council.router.messages_for("gap_identifier_2")) == 1


async def test_no_follow_up_queries_means_one_refine_call_for_each_target() -> None:
    council = make_council(RefineRouter())
    state = make_mid_state([make_record("q-1")])

    await council.graph.run_second_half(
        state, [UserAnswer(question_id="q-1", status="answered", answer="Yes")]
    )

    council.research.research.assert_not_awaited()
    assert [len(council.router.messages_for(role)) for role in ROLES] == [1, 1]


async def test_a_failing_refine_call_keeps_that_roles_candidates() -> None:
    reply = {
        "gaps": [{"title": "Sharper kiln sealing", "description": "d2", "evidence": ["[Q1]"]}],
        "new_gaps": [],
        "follow_up_queries": [],
    }
    router = RefineRouter(replies={"gap_identifier_2": [reply]}, fail_roles={"gap_identifier_1"})
    council = make_council(router)

    result, _ = await council.graph.run_second_half(
        make_mid_state([make_record("q-1")]),
        [UserAnswer(question_id="q-1", status="answered", answer="Yes")],
    )

    assert result == [council.need]
    assert council.critic.run.await_args is not None
    titles = [c.title for c in council.critic.run.await_args.args[0]]
    assert titles == ["Heat recovery", "Sharper kiln sealing"]


async def test_questions_off_never_calls_a_wired_question_gate() -> None:
    gate = MagicMock(spec=QuestionGate)
    gate.judge = AsyncMock()
    identifier = MagicMock(spec=GapIdentifier)
    identifier.role_name = "gap_identifier_1"
    identifier.craft_queries = AsyncMock(return_value=["heat recovery"])
    identifier.run = AsyncMock(
        return_value=GapExploration(
            gaps=[make_gap("gap_identifier_1", 1, "Heat recovery")],
            findings="Graph evidence",
            proposed_questions=[
                ProposedQuestion(
                    question="Is waste heat available?",
                    purpose="clarify",
                    rationale="r",
                    hypothesis="h",
                    asker_role="gap_identifier_1",
                )
            ],
        )
    )
    council = make_council(RefineRouter())
    council.research.gate_pool = AsyncMock(side_effect=lambda pool, *_a: (pool, {}))
    graph = GapCouncilGraph(
        [identifier], council.critic, council.synthesiser, council.research, gate
    )
    initial: GapCouncilState = {**make_mid_state([]), "questions_enabled": False}

    state = await graph.run_first_half(initial)

    gate.judge.assert_not_awaited()
    assert state["pending_questions"] == []


async def test_run_with_questions_off_gives_the_same_needs() -> None:
    council = make_council(RefineRouter())
    council.research.gate_pool = AsyncMock(side_effect=lambda pool, *_a: (pool, {}))
    for identifier in council.graph._identifiers.values():
        identifier.craft_queries = AsyncMock(return_value=["heat recovery"])  # type: ignore[method-assign]
        identifier.run = AsyncMock(  # type: ignore[method-assign]
            return_value=GapExploration(gaps=[make_gap("x", 1, "Heat recovery")], findings="Graph")
        )

    result, _ = await council.graph.run(ProfessionalProfile(), "energy", run_id="run-9")

    assert result == [council.need]
    assert council.router.calls == []


def _new_gap(title: str, *evidence: str) -> dict[str, Any]:
    return {"title": title, "description": f"{title} description", "evidence": list(evidence)}


async def _critic_pool_after(
    new_gaps: list[dict[str, Any]],
    questions: list[QuestionRecord],
    answers: list[UserAnswer],
) -> list[CandidateGap]:
    reply = {"gaps": [], "new_gaps": new_gaps, "follow_up_queries": []}
    council = make_council(RefineRouter(replies={"gap_identifier_1": [reply]}))
    await council.graph.run_second_half(make_mid_state(questions), answers)
    assert council.critic.run.await_args is not None
    return list(council.critic.run.await_args.args[0])


async def test_added_gaps_are_capped_at_two_and_reach_the_critic() -> None:
    pool = await _critic_pool_after(
        [_new_gap("New A", "[Q1]"), _new_gap("New B", "[Q1]"), _new_gap("New C", "[Q1]")],
        [make_record("q-1")],
        [UserAnswer(question_id="q-1", status="answered", answer="Yes")],
    )

    added = [c for c in pool if "-a" in c.candidate_id]
    assert [(c.candidate_id, c.title) for c in added] == [
        ("gap_identifier_1-a1", "New A"),
        ("gap_identifier_1-a2", "New B"),
    ]


async def test_an_added_gap_citing_a_key_that_does_not_exist_is_dropped() -> None:
    pool = await _critic_pool_after(
        [_new_gap("Cites Q3", "[Q3]")],
        [make_record("q-1")],
        [UserAnswer(question_id="q-1", status="answered", answer="Yes")],
    )

    assert "Cites Q3" not in [c.title for c in pool]


async def test_an_added_gap_must_cite_an_answered_question() -> None:
    pool = await _critic_pool_after(
        [_new_gap("Cites skipped", "[Q2]"), _new_gap("Cites answered", "Q1")],
        [make_record("q-1"), make_record("q-2")],
        [
            UserAnswer(question_id="q-1", status="answered", answer="Yes"),
            UserAnswer(question_id="q-2", status="skipped"),
        ],
    )

    titles = [c.title for c in pool]
    assert "Cites skipped" not in titles
    assert "Cites answered" in titles


async def test_an_added_duplicate_of_earlier_output_is_held_not_stored() -> None:
    reply = {
        "gaps": [],
        "new_gaps": [_new_gap("Old gap", "[Q1]"), _new_gap("Fresh gap", "[Q1]")],
        "follow_up_queries": [],
    }
    council = make_council(
        RefineRouter(replies={"gap_identifier_1": [reply]}), ScoreDedup({"Old gap": 0.95})
    )
    state = {
        **make_mid_state([make_record("q-1")]),
        "user_answers": [UserAnswer(question_id="q-1", status="answered", answer="Yes")],
    }

    update = await run_refine_node(
        council.graph._identifiers,
        council.research,
        state,  # type: ignore[arg-type]
    )

    assert [c.title for c in update["candidates"]] == ["Heat recovery", "Kiln sealing", "Fresh gap"]
    assert update["held_discards"] == [
        {
            "title": "Old gap",
            "description": "Old gap description",
            "reason": "near-duplicate of a previous run's output",
            "domain": "energy",
        }
    ]
    council.research.gate_pool.assert_not_awaited()
    council.research.record_discards.assert_not_awaited()
