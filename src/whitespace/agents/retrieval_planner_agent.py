"""Retrieval planner — picks a retrieval strategy per query using the playbook.

Single LLM call per query. Returns a :class:`RetrievalPlan` for the
context agent to dispatch on. Any failure (LLM error, malformed JSON,
unknown strategy) raises :class:`PlanningFailed`, which the caller treats
as the signal to fall back to the deterministic default path.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from whitespace.models.router import ModelRouter
from whitespace.schemas.retrieval_plan import RetrievalPlan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior patent-landscape retrieval specialist. Your single "
    "job is to route a user query to the right retrieval strategy given "
    "the playbook below.\n"
    "\n"
    "Reasoning protocol (silent — do NOT emit it):\n"
    "  1. Scan the query for a focal entity (a patent number, inventor, "
    "company, or specific technology — not a category).\n"
    "  2. Classify intent: gap/limitation analysis, skill matching, "
    "citation tracing, or entity lookup.\n"
    "  3. Check the anti-signals for your first-guess strategy; if any "
    "fire, reconsider.\n"
    "  4. Commit to one strategy.\n"
    "\n"
    "Output discipline: emit ONLY the JSON object specified at the end "
    "of the playbook. No prose, no markdown code fences, no "
    "explanation outside the JSON.\n"
    "\n"
    "`reason` field: one short sentence that references a SPECIFIC "
    "signal from the playbook (e.g. 'open-ended limitation query', "
    "'user references their expertise'). Do NOT restate the query. "
    "Do NOT summarise the playbook generically.\n"
    "\n"
    "If you are genuinely uncertain between two strategies, prefer "
    "`gap_analysis` — it is the safest general-purpose default for "
    "a patent-analysis system."
)


class PlanningFailed(RuntimeError):
    """Raised when the planner can't produce a usable :class:`RetrievalPlan`."""


class RetrievalPlannerAgent:
    """Routes a user query to a retrieval strategy via a single LLM call."""

    def __init__(self, router: ModelRouter, playbook: str) -> None:
        self._router = router
        self._playbook = playbook

    async def plan(self, query: str) -> RetrievalPlan:
        if not query.strip():
            raise PlanningFailed("empty query")

        user_msg = f"{self._playbook}\n\nUser query: {query}"

        try:
            result = await self._router.call(
                role="retrieval_planner",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise PlanningFailed(f"LLM call failed: {exc}") from exc

        content = result["content"]
        try:
            plan = RetrievalPlan.model_validate_json(content)
        except ValidationError as exc:
            raise PlanningFailed(f"plan JSON invalid: {exc}") from exc

        needs_entity = ("skill_matching", "citation_chain", "entity_focused")
        if plan.strategy in needs_entity and not (plan.params.entity_name or "").strip():
            raise PlanningFailed(f"{plan.strategy} chosen but entity_name missing")

        logger.info(
            "RetrievalPlannerAgent: chose %s — %s",
            plan.strategy,
            plan.reason or "(no reason given)",
        )
        return plan
