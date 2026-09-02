from __future__ import annotations

from datetime import UTC, datetime

import pytest

from whitespace.schemas._question_scoring import compute_outcome_score
from whitespace.schemas.question import QuestionRecord

_CREATED_AT = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _record(**overrides: object) -> QuestionRecord:
    values: dict[str, object] = {
        "question_id": "q1",
        "run_id": "r1",
        "stage": "gap",
        "purpose": "clarify",
        "question": "Which operating temperature is required?",
        "hypothesis": "Below 80 C",
        "rationale": "This determines which materials remain viable.",
        "asker_role": "gap_identifier_1",
        "asked": True,
        "created_at": _CREATED_AT,
    }
    values.update(overrides)
    return QuestionRecord.model_validate(values)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", 0.0),
        ("skipped", -0.3),
        ("expired", 0.0),
    ],
)
def test_status_signal_without_downstream_bonuses(status: str, expected: float) -> None:
    assert compute_outcome_score(_record(status=status)) == pytest.approx(expected)


def test_answered_without_downstream_citation_is_capped_at_zero() -> None:
    assert compute_outcome_score(_record(status="answered")) == 0.0


def test_survival_bonus_prevents_answered_clamp() -> None:
    score = compute_outcome_score(_record(status="answered", survival_bonus=0.25))

    assert score == pytest.approx(1.25)


def test_selection_bonus_and_rerun_penalty_are_combined() -> None:
    score = compute_outcome_score(
        _record(status="answered", selection_bonus=2.0, rerun_penalty=-0.3)
    )

    assert score == pytest.approx(2.7)


def test_rerun_penalty_applies_to_non_answered_record() -> None:
    score = compute_outcome_score(_record(status="skipped", rerun_penalty=-0.3))

    assert score == pytest.approx(-0.6)
