"""Each run of the pipeline function takes its secrets from the loader, also after a change."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from _loop_helpers import Stubborn, tick
from _runtime_helpers import FakeShared, record_waits, use_factory, use_recorder
from neo4j.exceptions import AuthError, ServiceUnavailable

from whitespace.config import Config


def _config(password: str = "password-one") -> Config:
    return Config(
        _env_file=None,
        mode="saas",
        neo4j_uri="neo4j+s://graph.example.test",
        neo4j_username="neo4j",
        neo4j_password=password,
    )


def use_loader(monkeypatch: pytest.MonkeyPatch, runtime: Any, *results: Any) -> list[int]:
    """Make each run load the next result in turn; the last one repeats. Returns the calls."""
    calls: list[int] = []
    queue = list(results)

    async def load() -> Config:
        calls.append(len(calls))
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(runtime, "load_config", load)
    return calls


def _open(runtime: Any, tenant: str = "user_a") -> None:
    runtime.run(runtime.open_run(tenant))


@pytest.mark.protects("saas-secrets-loaded")
def test_the_kept_clients_and_the_run_use_the_loaded_config(
    monkeypatch: pytest.MonkeyPatch, runtime: Any
) -> None:
    loaded = _config()
    use_loader(monkeypatch, runtime, loaded)
    built_from: list[Config] = []
    monkeypatch.setattr(
        runtime, "build_shared", lambda config: built_from.append(config) or FakeShared()
    )
    recorder = use_recorder(monkeypatch, runtime)

    _open(runtime)

    assert built_from == [loaded]
    run_config = recorder.calls[0][1]
    assert run_config.graphiti_namespace == "user_a"
    assert run_config.neo4j_password == "password-one"


def test_a_secrets_error_leaves_no_run_open(monkeypatch: pytest.MonkeyPatch, runtime: Any) -> None:
    from _settings import SecretsError

    failure = SecretsError()
    use_loader(monkeypatch, runtime, failure)
    factory = use_factory(monkeypatch, runtime)

    with pytest.raises(SecretsError) as raised:
        _open(runtime)

    assert raised.value is failure
    assert factory.built == []
    with pytest.raises(RuntimeError):
        runtime.get_pipeline()


def test_the_run_reopened_after_a_retirement_uses_the_same_loader(
    monkeypatch: pytest.MonkeyPatch, runtime: Any
) -> None:
    import _teardown

    monkeypatch.setattr(_teardown, "CANCEL_WAIT", 0.05)
    calls = use_loader(monkeypatch, runtime, _config(), _config("password-two"))
    recorder = use_recorder(monkeypatch, runtime)
    _open(runtime)
    work = Stubborn()

    async def leave_work() -> None:
        asyncio.ensure_future(work.run())
        await tick()

    runtime.run(leave_work())
    assert runtime._run is None

    async def owner() -> str:
        result: str = runtime.current_owner()
        return result

    assert runtime.run(owner()) == "user_a"
    assert calls == [0, 1]
    assert recorder.calls[-1][1].neo4j_password == "password-two"


@pytest.mark.protects("saas-secrets-loaded")
def test_a_changed_secret_rebuilds_the_kept_clients_once(
    monkeypatch: pytest.MonkeyPatch, runtime: Any
) -> None:
    first, changed = _config(), _config("password-two")
    use_loader(monkeypatch, runtime, first, first, changed, changed)
    factory = use_factory(monkeypatch, runtime)
    recorder = use_recorder(monkeypatch, runtime)

    for _ in range(4):
        _open(runtime)
        runtime.finish_run()

    assert len(factory.built) == 2
    assert factory.built[0].calls[-1] == "close"
    assert "close" not in factory.built[1].calls
    assert [call[0] for call in recorder.calls] == [factory.built[0]] * 2 + [factory.built[1]] * 2


def test_a_rebuild_that_cannot_connect_is_tried_again_and_leaves_no_half_built_set(
    monkeypatch: pytest.MonkeyPatch, runtime: Any
) -> None:
    record_waits(monkeypatch)
    use_loader(monkeypatch, runtime, _config(), _config("password-two"))
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: FakeShared(initialise_error=ServiceUnavailable()) if n == 1 else FakeShared(),
    )
    _open(runtime)
    runtime.finish_run()

    _open(runtime)

    assert len(factory.built) == 3
    assert factory.built[0].calls[-1] == "close"
    assert factory.built[1].calls[-1] == "close"
    assert runtime._shared is factory.built[2]


@pytest.mark.protects("secret-values-not-logged")
def test_a_wrong_neo4j_login_shows_the_configuration_sentence(
    monkeypatch: pytest.MonkeyPatch, runtime: Any, caplog: pytest.LogCaptureFixture
) -> None:
    from _settings import USER_MESSAGE, SecretsError

    use_loader(monkeypatch, runtime, _config())
    refusal = AuthError("server-text-QWXZ")
    factory = use_factory(monkeypatch, runtime, lambda _n: FakeShared(initialise_error=refusal))

    with pytest.raises(SecretsError) as raised:
        _open(runtime)

    assert str(raised.value) == USER_MESSAGE
    assert raised.value.__cause__ is refusal
    assert len(factory.built) == 1
    assert factory.built[0].calls[-1] == "close"
    with pytest.raises(RuntimeError):
        runtime.get_pipeline()
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("AuthError" in text for text in errors)
    assert "server-text-QWXZ" not in caplog.text


def test_a_kept_set_that_refuses_the_login_stays_kept(
    monkeypatch: pytest.MonkeyPatch, runtime: Any
) -> None:
    from _settings import SecretsError

    use_loader(monkeypatch, runtime, _config())
    kept = FakeShared(check_errors=[None, AuthError("refused")])
    use_factory(monkeypatch, runtime, lambda _n: kept)
    _open(runtime)
    runtime.finish_run()

    with pytest.raises(SecretsError):
        _open(runtime)

    assert "close" not in kept.calls
    assert runtime._shared is kept
