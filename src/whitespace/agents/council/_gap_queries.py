"""Research queries written by a gap identifier for its domain."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._gap_prompts import NEIGHBOUR_CRAFT_BLOCK, QUERY_PROMPT
from whitespace.agents.council._helpers import format_profile
from whitespace.models.router import ModelRouter
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_MAX_QUERIES = 5


async def craft_gap_queries(
    router: ModelRouter,
    role: str,
    domain: str,
    profile: ProfessionalProfile,
    prior_queries: list[str] | None = None,
    neighbours: str = "",
) -> list[str]:
    """Up to five queries for the domain; the domain itself when the model fails to answer."""
    user_msg = f"## DOMAIN\n\n{domain}\n\n## USER PROFILE\n\n{format_profile(profile)}"
    if prior_queries:
        listed = "\n".join(f"- {q}" for q in prior_queries[:40])
        user_msg += (
            f"\n\n## ALREADY EXECUTED IN PREVIOUS RUNS (do not repeat; "
            f"their results are already available)\n\n{listed}"
        )
    if neighbours:
        user_msg += NEIGHBOUR_CRAFT_BLOCK.format(neighbours=neighbours)
    result = await router.call(
        role=role,
        messages=[
            {"role": "system", "content": QUERY_PROMPT.format(n=_MAX_QUERIES)},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )
    try:
        queries = json.loads(result["content"]).get("queries", [])
    except (json.JSONDecodeError, AttributeError):
        logger.warning("GapIdentifier[%s]: malformed query JSON", role)
        return [domain]
    cleaned = [q for q in queries if isinstance(q, str) and q.strip()]
    logger.info("GapIdentifier[%s]: crafted %d queries", role, len(cleaned))
    return cleaned[:_MAX_QUERIES] or [domain]
