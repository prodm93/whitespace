"""Close several resources in turn, so that one failed close never skips the others."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)

CLOSE_SECONDS = 5.0

Closer = tuple[str, Callable[[], Awaitable[object]]]


async def _attempt(close: Callable[[], Awaitable[object]]) -> BaseException | None:
    """Await one close and return what happened instead of raising it."""
    try:
        await close()
    except BaseException as error:
        return error
    return None


async def close_all(closers: Sequence[Closer], *, seconds: float | None = CLOSE_SECONDS) -> None:
    """Attempt every close in the order given.

    An ordinary error of a close is logged with its name and traceback, and the next close
    is attempted. An interruption (``CancelledError``, ``KeyboardInterrupt``, ``SystemExit``)
    is kept; the first one is raised after the last close. No ``Exception`` is raised.

    Each close gets at most ``seconds`` (``None``: no limit of its own). A close still
    running at the limit is cancelled and left behind. The limit uses ``asyncio.wait``,
    which returns at the limit; ``asyncio.wait_for`` on Python 3.11 waits for a cancelled
    close to end.
    """
    interruption: BaseException | None = None
    for name, close in closers:
        task = asyncio.ensure_future(_attempt(close))
        try:
            done, _ = await asyncio.wait({task}, timeout=seconds)
        except asyncio.CancelledError as cancelled:
            task.cancel()
            interruption = interruption or cancelled
            continue
        if not done:
            task.cancel()
            logger.warning("Closing %s did not end within %s seconds", name, seconds)
            continue
        outcome = task.result()
        if isinstance(outcome, Exception):
            logger.error("Closing %s failed", name, exc_info=outcome)
        elif outcome is not None and interruption is None:
            interruption = outcome
    if interruption is not None:
        raise interruption
