from pydantic import BaseModel, Field

from whitespace.domain import JobStatus
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal


class IngestRequest(BaseModel):
    domain_keywords: list[str] = Field(
        ..., description="Keywords describing the patent domain to search"
    )
    cpc_classes: list[str] = Field(
        default_factory=list,
        description="CPC classification codes to filter USPTO results",
    )


class ProfileUploadRequest(BaseModel):
    doc_paths: list[str] = Field(
        ..., description="Server-side paths to uploaded professional documents"
    )


class GapRequest(BaseModel):
    pass


class IdeateRequest(BaseModel):
    selected_needs: list[str] = Field(
        ..., description="Titles of UnmetNeed items the user selected for ideation"
    )


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural-language question about the graph")


class JobResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the async job")
    status: JobStatus = Field(..., description="Current job status")


class GapAnalysisResponse(BaseModel):
    needs: list[UnmetNeed] = Field(
        default_factory=list, description="Fleshed-out unmet needs with provenance"
    )


class IdeationResponse(BaseModel):
    proposals: list[IdeationProposal] = Field(
        default_factory=list, description="Full ideation proposals with provenance"
    )


class QueryResponse(BaseModel):
    answer: str = Field(..., description="Graph-grounded answer to the user's query")
