"""Pipelines with fake councils, and the need and proposal they return, for question tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from _question_runs_helpers import NEED

from whitespace.orchestration.pipeline import Pipeline
from whitespace.schemas.gap import UnmetNeed


def _pipeline(question_runs: Any = None, store: Any = None) -> Pipeline:
    gap_council = MagicMock()
    gap_council.run = AsyncMock(return_value=([UnmetNeed.model_validate(NEED)], []))
    ideation_council = MagicMock()
    ideation_council.run = AsyncMock(return_value=([], []))
    context_agent = MagicMock()
    context_agent.run = AsyncMock(return_value="Graph context")
    return Pipeline(
        config=MagicMock(),
        neo4j=MagicMock(),
        graphiti=MagicMock(),
        context_agent=context_agent,
        profile_agent=MagicMock(),
        ingest_graph=MagicMock(),
        gap_council=gap_council,
        ideation_council=ideation_council,
        query_graph=MagicMock(),
        router=MagicMock(),
        dedup=MagicMock(),
        session_store=store,
        question_runs=question_runs,
    )


_PROPOSAL = {
    "title": "Acoustic monitor",
    "problem_statement": "p",
    "technical_approach": "t",
    "why_this_person": "w",
    "differentiation_from_prior_art": "d",
    "limitations": "l",
}
_NEEDS = [UnmetNeed.model_validate(NEED)]
