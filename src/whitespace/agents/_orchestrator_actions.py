"""Capabilities the orchestrator can invoke, exposed as tools.

Each action executes a pipeline stage and returns a compact summary —
full payloads stay in the session object, never in the model's context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

if TYPE_CHECKING:
    from whitespace.orchestration.pipeline import Pipeline

logger = logging.getLogger(__name__)


@dataclass
class AnalysisSession:
    """What the orchestrator knows and produces across one run."""

    profile: ProfessionalProfile | None = None
    domain: str = ""
    doc_paths: list[str] = field(default_factory=list)
    keep_findings: bool = False
    run_id: str = ""
    needs: list[UnmetNeed] = field(default_factory=list)
    selected_titles: list[str] = field(default_factory=list)
    proposals: list[IdeationProposal] = field(default_factory=list)


class OrchestratorActions:
    """Tool surface over the analysis pipeline."""

    def __init__(self, pipeline: Pipeline, session: AnalysisSession) -> None:
        self._pipeline = pipeline
        self._session = session

    @property
    def session(self) -> AnalysisSession:
        return self._session

    def tool_definitions(self) -> list[dict[str, Any]]:
        empty = {"type": "object", "properties": {}}
        return [
            {
                "name": "get_status",
                "description": (
                    "What the session currently holds: profile, staged domain "
                    "and documents, gap results, user selections, proposals. "
                    "Call this first."
                ),
                "parameters": empty,
            },
            {
                "name": "run_gap_analysis",
                "description": (
                    "Full gap analysis: researches the staged domain, builds "
                    "the knowledge graph from user documents plus research, "
                    "runs the gap council. Slow and costly; run once unless "
                    "the domain changed. Returns gap titles."
                ),
                "parameters": empty,
            },
            {
                "name": "run_ideation",
                "description": (
                    "Develop the user's SELECTED gaps into invention "
                    "proposals. Only valid for titles the user chose; never "
                    "select on their behalf."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selected_titles": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["selected_titles"],
                },
            },
            {
                "name": "query_knowledge_graph",
                "description": (
                    "Answer a question from the knowledge graph (the user's "
                    "background connected to the domain research)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
            },
        ]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "get_status":
            return self._status()
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
            f"domain: {s.domain or 'not staged'}\n"
            f"documents staged: {len(s.doc_paths)}\n"
            f"gap results: {[n.title for n in s.needs] or 'none yet'}\n"
            f"user-selected gaps: {s.selected_titles or 'none'}\n"
            f"proposals: {len(s.proposals)}"
        )

    async def _gap_analysis(self) -> str:
        s = self._session
        if s.profile is None:
            return "Cannot run: no profile. Ask the user to upload profile documents."
        if not s.domain:
            return "Cannot run: no domain staged. Ask the user to name a domain."
        s.needs = await self._pipeline.analyse_gaps(
            s.profile,
            s.domain,
            s.doc_paths,
            keep_findings=s.keep_findings,
            run_id=s.run_id or None,
        )
        titles = "; ".join(n.title for n in s.needs)
        return f"Gap analysis complete. {len(s.needs)} gaps found: {titles}"

    async def _ideation(self, selected_titles: list[str]) -> str:
        s = self._session
        if s.profile is None:
            return "Cannot run: no profile."
        if not s.needs:
            return "Cannot run: no gap results yet. Run gap analysis first."
        chosen = [n for n in s.needs if n.title in selected_titles]
        if not chosen:
            return "None of those titles match the gap results. Check get_status."
        s.proposals = await self._pipeline.ideate(chosen, s.profile)
        titles = "; ".join(p.title for p in s.proposals)
        return f"Ideation complete. {len(s.proposals)} proposals: {titles}"
