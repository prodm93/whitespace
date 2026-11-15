"""The session store of each run is bound to the tenant of that run."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Any

import pytest
from _fake_sessions_table import install_sessions_table
from _saas_helpers import FakePipeline, FakeStore, install_runtime

from whitespace.config import Config
from whitespace.store.base import GapRun
from whitespace.store.dynamo_store import DynamoSessionStore

_runtime = importlib.import_module("_runtime")
_REAL_BUILD_SESSION_STORE = _runtime._build_session_store


@pytest.fixture()
def runtime_with_sessions_table(monkeypatch: Any, request: Any) -> Any:
    """The runtime with fake clients, the real store builder and a sessions table set."""
    install_runtime(monkeypatch, FakePipeline(), FakeStore(), request)
    monkeypatch.setattr(_runtime, "_build_session_store", _REAL_BUILD_SESSION_STORE)
    monkeypatch.setattr(
        _runtime,
        "Config",
        lambda: Config(_env_file=None, mode="saas", sessions_table="sessions"),
    )
    return _runtime


@pytest.mark.protects("session-store-partition-per-tenant")
def test_each_run_builds_its_store_for_its_own_tenant(
    monkeypatch: Any, runtime_with_sessions_table: Any
) -> None:
    runtime = runtime_with_sessions_table
    owners: list[str] = []

    def store_class(_table: str, _region: str, *, owner: str) -> object:
        owners.append(owner)
        return object()

    monkeypatch.setattr("whitespace.store.dynamo_store.DynamoSessionStore", store_class)

    for tenant in ("user_a", "user_a", "user_b"):
        runtime.run(runtime.open_run(tenant))
        runtime.finish_run()

    assert owners == ["user_a", "user_a", "user_b"]


@pytest.mark.protects("session-store-partition-per-tenant")
def test_rehydrate_never_reads_the_gap_run_of_another_tenant(
    monkeypatch: Any, runtime_with_sessions_table: Any
) -> None:
    import _actions

    runtime = runtime_with_sessions_table
    install_sessions_table(monkeypatch)
    gap_run = GapRun(run_id="gap-a", timestamp=datetime(2026, 7, 1, tzinfo=UTC), domain="x")
    store_a = DynamoSessionStore("sessions", "us-east-1", owner="user_a")
    runtime.run(store_a.save_gap_run(gap_run))

    runtime.run(runtime.open_run("user_b"))
    for_b = runtime.run(_actions._rehydrate({}))
    runtime.finish_run()
    runtime.run(runtime.open_run("user_a"))
    for_a = runtime.run(_actions._rehydrate({}))

    assert for_b == {"profile": None, "domain": "", "needs": [], "gap_run_id": ""}
    assert for_a["gap_run_id"] == "gap-a"
