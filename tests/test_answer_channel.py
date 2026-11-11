from __future__ import annotations

from datetime import UTC, datetime

from whitespace.agents.council._answer_prompts import (
    answered_keys,
    answers_section,
    render_user_answers,
)
from whitespace.schemas.question import QuestionRecord, UserAnswer


def _record(question_id: str, question: str, hypothesis: str) -> QuestionRecord:
    return QuestionRecord(
        question_id=question_id,
        run_id="run-1",
        stage="gap",
        purpose="clarify",
        question=question,
        hypothesis=hypothesis,
        rationale="Rationale",
        asker_role="gap_identifier_1",
        asked=True,
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


def test_answers_are_keyed_in_the_order_of_the_pending_questions() -> None:
    records = [
        _record("b", "Which substrate?", "Glass"),
        _record("a", "What volume?", "Lab scale"),
    ]
    answers = [
        UserAnswer(question_id="a", status="answered", answer="Pilot line"),
        UserAnswer(question_id="b", status="answered", answer="Silicon"),
    ]

    text = render_user_answers(records, answers)

    assert text == (
        "## USER ANSWERS (this run)\n"
        "\n"
        "- [Q1] Question: Which substrate?\n"
        "  Our hypothesis: Glass\n"
        "  Answer: Silicon\n"
        "- [Q2] Question: What volume?\n"
        "  Our hypothesis: Lab scale\n"
        "  Answer: Pilot line"
    )


def test_skipped_and_expired_questions_show_the_skip_line() -> None:
    records = [
        _record("a", "Which substrate?", "Glass"),
        _record("b", "What volume?", "Lab scale"),
    ]
    answers = [
        UserAnswer(question_id="a", status="skipped"),
        UserAnswer(question_id="b", status="expired", answer="stale text"),
    ]

    text = render_user_answers(records, answers)

    assert text.splitlines()[4] == "  Answer: (the user skipped this question)"
    assert text.splitlines()[7] == "  Answer: (the user skipped this question)"
    assert "stale text" not in text


def test_no_questions_or_no_answers_give_empty_text() -> None:
    records = [_record("a", "Which substrate?", "Glass")]

    assert render_user_answers([], []) == ""
    assert answers_section({}) == ""
    assert answers_section({"pending_questions": records}) == ""
    assert answers_section({"pending_questions": records, "user_answers": []}) == ""


def test_answered_keys_leave_out_skipped_and_expired_questions() -> None:
    records = [
        _record("a", "Which substrate?", "Glass"),
        _record("b", "What volume?", "Lab scale"),
        _record("c", "Which market?", "Medical"),
    ]
    answers = [
        UserAnswer(question_id="a", status="answered", answer="Silicon"),
        UserAnswer(question_id="b", status="skipped"),
        UserAnswer(question_id="c", status="expired"),
    ]

    assert answered_keys(records, answers) == {"Q1"}
