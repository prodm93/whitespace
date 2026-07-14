"""Shared targeted-revision request used by council generator agents."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from whitespace.agents.council._helpers import format_profile
from whitespace.models.router import ModelRouter
from whitespace.schemas.critique import CandidateLike
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)


async def request_revisions(
    router: ModelRouter,
    *,
    role: str,
    system_prompt: str,
    response_format: dict[str, Any],
    response_key: str,
    flagged: Sequence[tuple[CandidateLike, str]],
    graph_context: str,
    profile: ProfessionalProfile,
) -> tuple[str, list[dict[str, str]]]:
    """Ask the originating model to revise its flagged candidates.

    Returns the model ID that produced the revisions and the raw revised
    items, order-aligned with ``flagged``.
    """
    item_parts: list[str] = []
    for i, (candidate, feedback) in enumerate(flagged, 1):
        entry = f"{i}. **{candidate.title}**: {candidate.description}"
        evidence = getattr(candidate, "evidence", [])
        if evidence:
            entry += f"\n   evidence: {', '.join(evidence)}"
        entry += f"\n   Critic feedback: {feedback}"
        item_parts.append(entry)
    items = "\n\n".join(item_parts)
    user_msg = (
        f"## CANDIDATES TO REVISE\n\n{items}\n\n"
        f"## GRAPH CONTEXT\n\n{graph_context}\n\n"
        f"## USER PROFILE\n\n{format_profile(profile)}"
    )
    result = await router.call(
        role=role,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        response_format=response_format,
    )
    model_id: str = result["model_id"]
    revised: list[dict[str, str]] = json.loads(result["content"]).get(response_key, [])
    if len(revised) != len(flagged):
        logger.warning(
            "%s: expected %d revisions, got %d — pairing by order",
            role,
            len(flagged),
            len(revised),
        )
    return model_id, revised
