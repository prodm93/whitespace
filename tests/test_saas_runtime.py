"""Run lifecycle of the pipeline function: kept clients, one run pipeline for each run."""

from __future__ import annotations

from typing import Any

import pytest
from _runtime_helpers import UNREACHABLE, FakeShared, record_waits, use_factory, use_recorder
from _settings import SecretsError
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from whitespace.tenant import TenantIdError


@pytest.mark.protects("graph-namespace-bound-per-run")
def test_kept_clients_are_built_once_and_each_run_gets_its_own_namespace(
    monkeypatch: Any, runtime: Any
) -> None:
    factory = use_factory(monkeypatch, runtime)
    recorder = use_recorder(monkeypatch, runtime)

    for tenant in ("user_a", "user_a", "user_b"):
        runtime.run(runtime.open_run(tenant))
        runtime.finish_run()

    assert len(factory.built) == 1
    assert [config.graphiti_namespace for _, config, _ in recorder.calls] == [
        "user_a",
        "user_a",
        "user_b",
    ]
    assert all(shared is factory.built[0] for shared, _, _ in recorder.calls)


@pytest.mark.protects("run-pipeline-never-reused")
def test_after_finish_there_is_no_pipeline_and_no_store(runtime: Any) -> None:
    runtime.run(runtime.open_run("user_a"))
    runtime.finish_run()

    with pytest.raises(RuntimeError):
        runtime.get_pipeline()
    with pytest.raises(RuntimeError):
        runtime.get_store()


@pytest.mark.protects("tenant-id-validated")
def test_a_bad_tenant_id_is_refused_and_leaves_no_open_run(runtime: Any) -> None:
    runtime.run(runtime.open_run("user_a"))

    with pytest.raises(TenantIdError):
        runtime.run(runtime.open_run(""))
    with pytest.raises(RuntimeError):
        runtime.get_pipeline()


@pytest.mark.protects("run-pipeline-never-reused")
def test_a_second_open_without_finish_builds_a_new_run_pipeline(
    monkeypatch: Any, runtime: Any
) -> None:
    recorder = use_recorder(monkeypatch, runtime)
    runtime.run(runtime.open_run("user_a"))
    first = runtime.get_pipeline()

    runtime.run(runtime.open_run("user_a"))

    assert len(recorder.calls) == 2
    assert runtime.get_pipeline() is recorder.built[1]
    assert runtime.get_pipeline() is not first


@pytest.mark.protects("graph-unreachable-retried-then-failed")
def test_first_build_is_retried_until_the_graph_answers(monkeypatch: Any, runtime: Any) -> None:
    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: FakeShared(initialise_error=ServiceUnavailable("down") if n < 2 else None),
    )

    runtime.run(runtime.open_run("user_a"))

    assert len(factory.built) == 3
    assert "close" in factory.built[0].calls
    assert "close" in factory.built[1].calls
    assert runtime._shared is factory.built[2]


def test_a_new_build_is_checked_before_it_is_kept(monkeypatch: Any, runtime: Any) -> None:
    factory = use_factory(monkeypatch, runtime)

    runtime.run(runtime.open_run("user_a"))

    shared = factory.built[0]
    assert shared.calls == ["initialise", "check"]
    assert shared.kept_during_check == [False]
    assert runtime._shared is shared


def test_a_new_build_whose_check_fails_once_is_replaced(monkeypatch: Any, runtime: Any) -> None:
    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: FakeShared(check_errors=[ServiceUnavailable("graphiti down")] if n == 0 else []),
    )

    runtime.run(runtime.open_run("user_a"))

    assert len(factory.built) == 2
    assert "close" in factory.built[0].calls
    assert runtime._shared is factory.built[1]


@pytest.mark.protects("graph-unreachable-retried-then-failed")
def test_a_new_build_whose_check_always_fails_ends_in_the_unreachable_error(
    monkeypatch: Any, runtime: Any
) -> None:
    from _connection import GraphUnavailableError

    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda _n: FakeShared(check_errors=[ServiceUnavailable("graphiti down")]),
    )

    with pytest.raises(GraphUnavailableError) as raised:
        runtime.run(runtime.open_run("user_a"))

    assert str(raised.value) == UNREACHABLE
    assert len(factory.built) == 4
    assert all("close" in shared.calls for shared in factory.built)
    assert runtime._shared is None


@pytest.mark.protects("graph-unreachable-retried-then-failed")
def test_four_failed_connections_end_in_the_unreachable_error(
    monkeypatch: Any, runtime: Any
) -> None:
    from _connection import GraphUnavailableError

    waits = record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda _n: FakeShared(initialise_error=ServiceUnavailable("down")),
    )

    with pytest.raises(GraphUnavailableError) as raised:
        runtime.run(runtime.open_run("user_a"))

    assert str(raised.value) == UNREACHABLE
    assert len(factory.built) == 4
    assert runtime._shared is None
    assert waits == [9.0, 18.0, 36.0]


@pytest.mark.protects("graph-unreachable-retried-then-failed")
def test_an_auth_error_is_not_retried(monkeypatch: Any, runtime: Any) -> None:
    record_waits(monkeypatch)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda _n: FakeShared(initialise_error=AuthError("wrong password")),
    )

    with pytest.raises(SecretsError) as raised:
        runtime.run(runtime.open_run("user_a"))

    assert isinstance(raised.value.__cause__, AuthError)
    assert len(factory.built) == 1


@pytest.mark.protects("dead-connection-rebuilt")
def test_a_dead_kept_connection_is_replaced_and_the_run_goes_on(
    monkeypatch: Any, runtime: Any
) -> None:
    record_waits(monkeypatch)
    recorder = use_recorder(monkeypatch, runtime)
    factory = use_factory(
        monkeypatch,
        runtime,
        lambda n: FakeShared(check_errors=[None, SessionExpired("gone")] if n == 0 else []),
    )
    runtime.run(runtime.open_run("user_a"))
    runtime.finish_run()

    runtime.run(runtime.open_run("user_b"))

    assert len(factory.built) == 2
    assert "close" in factory.built[0].calls
    assert runtime._shared is factory.built[1]
    assert recorder.calls[-1][0] is factory.built[1]
    assert runtime.get_pipeline() is recorder.built[-1]
