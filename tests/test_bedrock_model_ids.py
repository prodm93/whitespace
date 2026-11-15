"""Model IDs that AWS lists, and the profile ID for models AWS serves only through a profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from whitespace.config import Config
from whitespace.models.providers import _OPENROUTER_MODEL_MAP, ProviderFactory
from whitespace.models.registry import ModelEntry, ModelPricing, ModelRegistry

_REGISTRY = Path(__file__).resolve().parents[1] / "model_registry.yaml"
_IDS_AWS_DOES_NOT_LIST = {
    "anthropic.claude-opus-4-6-20260219-v1:0",
    "gpt-5.4",
    "deepseek.deepseek-v3-2-v1:0",
    "amazon.nova-2-micro-v1:0",
}


def _entry(model_id: str) -> ModelEntry:
    return ModelEntry(
        model_id=model_id,
        provider="test",
        timeout_seconds=30,
        retries=0,
        pricing=ModelPricing(input_per_1m=0.0, output_per_1m=0.0),
    )


def _factory() -> ProviderFactory:
    return ProviderFactory(Config(_env_file=None, mode="saas"))


def _registry_ids() -> list[str]:
    registry = ModelRegistry(_REGISTRY)
    return [entry.model_id for role in registry.roles for entry in registry.get_chain(role)]


@pytest.mark.parametrize(
    ("model_id", "sent"),
    [
        ("anthropic.claude-opus-4-6-v1", "us.anthropic.claude-opus-4-6-v1"),
        ("anthropic.claude-opus-4-8", "us.anthropic.claude-opus-4-8"),
        ("anthropic.claude-sonnet-4-6", "us.anthropic.claude-sonnet-4-6"),
        ("openai.gpt-5.4", "us.openai.gpt-5.4"),
        ("amazon.nova-2-lite-v1:0", "us.amazon.nova-2-lite-v1:0"),
        ("zai.glm-5", "zai.glm-5"),
        ("deepseek.v3.2", "deepseek.v3.2"),
        ("amazon.nova-pro-v1:0", "amazon.nova-pro-v1:0"),
    ],
)
@pytest.mark.protects("bedrock-model-id-accepted")
def test_profile_only_models_get_the_us_profile_and_the_others_keep_their_id(
    model_id: str, sent: str
) -> None:
    assert _factory()._resolve_bedrock_model(_entry(model_id)) == sent


@pytest.mark.protects("bedrock-model-id-accepted")
async def test_a_saas_call_sends_the_profile_id_to_bedrock(monkeypatch: Any) -> None:
    import boto3

    class FakeClient:
        sent: dict[str, Any] = {}

        def converse(self, **kwargs: Any) -> dict[str, Any]:
            FakeClient.sent = kwargs
            return {"output": {"message": {"content": [{"text": "hi"}]}}, "usage": {}}

    monkeypatch.setattr(boto3, "client", lambda *_a, **_kw: FakeClient())

    await _factory().call(_entry("anthropic.claude-opus-4-8"), [], 0.0, None)

    assert FakeClient.sent["modelId"] == "us.anthropic.claude-opus-4-8"


def test_every_registry_model_has_an_openrouter_name() -> None:
    assert [model_id for model_id in _registry_ids() if model_id not in _OPENROUTER_MODEL_MAP] == []


def test_the_registry_uses_none_of_the_ids_that_aws_does_not_list() -> None:
    assert sorted(set(_registry_ids()) & _IDS_AWS_DOES_NOT_LIST) == []
