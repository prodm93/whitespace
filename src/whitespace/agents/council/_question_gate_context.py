"""Render proposal history and engagement context for the question gate."""

from __future__ import annotations

from whitespace.schemas._question_scoring import ENGAGEMENT_DIGEST_SIZE
from whitespace.schemas.question import ProposedQuestion, QuestionRecord

_EXEMPLARS_PER_PURPOSE = 3  # REVISIT: tune against eval results.


def build_gate_context(
    proposals: dict[str, ProposedQuestion],
    run_summary: str,
    stage: str,
    run_id: str,
    history: list[QuestionRecord],
    similar: list[tuple[str, float, QuestionRecord]],
) -> str:
    sections = [
        f"## COUNCIL STAGE\n\n{stage}",
        f"## RUN SUMMARY\n\n{run_summary or '(not provided)'}",
        f"## PROPOSED QUESTIONS\n\n{_format_proposals(proposals)}",
        f"## ENGAGEMENT DIGEST\n\n{_format_engagement(history, run_id)}",
        f"## LEARNED QUESTION EXAMPLES\n\n{_format_exemplars(history)}",
        f"## SIMILAR PAST QUESTIONS\n\n{_format_similar(similar)}",
    ]
    return "\n\n".join(sections)


def _format_proposals(proposals: dict[str, ProposedQuestion]) -> str:
    return "\n\n".join(
        (
            f"[{proposal_id}]\n"
            f"purpose: {proposal.purpose}\n"
            f"related_candidate_id: {proposal.related_candidate_id or '(none)'}\n"
            f"question: {proposal.question}\n"
            f"hypothesis: {proposal.hypothesis}\n"
            f"rationale: {proposal.rationale}"
        )
        for proposal_id, proposal in proposals.items()
    )


def _format_engagement(history: list[QuestionRecord], run_id: str) -> str:
    asked = [record for record in history if record.asked][:ENGAGEMENT_DIGEST_SIZE]
    if not asked:
        return "Cold start: no prior asked questions. Use normal judgment."

    counts = {
        status: sum(record.status == status for record in asked)
        for status in ("answered", "skipped", "expired", "pending")
    }
    skip_streak = 0
    for record in asked:
        if record.status != "skipped":
            break
        skip_streak += 1
    this_run = [record for record in asked if record.run_id == run_id]
    header = (
        f"Last {len(asked)} asked: answered={counts['answered']}, "
        f"skipped={counts['skipped']}, expired={counts['expired']}, "
        f"pending={counts['pending']}; current_skip_streak={skip_streak}; "
        f"earlier_this_run={len(this_run)}"
    )
    entries = "\n".join(_format_record(record) for record in asked)
    return f"{header}\n{entries}"


def _format_record(record: QuestionRecord) -> str:
    answer = f"; answer={record.answer}" if record.status == "answered" else ""
    return (
        f"- {record.created_at.isoformat()} [{record.purpose}] "
        f"{record.status}: {record.question}{answer}"
    )


def _format_exemplars(history: list[QuestionRecord]) -> str:
    blocks: list[str] = []
    for purpose in ("clarify", "unlock"):
        pool = [record for record in history if record.asked and record.purpose == purpose]
        positive = sorted(
            (record for record in pool if record.outcome_score > 0),
            key=lambda record: record.outcome_score,
            reverse=True,
        )[:_EXEMPLARS_PER_PURPOSE]
        negative = [
            record
            for record in pool
            if record.status in ("skipped", "expired")
            or (record.status == "answered" and record.outcome_score <= 0)
        ][:_EXEMPLARS_PER_PURPOSE]
        blocks.append(f"{purpose} high-value:\n{_format_scored(positive)}")
        blocks.append(f"{purpose} low-value or declined:\n{_format_scored(negative)}")
    return "\n\n".join(blocks)


def _format_scored(records: list[QuestionRecord]) -> str:
    if not records:
        return "(none)"
    return "\n".join(f"- score={record.outcome_score:.2f}; {record.question}" for record in records)


def _format_similar(similar: list[tuple[str, float, QuestionRecord]]) -> str:
    if not similar:
        return "(none)"
    return "\n".join(
        (
            f"- {proposal_id} similarity={score:.3f}; past_question={record.question}; "
            f"past_answer={record.answer}"
        )
        for proposal_id, score, record in similar
    )
