"""The pipeline function's handler and actions on top of the run lifecycle."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from _runtime_helpers import UNREACHABLE, FakeShared, record_waits, use_factory
from _saas_helpers import (
    FakeDurableContext,
    _evt,
    _handler_boto3,
)
from neo4j.exceptions import ServiceUnavailable


def test_rehydrate_gives_the_empty_shape_when_the_run_store_has_no_gap_run(runtime: Any) -> None:
    import _actions

    runtime.run(runtime.open_run("u1"))

    assert runtime.run(_actions._rehydrate({})) == {
        "profile": None,
        "domain": "",
        "needs": [],
        "gap_run_id": "",
    }


@pytest.mark.parametrize(
    "make",
    [
        lambda _n: FakeShared(initialise_error=ServiceUnavailable("down")),
        lambda _n: FakeShared(check_errors=[ServiceUnavailable("graphiti down")]),
    ],
    ids=["connect-fails", "graphiti-check-fails"],
)
@pytest.mark.protects("run-slot-returned-on-failure")
@pytest.mark.protects("job-failure-recorded")
@pytest.mark.protects("graph-unreachable-retried-then-failed")
def test_an_unreachable_graph_fails_the_job_with_the_unreachable_text_before_any_paid_step(
    monkeypatch: Any, runtime: Any, make: Any
) -> None:
    import _failure
    import handler
    from _connection import GraphUnavailableError

    record_waits(monkeypatch)
    use_factory(monkeypatch, runtime, make)
    monkeypatch.setitem(sys.modules, "boto3", _handler_boto3(with_reservation=True))
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "required")
    monkeypatch.setattr(handler, "_validate_usage_config", lambda: None)
    cleanup = MagicMock()
    set_status = MagicMock()
    monkeypatch.setattr(_failure, "_cleanup_reservation", cleanup)
    monkeypatch.setattr(_failure, "_set_status", set_status)
    ctx = FakeDurableContext()

    with pytest.raises(GraphUnavailableError):
        handler.handler(_evt("j1", "Run gaps", user_id="u1"), ctx)

    set_status.assert_called_once_with("j1", "failed", error=UNREACHABLE)
    cleanup.assert_called_once_with("u1", "j1")
    assert "rehydrate_session" not in ctx.step_calls
    assert "gap_analysis" not in ctx.step_calls
    assert not [name for name in ctx.step_calls if name.startswith("decide-")]
