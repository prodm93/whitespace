"""Identifies candidate unmet needs from research findings and graph traversal."""

from __future__ import annotations

import json
import logging

from whitespace.agents._graph_actions import GraphActions
from whitespace.agents._tool_loop import run_tool_loop
from whitespace.agents.council._gap_prompts import (
    CONCLUDE_PROMPT,
    EXPLORE_PROMPT,
    GAPS_FORMAT,
    QUERY_PROMPT,
    REVISION_PROMPT,
)
from whitespace.agents.council._helpers import format_profile
from whitespace.agents.council._revision import request_revisions
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import CandidateGap, GapExploration
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 8
_MAX_QUERIES = 5


class GapIdentifier:
    """One council member: crafts research queries, then analyses the
    two evidence channels (raw findings + its own graph traversal).

    Runs independently — the council fans out to multiple instances on
    different models. Each model writes different queries and explores
    the graph differently, which is the diversity the council wants.
    """

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        role_name: str,
        graph_actions: GraphActions,
    ) -> None:
        self._config = config
        self._router = router
        self._role_name = role_name
        self._graph = graph_actions

    @property
    def role_name(self) -> str:
        return self._role_name

    async def craft_queries(
        self,
        domain: str,
        profile: ProfessionalProfile,
        prior_queries: list[str] | None = None,
    ) -> list[str]:
        """Write this member's research queries for the domain."""
        user_msg = f"## DOMAIN\n\n{domain}\n\n## USER PROFILE\n\n{format_profile(profile)}"
        if prior_queries:
            listed = "\n".join(f"- {q}" for q in prior_queries[:40])
            user_msg += (
                f"\n\n## ALREADY EXECUTED IN PREVIOUS RUNS (do not repeat; "
                f"their results are already available)\n\n{listed}"
            )
        result = await self._router.call(
            role=self._role_name,
            messages=[
                {"role": "system", "content": QUERY_PROMPT.format(n=_MAX_QUERIES)},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        try:
            queries = json.loads(result["content"]).get("queries", [])
        except (json.JSONDecodeError, AttributeError):
            logger.warning("GapIdentifier[%s]: malformed query JSON", self._role_name)
            return [domain]
        cleaned = [q for q in queries if isinstance(q, str) and q.strip()]
        logger.info("GapIdentifier[%s]: crafted %d queries", self._role_name, len(cleaned))
        return cleaned[:_MAX_QUERIES] or [domain]

    async def run(
        self,
        profile: ProfessionalProfile,
        raw_findings: str,
        memory: str = "",
    ) -> GapExploration:
        """Explore the graph, then conclude gaps from both channels."""
        logger.info("GapIdentifier[%s]: exploring graph", self._role_name)
        exploration = await run_tool_loop(
            self._router,
            role=self._role_name,
            system_prompt=EXPLORE_PROMPT,
            user_prompt=f"## USER PROFILE\n\n{format_profile(profile)}",
            toolkit=self._graph,
            max_tool_calls=_MAX_TOOL_CALLS,
            temperature=0.7,
        )
        user_msg = (
            f"## RAW RESEARCH FINDINGS\n\n{raw_findings}\n\n"
            f"## GRAPH EXPLORATION\n\n{exploration}\n\n"
            f"## USER PROFILE\n\n{format_profile(profile)}"
        )
        if memory:
            user_msg += f"\n\n## PRIOR ANALYSES AND REJECTIONS\n\n{memory}"
        result = await self._router.call(
            role=self._role_name,
            messages=[
                {"role": "system", "content": CONCLUDE_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            response_format=GAPS_FORMAT,
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
            "GapIdentifier[%s]: surfaced %d candidate gaps via %s",
            self._role_name,
            len(gaps),
            model_id,
        )
        return GapExploration(gaps=gaps, findings=exploration)

    async def revise(
        self,
        flagged: list[tuple[CandidateGap, str]],
        graph_context: str,
        profile: ProfessionalProfile,
    ) -> list[CandidateGap]:
        """Revise this identifier's own candidates per the critic's feedback."""
        logger.info(
            "GapIdentifier[%s]: revising %d flagged candidates",
            self._role_name,
            len(flagged),
        )
        model_id, items = await request_revisions(
            self._router,
            role=self._role_name,
            system_prompt=REVISION_PROMPT,
            response_format=GAPS_FORMAT,
            response_key="gaps",
            flagged=flagged,
            graph_context=graph_context,
            profile=profile,
        )
        return [
            CandidateGap(
                title=item["title"],
                description=item["description"],
                source_model=model_id,
                candidate_id=original.candidate_id,
                source_role=original.source_role,
            )
            for (original, _), item in zip(flagged, items, strict=False)
        ]
