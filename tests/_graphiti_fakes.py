"""Fakes for Graphiti, its driver and its three HTTP clients, recording each close."""

from __future__ import annotations

from typing import Any

from whitespace.graph import graphiti_client as module


class CloseRecorder:
    """Records each close, and raises the error set for a name."""

    def __init__(self, errors: dict[str, BaseException] | None = None) -> None:
        self.names: list[str] = []
        self._errors = errors or {}

    async def close(self, name: str) -> None:
        self.names.append(name)
        if name in self._errors:
            raise self._errors[name]


def install_graphiti_fakes(
    monkeypatch: Any, closes: CloseRecorder, *, real_wrappers: bool = False
) -> list[dict[str, Any]]:
    """Replace Graphiti, its driver, its HTTP clients and (unless ``real_wrappers``) its wrappers.

    The HTTP clients are named ``model``, ``embedder`` and ``reranker`` by the order in which
    they are built. Returns the keyword arguments that each fake ``Graphiti`` was built with.
    """
    http_names = ["model", "embedder", "reranker"]
    built_http: list[FakeHttp] = []
    built_with: list[dict[str, Any]] = []

    class FakeHttp:
        def __init__(self, name: str) -> None:
            self.name = name

        async def close(self) -> None:
            await closes.close(self.name)

    def http_client(**_kwargs: Any) -> FakeHttp:
        client = FakeHttp(http_names[len(built_http) % len(http_names)])
        built_http.append(client)
        return client

    class FakeWrapper:
        def __init__(self, **_kwargs: Any) -> None:
            pass

    class FakeGraphiti:
        def __init__(self, **kwargs: Any) -> None:
            built_with.append(kwargs)

        async def close(self) -> None:
            await closes.close("graphiti")

    monkeypatch.setattr(module, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(module, "Neo4jDriver", lambda **_kwargs: object())
    monkeypatch.setattr(module, "AsyncOpenAI", http_client)
    if not real_wrappers:
        for name in ("OpenAIClient", "OpenAIEmbedder", "OpenAIRerankerClient"):
            monkeypatch.setattr(module, name, FakeWrapper)
    return built_with
