from pydantic import BaseModel, Field

from whitespace.domain import JobStatus


class OrchestrateRequest(BaseModel):
    intent: str = Field(..., description="Natural-language statement of what the user wants")
    selected_titles: list[str] = Field(
        default_factory=list,
        description="Gap titles the user checked; present only when ideation is requested",
    )
    fresh_start: bool = Field(default=False, description="Bypass cross-run memory for this job")


class GapRequest(BaseModel):
    fresh_start: bool = Field(default=False, description="Bypass cross-run memory for this job")


class IdeateRequest(BaseModel):
    selected_needs: list[str] = Field(
        default_factory=list,
        description="Gap titles selected for ideation",
    )
    fresh_start: bool = Field(default=False, description="Bypass cross-run memory for this job")


class QueryRequest(BaseModel):
    query: str = Field(..., description="Question to ask the knowledge graph")


class QueryResponse(BaseModel):
    answer: str = Field(..., description="Knowledge graph answer")


class JobResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the async job")
    status: JobStatus = Field(..., description="Current job status")
