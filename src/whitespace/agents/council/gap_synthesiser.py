"""Fleshes out surviving candidate gaps into full UnmetNeed objects."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._helpers import format_for_synthesis, format_profile
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.critique import CriticReport
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent-landscape strategist. You will receive:

1. SURVIVING CANDIDATES — candidate unmet needs that passed council \
review, ranked best-first. Each carries its ID, its original text, and \
the critic's guidance: scores, notes, sometimes a developed version, \
and sometimes candidates to combine with.

2. GRAPH CONTEXT — structured facts and excerpts from the knowledge graph \
(patents, papers, web sources) that originally surfaced these gaps.

3. USER PROFILE — the professional's skills and domain knowledge.

Synthesis rules:
- Work from the ORIGINAL candidate text; use the critic's developed \
version and notes as guidance for strengthening, not as a replacement \
to copy.
- Where the critic marked candidates to combine ("Combine with"), merge \
them into ONE holistic entry that keeps the strongest material from \
each — mitigate information loss; do not flatten details away.
- Preserve the input ranking order. Do not add new gaps and do not \
resurrect anything not listed.

For each entry, produce a fully fleshed-out unmet need:

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
- **source_candidate_ids**: the IDs of every candidate this entry drew \
from — the ranked anchor plus any combined candidates\
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
                            "source_candidate_ids": {
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
                            "source_candidate_ids",
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


class GapSynthesiser:
    """Expands surviving candidate gaps into full UnmetNeed objects."""

    def __init__(self, config: Config, router: ModelRouter) -> None:
        self._config = config
        self._router = router

    async def run(
        self,
        pool: list[CandidateGap],
        report: CriticReport,
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[UnmetNeed]:
        logger.info("GapSynthesiser: synthesising %d survivors", len(report.ranking))
        if not report.ranking:
            return []

        user_msg = (
            f"## SURVIVING CANDIDATES\n\n{format_for_synthesis(pool, report)}\n\n"
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
        by_id = {c.candidate_id: c for c in pool}
        needs: list[UnmetNeed] = []
        for item in parsed.get("needs", []):
            source_ids: list[str] = item.pop("source_candidate_ids", [])
            assessment = report.assessment_for(source_ids[0]) if source_ids else None
            models: list[str] = []
            for cid in source_ids:
                candidate = by_id.get(cid)
                if candidate is not None and candidate.source_model not in models:
                    models.append(candidate.source_model)
            needs.append(
                UnmetNeed(
                    **item,
                    scores=assessment.scores if assessment else {},
                    contributing_models=models,
                    critique_notes=assessment.objections if assessment else None,
                )
            )
        logger.info("GapSynthesiser: produced %d fleshed-out unmet needs", len(needs))
        return needs
