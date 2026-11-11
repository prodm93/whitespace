"""The duplicate gate: candidates scored against the output of earlier runs."""

from __future__ import annotations

from typing import TypeVar

from whitespace.schemas.critique import CandidateLike
from whitespace.tools.dedup import SemanticDeduplicator

C = TypeVar("C", bound=CandidateLike)

_GATE_KILL_THRESHOLD = 0.95
_GATE_FLAG_FLOOR = 0.85


async def gate_against_prior(
    dedup: SemanticDeduplicator,
    pool: list[C],
    prior_texts: list[str],
) -> tuple[list[C], dict[str, str], list[dict[str, str]]]:
    """Kill near-duplicates of earlier output and flag near-matches; store nothing.

    Returns the kept candidates, a note for the critic for each flagged
    candidate ID, and one discard item (title, description, reason) for each
    killed candidate.
    """
    if not prior_texts or not pool:
        return pool, {}, []
    candidate_texts = [f"{c.title}: {c.description}" for c in pool]
    scored = await dedup.score_against_with_best(candidate_texts, prior_texts)
    kept: list[C] = []
    flags: dict[str, str] = {}
    kill_items: list[dict[str, str]] = []
    for candidate, (score, best_match) in zip(pool, scored, strict=True):
        if score >= _GATE_KILL_THRESHOLD:
            kill_items.append(
                {
                    "title": candidate.title,
                    "description": candidate.description,
                    "reason": "near-duplicate of a previous run's output",
                }
            )
        elif score >= _GATE_FLAG_FLOOR:
            kept.append(candidate)
            flags[candidate.candidate_id] = (
                f"resembles prior work (score {score:.2f}): {best_match[:200]}"
            )
        else:
            kept.append(candidate)
    return kept, flags, kill_items
