from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding


class GapRun(BaseModel):
    run_id: str = Field(..., description="Unique identifier for this gap analysis run")
    timestamp: datetime = Field(..., description="When the run completed")
    needs: list[UnmetNeed] = Field(default_factory=list)
    domain: str | None = Field(default=None, description="Normalised domain string for this run")


class IdeaRun(BaseModel):
    run_id: str = Field(..., description="Unique identifier for this ideation run")
    gap_run_id: str = Field(..., description="The gap run these ideas were generated from")
    selected_need_titles: list[str] = Field(
        default_factory=list,
        description="Titles of the needs the user selected for ideation",
    )
    timestamp: datetime = Field(..., description="When the run completed")
    proposals: list[IdeationProposal] = Field(default_factory=list)


class SessionStore(ABC):
    @abstractmethod
    async def save_gap_run(self, run: GapRun) -> None: ...

    @abstractmethod
    async def save_idea_run(self, run: IdeaRun) -> None: ...

    @abstractmethod
    async def list_gap_runs(self) -> list[GapRun]: ...

    @abstractmethod
    async def list_idea_runs(
        self,
        gap_run_id: str | None = None,
    ) -> list[IdeaRun]: ...

    @abstractmethod
    async def get_gap_run(self, run_id: str) -> GapRun | None: ...

    @abstractmethod
    async def get_idea_run(self, run_id: str) -> IdeaRun | None: ...

    @abstractmethod
    async def get_all_previous_needs(self) -> list[UnmetNeed]: ...

    @abstractmethod
    async def get_all_previous_proposals(self) -> list[IdeationProposal]: ...

    async def save_raw_findings(self, run_id: str, findings: list[RawFinding]) -> None:
        """Persist dated research findings. Default: no-op (opt-in feature)."""
        return None

    async def list_raw_findings(self, run_id: str | None = None) -> list[RawFinding]:
        """Return stored findings, newest first. Default: none."""
        return []

    async def get_latest_gap_run(self) -> GapRun | None:
        """Most recent gap run, for selection resolution and rerun memory."""
        runs = await self.list_gap_runs()
        return runs[0] if runs else None

    async def save_discards(self, run_id: str, kind: str, items: list[dict[str, str]]) -> None:
        """Persist candidates discarded for grounded reasons (critic kills,
        novelty duplicates) so reruns never resurrect them. Default: no-op."""
        return None

    async def list_discards(self, kind: str | None = None) -> list[dict[str, str]]:
        """Return discarded candidates ({title, description, reason, kind, domain})."""
        return []
