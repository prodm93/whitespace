"""Create and persist asked and declined question records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from whitespace.agents.council._question_gate_selection import SelectedQuestion
from whitespace.schemas.question import ProposedQuestion, QuestionRecord
from whitespace.store.base import SessionStore

Stage = Literal["gap", "ideation"]


async def save_gate_records(
    store: SessionStore,
    proposals: list[ProposedQuestion],
    selected: list[SelectedQuestion],
    stage: Stage,
    run_id: str,
    domain: str,
) -> list[QuestionRecord]:
    now = datetime.now(UTC)
    selected_sources = {source_id for question in selected for source_id in question.source_ids}
    records = [
        _record(
            question.question,
            question.purpose,
            question.hypothesis,
            question.rationale,
            question.asker_role,
            question.related_candidate_id,
            True,
            stage,
            run_id,
            domain,
            now,
        )
        for question in selected
    ]
    records.extend(
        _record(
            proposal.question,
            proposal.purpose,
            proposal.hypothesis,
            proposal.rationale,
            proposal.asker_role,
            proposal.related_candidate_id,
            False,
            stage,
            run_id,
            domain,
            now,
        )
        for index, proposal in enumerate(proposals, 1)
        if f"P{index}" not in selected_sources
    )
    await store.save_question_records(records)
    return records


def _record(
    question: str,
    purpose: Literal["clarify", "unlock"],
    hypothesis: str,
    rationale: str,
    asker_role: str,
    related_candidate_id: str,
    asked: bool,
    stage: Stage,
    run_id: str,
    domain: str,
    created_at: datetime,
) -> QuestionRecord:
    return QuestionRecord(
        question_id=str(uuid.uuid4()),
        run_id=run_id,
        stage=stage,
        purpose=purpose,
        question=question,
        hypothesis=hypothesis,
        rationale=rationale,
        asker_role=asker_role,
        related_candidate_id=related_candidate_id,
        asked=asked,
        domain=domain,
        created_at=created_at,
    )
