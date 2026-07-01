import logging

from fastapi import APIRouter, Depends, Request

from whitespace.api.models import IngestRequest, JobResponse
from whitespace.domain import JobStatus
from whitespace.middleware.auth import CurrentUser, get_current_user
from whitespace.middleware.usage import check_usage
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest", response_model=JobResponse)
async def trigger_ingest(
    body: IngestRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    _usage: None = Depends(check_usage),
) -> JobResponse:
    """Enqueue domain ingestion (USPTO search + web search + optional docs)."""
    logger.info(
        "Ingest requested by user=%s keywords=%s",
        user.user_id,
        body.domain_keywords,
    )
    queue: JobQueue = request.app.state.queue
    job_id = await queue.enqueue(
        "ingest",
        {
            "domain_keywords": body.domain_keywords,
            "cpc_classes": body.cpc_classes,
        },
    )
    return JobResponse(job_id=job_id, status=JobStatus.PENDING)
