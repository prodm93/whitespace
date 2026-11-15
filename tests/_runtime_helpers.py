"""Fakes for the run lifecycle of the pipeline function's runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from _saas_helpers import FakePipeline

UNREACHABLE = "The knowledge graph could not be reached. Please try again in a few minutes."


class FakeShared:
    """Stands in for the kept clients and records each lifecycle call.

    ``check_errors`` lists what each call of ``check`` raises in turn; ``None`` is a
    passing check, and calls past the end of the list pass. ``close_error`` is raised by
    ``close`` after the call is recorded.
    """

    def __init__(
        self,
        initialise_error: BaseException | None = None,
        check_errors: list[BaseException | None] | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.kept_during_check: list[bool] = []
        self._initialise_error = initialise_error
        self._check_errors = list(check_errors or [])
        self._close_error = close_error

    async def initialise(self) -> None:
        self.calls.append("initialise")
        if self._initialise_error is not None:
            raise self._initialise_error

    async def check(self) -> None:
        import _runtime

        self.calls.append("check")
        self.kept_during_check.append(_runtime._shared is self)
        error = self._check_errors.pop(0) if self._check_errors else None
        if error is not None:
            raise error

    async def close(self) -> None:
        self.calls.append("close")
        if self._close_error is not None:
            raise self._close_error


class TaskShared(FakeShared):
    """A kept part that starts a long background task in ``initialise``."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.task: asyncio.Task[None] | None = None

    async def initialise(self) -> None:
        self.task = asyncio.ensure_future(asyncio.Event().wait())
        await super().initialise()


class SharedFactory:
    """Builds fake kept parts in turn; ``make(n)`` gives the n-th one."""

    def __init__(self, make: Callable[[int], Any] | None = None) -> None:
        self.built: list[Any] = []
        self._make = make or (lambda _n: FakeShared())

    def __call__(self, _config: Any) -> Any:
        shared = self._make(len(self.built))
        self.built.append(shared)
        return shared


class PipelineRecorder:
    """Replaces ``Pipeline``; records each run pipeline it is asked to build."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, Any]] = []
        self.built: list[FakePipeline] = []

    def from_shared(self, shared: Any, config: Any, *, session_store: Any = None) -> FakePipeline:
        self.calls.append((shared, config, session_store))
        pipeline = FakePipeline()
        self.built.append(pipeline)
        return pipeline


def use_factory(
    monkeypatch: Any, runtime: Any, make: Callable[[int], Any] | None = None
) -> SharedFactory:
    """Make the runtime build its kept parts with a ``SharedFactory``."""
    factory = SharedFactory(make)
    monkeypatch.setattr(runtime, "build_shared", factory)
    return factory


def use_recorder(monkeypatch: Any, runtime: Any) -> PipelineRecorder:
    """Make the runtime build its run pipelines with a ``PipelineRecorder``."""
    recorder = PipelineRecorder()
    monkeypatch.setattr(runtime, "Pipeline", recorder)
    return recorder


def record_waits(monkeypatch: Any) -> list[float]:
    """Record the requested waits instead of sleeping."""
    requested: list[float] = []

    async def _sleep(seconds: float) -> None:
        requested.append(seconds)

    monkeypatch.setattr("asyncio.sleep", _sleep)
    return requested
