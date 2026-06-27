from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalisedDocument(BaseModel):
    title: str = Field(..., description="Document or patent title")
    content: str = Field(..., description="Full extracted text content")
    source_type: Literal["api", "web", "pdf"] = Field(
        ..., description="Origin modality: USPTO API, web crawl, or uploaded file"
    )
    source_url: str | None = Field(
        default=None,
        description="URL or file path the document was retrieved from",
    )
    source_name: str = Field(
        ..., description="Human-readable source identifier (e.g. patent number, filename)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific metadata (CPC classes, inventors, publication date, etc.)",
    )
