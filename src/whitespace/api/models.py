from pydantic import BaseModel, Field

from whitespace.domain import JobStatus
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal


class ByokCredentials(BaseModel):
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    neo4j_uri: str = Field(..., description="Neo4j connection URI")
    neo4j_username: str = Field(..., description="Neo4j username")
    neo4j_password: str = Field(..., description="Neo4j password")
    neo4j_database: str = Field(..., description="Neo4j database name")


class IngestRequest(BaseModel):
    domain_keywords: list[str] = Field(
        ..., description="Keywords describing the patent domain to search"
    )
    cpc_classes: list[str] = Field(
        default_factory=list,
        description="CPC classification codes to filter USPTO results",
    )
    credentials: ByokCredentials | None = Field(
        default=None, description="BYOK credentials (omit in SaaS mode)"
    )


class ProfileUploadRequest(BaseModel):
    doc_paths: list[str] = Field(
        ..., description="Server-side paths to uploaded professional documents"
    )
    credentials: ByokCredentials | None = Field(
        default=None, description="BYOK credentials (omit in SaaS mode)"
    )


class GapRequest(BaseModel):
    credentials: ByokCredentials | None = Field(
        default=None, description="BYOK credentials (omit in SaaS mode)"
    )


class IdeateRequest(BaseModel):
    selected_needs: list[str] = Field(
        ..., description="Titles of UnmetNeed items the user selected for ideation"
    )
    credentials: ByokCredentials | None = Field(
        default=None, description="BYOK credentials (omit in SaaS mode)"
    )


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural-language question about the graph")
    credentials: ByokCredentials | None = Field(
        default=None, description="BYOK credentials (omit in SaaS mode)"
    )


class CredentialValidateRequest(BaseModel):
    credentials: ByokCredentials = Field(..., description="Credentials to validate")


class CredentialValidateResponse(BaseModel):
    openrouter_ok: bool = Field(..., description="Whether the OpenRouter API key is valid")
    neo4j_ok: bool = Field(..., description="Whether Neo4j connectivity succeeded")
    openrouter_error: str | None = Field(
        default=None, description="Error detail if OpenRouter validation failed"
    )
    neo4j_error: str | None = Field(
        default=None, description="Error detail if Neo4j validation failed"
    )


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
