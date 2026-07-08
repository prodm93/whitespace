import logging

from fastapi import APIRouter, Depends, Request

from whitespace.api.models import JobResponse, OrchestrateRequest
from whitespace.domain import JobStatus
from whitespace.middleware.auth import CurrentUser, get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/orchestrate", response_model=JobResponse)
async def trigger_orchestration(
    body: OrchestrateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    _usage: None = Depends(check_usage),
) -> JobResponse:
    """Submit a natural-language intent; the orchestrator decides what to run."""
    logger.info("Orchestration requested by user=%s", user.user_id)
    queue: JobQueue = request.app.state.queue
    job_id = await queue.enqueue("orchestrate", {"intent": body.intent})
    return JobResponse(job_id=job_id, status=JobStatus.PENDING)
