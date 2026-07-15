"""Orchestrator agent -- decides which analysis capabilities to run and when.

The top of the agentic system: receives the user's intent in natural
language and drives the pipeline through tools, instead of the API
calling fixed methods in a fixed order. Councils stay structured
ensembles internally; autonomy lives here and in their critics.
"""

from __future__ import annotations

import logging

from whitespace.agents._orchestrator_actions import OrchestratorActions
from whitespace.agents._orchestrator_session import AnalysisSession, OrchestratorResult
from whitespace.agents._tool_loop import run_tool_loop
from whitespace.models.router import ModelRouter

logger = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 12

_SYSTEM_PROMPT = """\
You are the orchestrator of WhiteSpace, a patent whitespace analysis \
system. A user states an intent; you decide which capabilities to run, \
in what order, and when you are done. Always call get_status first.

The system's premise: a knowledge graph connects the user's own \
experience and background to the researched patent landscape; the \
councils mine that connection for unmet needs and invention proposals.

Tools:
  get_status          -- what the session holds now; call first.
  extract_profile     -- build a profile from staged profile documents;
                         required before any analysis if profile is MISSING.
  stage(domain, ...)  -- record the domain string and keep_findings flag;
                         required before run_gap_analysis if domain is
                         'not staged'.
  run_gap_analysis    -- research the domain, build the graph, run the gap
                         council. Slow and costly; call at most once per job.
  run_ideation(...)   -- develop the user's SELECTED gaps into proposals.
                         Only call with titles visible in get_status under
                         user-selected gaps. Never select gaps yourself.
  query_knowledge_graph(question) -- answer a question from the graph;
                         use for all queries, no new analysis run needed.

Hard rules:
- Gap selection belongs to the HUMAN. If gap analysis is complete, stop.
  Do not call run_ideation in the same request. run_ideation is only valid
  on a later request when user-selected gaps are present in get_status.
  Never choose gaps yourself.
- You must not call run_ideation unless user-selected gaps in get_status
  is non-empty; the tool enforces this.
- run_gap_analysis runs at most once per job; a second call returns the
  cached result.
- If a prerequisite is missing, stop and state exactly what is needed.
  Do not invent workarounds.
- Blocked outcomes surface as reason text in the result; do not repeat
  them in a narrative -- return only what the tools produce.\
"""


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
        if session.proposals:
            status = "done"
        elif session.blocked_reason:
            status = "blocked"
        elif session.needs:
            status = "awaiting_selection"
        else:
            status = "done"
        logger.info("OrchestratorAgent: finished status=%s narrative=%r", status, narrative[:200])
        return OrchestratorResult(
            status=status,
            needs=session.needs,
            proposals=session.proposals,
            reason=session.blocked_reason,
        )


__all__ = ["AnalysisSession", "OrchestratorAgent", "OrchestratorResult"]
