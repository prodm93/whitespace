"""Identifies candidate unmet needs from graph context + user profile."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent-landscape analyst. You will receive two inputs:

1. GRAPH CONTEXT — structured facts and excerpts from a knowledge graph \
built from patents, technical papers, and web sources in a specific domain.

2. USER PROFILE — a structured summary of a professional's skills, \
domain knowledge, methodologies, and past projects.

Your task is to identify **unmet needs** in the patent landscape that \
are specifically relevant to this user's expertise. An unmet need is a \
gap where:
- Existing patents or solutions are inadequate, limited, or missing
- The user's specific skills and domain knowledge position them to \
contribute a novel solution
- There is evidence in the graph context (limitations mentioned in \
patents, complaints in web sources, missing connections between \
technologies)

For each gap, provide:
- **title**: a concise name (5-10 words)
- **description**: a substantive explanation (3-5 sentences) covering \
what the gap is, why it matters, and what evidence from the context \
supports its existence

Aim for 5-8 candidate gaps. Prefer specificity over breadth — \
"lack of real-time corrosion monitoring in subsea pipelines" is better \
than "need for better monitoring". Ground every gap in something \
concrete from the context.\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "CandidateGaps",
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


class GapIdeator:
    """Identifies candidate unmet needs from graph context + user profile.

    Runs independently — the council graph fans out to multiple instances,
    each assigned a different model by the router. This agent does not know
    about other ideators.
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

    async def run(
        self,
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[CandidateGap]:
        logger.info("GapIdeator[%s]: analysing context", self._role_name)
        user_msg = (
            f"## GRAPH CONTEXT\n\n{graph_context}\n\n## USER PROFILE\n\n{format_profile(profile)}"
        )
        result = await self._router.call(
            role=self._role_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            response_format=_RESPONSE_FORMAT,
        )
        model_id = result["model_id"]
        parsed = json.loads(result["content"])
        gaps = [
            CandidateGap(
                title=g["title"],
                description=g["description"],
                source_model=model_id,
            )
            for g in parsed.get("gaps", [])
        ]
        logger.info(
            "GapIdeator[%s]: surfaced %d candidate gaps via %s",
            self._role_name,
            len(gaps),
            model_id,
        )
        return gaps
