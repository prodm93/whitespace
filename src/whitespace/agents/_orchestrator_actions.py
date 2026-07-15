"""Capabilities the orchestrator can invoke, exposed as tools.

Each action executes a pipeline stage and returns a compact summary;
full payloads stay in the session object, never in the model's context.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from whitespace.agents._orchestrator_session import AnalysisSession
from whitespace.agents._orchestrator_tool_defs import TOOL_DEFINITIONS

if TYPE_CHECKING:
    from whitespace.agents._orchestrator_session import _StateWriter
    from whitespace.orchestration.pipeline import Pipeline

logger = logging.getLogger(__name__)


class OrchestratorActions:
    """Tool surface over the analysis pipeline."""

    def __init__(
        self,
        pipeline: Pipeline,
        session: AnalysisSession,
        state_writer: _StateWriter | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._session = session
        self._state_writer = state_writer
        self._gap_analysis_ran = False

    @property
    def session(self) -> AnalysisSession:
        return self._session

    def tool_definitions(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "get_status":
            return self._status()
        if name == "extract_profile":
            return await self._extract_profile()
        if name == "stage":
            return await self._stage(
                str(arguments.get("domain", "")),
                bool(arguments.get("keep_findings", False)),
            )
        if name == "run_gap_analysis":
            return await self._gap_analysis()
        if name == "run_ideation":
            return await self._ideation(list(arguments.get("selected_titles", [])))
        if name == "query_knowledge_graph":
            question = str(arguments.get("question", ""))
            return await self._pipeline.query(question) if question else "No question given."
        return f"Unknown tool: {name}"

    def _status(self) -> str:
        s = self._session
        return (
            f"profile: {'ready' if s.profile else 'MISSING'}\n"
            f"profile paths staged: {len(s.profile_paths)}\n"
            f"domain: {s.domain or 'not staged'}\n"
            f"keep_findings: {s.keep_findings}\n"
            f"domain docs staged: {len(s.doc_paths)}\n"
            f"gap results: {[n.title for n in s.needs] or 'none yet'}\n"
            f"user-selected gaps: {s.user_selected_titles or 'none'}\n"
            f"proposals: {len(s.proposals)}"
        )

    async def _extract_profile(self) -> str:
        s = self._session
        if not s.profile_paths:
            msg = "No profile paths staged. Upload profile documents via /api/ingest first."
            s.blocked_reason = msg
            return msg
        s.profile = await self._pipeline.extract_profile(s.profile_paths)
        if self._state_writer is not None:
            self._state_writer.set_profile(s.profile)
        s.blocked_reason = None
        skills = len(s.profile.hard_skills)
        domains = len(s.profile.domain_knowledge)
        return f"Profile extracted: {skills} hard skills, {domains} domain areas."

    async def _stage(self, domain: str, keep_findings: bool) -> str:
        if not domain:
            return "domain is required. Provide a patent domain string."
        s = self._session
        s.domain = domain
        s.keep_findings = keep_findings
        if self._state_writer is not None:
            self._state_writer.set_pending_ingest(domain, s.doc_paths, keep_findings)
        s.blocked_reason = None
        return f"Staged: domain={domain!r}, keep_findings={keep_findings}."

    async def _gap_analysis(self) -> str:
        s = self._session
        if self._gap_analysis_ran:
            titles = "; ".join(n.title for n in s.needs)
            return f"Gap analysis already ran this job. {len(s.needs)} gaps: {titles}"
        if s.profile is None:
            msg = "Cannot run: no profile. Call extract_profile first."
            s.blocked_reason = msg
            return msg
        if not s.domain:
            msg = "Cannot run: no domain. Call stage(domain=...) first."
            s.blocked_reason = msg
            return msg
        self._gap_analysis_ran = True
        s.needs = await self._pipeline.analyse_gaps(
            s.profile,
            s.domain,
            s.doc_paths,
            keep_findings=s.keep_findings,
            run_id=s.run_id or None,
            fresh_start=s.fresh_start,
        )
        s.blocked_reason = None
        titles = "; ".join(n.title for n in s.needs)
        return f"Gap analysis complete. {len(s.needs)} gaps found: {titles}"

    async def _ideation(self, selected_titles: list[str]) -> str:
        s = self._session
        if not s.user_selected_titles:
            return (
                "Cannot run: gap selection must come from the user's confirmed "
                "checkbox state, not from this tool. No sidecar was provided."
            )
        allowed = set(s.user_selected_titles)
        requested = [t for t in selected_titles if t in allowed]
        if not requested:
            return (
                f"None of the requested titles are in the user's confirmed "
                f"selection {sorted(allowed)}. Check get_status."
            )
        if s.profile is None:
            msg = "Cannot run: no profile."
            s.blocked_reason = msg
            return msg
        if not s.needs:
            msg = "Cannot run: no gap results yet. Run gap analysis first."
            s.blocked_reason = msg
            return msg
        chosen = [n for n in s.needs if n.title in set(requested)]
        if not chosen:
            return "None of the allowed titles match the gap results. Check get_status."
        s.proposals = await self._pipeline.ideate(
            chosen,
            s.profile,
            gap_run_id=s.gap_run_id,
            fresh_start=s.fresh_start,
        )
        s.blocked_reason = None
        titles = "; ".join(p.title for p in s.proposals)
        return f"Ideation complete. {len(s.proposals)} proposals: {titles}"
