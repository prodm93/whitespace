from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from whitespace.schemas.question import ProposedQuestion, QuestionRecord
from whitespace.store.noop_store import NoopSessionStore


class FakeRouter:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeDedup:
    def __init__(self, matches: list[tuple[float, str]] | None = None) -> None:
        self.matches = matches or []
        self.calls: list[tuple[list[str], list[str]]] = []

    async def score_against_with_best(
        self, texts: list[str], reference: list[str]
    ) -> list[tuple[float, str]]:
        self.calls.append((texts, reference))
        return self.matches


class FakeStore(NoopSessionStore):
    def __init__(self, history: list[QuestionRecord] | None = None) -> None:
        self.history = history or []
        self.saved: list[QuestionRecord] = []

    async def list_question_records(self, limit: int | None = None) -> list[QuestionRecord]:
        return self.history if limit is None else self.history[:limit]

    async def save_question_records(self, records: list[QuestionRecord]) -> None:
        self.saved.extend(records)


def proposal(
    index: int,
    *,
    purpose: str = "clarify",
    related_candidate_id: str = "",
) -> ProposedQuestion:
    return ProposedQuestion(
        question=f"Question {index}?",
        purpose=purpose,
        rationale=f"Rationale {index}",
        hypothesis=f"Hypothesis {index}",
        asker_role="gap_identifier_1",
        related_candidate_id=related_candidate_id,
    )


def past_answer(question: str = "Past question?") -> QuestionRecord:
    return QuestionRecord(
        question_id="past-1",
        run_id="past-run",
        stage="gap",
        purpose="clarify",
        question=question,
        hypothesis="Past hypothesis",
        rationale="Past rationale",
        asker_role="gap_identifier_1",
        asked=True,
        status="answered",
        answer="Past answer",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def selection(proposal_id: str, *, purpose: str = "clarify") -> dict[str, object]:
    return {
        "source_proposal_ids": [proposal_id],
        "question": f"Selected {proposal_id}?",
        "purpose": purpose,
        "rationale": f"Selected rationale {proposal_id}",
        "hypothesis": f"Selected hypothesis {proposal_id}",
    }


def gate_response(
    *,
    ask: bool,
    selected: list[dict[str, object]] | None = None,
    ranking: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "content": json.dumps(
            {
                "ask": ask,
                "selected_questions": selected or [],
                "ranked_proposal_ids": ranking or [],
                "reasoning": "Gate reasoning",
            }
        ),
        "model_id": "gate-model",
    }
