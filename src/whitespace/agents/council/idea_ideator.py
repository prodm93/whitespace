"""Generates candidate patentable ideas from selected unmet needs."""

from __future__ import annotations

import json
import logging

from whitespace.agents.council._answer_prompts import IDEA_REFINE_FORMAT, IDEA_REFINE_PROMPT
from whitespace.agents.council._answer_refinement import Refined, request_refinement
from whitespace.agents.council._helpers import format_needs, format_profile
from whitespace.agents.council._idea_prompts import (
    IDEA_REVISIONS_FORMAT,
    IDEAS_FORMAT,
    REVISION_PROMPT,
    SYSTEM_PROMPT,
)
from whitespace.agents.council._novelty import run_novelty_filter
from whitespace.agents.council._question_proposals import parse_proposed_questions
from whitespace.agents.council._revision import request_revisions
from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea, IdeaExploration
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)


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
    ) -> IdeaExploration:
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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.9,
            response_format=IDEAS_FORMAT,
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
        return IdeaExploration(
            ideas=ideas,
            proposed_questions=parse_proposed_questions(
                parsed.get("questions_for_user"), self._role_name
            ),
        )

    async def novelty_filter(
        self,
        own: list[CandidateIdea],
        prior_art: PriorArtAgent,
    ) -> tuple[list[CandidateIdea], list[CandidateIdea]]:
        """Hunt duplicates of this ideator's own ideas: (survivors, dropped)."""
        return await run_novelty_filter(self._router, self._role_name, own, prior_art)

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
            system_prompt=REVISION_PROMPT,
            response_format=IDEA_REVISIONS_FORMAT,
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

    async def refine(
        self,
        own: list[CandidateIdea],
        answers_text: str,
        context: str,
        profile: ProfessionalProfile,
        *,
        allow_queries: bool,
        valid_keys: set[str],
    ) -> Refined[CandidateIdea]:
        """Revise and extend this ideator's own ideas from the user's answers; no search."""
        out = await request_refinement(
            self._router,
            role=self._role_name,
            system_prompt=IDEA_REFINE_PROMPT,
            response_format=IDEA_REFINE_FORMAT,
            response_key="ideas",
            new_key="new_ideas",
            own=own,
            answers_text=answers_text,
            context=context,
            profile=profile,
            allow_queries=False,
            valid_keys=valid_keys,
        )
        revised = [
            CandidateIdea(
                title=item["title"],
                description=item["description"],
                source_model=out.model_id,
                candidate_id=original.candidate_id,
                source_role=original.source_role,
            )
            for original, item in zip(own, out.items, strict=False)
        ] + own[len(out.items) :]
        added = [
            CandidateIdea(
                title=item["title"],
                description=item["description"],
                source_model=out.model_id,
                candidate_id=f"{self._role_name}-a{n}",
                source_role=self._role_name,
            )
            for n, item in enumerate(out.new_items, start=1)
        ]
        return Refined(revised=revised, added=added)
