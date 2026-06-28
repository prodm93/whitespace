"""Scores and ranks candidate ideas from all ideators."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import (
    format_idea_candidates,
    format_profile,
)
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.idea import CandidateIdea
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent ideation critic. You will receive candidate ideas \
from multiple independent analysts (each using a different model and \
framing), plus a user's professional profile.

Your task:

1. **Deduplicate**: merge ideas that target the same core invention, \
even if framed differently.

2. **Score** each surviving idea on four criteria (1-10 each):
   - **Novelty** — how distinct is this from existing patents?
   - **Feasibility** — could this realistically be built or implemented?
   - **Specificity** — is the idea concrete enough to draft claims around?
   - **Profile alignment** — does the user have the right skills?

3. **Rank** by composite score, best-first. Discard ideas scoring \
below 5 on any single criterion.

For each surviving idea:
- **title**: concise (5-10 words), may be refined
- **description**: best synthesis of merged descriptions (4-6 sentences)

Output 3-8 ideas, ranked best-first.\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "RankedIdeas",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "ideas": {
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
            "required": ["ideas"],
            "additionalProperties": False,
        },
    },
}


class IdeaCritic:
    """Scores and ranks candidate ideas from all ideators."""

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router

    async def run(
        self,
        candidates: list[list[CandidateIdea]],
        profile: ProfessionalProfile,
    ) -> list[CandidateIdea]:
        logger.info("IdeaCritic: evaluating %d idea lists", len(candidates))
        flat_count = sum(len(g) for g in candidates)
        if flat_count == 0:
            logger.warning("IdeaCritic: no candidate ideas to evaluate")
            return []

        user_msg = (
            f"## CANDIDATE IDEAS\n\n{format_idea_candidates(candidates)}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        result = await self._router.call(
            role="idea_critic",
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
            CandidateIdea(
                title=item["title"],
                description=item["description"],
                source_model=model_id,
                framing="critic_merged",
            )
            for item in parsed.get("ideas", [])
        ]
        logger.info(
            "IdeaCritic: %d candidates → %d ranked ideas",
            flat_count,
            len(ranked),
        )
        return ranked
