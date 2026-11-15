"""The credential check answers whether the OpenRouter key and the Neo4j login work."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _module_loading import call_with_body, load_module, own_event_loop

_HANDLER = (
    Path(__file__).resolve().parents[1] / "deploy" / "aws" / "lambda" / "credential_validator"
)
_CREDENTIALS = {"openrouter_api_key": "k", "neo4j_uri": "neo4j+s://db", "neo4j_password": "p"}


@pytest.fixture()
def validator() -> Iterator[Any]:
    module = load_module("credential_validator", _HANDLER / "handler.py")
    with own_event_loop():
        yield module


def _fake_services(
    monkeypatch: Any, *, openrouter: Exception | None, neo4j: Exception | None
) -> list[str]:
    import neo4j as neo4j_package
    import openai

    closed: list[str] = []

    class Models:
        async def list(self) -> list[str]:
            if openrouter is not None:
                raise openrouter
            return []

    class Driver:
        async def verify_connectivity(self) -> None:
            if neo4j is not None:
                raise neo4j

        async def close(self) -> None:
            closed.append("neo4j")

    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **_kw: type("C", (), {"models": Models()})())
    monkeypatch.setattr(neo4j_package.AsyncGraphDatabase, "driver", lambda *_a, **_kw: Driver())
    return closed


def test_a_body_that_is_not_json_is_refused(validator: Any) -> None:
    assert call_with_body(validator, "{not json") == (400, {"error": "Invalid JSON body"})


@pytest.mark.protects("credential-check-reports-each-service")
def test_a_missing_key_or_database_address_is_refused(validator: Any) -> None:
    assert call_with_body(validator, {"credentials": {"openrouter_api_key": "k"}}) == (
        400,
        {"error": "Missing required credentials"},
    )


@pytest.mark.protects("credential-check-reports-each-service")
def test_working_credentials_are_both_reported_ok(validator: Any, monkeypatch: Any) -> None:
    closed = _fake_services(monkeypatch, openrouter=None, neo4j=None)

    assert call_with_body(validator, {"credentials": _CREDENTIALS}) == (
        200,
        {"openrouter_ok": True, "neo4j_ok": True, "openrouter_error": None, "neo4j_error": None},
    )
    assert closed == ["neo4j"]


@pytest.mark.protects("credential-check-reports-each-service")
def test_failing_credentials_are_reported_with_their_errors(
    validator: Any, monkeypatch: Any
) -> None:
    closed = _fake_services(
        monkeypatch, openrouter=RuntimeError("bad key"), neo4j=OSError("no route")
    )

    assert call_with_body(validator, {"credentials": _CREDENTIALS}) == (
        200,
        {
            "openrouter_ok": False,
            "neo4j_ok": False,
            "openrouter_error": "bad key",
            "neo4j_error": "no route",
        },
    )
    assert closed == ["neo4j"]
