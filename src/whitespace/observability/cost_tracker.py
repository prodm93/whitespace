import logging
from typing import Any

from whitespace.models.registry import ModelEntry
from whitespace.observability.metrics import MetricsEmitter

logger = logging.getLogger(__name__)


class CostTracker:
    """Calculates estimated cost per LLM call and delegates to MetricsEmitter."""

    def __init__(self, emitter: MetricsEmitter) -> None:
        self._emitter = emitter

    async def record(self, entry: ModelEntry, result: dict[str, Any]) -> None:
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        input_cost = input_tokens * entry.pricing.input_per_1m / 1_000_000
        output_cost = output_tokens * entry.pricing.output_per_1m / 1_000_000
        estimated_cost = input_cost + output_cost

        dims = {"model_id": entry.model_id}

        await self._emitter.emit("tokens_consumed_input", float(input_tokens), dims)
        await self._emitter.emit("tokens_consumed_output", float(output_tokens), dims)
        await self._emitter.emit("estimated_cost_usd", estimated_cost, dims)
