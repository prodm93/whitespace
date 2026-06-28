"""Searches for prior art and validates novelty of ideation proposals."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.idea import IdeationProposal, PriorArtResult
from whitespace.tools.search.scholar_client import ScholarClient
from whitespace.tools.search.uspto_client import UsptpClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a patent prior-art analyst. You will receive a proposed invention \
and search results from USPTO and Semantic Scholar.

Assess whether any of the search results represent **significant prior \
art** — existing work that substantially overlaps with the proposed \
invention in both problem and approach.

Minor topical overlap does not count. Prior art must address the same \
problem AND use a materially similar technical approach.

Return:
- **similar_found**: true only if at least one result is genuinely close
- **notes**: if similar, cite the specific patents/papers and explain \
what overlaps. If not similar, briefly explain why the closest results \
are still distinct. Keep under 200 words.\
"""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "PriorArtAssessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "similar_found": {"type": "boolean"},
                "notes": {"type": "string"},
            },
            "required": ["similar_found", "notes"],
            "additionalProperties": False,
        },
    },
}

_MAX_PATENT_RESULTS = 10
_MAX_PAPER_RESULTS = 10
_ABSTRACT_TRUNCATE = 200


class PriorArtAgent:
    """Checks ideation proposals against USPTO and Semantic Scholar."""

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        uspto_client: UsptpClient,
        scholar_client: ScholarClient,
    ) -> None:
        self._config = config
        self._router = router
        self._uspto = uspto_client
        self._scholar = scholar_client

    async def run(
        self,
        proposals: list[IdeationProposal],
    ) -> PriorArtResult:
        logger.info("PriorArtAgent: checking %d proposals", len(proposals))
        if not proposals:
            return PriorArtResult(proposals=[], prior_art_found=False)

        checks = await asyncio.gather(
            *[self._check_one(p) for p in proposals],
        )
        annotated = [c[0] for c in checks]
        any_found = any(c[1] for c in checks)
        logger.info(
            "PriorArtAgent: prior art found for %d/%d proposals",
            sum(1 for c in checks if c[1]),
            len(proposals),
        )
        return PriorArtResult(proposals=annotated, prior_art_found=any_found)

    async def _check_one(
        self,
        proposal: IdeationProposal,
    ) -> tuple[IdeationProposal, bool]:
        patents, papers = await asyncio.gather(
            self._safe_search_patents(proposal.title),
            self._safe_search_papers(proposal.title),
        )
        if not patents and not papers:
            return proposal, False

        search_ctx = _format_search_results(patents, papers)
        user_msg = (
            f"## PROPOSED INVENTION\n\n"
            f"**{proposal.title}**\n\n"
            f"{proposal.problem_statement}\n\n"
            f"Technical approach: {proposal.technical_approach}\n\n"
            f"## SEARCH RESULTS\n\n{search_ctx}"
        )
        try:
            result = await self._router.call(
                role="prior_art_checker",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                response_format=_RESPONSE_FORMAT,
            )
        except Exception:
            logger.exception("Prior art check failed for %r", proposal.title)
            return proposal, False

        parsed = json.loads(result["content"])
        if parsed.get("similar_found") and parsed.get("notes"):
            annotated = proposal.model_copy(
                update={"prior_art_notes": parsed["notes"]},
            )
            return annotated, True
        return proposal, False

    async def _safe_search_patents(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        try:
            return await self._uspto.search_patents(
                query,
                max_results=_MAX_PATENT_RESULTS,
            )
        except Exception:
            logger.warning("Prior art USPTO search failed for %r", query)
            return []

    async def _safe_search_papers(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        try:
            return await self._scholar.search_papers(
                query,
                max_results=_MAX_PAPER_RESULTS,
            )
        except Exception:
            logger.warning("Prior art Scholar search failed for %r", query)
            return []


def _format_search_results(
    patents: list[dict[str, Any]],
    papers: list[dict[str, Any]],
) -> str:
    sections: list[str] = []
    if patents:
        lines = ["### Patents"]
        for p in patents[:5]:
            num = p.get("patent_number", "")
            title = p.get("title", "")
            abstract = (p.get("abstract") or "")[:_ABSTRACT_TRUNCATE]
            lines.append(f"- {num}: {title} — {abstract}")
        sections.append("\n".join(lines))
    if papers:
        lines = ["### Papers"]
        for p in papers[:5]:
            title = p.get("title", "")
            year = p.get("year", "n/a")
            abstract = (p.get("abstract") or "")[:_ABSTRACT_TRUNCATE]
            lines.append(f"- {title} ({year}) — {abstract}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
