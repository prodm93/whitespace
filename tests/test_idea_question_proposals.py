"""Tests for adaptive question proposals from idea ideators."""

from __future__ import annotations

import json

import pytest
from _question_proposal_helpers import FakeRouter, proposal

from whitespace.agents.council._idea_prompts import IDEA_REVISIONS_FORMAT, IDEAS_FORMAT
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.config import Config
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.schemas.idea import CandidateIdea, IdeaExploration
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion


class StubIdeator:
    role_name = "idea_ideator_1"

    async def run(self, *args: object) -> IdeaExploration:
        return IdeaExploration(
            ideas=[
                CandidateIdea(
                    title="Adaptive kiln control",
                    description="A concrete idea.",
                    source_model="model-a",
                )
            ],
            proposed_questions=[
                ProposedQuestion(
                    **proposal(),
                    asker_role=self.role_name,
                )
            ],
        )


def test_idea_question_schema_requires_an_array_that_may_be_empty() -> None:
    schema = IDEAS_FORMAT["json_schema"]["schema"]
    assert "questions_for_user" in schema["required"]
    assert schema["properties"]["questions_for_user"]["type"] == "array"
    assert "maxItems" not in schema["properties"]["questions_for_user"]


def test_idea_revision_schema_remains_candidate_only() -> None:
    schema = IDEA_REVISIONS_FORMAT["json_schema"]["schema"]
    assert "questions_for_user" not in schema["properties"]
    assert "questions_for_user" not in schema["required"]


@pytest.mark.asyncio
async def test_ideation_graph_links_question_after_assigning_candidate_id() -> None:
    graph = IdeationCouncilGraph.__new__(IdeationCouncilGraph)
    ideator = StubIdeator()
    graph._ideators = {ideator.role_name: ideator}  # type: ignore[assignment]
    result = await graph._run_ideators(  # type: ignore[arg-type]
        {
            "selected_needs": [],
            "graph_context": "Graph context",
            "profile": ProfessionalProfile(),
        }
    )
    (candidate,) = result["candidates"]
    (question,) = result["proposed_questions"]
    assert candidate.candidate_id == "idea_ideator_1-1"
    assert question.related_candidate_id == candidate.candidate_id


@pytest.mark.asyncio
async def test_idea_ideator_captures_questions_without_model_supplied_role() -> None:
    response = {
        "ideas": [
            {
                "title": "Adaptive kiln control",
                "description": "A concrete idea.",
            }
        ],
        "questions_for_user": [proposal()],
    }
    router = FakeRouter([{"content": json.dumps(response), "model_id": "model-a"}])
    ideator = IdeaIdeator(
        Config(),
        router,  # type: ignore[arg-type]
        "idea_ideator_1",
    )
    result = await ideator.run([], "Graph context", ProfessionalProfile())
    assert len(result.ideas) == 1
    assert len(result.proposed_questions) == 1
    question = result.proposed_questions[0]
    assert question.asker_role == "idea_ideator_1"
    assert question.related_candidate_title == "Adaptive kiln control"
    assert router.calls[-1]["response_format"] == IDEAS_FORMAT


@pytest.mark.asyncio
async def test_idea_ideator_accepts_legacy_output_without_questions() -> None:
    router = FakeRouter([{"content": json.dumps({"ideas": []}), "model_id": "model-a"}])
    ideator = IdeaIdeator(
        Config(),
        router,  # type: ignore[arg-type]
        "idea_ideator_1",
    )
    result = await ideator.run([], "Graph context", ProfessionalProfile())
    assert result.proposed_questions == []
