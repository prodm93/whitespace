"""Graphiti's reranker on Bedrock, through the ``Rerank`` operation."""

from __future__ import annotations

import logging
from typing import Any

from graphiti_core.cross_encoder.client import CrossEncoderClient

from whitespace.graph._bedrock_calls import call_with_retry

logger = logging.getLogger(__name__)


class BedrockReranker(CrossEncoderClient):
    """Scores passages against a query with a Bedrock reranking model.

    Every passage of the input is in the answer, highest score first. Rerank refuses an
    empty text, so an empty query or passage is not sent: an empty query gives every
    passage 0.0, and an empty passage scores 0.0. A passage that no result names also
    scores 0.0.
    """

    def __init__(self, client: Any, model_arn: str) -> None:
        self._client = client
        self._model_arn = model_arn

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        scores = [0.0] * len(passages)
        sent = [index for index, passage in enumerate(passages) if passage]
        if query and sent:
            for result in await self._results(query, [passages[index] for index in sent]):
                scores[sent[result["index"]]] = float(result["relevanceScore"])
        ranked = list(zip(passages, scores, strict=True))
        return sorted(ranked, key=lambda pair: pair[1], reverse=True)

    async def _results(self, query: str, texts: list[str]) -> list[dict[str, Any]]:
        request: dict[str, Any] = {
            "queries": [{"type": "TEXT", "textQuery": {"text": query}}],
            "sources": [
                {
                    "type": "INLINE",
                    "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": text}},
                }
                for text in texts
            ],
            "rerankingConfiguration": {
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": self._model_arn},
                    "numberOfResults": len(texts),
                },
            },
        }
        results: list[dict[str, Any]] = []
        for _ in range(len(texts)):
            answer = await call_with_retry(self._client.rerank, **request)
            results.extend(answer.get("results", []))
            token = answer.get("nextToken")
            if not token:
                return results
            request["nextToken"] = token
        logger.warning("Rerank gave more pages than passages; the rest is not read")
        return results
