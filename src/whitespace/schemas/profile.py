from pydantic import BaseModel, Field


class ProjectSummary(BaseModel):
    name: str = Field(..., description="Project or engagement name")
    description: str = Field(..., description="What the project accomplished")
    technologies: list[str] = Field(
        default_factory=list,
        description="Technologies, frameworks, or tools used",
    )
    outcomes: list[str] = Field(
        default_factory=list,
        description="Key results, publications, or deliverables",
    )


class ProfessionalProfile(BaseModel):
    hard_skills: list[str] = Field(
        default_factory=list,
        description="Technical skills extracted from professional documents",
    )
    domain_knowledge: list[str] = Field(
        default_factory=list,
        description="Subject-matter domains the user has expertise in",
    )
    methodologies: list[str] = Field(
        default_factory=list,
        description="Research or engineering methodologies the user practises",
    )
    past_projects: list[ProjectSummary] = Field(
        default_factory=list,
        description="Structured summaries of notable past projects",
    )
    publication_topics: list[str] = Field(
        default_factory=list,
        description="Topics covered in the user's publications or patents",
    )
    years_experience: int | None = Field(
        default=None,
        description="Approximate years of professional experience, if determinable",
    )
