"""Refines surviving candidate ideas into full IdeationProposal objects."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_for_synthesis, format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.idea import CandidateIdea, IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent proposal writer. You will receive:

1. SURVIVING CANDIDATES — candidate ideas that passed council review, \
ranked best-first. Each carries its ID, its original text, and the \
critic's guidance: scores, notes, sometimes a developed version, and \
sometimes candidates to combine with.

2. GRAPH CONTEXT — structured facts and excerpts from the knowledge graph.

3. USER PROFILE — the professional's skills and domain knowledge.

You are a write-up agent, not a judge. Selection, cross-synthesis, and \
ranking were all decided by the council critic. Rules:
- Where an entry has a "Final version (critic-authored)", that IS the \
idea — expand it faithfully into the template below. The original and \
any "Merged from" texts are reference material for detail and \
provenance, not competing versions.
- Where there is no critic-authored version, expand the original text, \
using the critic's notes for emphasis.
- Preserve the input ranking order. Do not add, drop, merge, or reorder \
anything.

For each entry, produce a fully fleshed-out proposal:

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
- **source_candidate_ids**: the IDs of every candidate this proposal \
drew from — the ranked anchor plus any combined candidates\
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
                            "source_candidate_ids": {
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
                            "source_candidate_ids",
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


class IdeaSynthesiser:
    """Refines surviving candidate ideas into full IdeationProposal objects."""

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router

    async def run(
        self,
        pool: list[CandidateIdea],
        report: CriticReport,
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[IdeationProposal]:
        logger.info("IdeaSynthesiser: synthesising %d survivors", len(report.ranking))
        if not report.ranking:
            return []

        user_msg = (
            f"## SURVIVING CANDIDATES\n\n{format_for_synthesis(pool, report)}\n\n"
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
        by_id = {c.candidate_id: c for c in pool}
        proposals: list[IdeationProposal] = []
        for item in parsed.get("proposals", []):
            source_ids: list[str] = item.pop("source_candidate_ids", [])
            assessment = report.assessment_for(source_ids[0]) if source_ids else None
            models: list[str] = []
            for cid in source_ids:
                candidate = by_id.get(cid)
                if candidate is not None and candidate.source_model not in models:
                    models.append(candidate.source_model)
            proposals.append(
                IdeationProposal(
                    **item,
                    scores=assessment.scores if assessment else {},
                    contributing_models=models,
                    critique_notes=assessment.objections if assessment else None,
                )
            )
        logger.info("IdeaSynthesiser: produced %d full proposals", len(proposals))
        return proposals
