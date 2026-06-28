"""Deduplicates, merges, and ranks candidate gaps from all ideators."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_candidates, format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent-landscape gap analyst performing quality control. You \
will receive candidate unmet needs identified by multiple independent \
analysts (each using a different model), plus a user's professional profile.

Your task:

1. **Deduplicate**: identify gaps that describe the same underlying need \
(even if worded differently). Merge them into a single entry, combining \
the strongest evidence and clearest framing from each.

2. **Eliminate weak entries**: remove gaps that are too vague ("need \
better tools"), unsupported by evidence, or not genuinely unmet.

3. **Rank**: order the surviving gaps from most to least relevant, using \
these criteria:
   - **Relevance to user profile** — does this gap align with the \
user's skills, domain knowledge, and methodologies?
   - **Specificity** — is the gap concrete and actionable?
   - **Evidence strength** — is there clear support from the patent \
landscape?
   - **Novelty** — would addressing this gap produce genuinely new IP?

For each surviving gap:
- **title**: concise (5-10 words), may be refined from the originals
- **description**: the best synthesis of the merged descriptions (3-5 \
sentences)

Output 3-7 gaps, ranked best-first.\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "RankedGaps",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["title", "description"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["gaps"],
            "additionalProperties": False,
        },
    },
}


class GapCritic:
    """Deduplicates, merges, and ranks candidate gaps from all ideators."""

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router

    async def run(
        self,
        candidates: list[list[CandidateGap]],
        profile: ProfessionalProfile,
    ) -> list[CandidateGap]:
        logger.info("GapCritic: evaluating %d gap lists", len(candidates))
        flat_count = sum(len(g) for g in candidates)
        if flat_count == 0:
            logger.warning("GapCritic: no candidate gaps to evaluate")
            return []

        user_msg = (
            f"## CANDIDATE GAPS\n\n{format_candidates(candidates)}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        result = await self._router.call(
            role="gap_critic",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            response_format=_RESPONSE_FORMAT,
        )
        model_id = result["model_id"]
        parsed = json.loads(result["content"])
        ranked = [
            CandidateGap(
                title=g["title"],
                description=g["description"],
                source_model=model_id,
            )
            for g in parsed.get("gaps", [])
        ]
        logger.info(
            "GapCritic: %d candidates → %d ranked gaps",
            flat_count,
            len(ranked),
        )
        return ranked
