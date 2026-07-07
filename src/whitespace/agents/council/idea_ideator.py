"""Generates candidate patentable ideas from selected unmet needs."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_needs, format_profile
from whitespace.agents.council._revision import request_revisions
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent ideation specialist. You will receive:

1. SELECTED NEEDS — unmet needs in the patent landscape that the user \
wants to develop into patentable ideas.

2. GRAPH CONTEXT — structured facts and excerpts from the knowledge graph \
that surfaced these needs.

3. USER PROFILE — the professional's skills and domain knowledge.

Every idea you propose must be a complete proposition. A patent idea is \
not complete unless it addresses ALL THREE of the following as facets of \
one whole — they are dimensions of a single idea, not alternative angles:

- **Technical feasibility** — how it could concretely be built: specific \
techniques, architectures, materials, algorithms, or processes. The \
technical path must be concrete enough to evaluate for implementability.
- **Commercial value** — what market or customer segment it serves and \
why the value proposition is defensible against alternatives.
- **Cross-domain transfer** — whether techniques, methods, or solutions \
from adjacent fields transfer in. The most novel patents often apply \
well-understood principles from one domain to unsolved problems in \
another. Consider this for every idea; apply it where genuinely relevant.

For each idea:
- **title**: concise name (5-10 words)
- **description**: substantive explanation (5-8 sentences) covering what \
the idea is, how it addresses the need, how it would be built, what \
market it serves, any cross-domain technique it draws on, and why it \
is novel

Generate 4-6 ideas per unmet need — never fewer than 4. Each idea must \
be concrete enough to evaluate: not a vague direction but a specific \
technical and commercial proposition.\
"""

_REVISION_PROMPT = """\
You are a patent ideation specialist revising your own earlier candidate \
ideas. A council critic reviewed them and returned specific feedback on \
each.

For each candidate below, produce a revised version that addresses the \
critic's feedback: make the technical path more concrete, sharpen the \
commercial case, or follow up the cross-domain angle it flagged. Keep \
what was already strong. Do not change the subject of a candidate — \
develop it.

Return exactly one revised idea per candidate, in the same order, with \
the same output shape: title and description.\
"""

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

    All instances share one prompt; each is assigned a different model
    by the router (via its registry role), so diversity comes from
    genuine differences between models rather than prompt variation.
    """

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        role_name: str,
    ) -> None:
        self._config = config
        self._router = router
        self._role_name = role_name

    @property
    def role_name(self) -> str:
        return self._role_name

    async def run(
        self,
        selected_needs: list[UnmetNeed],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[CandidateIdea]:
        logger.info(
            "IdeaIdeator[%s]: ideating on %d needs",
            self._role_name,
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
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.9,
            response_format=_RESPONSE_FORMAT,
        )
        model_id = result["model_id"]
        parsed = json.loads(result["content"])
        ideas = [
            CandidateIdea(
                title=item["title"],
                description=item["description"],
                source_model=model_id,
            )
            for item in parsed.get("ideas", [])
        ]
        logger.info(
            "IdeaIdeator[%s]: generated %d ideas via %s",
            self._role_name,
            len(ideas),
            model_id,
        )
        return ideas

    async def revise(
        self,
        flagged: list[tuple[CandidateIdea, str]],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[CandidateIdea]:
        """Revise this ideator's own candidates per the critic's feedback."""
        logger.info(
            "IdeaIdeator[%s]: revising %d flagged candidates",
            self._role_name,
            len(flagged),
        )
        model_id, items = await request_revisions(
            self._router,
            role=self._role_name,
            system_prompt=_REVISION_PROMPT,
            response_format=_RESPONSE_FORMAT,
            response_key="ideas",
            flagged=flagged,
            graph_context=graph_context,
            profile=profile,
        )
        return [
            CandidateIdea(
                title=item["title"],
                description=item["description"],
                source_model=model_id,
                candidate_id=original.candidate_id,
                source_role=original.source_role,
            )
            for (original, _), item in zip(flagged, items, strict=False)
        ]
