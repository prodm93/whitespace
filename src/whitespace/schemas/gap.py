from pydantic import BaseModel, Field


class CandidateGap(BaseModel):
    title: str = Field(..., description="Short name for the candidate gap")
    description: str = Field(..., description="What the gap is and why it matters")
    source_model: str = Field(
        ..., description="Model ID that surfaced this gap (for provenance tracking)"
    )


class UnmetNeed(BaseModel):
    title: str = Field(..., description="Concise name for the unmet need")
    description: str = Field(..., description="Detailed explanation of the gap")
    current_state: str = Field(..., description="What existing patents/tech attempt")
    why_unmet: str = Field(..., description="Why current approaches fall short")
    matching_skills: list[str] = Field(
        default_factory=list,
        description="User skills relevant to this need",
    )
    provenance: list[str] = Field(
        default_factory=list,
        description="Graph paths and source references that surfaced this need",
    )
