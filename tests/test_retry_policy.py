"""Tests for the one retry policy used across the codebase."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
from test_model_router import FakeCostTracker, FakeRegistry, make_entry

from whitespace.models.router import ModelRouter
from whitespace.tools.retry import transient_retry

_ROOT = Path(__file__).resolve().parents[1]


class _Flaky:
    """Raises ``error`` for the first ``failures`` calls, then returns ``"ok"``."""

    def __init__(self, error: Exception, failures: int) -> None:
        self.error = error
        self.failures = failures
        self.calls = 0

    async def __call__(self, value: str) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return value


@pytest.fixture()
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the requested waits instead of sleeping."""
    requested: list[float] = []

    async def _sleep(seconds: float) -> None:
        requested.append(seconds)

    monkeypatch.setattr("asyncio.sleep", _sleep)
    return requested


def _policy(attempts: int) -> Any:
    return transient_retry(
        attempts=attempts, first_wait=1.0, max_wait=30.0, retry_on=(ConnectionError,)
    )


async def test_transient_error_is_retried_until_the_call_succeeds(waits: list[float]) -> None:
    flaky = _Flaky(ConnectionError("dropped"), failures=2)

    assert await _policy(3)(flaky, "ok") == "ok"
    assert flaky.calls == 3
    assert waits == [1.0, 2.0]


async def test_last_transient_error_itself_comes_out_when_attempts_run_out(
    waits: list[float],
) -> None:
    error = ConnectionError("dropped")
    flaky = _Flaky(error, failures=5)

    with pytest.raises(ConnectionError) as raised:
        await _policy(2)(flaky, "ok")

    assert raised.value is error
    assert flaky.calls == 2


async def test_other_errors_are_not_retried(waits: list[float]) -> None:
    flaky = _Flaky(ValueError("bad input"), failures=5)

    with pytest.raises(ValueError):
        await _policy(3)(flaky, "ok")

    assert flaky.calls == 1
    assert waits == []


class _AlwaysTimesOut:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, entry: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(entry.model_id)
        if entry.model_id == "model-1":
            raise TimeoutError("slow")
        return {"content": "hi", "model_id": entry.model_id}


async def test_router_tries_a_model_retries_plus_one_times_then_the_next(
    waits: list[float],
) -> None:
    first = dataclasses.replace(make_entry("model-1"), retries=2)
    provider = _AlwaysTimesOut()
    router = ModelRouter(
        FakeRegistry([first, make_entry("model-2")]),  # type: ignore[arg-type]
        provider,  # type: ignore[arg-type]
        FakeCostTracker(),  # type: ignore[arg-type]
    )

    result = await router.call(role="any", messages=[])

    assert provider.calls == ["model-1", "model-1", "model-1", "model-2"]
    assert result["model_id"] == "model-2"


def test_no_source_file_uses_the_old_retry_helper() -> None:
    offenders = [
        str(path.relative_to(_ROOT))
        for folder in ("src", "deploy")
        for path in (_ROOT / folder).rglob("*.py")
        if "retry_async" in path.read_text()
    ]
    assert offenders == []


def _factory(mode: str) -> Any:
    from whitespace.config import Config
    from whitespace.models.providers import ProviderFactory

    return ProviderFactory(Config(_env_file=None, mode=mode))  # type: ignore[call-arg]


def test_openrouter_client_does_not_retry_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    from whitespace.models import providers

    made: list[dict[str, Any]] = []
    monkeypatch.setattr(providers, "AsyncOpenAI", lambda **kwargs: made.append(kwargs))

    _factory("byok")._get_openrouter_client()

    assert made[0]["max_retries"] == 0


def test_bedrock_client_does_not_retry_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[dict[str, Any]] = []
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: made.append(kwargs))

    _factory("saas")._get_bedrock_client()

    assert made[0]["config"].retries == {"total_max_attempts": 1}
