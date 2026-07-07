import pytest

from whitespace.models.registry import (
    ModelEntry,
    ModelPricing,
)
from whitespace.models.router import ModelRouter


class FakeRegistry:
    def __init__(self, chain):
        self.chain = chain

    def get_chain(self, role):
        return self.chain


class FakeCostTracker:
    def __init__(self):
        self.calls = []

    async def record(self, entry, result):
        self.calls.append((entry, result))


class FakeProviderFactory:
    def __init__(self, responses):
        self.responses = responses
        self.index = 0

    async def call(
        self,
        entry,
        messages,
        temperature,
        response_format,
        tools=None,
        tool_choice=None,
    ):
        response = self.responses[self.index]
        self.index += 1

        if isinstance(response, Exception):
            raise response

        return response


def make_entry(model_id):
    return ModelEntry(
        model_id=model_id,
        provider="openrouter",
        timeout_seconds=30,
        retries=0,
        pricing=ModelPricing(
            input_per_1m=1.0,
            output_per_1m=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_router_falls_back_to_second_model():
    first = make_entry("model-1")
    second = make_entry("model-2")

    provider = FakeProviderFactory(
        [
            RuntimeError("boom"),
            {
                "content": "hello",
                "model_id": "model-2",
                "input_tokens": 1,
                "output_tokens": 1,
            },
        ]
    )

    cost_tracker = FakeCostTracker()

    router = ModelRouter(
        FakeRegistry([first, second]),
        provider,
        cost_tracker,
    )

    result = await router.call(
        role="test",
        messages=[],
    )

    assert result["model_id"] == "model-2"
    assert len(cost_tracker.calls) == 1


@pytest.mark.asyncio
async def test_router_raises_when_all_models_fail():
    first = make_entry("model-1")
    second = make_entry("model-2")

    provider = FakeProviderFactory(
        [
            RuntimeError("boom"),
            RuntimeError("still broken"),
        ]
    )

    router = ModelRouter(
        FakeRegistry([first, second]),
        provider,
        FakeCostTracker(),
    )

    with pytest.raises(RuntimeError):
        await router.call(
            role="test",
            messages=[],
        )


@pytest.mark.asyncio
async def test_router_records_cost_on_success():
    entry = make_entry("model-1")

    result = {
        "content": "hello",
        "model_id": "model-1",
        "input_tokens": 10,
        "output_tokens": 20,
    }

    provider = FakeProviderFactory([result])
    cost_tracker = FakeCostTracker()

    router = ModelRouter(
        FakeRegistry([entry]),
        provider,
        cost_tracker,
    )

    await router.call(
        role="test",
        messages=[],
    )

    assert cost_tracker.calls == [
        (
            entry,
            result,
        )
    ]
