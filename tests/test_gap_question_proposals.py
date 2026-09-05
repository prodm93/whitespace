"""Tests for adaptive question proposals from gap identifiers."""

from __future__ import annotations

import json

import pytest
from _question_proposal_helpers import EmptyToolkit, FakeRouter, proposal

from whitespace.agents.council._gap_prompts import GAP_REVISIONS_FORMAT, GAPS_FORMAT
from whitespace.agents.council._question_proposals import (
    MAX_PROPOSED_QUESTIONS,
    parse_proposed_questions,
    resolve_question_candidate_ids,
)
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.config import Config
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion


def _gap(title: str, role: str, candidate_id: str) -> CandidateGap:
    return CandidateGap(
        title=title,
        description="Description",
        source_model="model",
        source_role=role,
        candidate_id=candidate_id,
    )


def test_gap_question_schema_requires_an_array_that_may_be_empty() -> None:
    schema = GAPS_FORMAT["json_schema"]["schema"]
    assert "questions_for_user" in schema["required"]
    assert schema["properties"]["questions_for_user"]["type"] == "array"
    assert "maxItems" not in schema["properties"]["questions_for_user"]


def test_gap_revision_schema_remains_candidate_only() -> None:
    schema = GAP_REVISIONS_FORMAT["json_schema"]["schema"]
    assert "questions_for_user" not in schema["properties"]
    assert "questions_for_user" not in schema["required"]


def test_parse_proposals_rejects_malformed_entries_and_caps_valid_ones() -> None:
    raw: list[object] = [None, {"purpose": "clarify"}, proposal(purpose="invalid")]
    raw.extend(proposal(question=f"Question {index}?") for index in range(7))
    parsed = parse_proposed_questions(raw, "gap_identifier_1")
    assert len(parsed) == MAX_PROPOSED_QUESTIONS
    assert [item.question for item in parsed] == [f"Question {index}?" for index in range(5)]
    assert {item.asker_role for item in parsed} == {"gap_identifier_1"}


def test_parse_clarify_proposal_discards_candidate_title() -> None:
    (parsed,) = parse_proposed_questions([proposal(purpose="clarify")], "gap_identifier_1")
    assert parsed.related_candidate_title == ""


def test_candidate_title_is_not_serialised_beyond_proposal_capture() -> None:
    (parsed,) = parse_proposed_questions([proposal()], "gap_identifier_1")
    assert "related_candidate_title" not in parsed.model_dump()


@pytest.mark.parametrize("raw", [None, {}, "malformed"])
def test_parse_proposals_treats_missing_or_malformed_collection_as_empty(raw: object) -> None:
    assert parse_proposed_questions(raw, "gap_identifier_1") == []


def test_resolve_candidate_ids_uses_exact_title_and_asker_role() -> None:
    proposals = [
        ProposedQuestion(**proposal(), asker_role="gap_identifier_1"),
        ProposedQuestion(
            **proposal(question="Same title, other agent?"),
            asker_role="gap_identifier_2",
        ),
        ProposedQuestion(
            **proposal(question="Unmatched?", title="Unknown gap"),
            asker_role="gap_identifier_1",
        ),
        ProposedQuestion(
            **proposal(question="Clarify?", purpose="clarify", title=""),
            asker_role="gap_identifier_1",
        ),
    ]
    candidates = [
        _gap("Adaptive kiln control", "gap_identifier_1", "gap_identifier_1-1"),
        _gap("Adaptive kiln control", "gap_identifier_2", "gap_identifier_2-1"),
    ]
    resolved = resolve_question_candidate_ids(proposals, candidates)
    assert [item.related_candidate_id for item in resolved] == [
        "gap_identifier_1-1",
        "gap_identifier_2-1",
        "",
        "",
    ]


@pytest.mark.asyncio
async def test_gap_identifier_captures_questions_without_model_supplied_role() -> None:
    conclusion = {
        "gaps": [
            {
                "title": "Adaptive kiln control",
                "description": "A supported gap.",
                "evidence": ["[F2]"],
            }
        ],
        "questions_for_user": [proposal()],
    }
    router = FakeRouter(
        [
            {"content": "Graph finding", "tool_calls": []},
            {"content": json.dumps(conclusion), "model_id": "model-a"},
        ]
    )
    identifier = GapIdentifier(
        Config(),
        router,  # type: ignore[arg-type]
        "gap_identifier_1",
        EmptyToolkit(),  # type: ignore[arg-type]
    )
    result = await identifier.run(ProfessionalProfile(), "[F2] Finding")
    assert len(result.gaps) == 1
    assert len(result.proposed_questions) == 1
    question = result.proposed_questions[0]
    assert question.asker_role == "gap_identifier_1"
    assert question.related_candidate_title == "Adaptive kiln control"
    assert router.calls[-1]["response_format"] == GAPS_FORMAT


@pytest.mark.asyncio
async def test_gap_identifier_accepts_legacy_output_without_questions() -> None:
    router = FakeRouter(
        [
            {"content": "Graph finding", "tool_calls": []},
            {"content": json.dumps({"gaps": []}), "model_id": "model-a"},
        ]
    )
    identifier = GapIdentifier(
        Config(),
        router,  # type: ignore[arg-type]
        "gap_identifier_1",
        EmptyToolkit(),  # type: ignore[arg-type]
    )
    result = await identifier.run(ProfessionalProfile(), "[F2] Finding")
    assert result.proposed_questions == []
