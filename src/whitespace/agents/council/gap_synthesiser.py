"""Fleshes out ranked candidate gaps into full UnmetNeed objects."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent-landscape strategist. You will receive:

1. RANKED GAPS — candidate unmet needs already deduplicated and ranked \
by a prior analysis step.

2. GRAPH CONTEXT — structured facts and excerpts from the knowledge graph \
(patents, papers, web sources) that originally surfaced these gaps.

3. USER PROFILE — the professional's skills and domain knowledge.

For each gap, produce a fully fleshed-out unmet need:

- **title**: keep or lightly refine the existing title
- **description**: expand to a thorough explanation (4-6 sentences)
- **current_state**: what existing patents and technologies currently \
attempt in this space — be specific about patent numbers, methods, or \
companies where the graph context provides them
- **why_unmet**: why those existing approaches fall short — cite \
concrete limitations, failure modes, or missing capabilities from the \
context
- **matching_skills**: which of the user's specific skills are relevant \
to addressing this gap (use the exact skill names from the profile)
- **provenance**: list the graph paths or source references that \
support this gap's existence, formatted as \
"[SOURCE → EDGE_TYPE → TARGET]" or "source: <document name>"

Preserve the input ranking order. Do not add new gaps — only flesh out \
the ones provided.\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "UnmetNeeds",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "needs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "current_state": {"type": "string"},
                            "why_unmet": {"type": "string"},
                            "matching_skills": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "provenance": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "title",
                            "description",
                            "current_state",
                            "why_unmet",
                            "matching_skills",
                            "provenance",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["needs"],
            "additionalProperties": False,
        },
    },
}


def _format_gaps(gaps: list[CandidateGap]) -> str:
    lines: list[str] = []
    for i, g in enumerate(gaps, 1):
        lines.append(f"{i}. **{g.title}**: {g.description}")
    return "\n".join(lines)


class GapSynthesiser:
    """Expands ranked candidate gaps into full UnmetNeed objects."""

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router

    async def run(
        self,
        ranked_gaps: list[CandidateGap],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[UnmetNeed]:
        logger.info("GapSynthesiser: fleshing out %d gaps", len(ranked_gaps))
        if not ranked_gaps:
            return []

        user_msg = (
            f"## RANKED GAPS\n\n{_format_gaps(ranked_gaps)}\n\n"
            f"## GRAPH CONTEXT\n\n{graph_context}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        result = await self._router.call(
            role="gap_synthesiser",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            response_format=_RESPONSE_FORMAT,
        )
        parsed = json.loads(result["content"])
        needs = [UnmetNeed.model_validate(n) for n in parsed.get("needs", [])]
        logger.info(
            "GapSynthesiser: produced %d fleshed-out unmet needs",
            len(needs),
        )
        return needs
