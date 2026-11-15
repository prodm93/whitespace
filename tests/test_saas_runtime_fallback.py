"""The end of a run in the fallback mode: everything is closed, also when a close fails."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from _runtime_helpers import FakeShared, TaskShared, use_factory


@pytest.fixture(autouse=True)
def _invocation_reuse(monkeypatch: Any) -> None:
    monkeypatch.setenv("PIPELINE_REUSE", "invocation")


@pytest.mark.parametrize(
    "error,raises",
    [(asyncio.CancelledError(), None), (KeyboardInterrupt(), KeyboardInterrupt)],
    ids=["cancelled-close", "interrupted-close"],
)
@pytest.mark.protects("fallback-close-leaves-nothing-kept")
def test_a_failed_close_still_finishes_the_cleanup(
    monkeypatch: Any, runtime: Any, error: BaseException, raises: Any
) -> None:
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: TaskShared(close_error=error) if n == 0 else FakeShared(),
    )
    runtime.run(runtime.open_run("user_a"))
    old_loop = runtime._loop
    task = factory.built[0].task
    finished: list[bool] = []
    held: list[Any] = []

    async def generator() -> Any:
        try:
            yield 1
            yield 2
        finally:
            finished.append(True)

    async def start() -> None:
        gen = generator()
        await gen.__anext__()
        held.append(gen)

    runtime.run(start())

    if raises is None:
        runtime.finish_run()
    else:
        with pytest.raises(raises):
            runtime.finish_run()

    assert task.cancelled()
    assert finished == [True]
    assert old_loop.is_closed()
    assert (runtime._shared, runtime._loop) == (None, None)
    runtime.run(runtime.open_run("user_a"))
    assert len(factory.built) == 2


@pytest.mark.protects("fallback-close-leaves-nothing-kept")
def test_a_running_thread_job_does_not_hold_the_end_of_the_run(runtime: Any) -> None:
    release = threading.Event()
    job_started = threading.Event()
    runtime.run(runtime.open_run("user_a"))

    def job() -> None:
        job_started.set()
        release.wait()

    async def start_thread_job() -> None:
        asyncio.ensure_future(asyncio.to_thread(job))
        for _ in range(200):
            if job_started.is_set():
                return
            await asyncio.sleep(0.01)

    runtime.run(start_thread_job())
    assert job_started.is_set()

    started = time.monotonic()
    runtime.finish_run()
    elapsed = time.monotonic() - started
    release.set()

    assert elapsed < 2.0


@pytest.mark.protects("fallback-close-leaves-nothing-kept")
def test_an_unknown_reuse_value_closes_the_kept_clients(monkeypatch: Any, runtime: Any) -> None:
    factory = use_factory(monkeypatch, runtime)
    monkeypatch.setenv("PIPELINE_REUSE", "invocaton")
    runtime.run(runtime.open_run("user_a"))
    old_loop = runtime._loop

    runtime.finish_run()

    assert "close" in factory.built[0].calls
    assert old_loop.is_closed()
