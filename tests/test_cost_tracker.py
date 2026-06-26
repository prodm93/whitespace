from whitespace.models.registry import ModelEntry, ModelPricing
from whitespace.observability.cost_tracker import CostTracker


class FakeEmitter:
    def __init__(self):
        self.events = []

    async def emit(self, metric, value, dims):
        self.events.append((metric, value, dims))


async def test_cost_tracker_calculates_estimated_cost():
    emitter = FakeEmitter()
    tracker = CostTracker(emitter)

    entry = ModelEntry(
        model_id="test-model",
        provider="openrouter",
        timeout_seconds=30,
        retries=1,
        pricing=ModelPricing(
            input_per_1m=1.0,
            output_per_1m=2.0,
        ),
    )

    result = {
        "input_tokens": 1000,
        "output_tokens": 500,
    }

    await tracker.record(entry, result)

    assert (
        "tokens_consumed_input",
        1000.0,
        {"model_id": "test-model"},
    ) in emitter.events

    assert (
        "tokens_consumed_output",
        500.0,
        {"model_id": "test-model"},
    ) in emitter.events

    expected_cost = (1000 * 1.0 / 1_000_000) + (500 * 2.0 / 1_000_000)

    assert (
        "estimated_cost_usd",
        expected_cost,
        {"model_id": "test-model"},
    ) in emitter.events
