from abc import ABC, abstractmethod

from whitespace.domain import JobResult


class JobQueue(ABC):
    @abstractmethod
    async def enqueue(self, job_type: str, payload: dict) -> str:
        """Enqueue a job. Returns a job_id for polling."""
        ...

    @abstractmethod
    async def get_status(self, job_id: str) -> JobResult:
        """Poll job status by ID."""
        ...
