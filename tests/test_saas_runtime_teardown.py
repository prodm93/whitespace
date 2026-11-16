"""Work left on the kept loop when a call ends: cancelled, or its loop is retired."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from _loop_helpers import tick
from _runtime_helpers import FakeShared, TaskShared, record_waits, use_factory
from _settings import SecretsError
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_a_leftover_task_is_cancelled_when_its_call_ends(runtime: Any) -> None:
    appended: list[str] = []

    async def fails() -> None:
        await asyncio.sleep(0)
        raise ValueError("boom")

    async def slow() -> None:
        await asyncio.sleep(0.05)
        appended.append("late")

    async def body() -> None:
        await asyncio.gather(fails(), slow())

    with pytest.raises(ValueError, match="boom"):
        runtime.run(body())
    loop = runtime._loop

    assert asyncio.all_tasks(loop) == set()
    runtime.run(asyncio.sleep(0.1))
    assert appended == []
    assert runtime._loop is loop


def test_a_background_task_of_the_kept_clients_is_spared(monkeypatch: Any, runtime: Any) -> None:
    factory = use_factory(monkeypatch, runtime, lambda _n: TaskShared())

    runtime.run(runtime.open_run("user_a"))
    runtime.run(asyncio.sleep(0))

    task = factory.built[0].task
    assert task is not None and not task.done()


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_the_task_of_a_rejected_candidate_is_cancelled(monkeypatch: Any, runtime: Any) -> None:
    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: TaskShared(check_errors=[ServiceUnavailable("down")] if n == 0 else []),
    )

    runtime.run(runtime.open_run("user_a"))

    first, second = factory.built
    assert first.task is not None and first.task.cancelled()
    assert second.task is not None and not second.task.done()


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interrupted_build_closes_its_candidate(monkeypatch: Any, runtime: Any) -> None:
    factory = use_factory(
        monkeypatch, runtime, lambda _n: FakeShared(initialise_error=asyncio.CancelledError())
    )

    with pytest.raises(asyncio.CancelledError):
        runtime.run(runtime.open_run("user_a"))

    assert "close" in factory.built[0].calls
    assert runtime._shared is None


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interrupted_close_of_a_failed_build_keeps_the_build_error(
    monkeypatch: Any, runtime: Any
) -> None:
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda _n: FakeShared(
            initialise_error=AuthError("wrong password"), close_error=asyncio.CancelledError()
        ),
    )

    with pytest.raises(SecretsError) as raised:
        runtime.run(runtime.open_run("user_a"))

    assert isinstance(raised.value.__cause__, AuthError)
    assert "close" in factory.built[0].calls


@pytest.mark.protects("dead-connection-rebuilt")
def test_an_interrupted_close_of_a_dead_set_does_not_stop_the_rebuild(
    monkeypatch: Any, runtime: Any
) -> None:
    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: (
            FakeShared(
                check_errors=[None, SessionExpired("gone")], close_error=asyncio.CancelledError()
            )
            if n == 0
            else FakeShared()
        ),
    )
    runtime.run(runtime.open_run("user_a"))
    runtime.finish_run()

    runtime.run(runtime.open_run("user_b"))

    assert "close" in factory.built[0].calls
    assert runtime._shared is factory.built[1]


_STOPS = [KeyboardInterrupt(), SystemExit(1)]


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
@pytest.mark.parametrize("stop", _STOPS, ids=["KeyboardInterrupt", "SystemExit"])
def test_a_stopped_close_of_a_failed_build_stops_the_run(
    monkeypatch: Any, runtime: Any, stop: BaseException
) -> None:
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda _n: FakeShared(initialise_error=AuthError("wrong password"), close_error=stop),
    )

    with pytest.raises(type(stop)):
        runtime.run(runtime.open_run("user_a"))

    assert "close" in factory.built[0].calls
    assert runtime._shared is None
    assert len(factory.built) == 1


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
@pytest.mark.parametrize("stop", _STOPS, ids=["KeyboardInterrupt", "SystemExit"])
def test_a_stopped_close_of_a_dead_set_stops_the_attempts(
    monkeypatch: Any, runtime: Any, stop: BaseException
) -> None:
    waits = record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda _n: FakeShared(check_errors=[None, SessionExpired("gone")], close_error=stop),
    )
    runtime.run(runtime.open_run("user_a"))
    runtime.finish_run()

    with pytest.raises(type(stop)):
        runtime.run(runtime.open_run("user_b"))

    assert "close" in factory.built[0].calls
    assert runtime._shared is None
    assert len(factory.built) == 1
    assert waits == []


@pytest.mark.protects("leftover-work-stopped-at-call-end")
@pytest.mark.parametrize("levels", [1, 3])
def test_a_task_that_starts_while_leftover_work_is_cancelled_is_stopped(
    runtime: Any, levels: int
) -> None:
    done: list[str] = []

    async def last() -> None:
        await asyncio.sleep(0.02)
        done.append("late")

    async def level(n: int) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            asyncio.ensure_future(level(n - 1) if n > 1 else last())

    async def body() -> None:
        asyncio.ensure_future(level(levels))
        await tick()

    runtime.run(body())
    loop = runtime._loop

    assert asyncio.all_tasks(loop) == set()
    runtime.run(asyncio.sleep(0.1))
    assert done == []
    assert runtime._loop is loop
