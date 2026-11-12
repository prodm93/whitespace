"""Identifies candidate unmet needs from research findings and graph traversal."""

from __future__ import annotations

import json
import logging

from whitespace.agents._graph_actions import GraphActions
from whitespace.agents._tool_loop import run_tool_loop
from whitespace.agents.council._answer_prompts import GAP_REFINE_FORMAT, GAP_REFINE_PROMPT
from whitespace.agents.council._answer_refinement import Refined, request_refinement
from whitespace.agents.council._gap_candidates import (
    added_gaps,
    gap_from_item,
    refined_gaps,
    revised_gaps,
)
from whitespace.agents.council._gap_prompts import (
    CONCLUDE_PROMPT,
    EXPLORE_PROMPT,
    GAP_REVISIONS_FORMAT,
    GAPS_FORMAT,
    NEIGHBOUR_CONCLUDE_BLOCK,
    REVISION_PROMPT,
)
from whitespace.agents.council._gap_queries import craft_gap_queries
from whitespace.agents.council._helpers import format_profile
from whitespace.agents.council._question_proposals import parse_proposed_questions
from whitespace.agents.council._revision import request_revisions
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import CandidateGap, GapExploration
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 8


class GapIdentifier:
    """One council member: crafts research queries, then analyses the
    two evidence channels (raw findings + its own graph traversal).

    Runs independently. The council fans out to multiple instances on
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
        neighbours: str = "",
    ) -> list[str]:
        """Write this member's research queries for the domain."""
        return await craft_gap_queries(
            self._router, self._role_name, domain, profile, prior_queries, neighbours
        )

    async def run(
        self,
        profile: ProfessionalProfile,
        raw_findings: str,
        memory: str = "",
        neighbours: str = "",
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
            user_msg += f"\n\n## EXACT PRIOR CONTEXT (same domain)\n\n{memory}"
        if neighbours:
            user_msg += NEIGHBOUR_CONCLUDE_BLOCK.format(neighbours=neighbours)
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
        gaps = [gap_from_item(g, model_id) for g in parsed.get("gaps", [])]
        logger.info(
            "GapIdentifier[%s]: surfaced %d candidate gaps via %s",
            self._role_name,
            len(gaps),
            model_id,
        )
        return GapExploration(
            gaps=gaps,
            findings=exploration,
            proposed_questions=parse_proposed_questions(
                parsed.get("questions_for_user"), self._role_name
            ),
        )

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
            response_format=GAP_REVISIONS_FORMAT,
            response_key="gaps",
            flagged=flagged,
            graph_context=graph_context,
            profile=profile,
        )
        return revised_gaps([original for original, _ in flagged], items, model_id)

    async def refine(
        self,
        own: list[CandidateGap],
        answers_text: str,
        context: str,
        profile: ProfessionalProfile,
        *,
        allow_queries: bool,
        valid_keys: set[str],
    ) -> Refined[CandidateGap]:
        """Revise and extend this identifier's own candidates from the user's answers."""
        out = await request_refinement(
            self._router,
            role=self._role_name,
            system_prompt=GAP_REFINE_PROMPT,
            response_format=GAP_REFINE_FORMAT,
            response_key="gaps",
            new_key="new_gaps",
            own=own,
            answers_text=answers_text,
            context=context,
            profile=profile,
            allow_queries=allow_queries,
            valid_keys=valid_keys,
        )
        return Refined(
            revised=refined_gaps(own, out.items, out.model_id),
            added=added_gaps(out.new_items, out.model_id, self._role_name),
            queries=out.follow_up_queries,
        )
