"""Raw research findings — dated, source-tagged, carried end to end."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RawFinding(BaseModel):
    """One search result from the research pass, preserved verbatim.

    Findings are dated at retrieval so the research base has a temporal
    dimension, and tagged with the query and surface that produced them
    for provenance.
    """

    title: str = Field(..., description="Result title")
    content: str = Field(..., description="Abstract, snippet, or extracted text")
    source_type: Literal["patent", "paper", "web"] = Field(
        ..., description="Which search surface produced this finding"
    )
    source_url: str | None = Field(default=None, description="Link to the source")
    source_name: str = Field(..., description="Patent number, paper title, or URL host")
    query: str = Field(..., description="The search query that surfaced this finding")
    published: str | None = Field(
        default=None, description="Publication date or year where the source provides one"
    )
    found_at: datetime = Field(
        default_factory=_utc_now,
        description="When this finding was retrieved",
    )
    domain: str | None = Field(
        default=None,
        description="Domain of the run that retrieved this finding",
    )
