from pydantic import BaseModel, Field


class CandidateGap(BaseModel):
    title: str = Field(..., description="Short name for the candidate gap")
    description: str = Field(..., description="What the gap is and why it matters")
    source_model: str = Field(
        ..., description="Model ID that surfaced this gap (for provenance tracking)"
    )
    candidate_id: str = Field(
        default="", description="Stable ID assigned by the council for critic referencing"
    )
    source_role: str = Field(
        default="", description="Registry role of the identifier that produced this gap"
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
    scores: dict[str, int] = Field(
        default_factory=dict,
        description="Critic scores (1-10 per criterion) from council review",
    )
    contributing_models: list[str] = Field(
        default_factory=list,
        description="Model IDs whose candidates contributed to this need",
    )
    critique_notes: str | None = Field(
        default=None,
        description="Critic objections or caveats retained for provenance",
    )
