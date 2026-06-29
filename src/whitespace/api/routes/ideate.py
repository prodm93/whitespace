import logging

from fastapi import APIRouter, Depends, Request

from whitespace.api.models import IdeateRequest, JobResponse
from whitespace.domain import JobStatus
from whitespace.middleware.auth import get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ideate", response_model=JobResponse)
async def trigger_ideation(
    body: IdeateRequest,
    request: Request,
    user=Depends(get_current_user),
    _usage=Depends(check_usage),
) -> JobResponse:
    """Enqueue ideation council on selected needs. Returns a job ID for polling."""
    logger.info(
        "Ideation requested by user=%s needs=%d",
        user.user_id,
        len(body.selected_needs),
    )
    queue: JobQueue = request.app.state.queue
    job_id = await queue.enqueue(
        "ideation",
        {"selected_needs": body.selected_needs},
    )
    return JobResponse(job_id=job_id, status=JobStatus.PENDING)
