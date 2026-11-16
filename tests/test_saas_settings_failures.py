"""The secrets loader retries a read that AWS did not answer, and never leaks a value."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from _runtime_helpers import record_waits
from _settings_helpers import SECRET, StandInClient, client_error, messages, unreachable
from _settings_helpers import settings as _settings


def _expire_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_settings, "MAX_AGE_SECONDS", 1)


async def test_an_unreachable_endpoint_is_tried_three_times_then_fails_the_load(
    use_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits = record_waits(monkeypatch)
    client = use_client(StandInClient(unreachable()))

    with pytest.raises(_settings.SecretsError) as raised:
        await _settings.load_config()

    assert str(raised.value) == _settings.USER_MESSAGE
    assert len(client.calls) == 3
    assert len(waits) == 2


@pytest.mark.parametrize(
    "fault",
    [unreachable, lambda: client_error("InternalServiceError")],
    ids=["unreachable", "internal service error"],
)
async def test_a_read_that_answers_on_the_third_attempt_gives_the_values(
    use_client: Any, monkeypatch: pytest.MonkeyPatch, fault: Any
) -> None:
    record_waits(monkeypatch)
    client = use_client(StandInClient(fault(), fault(), json.dumps(SECRET)))

    config = await _settings.load_config()

    assert config.neo4j_password == SECRET["neo4j_password"]
    assert len(client.calls) == 3


@pytest.mark.protects("saas-secrets-loaded")
async def test_an_unreachable_reread_keeps_the_last_good_values(
    use_client: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _expire_the_cache(monkeypatch)
    client = use_client(StandInClient(json.dumps(SECRET), unreachable()))
    first = await _settings.load_config()
    time.sleep(1.1)
    record_waits(monkeypatch)
    caplog.clear()

    again = await _settings.load_config()

    assert again == first
    assert len(client.calls) == 4
    assert len(messages(caplog, "WARNING")) == 1


async def test_a_refused_reread_does_not_fall_back_to_the_last_good_values(
    use_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_the_cache(monkeypatch)
    use_client(StandInClient(json.dumps(SECRET), client_error("AccessDeniedException")))
    await _settings.load_config()
    time.sleep(1.1)

    with pytest.raises(_settings.SecretsError):
        await _settings.load_config()


@pytest.mark.protects("saas-secrets-loaded")
async def test_a_changed_secret_is_read_once_the_cache_time_is_over(
    use_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _expire_the_cache(monkeypatch)
    changed = {**SECRET, "neo4j_password": "new-password-QWXZ"}
    use_client(StandInClient(json.dumps(SECRET), json.dumps(changed)))
    await _settings.load_config()
    time.sleep(1.1)

    config = await _settings.load_config()

    assert config.neo4j_password == "new-password-QWXZ"


def _chain(error: BaseException) -> list[BaseException]:
    """Every error reachable from ``error`` through both ``__cause__`` and ``__context__``."""
    seen: list[BaseException] = []
    todo: list[BaseException | None] = [error]
    while todo:
        current = todo.pop()
        if current is None or any(current is known for known in seen):
            continue
        seen.append(current)
        todo += [current.__cause__, current.__context__]
    return seen


@pytest.mark.protects("secret-values-not-logged")
@pytest.mark.parametrize(
    ("answers", "arn", "reread"),
    [
        ((json.dumps({**SECRET, "neo4j_uri": ""}),), True, False),
        ((json.dumps({k: v for k, v in SECRET.items() if k != "neo4j_uri"}),), True, False),
        ((json.dumps({**SECRET, "neo4j_uri": 42}),), True, False),
        (("password-QWXZ is not json",), True, False),
        ((json.dumps([SECRET]),), True, False),
        ((client_error("ResourceNotFoundException"),), True, False),
        ((client_error("AccessDeniedException"),), True, False),
        ((unreachable(),), True, False),
        ((json.dumps(SECRET),), False, False),
        ((json.dumps(SECRET), client_error("AccessDeniedException")), True, True),
    ],
    ids=[
        "required key empty",
        "required key absent",
        "required key a number",
        "not json",
        "a list",
        "not found",
        "access denied",
        "unreachable",
        "no secret arn",
        "refused re-read after a good read",
    ],
)
async def test_no_secret_value_reaches_an_error_or_a_log_line(
    use_client: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    answers: tuple[Any, ...],
    arn: bool,
    reread: bool,
) -> None:
    record_waits(monkeypatch)
    use_client(StandInClient(*answers))
    if not arn:
        monkeypatch.setenv("PIPELINE_SECRET_ARN", "")
    if reread:
        _expire_the_cache(monkeypatch)
        await _settings.load_config()
        time.sleep(1.1)

    with caplog.at_level("DEBUG"), pytest.raises(_settings.SecretsError) as raised:
        await _settings.load_config()

    texts = [caplog.text] + [
        f"{error!s} {error!r} {error.args!r} {vars(error)!r}" for error in _chain(raised.value)
    ]
    assert not any("QWXZ" in text for text in texts)
