"""Event loops of a test's own, and work that ignores cancellation."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


def drive(make: Callable[[], Awaitable[Any]]) -> None:
    """Run one coroutine on a loop of its own, as plain code drives it, then close the loop."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(make())  # type: ignore[arg-type]
    finally:
        loop.close()


async def tick() -> None:
    """Wait 0.01 seconds on a loop timer, untouched by a patched ``asyncio.sleep``."""
    loop = asyncio.get_running_loop()
    done = loop.create_future()
    loop.call_later(0.01, lambda: done.done() or done.set_result(None))
    await done


class Stubborn:
    """Work that ignores cancellation and counts its ticks until ``stop`` is set."""

    def __init__(self) -> None:
        self.ticks = 0
        self.stop = False

    async def run(self) -> None:
        while not self.stop:
            try:
                await tick()
            except asyncio.CancelledError:
                continue
            self.ticks += 1


def drive_timed(make: Callable[[], Awaitable[Any]], stubborn: Stubborn) -> float:
    """Drive ``make`` on a loop of its own and return how long it took.

    Then ``stubborn`` is stopped and allowed to end before the loop is closed.
    """
    loop = asyncio.new_event_loop()
    try:
        started = time.monotonic()
        loop.run_until_complete(make())  # type: ignore[arg-type]
        elapsed = time.monotonic() - started
        stubborn.stop = True
        loop.run_until_complete(asyncio.sleep(0.05))
    finally:
        loop.close()
    return elapsed


class Respawning:
    """Work that starts a copy of itself each time it is cancelled, while its loop is open."""

    def __init__(self) -> None:
        self.starts = 0

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self.starts += 1
        try:
            await asyncio.Event().wait()
        finally:
            if not loop.is_closed():
                loop.create_task(self.run())
