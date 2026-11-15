"""The event loop, the kept clients and the pipeline of the current run.

One event loop and one set of kept clients live as long as the warm container. The
run pipeline and the session store are built for one tenant at the start of each run
and dropped at its end; nothing bound to a tenant outlives its run. The container
runs one invocation at a time, so module state is safe.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

import _teardown
from _connection import CONNECTION_ERRORS, build_checked, discard, with_attempts
from _teardown import cancel_tasks, close_loop

from whitespace.config import Config
from whitespace.orchestration._wiring import build_shared
from whitespace.orchestration.pipeline import Pipeline
from whitespace.tenant import require_tenant_id

if TYPE_CHECKING:
    from whitespace.orchestration._shared_clients import SharedClients
    from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

_loop: asyncio.AbstractEventLoop | None = None
_shared: SharedClients | None = None
_run: Pipeline | None = None
_store: SessionStore | None = None
_owner: str | None = None
_kept_tasks: set[asyncio.Task[Any]] = set()
_reopen_for: str | None = None


def run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine to completion on the one kept event loop.

    When a retirement dropped an open run, that tenant's run is opened again first; if
    that fails, ``coro`` is closed unrun and the error is raised.
    """
    global _reopen_for
    owner = _reopen_for
    _reopen_for = None
    if owner is not None:
        try:
            _run_on_kept_loop(open_run(owner))
        except BaseException:
            coro.close()
            raise
    return _run_on_kept_loop(coro)


def _run_on_kept_loop(coro: Coroutine[Any, Any, _T]) -> _T:
    """Drive ``coro`` on the kept loop, then stop every task the call left running.

    A task that ends when cancelled is gone, and so is a task that starts while the
    others are cancelled. If one does not end, or the cancelling fails, the loop and the
    kept clients are retired so the task cannot run again. The kept clients' own tasks
    are spared. The result or error of ``coro`` is unchanged.
    """
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
    loop = _loop
    before = asyncio.all_tasks(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            left = cancel_tasks(loop, before | _kept_tasks, _teardown.CANCEL_WAIT)
        except Exception:
            logger.exception("Cancelling the tasks left by a call failed")
            _retire(loop)
        except BaseException:
            _retire(loop)
            raise
        else:
            if left:
                _retire(loop)


def _clear_run() -> None:
    """Forget the run pipeline, the store and the tenant of the run, and any pending reopen."""
    global _run, _store, _owner, _reopen_for
    _run = None
    _store = None
    _owner = None
    _reopen_for = None


def _take_kept() -> tuple[asyncio.AbstractEventLoop | None, SharedClients | None]:
    """Hand over the kept loop and clients, and forget them and their background tasks."""
    global _loop, _shared, _kept_tasks
    loop, shared = _loop, _shared
    _loop = None
    _shared = None
    _kept_tasks = set()
    return loop, shared


def _retire(loop: asyncio.AbstractEventLoop) -> None:
    """Drop the loop and the kept clients, then close them; the next call builds anew."""
    global _reopen_for
    reopen = _owner if _run is not None else None
    _clear_run()
    _reopen_for = reopen
    _, shared = _take_kept()
    logger.warning("Work left by a call did not end; the loop and the kept clients are retired")
    close_loop(loop, shared)


def _build_session_store(config: Config, owner: str) -> SessionStore:
    if config.sessions_table:
        from whitespace.store.dynamo_store import DynamoSessionStore

        return DynamoSessionStore(config.sessions_table, config.aws_region, owner=owner)
    logger.warning("SESSIONS_TABLE not set; session persistence disabled")
    from whitespace.store.noop_store import NoopSessionStore

    return NoopSessionStore()


async def _connect_once() -> SharedClients:
    """Return kept clients whose two drivers both answered in this attempt.

    A new set is kept with the tasks it started while it was built; those are spared at
    the end of each call. A kept set that fails its check is dropped first, then closed,
    and its error is raised, so the next attempt builds a new one.
    """
    global _shared, _kept_tasks
    if _shared is None:
        _shared, _kept_tasks = await build_checked(lambda: build_shared(Config()))
        return _shared
    try:
        await _shared.check()
    except CONNECTION_ERRORS:
        logger.exception("The kept graph connection failed its check; it is rebuilt")
        stale = _shared
        _shared = None
        _kept_tasks = set()
        await discard(stale)
        raise
    return _shared


async def open_run(user_id: str) -> None:
    """Build the run pipeline and the store of one tenant on the kept clients.

    The graph connection is tried four times, about one minute in all, before the run
    fails with ``GraphUnavailableError``. Only connection errors are retried.
    """
    global _run, _store, _owner
    _clear_run()
    owner = require_tenant_id(user_id)
    shared = await with_attempts(_connect_once)
    config = Config().model_copy(update={"graphiti_namespace": owner})
    _store = _build_session_store(config, owner)
    _run = Pipeline.from_shared(shared, config, session_store=_store)
    _owner = owner


def finish_run() -> None:
    """Drop the run pipeline, the store and the owner of the run that ends.

    Unless ``PIPELINE_REUSE`` is ``container`` (the default), the kept clients and the
    loop are closed too, so the next run builds everything again. An unknown value closes
    them as well: the switch is the fallback for a tenant-separation incident.
    """
    _clear_run()
    reuse = os.environ.get("PIPELINE_REUSE", "container")
    if reuse == "container" or _loop is None:
        return
    if reuse != "invocation":
        logger.warning("PIPELINE_REUSE=%r is not known; the kept clients are closed", reuse)
    loop, shared = _take_kept()
    if loop is not None:
        close_loop(loop, shared)


def current_owner() -> str:
    """Return the tenant ID that the open run was built for."""
    if _owner is None:
        raise RuntimeError("No run is open; call open_run first")
    return _owner


def get_pipeline() -> Pipeline:
    """Return the pipeline of the open run."""
    if _run is None:
        raise RuntimeError("No run is open; call open_run first")
    return _run


def get_store() -> SessionStore:
    """Return the session store of the open run."""
    if _store is None:
        raise RuntimeError("No run is open; call open_run first")
    return _store
