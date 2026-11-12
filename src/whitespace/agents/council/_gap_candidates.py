"""Candidate gaps built from a gap identifier's model output."""

from __future__ import annotations

from typing import Any

from whitespace.schemas.gap import CandidateGap


def gap_from_item(
    item: dict[str, Any], model_id: str, *, candidate_id: str = "", source_role: str = ""
) -> CandidateGap:
    """One candidate gap from a model item; non-string evidence entries are dropped."""
    return CandidateGap(
        title=item["title"],
        description=item["description"],
        source_model=model_id,
        candidate_id=candidate_id,
        source_role=source_role,
        evidence=[e for e in item.get("evidence", []) if isinstance(e, str)],
    )


def revised_gaps(
    originals: list[CandidateGap], items: list[dict[str, Any]], model_id: str
) -> list[CandidateGap]:
    """Revisions paired by order with the originals, keeping each ID and role."""
    return [
        gap_from_item(
            item, model_id, candidate_id=original.candidate_id, source_role=original.source_role
        )
        for original, item in zip(originals, items, strict=False)
    ]


def refined_gaps(
    own: list[CandidateGap], items: list[dict[str, Any]], model_id: str
) -> list[CandidateGap]:
    """Like ``revised_gaps``, but an original with no paired item stays unchanged."""
    return revised_gaps(own, items, model_id) + own[len(items) :]


def added_gaps(items: list[dict[str, Any]], model_id: str, role: str) -> list[CandidateGap]:
    """New gaps added by a member, with IDs ``<role>-a1``, ``<role>-a2`` and so on."""
    return [
        gap_from_item(item, model_id, candidate_id=f"{role}-a{n}", source_role=role)
        for n, item in enumerate(items, start=1)
    ]
