"""Closing the kept clients, the work left on the kept loop, and the loop itself."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, Any

from whitespace.closing import CLOSE_SECONDS

if TYPE_CHECKING:
    from whitespace.orchestration._shared_clients import SharedClients

logger = logging.getLogger(__name__)

CANCEL_WAIT = 5.0


async def close_quietly(shared: SharedClients) -> None:
    """Close the kept clients; an error is logged, never raised."""
    try:
        await shared.close()
    except Exception:
        logger.exception("Closing the kept clients failed")


def cancel_tasks(
    loop: asyncio.AbstractEventLoop,
    spared: Collection[asyncio.Task[Any]],
    seconds: float,
) -> set[asyncio.Task[Any]]:
    """Cancel every task of ``loop`` except ``spared``; return those still there at the limit.

    A cancelled task can start another one, so the loop is asked again after each wait,
    until it has no such task or the limit has passed. ``seconds`` is one limit for the
    whole step. The error of a task that ended is retrieved so that it is not reported as
    unseen.
    """
    deadline = loop.time() + seconds
    tasks = asyncio.all_tasks(loop) - set(spared)
    while tasks:
        for task in tasks:
            task.cancel()
        loop.run_until_complete(asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time())))
        for task in tasks:
            if task.done() and not task.cancelled():
                task.exception()
        tasks = asyncio.all_tasks(loop) - set(spared)
        if loop.time() >= deadline:
            break
    return tasks


def _stage(name: str, action: Callable[[], object]) -> BaseException | None:
    """Run one stage of closing a loop; return an interruption instead of raising it."""
    try:
        action()
    except asyncio.CancelledError:
        logger.warning("%s did not complete: it was cancelled", name)
    except Exception:
        logger.exception("%s failed", name)
    except BaseException as interruption:
        return interruption
    return None


def _close_clients(loop: asyncio.AbstractEventLoop, shared: SharedClients | None) -> None:
    if shared is not None:
        loop.run_until_complete(close_quietly(shared))


def _cancel_all(loop: asyncio.AbstractEventLoop) -> None:
    left = cancel_tasks(loop, (), CANCEL_WAIT)
    if left:
        logger.warning("%d tasks did not end when cancelled; the loop is closed anyway", len(left))


def _shut_down_generators(loop: asyncio.AbstractEventLoop) -> None:
    task = loop.create_task(loop.shutdown_asyncgens())
    loop.run_until_complete(asyncio.wait({task}, timeout=CLOSE_SECONDS))


def close_loop(loop: asyncio.AbstractEventLoop, shared: SharedClients | None) -> None:
    """Close the kept clients, cancel what is left on the loop, and close the loop.

    Each stage runs even when an earlier one failed or was interrupted. An ordinary
    error or a cancellation is logged and not raised; the first ``KeyboardInterrupt`` or
    ``SystemExit`` is raised after the loop is closed.
    """
    # No loop.shutdown_default_executor(): on 3.11 it waits without limit for a thread job.
    stages: list[tuple[str, Callable[[], object]]] = [
        ("Closing the kept clients", lambda: _close_clients(loop, shared)),
        ("Cancelling the tasks left on the loop", lambda: _cancel_all(loop)),
        ("Shutting down the async generators", lambda: _shut_down_generators(loop)),
        ("Closing the event loop", loop.close),
    ]
    first_interruption: BaseException | None = None
    for name, action in stages:
        interruption = _stage(name, action)
        first_interruption = first_interruption or interruption
    if first_interruption is not None:
        raise first_interruption
