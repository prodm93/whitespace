"""Storing the result of a council run in the session store."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.store.base import GapRun, IdeaRun, SessionStore


async def save_gap_result(
    store: SessionStore | None,
    run_id: str,
    domain: str,
    needs: list[UnmetNeed],
    discards: Sequence[dict[str, str]] = (),
) -> None:
    """Store a gap run's rejections, then the run itself when it found any need.

    This is the one place that stores the rejections of a gap council's
    second half. Both writes are safe to repeat for the same run.
    """
    if store is None:
        return
    if discards:
        await store.save_discards(run_id, "gap", list(discards))
    if needs:
        await store.save_gap_run(
            GapRun(
                run_id=run_id,
                timestamp=datetime.now(UTC),
                needs=needs,
                domain=domain.strip().lower(),
            )
        )


async def save_idea_result(
    store: SessionStore | None,
    run_id: str,
    gap_run_id: str,
    selected_need_titles: list[str],
    proposals: list[IdeationProposal],
    discards: Sequence[dict[str, str]],
) -> None:
    """Store an ideation run's discards, then the run itself when it produced proposals."""
    if store is None:
        return
    await store.save_discards(run_id, "idea", list(discards))
    if proposals:
        await store.save_idea_run(
            IdeaRun(
                run_id=run_id,
                gap_run_id=gap_run_id,
                selected_need_titles=selected_need_titles,
                timestamp=datetime.now(UTC),
                proposals=proposals,
            )
        )
