from pydantic import BaseModel, Field

from whitespace.domain import JobStatus


class QuestionAnswerIn(BaseModel):
    question_id: str
    answer: str | None = None
    skipped: bool = False


class OrchestrateRequest(BaseModel):
    intent: str = Field(..., description="Natural-language statement of what the user wants")
    selected_titles: list[str] = Field(
        default_factory=list,
        description="Gap titles the user checked; present only when ideation is requested",
    )
    fresh_start: bool = Field(default=False, description="Bypass cross-run memory for this job")
    question_answers: list[QuestionAnswerIn] | None = Field(
        default=None, description="The user's answers to a paused run; None means no submission"
    )
    ask_questions: bool | None = Field(
        default=None, description="The user's switch for questions; absent means on"
    )


class JobResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the async job")
    status: JobStatus = Field(..., description="Current job status")
