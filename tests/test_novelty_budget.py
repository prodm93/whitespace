from __future__ import annotations

import json
from typing import Any, cast

from whitespace.agents.council._novelty import run_novelty_filter
from whitespace.schemas.idea import CandidateIdea


class _Router:
    def __init__(self, queries: list[str]) -> None:
        self.queries = queries

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["response_format"] == {"type": "json_object"}:
            return {"content": json.dumps({"queries": self.queries})}
        return {"content": json.dumps({"decisions": []})}


class _PriorArt:
    def __init__(self) -> None:
        self.received: list[list[str]] = []

    async def research(self, queries: list[str], per_query: int = 5) -> list[Any]:
        self.received.append(queries)
        return []


def _idea(candidate_id: str) -> CandidateIdea:
    return CandidateIdea(
        title=f"Idea {candidate_id}",
        description="A buildable sketch",
        source_model="m",
        candidate_id=candidate_id,
    )


async def test_novelty_queries_are_cut_to_two_for_each_idea() -> None:
    router = _Router([f"query {n}" for n in range(10)])
    prior_art = _PriorArt()

    survivors, dropped = await run_novelty_filter(
        cast(Any, router), "idea_ideator_1", [_idea("i-1"), _idea("i-2")], cast(Any, prior_art)
    )

    assert prior_art.received == [["query 0", "query 1", "query 2", "query 3"]]
    assert [i.candidate_id for i in survivors] == ["i-1", "i-2"]
    assert dropped == []
