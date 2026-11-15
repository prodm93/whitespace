"""Retirement: a task that does not end when cancelled takes its loop and kept clients with it."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from _loop_helpers import Respawning, Stubborn, tick
from _runtime_helpers import UNREACHABLE, FakeShared, record_waits, use_factory, use_recorder
from neo4j.exceptions import ServiceUnavailable


def _leave_stubborn_task(work: Stubborn, error: BaseException | None = None) -> Any:
    async def body() -> int:
        asyncio.ensure_future(work.run())
        await tick()
        if error is not None:
            raise error
        return 7

    return body()


@pytest.fixture()
def short_cancel_wait(monkeypatch: Any, runtime: Any) -> None:
    import _teardown

    monkeypatch.setattr(_teardown, "CANCEL_WAIT", 0.05)


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_a_stubborn_task_retires_the_loop_and_its_old_work_stops(
    monkeypatch: Any, runtime: Any, short_cancel_wait: None
) -> None:
    factory = use_factory(monkeypatch, runtime)
    recorder = use_recorder(monkeypatch, runtime)
    runtime.run(runtime.open_run("user_a"))
    old_loop = runtime._loop
    work = Stubborn()

    assert runtime.run(_leave_stubborn_task(work)) == 7

    assert old_loop.is_closed()
    assert (runtime._loop, runtime._shared, runtime._run) == (None, None, None)
    assert "close" in factory.built[0].calls
    count = work.ticks

    async def second() -> Any:
        await asyncio.sleep(0.3)
        return runtime.get_pipeline()

    pipeline = runtime.run(second())
    assert work.ticks == count
    assert runtime._loop is not old_loop
    assert len(factory.built) == 2
    assert [config.graphiti_namespace for _, config, _ in recorder.calls] == ["user_a", "user_a"]
    assert pipeline is recorder.built[-1]


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_a_stubborn_task_with_no_run_open_builds_nothing_next(
    monkeypatch: Any, runtime: Any, short_cancel_wait: None
) -> None:
    factory = use_factory(monkeypatch, runtime)
    recorder = use_recorder(monkeypatch, runtime)

    runtime.run(_leave_stubborn_task(Stubborn()))
    runtime.run(asyncio.sleep(0))

    assert factory.built == []
    assert recorder.calls == []


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_a_failing_cancel_step_retires_the_loop_and_keeps_the_result(
    monkeypatch: Any, runtime: Any
) -> None:
    runtime.run(runtime.open_run("user_a"))
    old_loop = runtime._loop

    def broken(*_args: Any) -> Any:
        raise RuntimeError("cancel step failed")

    monkeypatch.setattr(runtime, "cancel_tasks", broken)

    async def seven() -> int:
        return 7

    assert runtime.run(seven()) == 7
    assert old_loop.is_closed()
    assert (runtime._loop, runtime._shared) == (None, None)


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_a_failed_call_that_leaves_a_stubborn_task_keeps_its_error(
    runtime: Any, short_cancel_wait: None
) -> None:
    with pytest.raises(ValueError, match="own error"):
        runtime.run(_leave_stubborn_task(Stubborn(), ValueError("own error")))


def test_a_reopen_that_cannot_reach_the_graph_fails_the_call_once(
    monkeypatch: Any, runtime: Any, short_cancel_wait: None
) -> None:
    from _connection import GraphUnavailableError

    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: FakeShared(initialise_error=ServiceUnavailable("down") if n else None),
    )
    runtime.run(runtime.open_run("user_a"))
    runtime.run(_leave_stubborn_task(Stubborn()))
    ran = False

    async def body() -> None:
        nonlocal ran
        ran = True

    with pytest.raises(GraphUnavailableError) as raised:
        runtime.run(body())
    built = len(factory.built)
    runtime.run(asyncio.sleep(0))

    assert str(raised.value) == UNREACHABLE
    assert ran is False
    assert len(factory.built) == built


@pytest.mark.protects("run-pipeline-never-reused")
def test_no_tenant_is_open_between_a_retirement_and_the_reopened_run(
    monkeypatch: Any, runtime: Any, short_cancel_wait: None
) -> None:
    use_factory(monkeypatch, runtime)
    runtime.run(runtime.open_run("user_a"))
    runtime.run(_leave_stubborn_task(Stubborn()))

    with pytest.raises(RuntimeError):
        runtime.current_owner()

    async def owner_of_the_reopened_run() -> str:
        return str(runtime.current_owner())

    assert runtime.run(owner_of_the_reopened_run()) == "user_a"


@pytest.mark.protects("leftover-work-stopped-at-call-end")
def test_tasks_that_never_stop_coming_retire_the_loop(
    runtime: Any, short_cancel_wait: None
) -> None:
    runtime.run(asyncio.sleep(0))
    old_loop = runtime._loop
    work = Respawning()

    async def body() -> int:
        asyncio.ensure_future(work.run())
        await tick()
        return 7

    started = time.monotonic()
    assert runtime.run(body()) == 7
    assert time.monotonic() - started < 2
    assert old_loop.is_closed()
    assert runtime._loop is None
    starts = work.starts
    runtime.run(asyncio.sleep(0.2))
    assert work.starts == starts
    assert runtime._loop is not old_loop
