import logging
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from whitespace.config import Config
from whitespace.models.registry import ModelEntry

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_OPENROUTER_MODEL_MAP: dict[str, str] = {
    "anthropic.claude-opus-4-6-20260219-v1:0": "anthropic/claude-opus-4-6-20260219",
    "gpt-5.4": "openai/gpt-5.4",
    "deepseek.deepseek-v3-2-v1:0": "deepseek/deepseek-v3-2",
    "zai.glm-5": "zhipuai/glm-5",
    "moonshot.kimi-k2-thinking": "moonshotai/kimi-k2",
    "amazon.nova-2-micro-v1:0": "amazon/nova-micro-v1",
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

    def _get_openrouter_client(self) -> AsyncOpenAI:
        if self._openrouter_client is None:
            self._openrouter_client = AsyncOpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self._config.openrouter_api_key,
            )
        return self._openrouter_client

    def _resolve_openrouter_model(self, entry: ModelEntry) -> str:
        mapped = _OPENROUTER_MODEL_MAP.get(entry.model_id)
        if mapped is not None:
            return mapped
        return f"{entry.provider}/{entry.model_id}"

    async def call(
        self,
        entry: ModelEntry,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if self._config.mode == "saas":
            raise NotImplementedError("SaaS/Bedrock provider requires Phase 14b")
        return await self._call_openrouter(entry, messages, temperature, response_format)

    async def _call_openrouter(
        self,
        entry: ModelEntry,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        client = self._get_openrouter_client()
        model_id = self._resolve_openrouter_model(entry)

        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "timeout": entry.timeout_seconds,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        usage = response.usage

        return {
            "content": choice.message.content or "",
            "model_id": entry.model_id,
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }
