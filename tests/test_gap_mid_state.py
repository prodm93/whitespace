"""Serialisation of the gap council state between its two halves."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from whitespace.orchestration._gap_council_state import (
    GapCouncilState,
    dump_mid_state,
    load_mid_state,
)
from whitespace.orchestration._research_stage import RunMemory
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.profile import ProfessionalProfile, ProjectSummary
from whitespace.schemas.question import ProposedQuestion, QuestionRecord
from whitespace.schemas.research import RawFinding


def _mid_state() -> GapCouncilState:
    finding = RawFinding(
        title="Kiln exhaust study",
        content="Exhaust gases leave at 400C",
        source_type="paper",
        source_url="https://example.org/kiln",
        source_name="Kiln exhaust study",
        query="kiln heat recovery",
        published="2024",
        found_at=datetime(2026, 7, 1, 12, 30, tzinfo=UTC),
        domain="energy",
    )
    profile = ProfessionalProfile(
        hard_skills=["thermodynamics"],
        past_projects=[ProjectSummary(name="Pilot kiln", description="Ran trials")],
        years_experience=12,
    )
    candidate = CandidateGap(
        title="Heat recovery",
        description="Capture waste heat",
        source_model="m",
        candidate_id="gap_identifier_1-1",
        source_role="gap_identifier_1",
        evidence=["[F1]"],
    )
    question = ProposedQuestion(
        question="Is waste heat available?",
        purpose="unlock",
        rationale="Determines whether recovery is possible",
        hypothesis="Heat is available",
        asker_role="gap_identifier_1",
        related_candidate_id="gap_identifier_1-1",
        related_candidate_title="Heat recovery",
    )
    return {
        "domain": "energy",
        "profile": profile,
        "doc_paths": ["profile.pdf"],
        "keep_findings": True,
        "run_id": "run-1",
        "run_memory": RunMemory(
            prior_queries=["old query"],
            prior_findings=[finding],
            memory="Prior gaps",
            prior_texts=["Old gap: description"],
            neighbours="Nearby work",
        ),
        "queries": ["kiln heat recovery"],
        "findings_text": "- [F1] [paper] Kiln exhaust study",
        "findings_by_role": {"gap_identifier_1": "Graph evidence"},
        "candidates": [candidate],
        "proposed_questions": [question],
        "pending_questions": [
            QuestionRecord(
                question_id="q-1",
                run_id="run-1",
                stage="gap",
                purpose="unlock",
                question=question.question,
                hypothesis=question.hypothesis,
                rationale=question.rationale,
                asker_role=question.asker_role,
                related_candidate_id=question.related_candidate_id,
                asked=True,
                domain="energy",
                created_at=datetime(2026, 9, 24, 7, 0, tzinfo=UTC),
            )
        ],
        "gate_flags": {"gap_identifier_1-1": "near prior work"},
        "report": None,
        "revision_round": 0,
    }


def test_mid_state_survives_json_round_trip() -> None:
    state = _mid_state()

    restored = load_mid_state(json.loads(json.dumps(dump_mid_state(state))))

    assert restored == state


def test_run_memory_round_trip_restores_dated_findings() -> None:
    memory = _mid_state()["run_memory"]

    restored = RunMemory.from_dict(json.loads(json.dumps(memory.to_dict())))

    assert restored == memory
    assert restored.prior_findings[0].found_at == datetime(2026, 7, 1, 12, 30, tzinfo=UTC)
