import logging

from fastapi import APIRouter, Depends, Request

from whitespace.api.models import GapRequest, JobResponse
from whitespace.domain import JobStatus
from whitespace.middleware.auth import CurrentUser, get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/gaps", response_model=JobResponse)
async def trigger_gap_analysis(
    body: GapRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    _usage: None = Depends(check_usage),
) -> JobResponse:
    """Enqueue a gap analysis council run. Returns a job ID for polling."""
    logger.info("Gap analysis requested by user=%s", user.user_id)
    queue: JobQueue = request.app.state.queue
    job_id = await queue.enqueue("gap_analysis", {})
    return JobResponse(job_id=job_id, status=JobStatus.PENDING)
