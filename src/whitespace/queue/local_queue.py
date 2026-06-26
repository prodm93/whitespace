import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from whitespace.domain import JobResult, JobStatus
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)

JobHandler = Callable[[str, dict], Coroutine[Any, Any, dict]]


class LocalAsyncQueue(JobQueue):
    """Runs jobs as asyncio background tasks. For BYOK Docker mode."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobResult] = {}
        self._handlers: dict[str, JobHandler] = {}

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def enqueue(self, job_type: str, payload: dict) -> str:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = JobResult(job_id=job_id, status=JobStatus.PENDING)

        handler = self._handlers.get(job_type)
        if handler is None:
            self._jobs[job_id] = JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error=f"No handler registered for job_type={job_type}",
            )
            return job_id

        asyncio.create_task(self._run_job(job_id, job_type, handler, payload))
        logger.info("LocalAsyncQueue: enqueued job_id=%s type=%s", job_id, job_type)
        return job_id

    async def get_status(self, job_id: str) -> JobResult:
        result = self._jobs.get(job_id)
        if result is None:
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error=f"Unknown job_id={job_id}",
            )
        return result

    async def _run_job(
        self,
        job_id: str,
        job_type: str,
        handler: JobHandler,
        payload: dict,
    ) -> None:
        self._jobs[job_id] = JobResult(job_id=job_id, status=JobStatus.RUNNING)
        try:
            result_data = await handler(job_id, payload)
            self._jobs[job_id] = JobResult(
                job_id=job_id, status=JobStatus.COMPLETED, result=result_data
            )
            logger.info("LocalAsyncQueue: job_id=%s completed", job_id)
        except Exception as exc:
            logger.error(
                "LocalAsyncQueue: job_id=%s type=%s failed: %s",
                job_id,
                job_type,
                exc,
            )
            self._jobs[job_id] = JobResult(job_id=job_id, status=JobStatus.FAILED, error=str(exc))
