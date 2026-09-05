"""Parse gate selections and apply the hard question-count rails."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from whitespace.schemas._question_scoring import QUESTION_CAP
from whitespace.schemas.question import ProposedQuestion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectedQuestion:
    source_ids: tuple[str, ...]
    question: str
    purpose: Literal["clarify", "unlock"]
    rationale: str
    hypothesis: str
    related_candidate_id: str
    asker_role: str


def parse_selected_questions(
    raw: object,
    proposals: dict[str, ProposedQuestion],
) -> list[SelectedQuestion]:
    if not isinstance(raw, dict) or not isinstance(raw.get("selected_questions"), list):
        return []
    selected: list[SelectedQuestion] = []
    used_sources: set[str] = set()
    for item in raw["selected_questions"]:
        parsed = _parse_one(item, proposals, used_sources)
        if parsed is None:
            continue
        selected.append(parsed)
        used_sources.update(parsed.source_ids)
    return selected[:QUESTION_CAP]


def _parse_one(
    item: object,
    proposals: dict[str, ProposedQuestion],
    used_sources: set[str],
) -> SelectedQuestion | None:
    if not isinstance(item, dict):
        return None
    raw_sources = item.get("source_proposal_ids")
    if not isinstance(raw_sources, list):
        return None
    string_sources = [source for source in raw_sources if isinstance(source, str)]
    source_ids = tuple(
        proposal_id
        for proposal_id in dict.fromkeys(string_sources)
        if proposal_id in proposals and proposal_id not in used_sources
    )
    purpose = item.get("purpose")
    values = (item.get("question"), item.get("rationale"), item.get("hypothesis"))
    if not source_ids or purpose not in ("clarify", "unlock"):
        return None
    if not all(isinstance(value, str) and value.strip() for value in values):
        return None
    sources = [proposals[proposal_id] for proposal_id in source_ids]
    related_id = next(
        (
            source.related_candidate_id
            for source in sources
            if source.purpose == "unlock" and source.related_candidate_id
        ),
        "",
    )
    if purpose == "unlock" and not related_id:
        return None
    question, rationale, hypothesis = values
    assert isinstance(question, str)
    assert isinstance(rationale, str)
    assert isinstance(hypothesis, str)
    return SelectedQuestion(
        source_ids=source_ids,
        question=question.strip(),
        purpose=purpose,
        rationale=rationale.strip(),
        hypothesis=hypothesis.strip(),
        related_candidate_id=related_id if purpose == "unlock" else "",
        asker_role=sources[0].asker_role,
    )


def apply_selection_rails(
    selected: list[SelectedQuestion],
    raw: dict[str, Any],
    proposals: dict[str, ProposedQuestion],
) -> list[SelectedQuestion]:
    unlocks = {
        proposal_id: proposal
        for proposal_id, proposal in proposals.items()
        if proposal.purpose == "unlock" and proposal.related_candidate_id
    }
    if not unlocks or any(question.purpose == "unlock" for question in selected):
        return selected[:QUESTION_CAP]

    used_sources = {source_id for question in selected for source_id in question.source_ids}
    available = {key: value for key, value in unlocks.items() if key not in used_sources}
    candidates = available or unlocks
    ranking = raw.get("ranked_proposal_ids")
    ranked = ranking if isinstance(ranking, list) else []
    unlock_id = next(
        (proposal_id for proposal_id in ranked if proposal_id in candidates),
        next(iter(candidates)),
    )
    proposal = candidates[unlock_id]
    selected = [question for question in selected if unlock_id not in question.source_ids]
    if len(selected) >= QUESTION_CAP:
        selected = selected[: QUESTION_CAP - 1]
    logger.info("QuestionGate: unlock floor added proposal %s", unlock_id)
    return [
        *selected,
        SelectedQuestion(
            source_ids=(unlock_id,),
            question=proposal.question,
            purpose="unlock",
            rationale=proposal.rationale,
            hypothesis=proposal.hypothesis,
            related_candidate_id=proposal.related_candidate_id,
            asker_role=proposal.asker_role,
        ),
    ]
