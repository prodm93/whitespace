"""Refines top-ranked candidate ideas into full IdeationProposal objects."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.idea import CandidateIdea, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent proposal writer. You will receive:

1. RANKED IDEAS — candidate ideas already scored and ranked by a critic.

2. GRAPH CONTEXT — structured facts and excerpts from the knowledge graph.

3. USER PROFILE — the professional's skills and domain knowledge.

For each idea, produce a fully fleshed-out proposal:

- **title**: keep or lightly refine the existing title
- **problem_statement**: the unmet need this addresses and why it matters \
(3-4 sentences)
- **technical_approach**: how the idea works at a technical level — be \
specific about methods, architectures, or processes (4-6 sentences)
- **why_this_person**: why this user's specific skills and experience \
position them to pursue this (2-3 sentences, reference exact skills)
- **differentiation_from_prior_art**: how this differs from existing \
patents and solutions mentioned in the context (3-4 sentences)
- **limitations**: known risks, open questions, or implementation \
challenges (2-3 sentences)
- **provenance**: list the graph paths or source references that support \
this idea, formatted as "[SOURCE → EDGE_TYPE → TARGET]" or \
"source: <document name>"

Preserve the input ranking order. Do not add new ideas.\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "IdeationProposals",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "problem_statement": {"type": "string"},
                            "technical_approach": {"type": "string"},
                            "why_this_person": {"type": "string"},
                            "differentiation_from_prior_art": {
                                "type": "string",
                            },
                            "limitations": {"type": "string"},
                            "provenance": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "title",
                            "problem_statement",
                            "technical_approach",
                            "why_this_person",
                            "differentiation_from_prior_art",
                            "limitations",
                            "provenance",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["proposals"],
            "additionalProperties": False,
        },
    },
}


def _format_ideas(ideas: list[CandidateIdea]) -> str:
    lines: list[str] = []
    for i, idea in enumerate(ideas, 1):
        lines.append(f"{i}. **{idea.title}**: {idea.description}")
    return "\n".join(lines)


class IdeaSynthesiser:
    """Refines ranked candidate ideas into full IdeationProposal objects."""

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router

    async def run(
        self,
        ranked_ideas: list[CandidateIdea],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[IdeationProposal]:
        logger.info(
            "IdeaSynthesiser: refining %d ideas into proposals",
            len(ranked_ideas),
        )
        if not ranked_ideas:
            return []

        user_msg = (
            f"## RANKED IDEAS\n\n{_format_ideas(ranked_ideas)}\n\n"
            f"## GRAPH CONTEXT\n\n{graph_context}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        result = await self._router.call(
            role="idea_synthesiser",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            response_format=_RESPONSE_FORMAT,
        )
        parsed = json.loads(result["content"])
        proposals = [IdeationProposal.model_validate(p) for p in parsed.get("proposals", [])]
        logger.info(
            "IdeaSynthesiser: produced %d full proposals",
            len(proposals),
        )
        return proposals
