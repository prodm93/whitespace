"""Graphiti's embedder on Bedrock, one ``invoke_model`` call for each text."""

from __future__ import annotations

import functools
import json
from collections.abc import Iterable
from typing import Any

from graphiti_core.embedder.client import EMBEDDING_DIM, EmbedderClient
from graphiti_core.helpers import semaphore_gather

from whitespace.graph._bedrock_calls import call_with_retry, invoke_model_json

DIMENSIONS = EMBEDDING_DIM
_BATCH_WIDTH = 8


class BedrockEmbedder(EmbedderClient):
    """Embeds texts with a Bedrock text embedding model that takes one text for each request.

    A text that is empty after stripping is not sent, since Bedrock refuses it; its vector
    is all zeros, which scores 0.0 against every other vector.
    """

    def __init__(self, client: Any, model_id: str) -> None:
        self._client = client
        self._model_id = model_id

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        """Return the vector of a text, or of the first text of a list of texts."""
        if isinstance(input_data, str):
            return await self._embed(input_data)
        if (
            isinstance(input_data, list)
            and input_data
            and all(isinstance(item, str) for item in input_data)
        ):
            return await self._embed(input_data[0])
        raise TypeError("BedrockEmbedder takes text only")

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """Return one vector for each text, in the order of the input."""
        if not input_data_list:
            return []
        return await semaphore_gather(
            *(self._embed(text) for text in input_data_list), max_coroutines=_BATCH_WIDTH
        )

    async def _embed(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * DIMENSIONS
        payload = await call_with_retry(
            functools.partial(invoke_model_json, self._client),
            modelId=self._model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True}),
        )
        return list(payload["embedding"])
