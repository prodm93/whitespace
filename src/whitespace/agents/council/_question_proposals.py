"""Question proposal parsing and candidate linking for council agents."""

from __future__ import annotations

from collections.abc import Sequence

from whitespace.schemas.critique import CandidateLike
from whitespace.schemas.question import ProposedQuestion

MAX_PROPOSED_QUESTIONS = 5

QUESTION_PROPOSALS_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "purpose": {"type": "string", "enum": ["clarify", "unlock"]},
            "rationale": {"type": "string"},
            "hypothesis": {"type": "string"},
            "related_candidate_title": {"type": "string"},
        },
        "required": [
            "question",
            "purpose",
            "rationale",
            "hypothesis",
            "related_candidate_title",
        ],
        "additionalProperties": False,
    },
}


def parse_proposed_questions(
    value: object,
    asker_role: str,
) -> list[ProposedQuestion]:
    """Parse valid proposals defensively and enforce the per-agent cap."""
    if not isinstance(value, list):
        return []

    proposals: list[ProposedQuestion] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        purpose = item.get("purpose")
        rationale = item.get("rationale")
        hypothesis = item.get("hypothesis")
        title = item.get("related_candidate_title")
        if not isinstance(question, str):
            continue
        if not isinstance(purpose, str):
            continue
        if not isinstance(rationale, str):
            continue
        if not isinstance(hypothesis, str):
            continue
        if not isinstance(title, str):
            continue
        if purpose not in ("clarify", "unlock"):
            continue
        if not question.strip() or not rationale.strip() or not hypothesis.strip():
            continue
        if purpose == "unlock" and not title.strip():
            continue

        proposals.append(
            ProposedQuestion(
                question=question.strip(),
                purpose=purpose,
                rationale=rationale.strip(),
                hypothesis=hypothesis.strip(),
                asker_role=asker_role,
                related_candidate_title=title.strip() if purpose == "unlock" else "",
            )
        )
        if len(proposals) == MAX_PROPOSED_QUESTIONS:
            break
    return proposals


def resolve_question_candidate_ids(
    proposals: list[ProposedQuestion],
    candidates: Sequence[CandidateLike],
) -> list[ProposedQuestion]:
    """Resolve exact candidate titles within the proposing agent's own output."""
    ids_by_origin = {
        (candidate.source_role, candidate.title): candidate.candidate_id for candidate in candidates
    }
    return [
        proposal.model_copy(
            update={
                "related_candidate_id": ids_by_origin.get(
                    (proposal.asker_role, proposal.related_candidate_title), ""
                )
                if proposal.purpose == "unlock"
                else ""
            }
        )
        for proposal in proposals
    ]
