from pydantic import BaseModel, Field


class CandidateIdea(BaseModel):
    title: str = Field(..., description="Short name for the candidate idea")
    description: str = Field(
        ..., description="What the idea is and how it addresses the unmet need"
    )
    source_model: str = Field(..., description="Model ID that generated this idea")
    candidate_id: str = Field(
        default="", description="Stable ID assigned by the council for critic referencing"
    )
    source_role: str = Field(
        default="", description="Registry role of the ideator that produced this idea"
    )


class IdeationProposal(BaseModel):
    title: str = Field(..., description="Concise title for the proposed idea")
    problem_statement: str = Field(
        ..., description="The unmet need this idea addresses and why it matters"
    )
    technical_approach: str = Field(..., description="How the idea works at a technical level")
    why_this_person: str = Field(
        ..., description="Why the user's profile positions them to pursue this"
    )
    differentiation_from_prior_art: str = Field(
        ..., description="How this idea differs from existing patents and solutions"
    )
    limitations: str = Field(..., description="Known limitations, risks, or open questions")
    provenance: list[str] = Field(
        default_factory=list,
        description="Graph paths tracing how the system arrived at this idea",
    )
    prior_art_notes: str | None = Field(
        default=None,
        description="Similar prior art found during novelty validation, if any",
    )
    scores: dict[str, int] = Field(
        default_factory=dict,
        description="Critic scores (1-10 per criterion) from council review",
    )
    contributing_models: list[str] = Field(
        default_factory=list,
        description="Model IDs whose candidates contributed to this proposal",
    )
    critique_notes: str | None = Field(
        default=None,
        description="Critic objections or caveats retained for provenance",
    )
