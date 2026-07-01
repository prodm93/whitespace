from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResult(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the async job")
    status: JobStatus = Field(..., description="Current job status")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Job output payload, present only when status is completed",
    )
    error: str | None = Field(
        default=None,
        description="Error message, present only when status is failed",
    )


class IngestResult(BaseModel):
    documents_processed: int = Field(..., description="Number of documents successfully ingested")
    documents_failed: int = Field(
        default=0, description="Number of documents that failed ingestion"
    )
    failed_files: list[str] = Field(
        default_factory=list,
        description="Basenames of documents that failed ingestion",
    )
    source_types: list[str] = Field(
        default_factory=list,
        description="Distinct source types ingested (api, web, pdf, etc.)",
    )


class CouncilOutcome(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Node:
    """A graph node returned to the agent layer."""

    id: str
    labels: tuple[str, ...] = ()
    name: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Edge:
    """A graph edge returned to the agent layer."""

    id: str
    edge_type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)
