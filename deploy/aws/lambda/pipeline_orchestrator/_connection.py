"""Connecting the kept clients: one checked build, and the connection attempts of a run."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from _teardown import close_quietly
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from whitespace.tools.retry import transient_retry

if TYPE_CHECKING:
    from whitespace.orchestration._shared_clients import SharedClients

logger = logging.getLogger(__name__)

CONNECTION_ERRORS: tuple[type[BaseException], ...] = (ServiceUnavailable, SessionExpired, OSError)
CONNECT_ATTEMPTS = 4
UNREACHABLE = "The knowledge graph could not be reached. Please try again in a few minutes."


class GraphUnavailableError(RuntimeError):
    """The knowledge graph did not answer within the connection attempts of a run."""


async def discard(shared: SharedClients) -> None:
    """Close a set of kept clients that is dropped because of an error.

    A cancellation of the close is logged and not raised, so the error that caused the
    drop comes out. A ``KeyboardInterrupt`` or ``SystemExit`` of the close is raised, after
    every close was attempted.
    """
    try:
        await close_quietly(shared)
    except asyncio.CancelledError:
        logger.exception("Closing a dropped set of kept clients was interrupted")


async def build_checked(
    build: Callable[[], SharedClients],
) -> tuple[SharedClients, set[asyncio.Task[Any]]]:
    """Build a set of kept clients whose two drivers both answered.

    Returns the set and the tasks it started while it was built, which are its own
    background work. A set that fails, or whose build is interrupted, is closed and the
    error of the build is raised, unless the close of the failed set is stopped by
    ``KeyboardInterrupt`` or ``SystemExit``.
    """
    before = asyncio.all_tasks()
    candidate = build()
    try:
        await candidate.initialise()
        await candidate.check()
    except BaseException:
        await discard(candidate)
        raise
    return candidate, asyncio.all_tasks() - before


async def with_attempts(connect_once: Callable[[], Awaitable[SharedClients]]) -> SharedClients:
    """Try ``connect_once`` four times, about one minute in all.

    Only connection errors are retried. When every attempt fails, the run fails with
    ``GraphUnavailableError``; any other error comes out unchanged.
    """
    policy = transient_retry(
        attempts=CONNECT_ATTEMPTS,
        first_wait=9.0,
        max_wait=36.0,
        retry_on=CONNECTION_ERRORS,
    )
    try:
        return await policy(connect_once)
    except CONNECTION_ERRORS as error:
        logger.exception("The knowledge graph did not answer in %d attempts", CONNECT_ATTEMPTS)
        raise GraphUnavailableError(UNREACHABLE) from error
