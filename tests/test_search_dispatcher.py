"""The search dispatcher fans out to the patent and web searches and stores the results."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _module_loading import call_with_body, load_module, own_event_loop

_HANDLER = Path(__file__).resolve().parents[1] / "deploy" / "aws" / "lambda" / "search_dispatcher"
_PATENT = {"patent_number": "1", "patent_title": "T", "patent_abstract": "A", "patent_date": "d"}


class _FakeS3:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.puts.append(kwargs)


@pytest.fixture()
def dispatcher(monkeypatch: Any) -> Iterator[tuple[Any, _FakeS3]]:
    module = load_module("search_dispatcher", _HANDLER / "handler.py")
    s3 = _FakeS3()
    monkeypatch.setattr(module, "_get_s3", lambda: s3)
    with own_event_loop():
        yield module, s3


def _fake_searches(monkeypatch: Any, *, patents_fail: bool = False) -> None:
    import duckduckgo_search
    import httpx

    class Response:
        def raise_for_status(self) -> None:
            if patents_fail:
                raise httpx.HTTPError("patents down")

        def json(self) -> dict:
            return {"patents": [_PATENT]}

    class Client:
        def __init__(self, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> Response:
            return Response()

    class Search:
        def text(self, _query: str, max_results: int) -> list[dict]:
            return [{"title": "W", "href": "https://w", "body": "s"}]

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(duckduckgo_search, "DDGS", Search)


def test_a_body_that_is_not_json_is_refused(dispatcher: tuple[Any, _FakeS3]) -> None:
    assert call_with_body(dispatcher[0], "{not json") == (400, {"error": "Invalid JSON body"})


def test_a_request_with_no_keywords_is_refused(dispatcher: tuple[Any, _FakeS3]) -> None:
    assert call_with_body(dispatcher[0], {"domain_keywords": []}) == (
        400,
        {"error": "domain_keywords required"},
    )


@pytest.mark.protects("search-results-stored")
def test_both_searches_are_stored_and_counted(
    dispatcher: tuple[Any, _FakeS3], monkeypatch: Any
) -> None:
    module, s3 = dispatcher
    _fake_searches(monkeypatch)

    status, body = call_with_body(module, {"domain_keywords": ["battery"]})

    assert (status, body["patent_count"], body["web_count"]) == (200, 1, 1)
    assert [put["Key"] for put in s3.puts] == [body["result_key"]]
    assert body["result_key"].startswith("search-results/")
    stored = json.loads(s3.puts[0]["Body"])
    assert stored["patents"][0]["patent_number"] == "1"
    assert stored["web_results"][0]["url"] == "https://w"


@pytest.mark.protects("search-surface-failure-degrades")
def test_a_failed_patent_search_still_stores_the_web_results(
    dispatcher: tuple[Any, _FakeS3], monkeypatch: Any
) -> None:
    module, s3 = dispatcher
    _fake_searches(monkeypatch, patents_fail=True)

    status, body = call_with_body(module, {"domain_keywords": ["battery"]})

    assert (status, body["patent_count"], body["web_count"]) == (200, 0, 1)
