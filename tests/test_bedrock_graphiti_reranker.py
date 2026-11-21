"""Graphiti's reranker on Bedrock: every passage comes back with a score, highest first."""

from __future__ import annotations

from typing import Any

import pytest
from _bedrock_fakes import StandInBedrock, client_error

from whitespace.graph._bedrock_reranker import BedrockReranker

_ARN = "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"


def _results(*scores: tuple[int, float], token: str | None = None) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "results": [{"index": index, "relevanceScore": score} for index, score in scores]
    }
    if token is not None:
        answer["nextToken"] = token
    return answer


def _sent(kwargs: dict[str, Any]) -> list[str]:
    return [source["inlineDocumentSource"]["textDocument"]["text"] for source in kwargs["sources"]]


async def test_three_passages_make_one_call_and_come_back_highest_first() -> None:
    client = StandInBedrock(_results((2, 0.9), (0, 0.5), (1, 0.1)))

    ranked = await BedrockReranker(client, _ARN).rank("hot battery", ["a", "b", "c"])

    assert ranked == [("c", 0.9), ("a", 0.5), ("b", 0.1)]
    assert len(client.calls) == 1
    operation, kwargs = client.calls[0]
    assert operation == "rerank"
    assert kwargs["queries"] == [{"type": "TEXT", "textQuery": {"text": "hot battery"}}]
    assert kwargs["sources"][0] == {
        "type": "INLINE",
        "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": "a"}},
    }
    assert _sent(kwargs) == ["a", "b", "c"]
    assert kwargs["rerankingConfiguration"] == {
        "type": "BEDROCK_RERANKING_MODEL",
        "bedrockRerankingConfiguration": {
            "modelConfiguration": {"modelArn": _ARN},
            "numberOfResults": 3,
        },
    }
    assert "nextToken" not in kwargs


async def test_an_answer_in_two_pages_is_read_in_full() -> None:
    client = StandInBedrock(_results((1, 0.8), token="page-2"), _results((0, 0.3)))

    ranked = await BedrockReranker(client, _ARN).rank("q", ["a", "b"])

    assert ranked == [("b", 0.8), ("a", 0.3)]
    assert len(client.calls) == 2
    assert client.calls[1][1]["nextToken"] == "page-2"


async def test_more_pages_than_passages_stop_the_reading(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = StandInBedrock(_results((0, 0.5), token="again"))

    ranked = await BedrockReranker(client, _ARN).rank("q", ["a", "b"])

    assert ranked == [("a", 0.5), ("b", 0.0)]
    assert len(client.calls) == 2
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


async def test_a_passage_no_result_names_scores_zero() -> None:
    client = StandInBedrock(_results((0, 0.7), (2, 0.2)))

    ranked = await BedrockReranker(client, _ARN).rank("q", ["a", "b", "c"])

    assert ranked == [("a", 0.7), ("c", 0.2), ("b", 0.0)]


async def test_no_passages_make_no_call() -> None:
    client = StandInBedrock(_results())

    assert await BedrockReranker(client, _ARN).rank("q", []) == []
    assert client.calls == []


async def test_an_empty_query_makes_no_call_and_every_passage_scores_zero() -> None:
    client = StandInBedrock(_results())

    ranked = await BedrockReranker(client, _ARN).rank("", ["a", "b"])

    assert ranked == [("a", 0.0), ("b", 0.0)]
    assert client.calls == []


async def test_empty_passages_are_not_sent_and_score_zero() -> None:
    client = StandInBedrock(_results((1, 0.6), (0, 0.4)))

    ranked = await BedrockReranker(client, _ARN).rank("q", ["a", "", "b"])

    assert ranked == [("b", 0.6), ("a", 0.4), ("", 0.0)]
    assert _sent(client.calls[0][1]) == ["a", "b"]
    assert (
        client.calls[0][1]["rerankingConfiguration"]["bedrockRerankingConfiguration"][
            "numberOfResults"
        ]
        == 2
    )


async def test_only_empty_passages_make_no_call() -> None:
    client = StandInBedrock(_results())

    assert await BedrockReranker(client, _ARN).rank("q", ["", ""]) == [("", 0.0), ("", 0.0)]
    assert client.calls == []


async def test_access_denied_comes_out_unchanged_after_one_call() -> None:
    error = client_error("AccessDeniedException", "Rerank")
    client = StandInBedrock(error)

    with pytest.raises(type(error)) as raised:
        await BedrockReranker(client, _ARN).rank("q", ["a"])

    assert raised.value is error
    assert len(client.calls) == 1
