"""Ideation council halves: first half to the question gate, second half to proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._ideation_council_state import (
    build_initial_ideation_state,
    dump_ideation_state,
    load_ideation_state,
)
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.schemas.critique import CandidateLike, CriticAssessment, CriticReport
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeaExploration, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import GateDecision, ProposedQuestion, QuestionRecord

_NEED = UnmetNeed(title="Early runaway warning", description="d", current_state="s", why_unmet="w")


def _idea(title: str) -> CandidateIdea:
    return CandidateIdea(title=title, description=f"{title} description", source_model="m")


def _proposal(title: str) -> IdeationProposal:
    return IdeationProposal(
        title=title,
        problem_statement="p",
        technical_approach="t",
        why_this_person="w",
        differentiation_from_prior_art="d",
        limitations="l",
    )


def _kill_named(title: str) -> Any:
    def report(candidates: list[CandidateLike], *args: Any, **kwargs: Any) -> CriticReport:
        assessments = [
            CriticAssessment(
                candidate_id=c.candidate_id,
                verdict="kill" if c.title == title else "keep",
                scores={"specificity": 8},
                objections="Too close to US1" if c.title == title else "",
            )
            for c in candidates
        ]
        ranking = [c.candidate_id for c in candidates if c.title != title]
        return CriticReport(assessments=assessments, ranking=ranking)

    return report


@dataclass
class Council:
    graph: IdeationCouncilGraph
    ideators: list[MagicMock]
    critic: MagicMock
    synthesiser: MagicMock


def _ideator(
    role: str,
    ideas: list[CandidateIdea],
    dropped_title: str = "",
    questions: list[ProposedQuestion] | None = None,
) -> MagicMock:
    ideator = MagicMock(spec=IdeaIdeator)
    ideator.role_name = role
    ideator.run = AsyncMock(
        return_value=IdeaExploration(ideas=ideas, proposed_questions=questions or [])
    )

    async def novelty(own: list[CandidateIdea], _prior_art: Any) -> Any:
        kept = [c for c in own if c.title != dropped_title]
        return kept, [c for c in own if c.title == dropped_title]

    ideator.novelty_filter = AsyncMock(side_effect=novelty)
    return ideator


def _council(questions: list[ProposedQuestion] | None = None, **graph_kwargs: Any) -> Council:
    graph_kwargs.setdefault("dedup", MagicMock())
    ideators = [
        _ideator(
            "idea_ideator_1",
            [_idea("Acoustic monitor"), _idea("Gas sniffer")],
            "Gas sniffer",
            questions,
        ),
        _ideator("idea_ideator_2", [_idea("Strain gauge mesh")]),
    ]
    critic = MagicMock(spec=IdeaCritic)
    critic.run = AsyncMock(side_effect=_kill_named("Strain gauge mesh"))
    synthesiser = MagicMock(spec=IdeaSynthesiser)
    synthesiser.run = AsyncMock(return_value=[_proposal("Acoustic monitor")])
    graph = IdeationCouncilGraph(
        ideators, critic, synthesiser, MagicMock(spec=PriorArtAgent), **graph_kwargs
    )
    return Council(graph, ideators, critic, synthesiser)


async def test_run_gives_the_proposals_and_discards_it_gave_before() -> None:
    council = _council()

    proposals, discards = await council.graph.run([_NEED], "Graph context", ProfessionalProfile())

    assert proposals == [_proposal("Acoustic monitor")]
    assert discards == [
        {
            "title": "Gas sniffer",
            "description": "Gas sniffer description",
            "reason": "identified (semi-)duplicate during novelty check",
        },
        {
            "title": "Strain gauge mesh",
            "description": "Strain gauge mesh description",
            "reason": "Too close to US1",
        },
    ]
    assert council.critic.run.await_args is not None
    assert council.critic.run.await_args.kwargs["evidence"] == "Graph context"


def _question(purpose: str, related_title: str = "") -> ProposedQuestion:
    return ProposedQuestion(
        question=f"{purpose} question?",
        purpose=purpose,  # type: ignore[arg-type]
        rationale="r",
        hypothesis="h",
        asker_role="idea_ideator_1",
        related_candidate_title=related_title,
    )


def _asking_gate() -> MagicMock:
    gate = MagicMock(spec=QuestionGate)
    record = QuestionRecord(
        question_id="q-1",
        run_id="job-1",
        stage="ideation",
        purpose="clarify",
        question="clarify question?",
        hypothesis="h",
        rationale="r",
        asker_role="idea_ideator_1",
        asked=True,
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )
    gate.judge = AsyncMock(return_value=GateDecision(ask=True, questions=[record], reasoning=""))
    return gate


def _initial() -> Any:
    return build_initial_ideation_state(
        [_NEED],
        ProfessionalProfile(),
        "Graph context",
        run_id="job-1",
        gap_run_id="gap-1",
        domain="d",
        questions_enabled=True,
        prior_idea_texts=[],
    )


async def test_question_gate_runs_after_novelty_with_the_run_summary() -> None:
    gate = _asking_gate()
    council = _council([_question("clarify")], question_gate=gate)

    await council.graph.run_first_half(_initial())

    assert gate.judge.await_args is not None
    summary = gate.judge.await_args.args[1]
    assert summary == (
        "Candidates: 2 (idea_ideator_1: 1, idea_ideator_2: 1)\n"
        "Removed as duplicates of existing work before this point: 1\n"
        "- [idea_ideator_1-1] Acoustic monitor\n"
        "- [idea_ideator_2-1] Strain gauge mesh"
    )


async def test_an_unlock_question_for_a_dropped_idea_never_reaches_the_gate() -> None:
    gate = _asking_gate()
    council = _council(
        [_question("unlock", "Gas sniffer"), _question("clarify")], question_gate=gate
    )

    await council.graph.run_first_half(_initial())

    assert gate.judge.await_args is not None
    assert [p.purpose for p in gate.judge.await_args.args[0]] == ["clarify"]


def test_ideation_state_survives_a_json_round_trip() -> None:
    state = {
        **_initial(),
        "candidates": [_idea("Acoustic monitor")],
        "user_answers": [],
        "gate_flags": {"idea_ideator_1-1": "resembles prior work"},
        "discards": [{"title": "t", "description": "d", "reason": "r"}],
        "report": None,
        "revision_round": 0,
    }

    restored = load_ideation_state(json.loads(json.dumps(dump_ideation_state(state))))

    assert restored == state


async def test_the_run_id_and_domain_reach_the_gate_and_the_mid_state() -> None:
    gate = _asking_gate()
    council = _council([_question("clarify")], question_gate=gate)

    state = await council.graph.run_first_half(_initial())

    assert gate.judge.await_args is not None
    assert gate.judge.await_args.args[3:] == ("job-1", "d")
    dumped = dump_ideation_state(state)
    assert dumped["run_id"] == "job-1"
    assert dumped["gap_run_id"] == "gap-1"
    assert [q["question_id"] for q in dumped["pending_questions"]] == ["q-1"]
