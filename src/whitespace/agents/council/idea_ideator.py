"""Generates candidate patentable ideas from selected unmet needs."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_needs, format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_BASE_PROMPT = """\
You are a patent ideation specialist. You will receive:

1. SELECTED NEEDS — unmet needs in the patent landscape that the user \
wants to develop into patentable ideas.

2. GRAPH CONTEXT — structured facts and excerpts from the knowledge graph \
that surfaced these needs.

3. USER PROFILE — the professional's skills and domain knowledge.

{framing_instruction}

For each idea:
- **title**: concise name (5-10 words)
- **description**: substantive explanation (4-6 sentences) covering the \
idea, how it addresses the need, and why it is novel

Aim for 2-4 ideas per unmet need. Each idea must be concrete enough to \
evaluate — not a vague direction but a specific technical or commercial \
proposition.\
"""

_FRAMING_INSTRUCTIONS: dict[str, str] = {
    "technical_feasibility": (
        "Your framing is **technical feasibility**. For each unmet need, "
        "propose ideas focusing on HOW they could be built: specific "
        "techniques, architectures, materials, algorithms, or processes. "
        "Favour ideas whose technical path is concrete enough to evaluate "
        "for implementability."
    ),
    "commercial_value": (
        "Your framing is **commercial value**. For each unmet need, "
        "propose ideas focusing on WHAT MARKET they serve: customer "
        "segments, business models, competitive advantages, and market "
        "gaps. Favour ideas with clear commercial potential and "
        "defensible value propositions."
    ),
    "cross_domain_transfer": (
        "Your framing is **cross-domain transfer**. For each unmet need, "
        "look for techniques, methods, or solutions from ADJACENT FIELDS "
        "that could be adapted. The most novel patents often apply well-"
        "understood principles from one domain to unsolved problems in "
        "another. Favour unexpected connections."
    ),
}

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "CandidateIdeas",
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


class IdeaIdeator:
    """Generates candidate ideas for selected unmet needs.

    Each instance uses a different framing (technical, commercial,
    cross-domain) and a different model via the router, producing
    genuinely diverse proposals.
    """

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        role_name: str,
        framing: str,
    ) -> None:
        if framing not in _FRAMING_INSTRUCTIONS:
            raise ValueError(f"Unknown framing: {framing!r}")
        self._config = config
        self._router = router
        self._role_name = role_name
        self._framing = framing
        self._system_prompt = _BASE_PROMPT.format(
            framing_instruction=_FRAMING_INSTRUCTIONS[framing],
        )

    async def run(
        self,
        selected_needs: list[UnmetNeed],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[CandidateIdea]:
        logger.info(
            "IdeaIdeator[%s/%s]: ideating on %d needs",
            self._role_name,
            self._framing,
            len(selected_needs),
        )
        user_msg = (
            f"## SELECTED NEEDS\n\n{format_needs(selected_needs)}\n\n"
            f"## GRAPH CONTEXT\n\n{graph_context}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        result = await self._router.call(
            role=self._role_name,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            response_format=_RESPONSE_FORMAT,
        )
        model_id = result["model_id"]
        parsed = json.loads(result["content"])
        ideas = [
            CandidateIdea(
                title=item["title"],
                description=item["description"],
                source_model=model_id,
                framing=self._framing,
            )
            for item in parsed.get("ideas", [])
        ]
        logger.info(
            "IdeaIdeator[%s/%s]: generated %d ideas via %s",
            self._role_name,
            self._framing,
            len(ideas),
            model_id,
        )
        return ideas
