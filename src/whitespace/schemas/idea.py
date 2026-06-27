from pydantic import BaseModel, Field


class CandidateIdea(BaseModel):
    title: str = Field(..., description="Short name for the candidate idea")
    description: str = Field(
        ..., description="What the idea is and how it addresses the unmet need"
    )
    source_model: str = Field(..., description="Model ID that generated this idea")
    framing: str = Field(
        ...,
        description=(
            "Perspective: technical_feasibility, "
            "commercial_value, or cross_domain_transfer"
        )
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


class PriorArtResult(BaseModel):
    proposals: list[IdeationProposal] = Field(
        ...,
        description="Proposals with prior_art_notes populated where relevant",
    )
    prior_art_found: bool = Field(
        ...,
        description="Whether significant prior art was found for any proposal",
    )
