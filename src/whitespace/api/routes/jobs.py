import logging

from fastapi import APIRouter, Request

from whitespace.domain import JobResult
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResult)
async def get_job_status(job_id: str, request: Request) -> JobResult:
    """Poll async job status by ID."""
    queue: JobQueue = request.app.state.queue
    return await queue.get_status(job_id)
