"""Gap council stage boundaries and composed execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.agents.council.question_gate import QuestionGate
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._research_stage import ResearchStage, RunMemory
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.schemas.critique import CriticAssessment, CriticReport, Verdict
from whitespace.schemas.gap import CandidateGap, GapExploration, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import GateDecision, ProposedQuestion, QuestionRecord


@dataclass
class Council:
    graph: GapCouncilGraph
    identifier: MagicMock
    critic: MagicMock
    synthesiser: MagicMock
    research: MagicMock
    initial: GapCouncilState
    need: UnmetNeed


@pytest.fixture
def council() -> Council:
    candidate = CandidateGap(
        title="Heat recovery", description="Capture waste heat", source_model="m"
    )
    question = ProposedQuestion(
        question="Is waste heat available?",
        purpose="unlock",
        rationale="Determines whether recovery is possible",
        hypothesis="Heat is available",
        asker_role="gap_identifier_1",
        related_candidate_title=candidate.title,
    )
    identifier = MagicMock(spec=GapIdentifier)
    identifier.role_name = "gap_identifier_1"
    identifier.craft_queries = AsyncMock(return_value=["heat recovery"])
    identifier.run = AsyncMock(
        return_value=GapExploration(
            gaps=[candidate], findings="Graph evidence", proposed_questions=[question]
        )
    )
    identifier.revise = AsyncMock(return_value=[])
    critic = MagicMock(spec=GapCritic)
    critic.run = AsyncMock(return_value=_report("keep"))
    need = UnmetNeed(
        title=candidate.title,
        description=candidate.description,
        current_state="Heat is vented",
        why_unmet="No recovery system",
    )
    synthesiser = MagicMock(spec=GapSynthesiser)
    synthesiser.run = AsyncMock(return_value=[need])
    research = MagicMock(spec=ResearchStage)
    research.research = AsyncMock(return_value=[])
    research.gate_pool = AsyncMock(
        side_effect=lambda pool, *_args: (pool, {"gap_identifier_1-1": "near prior work"})
    )
    initial: GapCouncilState = {
        "domain": "energy",
        "profile": ProfessionalProfile(),
        "doc_paths": ["profile.pdf"],
        "keep_findings": True,
        "run_id": "run-1",
        "run_memory": RunMemory(prior_queries=["old query"], memory="Prior gaps"),
    }
    graph = GapCouncilGraph([identifier], critic, synthesiser, research)
    return Council(graph, identifier, critic, synthesiser, research, initial, need)


def _report(verdict: Verdict) -> CriticReport:
    return CriticReport(
        assessments=[
            CriticAssessment(
                candidate_id="gap_identifier_1-1",
                verdict=verdict,
                scores={"specificity": 8},
                feedback_for_originator="Explain the heat exchanger",
            )
        ],
        ranking=["gap_identifier_1-1"],
    )


async def test_first_half_preserves_evidence_and_stops_before_critique(council: Council) -> None:
    state = await council.graph.run_first_half(council.initial)

    council.critic.run.assert_not_awaited()
    council.synthesiser.run.assert_not_awaited()
    council.research.ingest.assert_awaited_once_with(["profile.pdf"], [])
    assert state["run_memory"] == council.initial["run_memory"]
    assert state["findings_by_role"] == {"gap_identifier_1": "Graph evidence"}
    assert state["proposed_questions"][0].related_candidate_id == "gap_identifier_1-1"
    assert state["gate_flags"] == {"gap_identifier_1-1": "near prior work"}
    assert state["pending_questions"] == []
    assert state["report"] is None
    assert state["revision_round"] == 0


async def test_second_half_uses_supplied_state_without_research(council: Council) -> None:
    state = await council.graph.run_first_half(council.initial)
    restored = GapCouncilGraph(
        [council.identifier], council.critic, council.synthesiser, council.research
    )

    assert await restored.run_second_half(state) == [council.need]

    council.identifier.craft_queries.assert_awaited_once()
    council.identifier.run.assert_awaited_once()
    council.research.research.assert_awaited_once()
    council.research.ingest.assert_awaited_once()
    council.critic.run.assert_awaited_once()
    evidence = council.critic.run.call_args.kwargs["evidence"]
    assert "Graph evidence" in evidence
    assert "near prior work" in evidence
    council.research.record_kills.assert_awaited_once()


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("verdict,revisions", [("keep", 0), ("delegate_back", 2)])
async def test_composed_council_keeps_revision_limit(
    council: Council, split: bool, verdict: Verdict, revisions: int
) -> None:
    council.critic.run.return_value = _report(verdict)
    if split:
        state = await council.graph.run_first_half(council.initial)
        result = await council.graph.run_second_half(state)
    else:
        result = await council.graph.run(
            council.initial["profile"],
            council.initial["domain"],
            council.initial["doc_paths"],
            keep_findings=True,
            run_id="run-1",
            run_memory=council.initial["run_memory"],
        )

    assert result == [council.need]
    assert council.critic.run.await_count == revisions + 1
    assert council.identifier.revise.await_count == revisions
    council.identifier.run.assert_awaited_once()
    council.research.ingest.assert_awaited_once()
    resolved = council.synthesiser.run.call_args.args[1]
    assert resolved.assessments[0].verdict == "keep"
    assert resolved.ranking == ["gap_identifier_1-1"]


async def test_run_refuses_to_continue_past_pending_questions(council: Council) -> None:
    gate = MagicMock(spec=QuestionGate)
    record = QuestionRecord(
        question_id="q-1",
        run_id="run-1",
        stage="gap",
        purpose="unlock",
        question="Is waste heat available?",
        hypothesis="Heat is available",
        rationale="Determines whether recovery is possible",
        asker_role="gap_identifier_1",
        asked=True,
        created_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    gate.judge = AsyncMock(return_value=GateDecision(ask=True, questions=[record], reasoning=""))
    council.research.deduplicator.similarity_matrix = AsyncMock(return_value=[[1.0]])
    graph = GapCouncilGraph(
        [council.identifier], council.critic, council.synthesiser, council.research, gate
    )

    state = await graph.run_first_half(council.initial)
    assert state["pending_questions"] == [record]

    with pytest.raises(RuntimeError):
        await graph.run(council.initial["profile"], council.initial["domain"])
    council.critic.run.assert_not_awaited()
