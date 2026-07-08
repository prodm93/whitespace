import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from whitespace.middleware.auth import CurrentUser, get_current_user
from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/runs/latest")
async def latest_runs(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Rehydration endpoint: the latest gap run and its ideation runs.

    Lets the frontend restore results after a reload instead of
    re-running the pipeline.
    """
    store: SessionStore = request.app.state.store
    gap_run = await store.get_latest_gap_run()
    if gap_run is None:
        return {"gap_run": None, "idea_runs": []}
    idea_runs = await store.list_idea_runs(gap_run.run_id)
    return {
        "gap_run": gap_run.model_dump(),
        "idea_runs": [r.model_dump() for r in idea_runs],
    }
