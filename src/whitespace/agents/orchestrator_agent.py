"""Orchestrator agent — decides which analysis capabilities to run and when.

The top of the agentic system: receives the user's intent in natural
language and drives the pipeline through tools, instead of the API
calling fixed methods in a fixed order. Councils stay structured
ensembles internally; autonomy lives here and in their critics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from whitespace.agents._orchestrator_actions import AnalysisSession, OrchestratorActions
from whitespace.agents._tool_loop import run_tool_loop
from whitespace.models.router import ModelRouter
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal

logger = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 12

_SYSTEM_PROMPT = """\
You are the orchestrator of WhiteSpace, a patent whitespace analysis \
system. A user states an intent; you decide which capabilities to run, \
in what order, and when you are done. Always call get_status first.

The system's premise: a knowledge graph connects the user's own \
experience and background to the researched patent landscape, and the \
councils mine that connection for unmet needs and invention proposals.

Hard rules:
- Gap selection belongs to the HUMAN. If the intent needs gaps and none \
exist, run gap analysis and finish by presenting the gap titles for \
selection. Never choose gaps for the user; run_ideation only with \
selections the user's intent explicitly contains.
- run_gap_analysis is slow and costly: run it at most once per request, \
and only when the intent needs fresh analysis and the session lacks it.
- Questions about the domain, the graph, or prior results go to \
query_knowledge_graph, not to a fresh analysis run.
- If a prerequisite is missing (no profile, no domain), stop and say \
exactly what the user must provide.

Finish with a short plain-language summary of what you did and what \
the user should do next.\
"""


@dataclass
class OrchestratorResult:
    narrative: str
    needs: list[UnmetNeed]
    proposals: list[IdeationProposal]


class OrchestratorAgent:
    """Tool-driven supervisor over the analysis flow."""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    async def run(self, intent: str, actions: OrchestratorActions) -> OrchestratorResult:
        logger.info("OrchestratorAgent: intent=%r", intent[:120])
        narrative = await run_tool_loop(
            self._router,
            role="orchestrator",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"## USER INTENT\n\n{intent}",
            toolkit=actions,
            max_tool_calls=_MAX_TOOL_CALLS,
            temperature=0.2,
        )
        session = actions.session
        return OrchestratorResult(
            narrative=narrative,
            needs=session.needs,
            proposals=session.proposals,
        )


__all__ = ["AnalysisSession", "OrchestratorAgent", "OrchestratorResult"]
