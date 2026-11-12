"""Fixtures for gap council tests: real identifiers on a fake router, mocked judges."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.orchestration._gap_council_state import GapCouncilState
from whitespace.orchestration._research_stage import ResearchStage, RunMemory
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.schemas.critique import CandidateLike, CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import QuestionRecord

ROLES = ("gap_identifier_1", "gap_identifier_2")


@dataclass
class RefineRouter:
    """Answers refine calls per role; records every call it receives."""

    replies: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    fail_roles: set[str] = field(default_factory=set)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role = kwargs["role"]
        if role in self.fail_roles:
            raise RuntimeError("model chain failed")
        queue = self.replies.get(role, [])
        reply = queue.pop(0) if queue else {"gaps": [], "new_gaps": [], "follow_up_queries": []}
        return {"model_id": f"{role}-model", "content": json.dumps(reply)}

    def messages_for(self, role: str) -> list[str]:
        return [c["messages"][1]["content"] for c in self.calls if c["role"] == role]


class ScoreDedup:
    def __init__(self, scores: dict[str, float] | None = None) -> None:
        self.scores = scores or {}

    async def score_against_with_best(
        self, texts: list[str], reference: list[str]
    ) -> list[tuple[float, str]]:
        return [(self.scores.get(t.split(":")[0], 0.0), "prior output") for t in texts]


def make_gap(role: str, n: int, title: str) -> CandidateGap:
    return CandidateGap(
        title=title,
        description=f"{title} description",
        source_model=f"{role}-model",
        candidate_id=f"{role}-{n}",
        source_role=role,
        evidence=["[F1]"],
    )


def make_record(question_id: str, purpose: str = "clarify", related: str = "") -> QuestionRecord:
    return QuestionRecord(
        question_id=question_id,
        run_id="run-1",
        stage="gap",
        purpose=purpose,  # type: ignore[arg-type]
        question=f"Question {question_id}?",
        hypothesis=f"Hypothesis {question_id}",
        rationale="Rationale",
        asker_role="gap_identifier_1",
        related_candidate_id=related,
        asked=True,
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


def keep_all(candidates: list[CandidateLike], *_args: Any, **_kw: Any) -> CriticReport:
    ids = [c.candidate_id for c in candidates]
    return CriticReport(
        assessments=[
            CriticAssessment(candidate_id=i, verdict="keep", scores={"specificity": 8}) for i in ids
        ],
        ranking=ids,
    )


@dataclass
class Council:
    graph: GapCouncilGraph
    router: RefineRouter
    critic: MagicMock
    synthesiser: MagicMock
    research: MagicMock
    need: UnmetNeed


def make_council(router: RefineRouter, dedup: ScoreDedup | None = None) -> Council:
    identifiers = [GapIdentifier(MagicMock(), router, role, MagicMock()) for role in ROLES]  # type: ignore[arg-type]
    critic = MagicMock(spec=GapCritic)
    critic.run = AsyncMock(side_effect=keep_all)
    need = UnmetNeed(
        title="Heat recovery", description="d", current_state="vented", why_unmet="none"
    )
    synthesiser = MagicMock(spec=GapSynthesiser)
    synthesiser.run = AsyncMock(return_value=[need])
    research = MagicMock(spec=ResearchStage)
    research.research = AsyncMock(return_value=[])
    research.deduplicator = dedup or ScoreDedup()
    graph = GapCouncilGraph(identifiers, critic, synthesiser, research)
    return Council(graph, router, critic, synthesiser, research, need)


def make_mid_state(questions: list[QuestionRecord]) -> GapCouncilState:
    return {
        "domain": "energy",
        "profile": ProfessionalProfile(),
        "doc_paths": [],
        "keep_findings": False,
        "run_id": "run-1",
        "run_memory": RunMemory(prior_queries=["old query"], prior_texts=["Old gap: text"]),
        "queries": ["heat recovery"],
        "findings_text": "- [F1] [web] Kiln heat\n- [F2] [paper] Exhaust study",
        "findings_by_role": {role: "Graph evidence" for role in ROLES},
        "candidates": [
            make_gap(ROLES[0], 1, "Heat recovery"),
            make_gap(ROLES[1], 1, "Kiln sealing"),
        ],
        "pending_questions": questions,
        "gate_flags": {},
        "report": None,
        "revision_round": 0,
        "questions_enabled": True,
    }
