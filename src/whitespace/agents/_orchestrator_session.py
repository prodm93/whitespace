"""Session dataclass, write-through protocol, and result type for the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile


class _StateWriter(Protocol):
    """Structural protocol for write-through to the process-wide app state."""

    def set_profile(self, profile: ProfessionalProfile) -> None: ...

    def set_pending_ingest(
        self, domain: str, doc_paths: list[str], keep_findings: bool
    ) -> None: ...


@dataclass
class AnalysisSession:
    """What the orchestrator knows and produces across one job."""

    profile: ProfessionalProfile | None = None
    profile_paths: list[str] = field(default_factory=list)
    domain: str = ""
    doc_paths: list[str] = field(default_factory=list)
    keep_findings: bool = False
    run_id: str = ""
    gap_run_id: str = ""
    fresh_start: bool = False
    needs: list[UnmetNeed] = field(default_factory=list)
    user_selected_titles: list[str] = field(default_factory=list)
    proposals: list[IdeationProposal] = field(default_factory=list)
    blocked_reason: str | None = None


@dataclass
class OrchestratorResult:
    """Output of one orchestrator job."""

    status: str
    needs: list[UnmetNeed]
    proposals: list[IdeationProposal]
    reason: str | None = None
