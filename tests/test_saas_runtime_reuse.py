"""Reuse of the kept loop and kept clients across runs, and the per-invocation fallback."""

from __future__ import annotations

import asyncio
import socketserver
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from _runtime_helpers import FakeShared, use_factory


@pytest.mark.protects("fallback-close-leaves-nothing-kept")
def test_invocation_reuse_closes_the_kept_clients_and_the_loop_at_each_finish(
    monkeypatch: Any, runtime: Any
) -> None:
    factory = use_factory(monkeypatch, runtime)
    monkeypatch.setenv("PIPELINE_REUSE", "invocation")
    runtime.run(runtime.open_run("user_a"))
    first_loop = runtime._loop

    runtime.finish_run()

    assert factory.built[0].calls[-1] == "close"
    assert first_loop.is_closed()
    assert runtime._loop is None
    assert runtime._shared is None
    runtime.run(runtime.open_run("user_a"))
    assert len(factory.built) == 2


def test_container_reuse_keeps_the_kept_clients_and_the_loop(
    monkeypatch: Any, runtime: Any
) -> None:
    factory = use_factory(monkeypatch, runtime)
    runtime.run(runtime.open_run("user_a"))
    first_loop = runtime._loop

    runtime.finish_run()

    assert "close" not in factory.built[0].calls
    assert runtime._loop is first_loop
    assert not first_loop.is_closed()


class _Echo(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        while data := self.request.recv(1024):
            self.request.sendall(data)


@pytest.fixture()
def echo_port() -> Iterator[int]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Echo)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


class SocketShared(FakeShared):
    """A kept part with a real connection and a lock, both bound to the loop of run 1."""

    def __init__(self, port: int) -> None:
        super().__init__()
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock: asyncio.Lock | None = None

    async def initialise(self) -> None:
        await super().initialise()
        self._reader, self._writer = await asyncio.open_connection("127.0.0.1", self._port)
        self._lock = asyncio.Lock()

    async def exchange(self, payload: bytes) -> bytes:
        assert self._reader is not None and self._writer is not None and self._lock is not None
        async with self._lock:
            self._writer.write(payload)
            await self._writer.drain()
            return await self._reader.readexactly(len(payload))

    async def close(self) -> None:
        await super().close()
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()


def test_one_kept_loop_serves_runs_driven_from_different_threads(
    monkeypatch: Any, runtime: Any, echo_port: int
) -> None:
    factory = use_factory(monkeypatch, runtime, lambda _n: SocketShared(echo_port))

    def one_run(number: int) -> tuple[int, bytes]:
        runtime.run(runtime.open_run("user_a"))
        echoed = runtime.run(runtime._shared.exchange(b"run-%d" % number))
        runtime.finish_run()
        return threading.get_ident(), echoed

    executors = [ThreadPoolExecutor(max_workers=2) for _ in range(4)]
    try:
        results = [pool.submit(one_run, n).result(timeout=10) for n, pool in enumerate(executors)]
    finally:
        for pool in executors:
            pool.shutdown(wait=True)
    runtime.run(factory.built[0].close())

    assert [echoed for _, echoed in results] == [b"run-0", b"run-1", b"run-2", b"run-3"]
    assert len({ident for ident, _ in results}) == 4
    assert len(factory.built) == 1
