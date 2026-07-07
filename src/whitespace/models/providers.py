"""Provider client factory: Bedrock (SaaS) or OpenRouter (BYOK)."""

from __future__ import annotations

import logging
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from whitespace.config import Config
from whitespace.models.bedrock_provider import call_bedrock
from whitespace.models.openrouter_provider import call_openrouter
from whitespace.models.registry import ModelEntry

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_OPENROUTER_MODEL_MAP: dict[str, str] = {
    "anthropic.claude-opus-4-6-20260219-v1:0": "anthropic/claude-opus-4.6",
    "anthropic.claude-opus-4-8": "anthropic/claude-opus-4.8",
    "anthropic.claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "gpt-5.4": "openai/gpt-5.4",
    "deepseek.deepseek-v3-2-v1:0": "deepseek/deepseek-v3.2",
    "zai.glm-5": "z-ai/glm-5",
    "moonshot.kimi-k2-thinking": "moonshotai/kimi-k2-thinking",
    "mistral.mistral-large-3-675b-instruct": "mistralai/mistral-large-2512",
    "amazon.nova-2-micro-v1:0": "amazon/nova-micro-v1",
    "amazon.nova-2-lite-v1:0": "amazon/nova-2-lite-v1",
    "amazon.nova-pro-v1:0": "amazon/nova-pro-v1",
}

TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    TimeoutError,
    ConnectionError,
)


class ProviderFactory:
    """Constructs provider-specific LLM clients from Config."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._openrouter_client: AsyncOpenAI | None = None
        self._bedrock_client: object | None = None

    def _get_openrouter_client(self) -> AsyncOpenAI:
        if self._openrouter_client is None:
            self._openrouter_client = AsyncOpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self._config.openrouter_api_key,
            )
        return self._openrouter_client

    def _get_bedrock_client(self) -> Any:
        if self._bedrock_client is None:
            import boto3

            self._bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=self._config.aws_region,
            )
        return self._bedrock_client

    def _resolve_openrouter_model(self, entry: ModelEntry) -> str:
        mapped = _OPENROUTER_MODEL_MAP.get(entry.model_id)
        if mapped is not None:
            return mapped
        return f"{entry.provider}/{entry.model_id}"

    async def call(
        self,
        entry: ModelEntry,
        messages: list[dict[str, Any]],
        temperature: float,
        response_format: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> dict[str, Any]:
        if self._config.mode == "saas":
            return await call_bedrock(
                self._get_bedrock_client(),
                entry,
                messages,
                temperature,
                response_format,
                tools,
                tool_choice,
            )
        return await call_openrouter(
            self._get_openrouter_client(),
            self._resolve_openrouter_model(entry),
            entry,
            messages,
            temperature,
            response_format,
            tools,
            tool_choice,
        )
