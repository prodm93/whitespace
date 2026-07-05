from __future__ import annotations

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.store.base import GapRun, IdeaRun, SessionStore


class NoopSessionStore(SessionStore):
    """Placeholder for SaaS mode until DynamoDB implementation exists."""

    async def save_gap_run(self, run: GapRun) -> None:
        pass

    async def save_idea_run(self, run: IdeaRun) -> None:
        pass

    async def list_gap_runs(self) -> list[GapRun]:
        return []

    async def list_idea_runs(
        self,
        gap_run_id: str | None = None,
    ) -> list[IdeaRun]:
        return []

    async def get_gap_run(self, run_id: str) -> GapRun | None:
        return None

    async def get_idea_run(self, run_id: str) -> IdeaRun | None:
        return None

    async def get_all_previous_needs(self) -> list[UnmetNeed]:
        return []

    async def get_all_previous_proposals(self) -> list[IdeationProposal]:
        return []
