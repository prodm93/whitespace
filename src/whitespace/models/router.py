import logging
from typing import Any

from whitespace.models.providers import TRANSIENT_EXCEPTIONS, ProviderFactory
from whitespace.models.registry import ModelEntry, ModelRegistry
from whitespace.observability.cost_tracker import CostTracker
from whitespace.tools.retry import retry_async

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes LLM calls through fallback chains with retry and metrics."""

    def __init__(
        self,
        registry: ModelRegistry,
        provider_factory: ProviderFactory,
        cost_tracker: CostTracker,
    ) -> None:
        self._registry = registry
        self._provider_factory = provider_factory
        self._cost_tracker = cost_tracker

    async def call(
        self,
        *,
        role: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call the preferred model for *role*, falling back on failure.

        Returns a dict with keys: ``content``, ``model_id``,
        ``input_tokens``, ``output_tokens``.
        """
        chain = self._registry.get_chain(role)
        last_error: Exception | None = None
        for entry in chain:
            try:
                result = await self._try_model(entry, messages, temperature, response_format)
                await self._cost_tracker.record(entry, result)
                return result
            except Exception as exc:
                logger.warning(
                    "ModelRouter: %s failed for role=%s: %s",
                    entry.model_id,
                    role,
                    exc,
                )
                last_error = exc
        raise RuntimeError(f"All models in chain for role={role} failed") from last_error

    async def _try_model(
        self,
        entry: ModelEntry,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return await retry_async(
            self._provider_factory.call,
            entry,
            messages,
            temperature,
            response_format,
            retries=entry.retries,
            transient_exceptions=TRANSIENT_EXCEPTIONS,
        )
