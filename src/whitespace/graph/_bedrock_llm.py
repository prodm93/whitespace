"""Graphiti's language model on Bedrock, through the ``Converse`` operation."""

from __future__ import annotations

import json
import logging
from typing import Any

from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from graphiti_core.llm_client.errors import RateLimitError
from graphiti_core.prompts.models import Message
from pydantic import BaseModel

from whitespace.graph._bedrock_calls import call

logger = logging.getLogger(__name__)


class BedrockLLMClient(LLMClient):
    """Answers Graphiti's prompts with a Bedrock model.

    Structured output uses one forced tool whose input schema is the response model's JSON
    schema. With no response model, no tool is sent and the text of the answer is parsed as
    JSON. The output limit of every request is at most ``max_output_tokens``. A transient
    Bedrock error is raised as Graphiti's ``RateLimitError``, which Graphiti's own retry
    repeats; the schema in the prompt, the cleaning and that retry are the base class's.
    """

    def __init__(self, config: LLMConfig, client: Any, max_output_tokens: int) -> None:
        super().__init__(config, cache=False)
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "modelId": model or self._model_for(model_size),
            "system": [{"text": m.content} for m in messages if m.role == "system"],
            "messages": [
                {"role": m.role, "content": [{"text": m.content}]}
                for m in messages
                if m.role != "system"
            ],
            "inferenceConfig": {
                "temperature": self.temperature,
                "maxTokens": min(max_tokens, self._max_output_tokens),
            },
        }
        if response_model is not None:
            request["toolConfig"] = _forced_tool(response_model)
        try:
            response = await call(self._client.converse, **request)
        except ConnectionError as error:
            raise RateLimitError(str(error)) from error  # type: ignore[no-untyped-call]
        if response.get("stopReason") == "max_tokens":
            logger.warning("A Graphiti answer was cut at the output limit")
        return _answer(response)

    def _model_for(self, model_size: ModelSize) -> str | None:
        if model_size == ModelSize.small and self.small_model:
            return self.small_model
        return self.model


def _forced_tool(response_model: type[BaseModel]) -> dict[str, Any]:
    name = response_model.__name__
    spec = {"name": name, "inputSchema": {"json": response_model.model_json_schema()}}
    return {"tools": [{"toolSpec": spec}], "toolChoice": {"tool": {"name": name}}}


def _answer(response: dict[str, Any]) -> dict[str, Any]:
    """The input of the first tool block, or else the joined text parsed as JSON."""
    content = response["output"]["message"]["content"]
    for block in content:
        if "toolUse" in block:
            found: dict[str, Any] = block["toolUse"]["input"]
            return found
    text = "".join(block["text"] for block in content if "text" in block)
    parsed: dict[str, Any] = json.loads(text)
    return parsed
