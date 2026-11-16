"""The SaaS pipeline function reads its secrets from Secrets Manager and checks the value."""

from __future__ import annotations

import json
from typing import Any

import pytest
from _settings_helpers import ARN, SECRET, StandInClient, client_error, messages
from _settings_helpers import settings as _settings


@pytest.mark.protects("saas-secrets-loaded")
async def test_the_five_values_of_the_secret_are_in_the_config(use_client: Any) -> None:
    client = use_client(StandInClient(json.dumps(SECRET)))

    config = await _settings.load_config()

    assert config.neo4j_uri == SECRET["neo4j_uri"]
    assert config.neo4j_username == SECRET["neo4j_username"]
    assert config.neo4j_password == SECRET["neo4j_password"]
    assert config.exa_api_key == SECRET["exa_api_key"]
    assert config.langsmith_api_key == SECRET["langsmith_api_key"]
    assert client.calls == [{"SecretId": ARN}]


async def test_a_second_read_inside_the_cache_time_makes_no_call(use_client: Any) -> None:
    client = use_client(StandInClient(json.dumps(SECRET)))

    first = await _settings.load_config()
    second = await _settings.load_config()

    assert second == first
    assert len(client.calls) == 1


async def test_absent_optional_keys_leave_their_fields_empty(
    use_client: Any, caplog: pytest.LogCaptureFixture
) -> None:
    required = {name: SECRET[name] for name in _settings.REQUIRED}
    use_client(StandInClient(json.dumps(required)))

    with caplog.at_level("INFO", logger="_settings"):
        config = await _settings.load_config()

    assert (config.exa_api_key, config.langsmith_api_key) == ("", "")
    info = messages(caplog, "INFO")
    assert len(info) == 1
    assert "exa_api_key" in info[0] and "langsmith_api_key" in info[0]


@pytest.mark.parametrize(
    "value",
    [None, "", 42],
    ids=["absent", "empty", "a number"],
)
async def test_a_required_key_without_a_text_value_fails_the_load(
    use_client: Any, caplog: pytest.LogCaptureFixture, value: Any
) -> None:
    secret = dict(SECRET)
    if value is None:
        del secret["neo4j_password"]
    else:
        secret["neo4j_password"] = value
    client = use_client(StandInClient(json.dumps(secret)))

    with pytest.raises(_settings.SecretsError) as raised:
        await _settings.load_config()

    assert str(raised.value) == _settings.USER_MESSAGE
    errors = messages(caplog, "ERROR")
    assert len(errors) == 1 and "neo4j_password" in errors[0]
    assert len(client.calls) == 1


async def test_keys_the_loader_does_not_know_are_not_passed_on(
    use_client: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MODE", "saas")
    use_client(StandInClient(json.dumps({**SECRET, "mode": "byok", "sqs_queue_url": "x"})))

    config = await _settings.load_config()

    assert config.mode == "saas"
    assert config.sqs_queue_url == ""
    warnings = messages(caplog, "WARNING")
    assert len(warnings) == 1
    assert "mode" in warnings[0] and "sqs_queue_url" in warnings[0]


async def test_a_json_list_fails_the_load(use_client: Any) -> None:
    client = use_client(StandInClient(json.dumps([SECRET])))

    with pytest.raises(_settings.SecretsError):
        await _settings.load_config()

    assert len(client.calls) == 1


async def test_an_unset_secret_arn_fails_the_load_with_no_call(
    use_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PIPELINE_SECRET_ARN", "")
    client = use_client(StandInClient(json.dumps(SECRET)))

    with pytest.raises(_settings.SecretsError) as raised:
        await _settings.load_config()

    assert str(raised.value) == _settings.USER_MESSAGE
    assert client.calls == []


async def test_a_value_that_is_not_json_fails_the_load_with_no_chained_error(
    use_client: Any,
) -> None:
    client = use_client(StandInClient("password-QWXZ is not json"))

    with pytest.raises(_settings.SecretsError) as raised:
        await _settings.load_config()

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert len(client.calls) == 1


@pytest.mark.parametrize("code", ["ResourceNotFoundException", "AccessDeniedException"])
async def test_a_refused_read_fails_the_load_at_once(
    use_client: Any, caplog: pytest.LogCaptureFixture, code: str
) -> None:
    client = use_client(StandInClient(client_error(code)))

    with pytest.raises(_settings.SecretsError):
        await _settings.load_config()

    assert len(client.calls) == 1
    errors = messages(caplog, "ERROR")
    assert len(errors) == 1 and code in errors[0]
