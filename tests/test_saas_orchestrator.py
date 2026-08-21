"""End-to-end SaaS pipeline handler tests: flow and error handling."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from _saas_helpers import (
    _DONE,
    FakeDurableContext,
    FakePipeline,
    FakeRouter,
    FakeStore,
    _evt,
    _handler_boto3,
    _need,
    _tc,
)

from whitespace.store.base import GapRun


@pytest.fixture(autouse=True)
def patch_actions(monkeypatch: Any) -> None:
    import _actions
    import _reservation_ops

    monkeypatch.setattr(_actions, "_pipeline", FakePipeline())
    monkeypatch.setattr(_actions, "_session_store", FakeStore())
    monkeypatch.setattr(_actions, "_ensure_init", AsyncMock())
    monkeypatch.setattr(_actions, "_localise_paths", AsyncMock(side_effect=lambda p: p))
    monkeypatch.setattr(_reservation_ops, "_USAGE_TABLE", "usage-t")


@pytest.fixture()
def pipeline() -> FakePipeline:
    import _actions

    return _actions._pipeline  # type: ignore[attr-defined]


def test_wait_for_callback_never_called(monkeypatch: Any, pipeline: FakePipeline) -> None:
    import _actions
    import _job_state
    import handler

    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("extract_profile"),
            _tc("stage", {"domain": "robotics"}),
            _tc("run_gap_analysis"),
            _DONE,
        ]
    )
    monkeypatch.setattr(_actions, "_pipeline", pipeline)
    monkeypatch.setattr(_job_state, "_JOBS_TABLE", "j")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    result = handler.handler(
        _evt("j1", "Run gap analysis", profile_paths=["cv.pdf"], user_id="u1"), ctx
    )
    assert "wait_for_callback" not in ctx.step_calls
    assert result["status"] == "awaiting_selection"
    assert result["needs"]


def test_request2_rehydrates_without_rerunning(monkeypatch: Any, pipeline: FakePipeline) -> None:
    import _actions
    import handler

    prior = GapRun(
        run_id="r1",
        timestamp=datetime.now(UTC),
        needs=[_need("Gap A")],
        domain="robotics",
    )
    monkeypatch.setattr(_actions, "_session_store", FakeStore(gap_run=prior))
    monkeypatch.setattr(_actions, "_pipeline", pipeline)
    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("extract_profile"),
            _tc("run_ideation", {"selected_titles": ["Gap A"]}),
            _DONE,
        ]
    )
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "not_required")
    ctx = FakeDurableContext()
    result = handler.handler(
        _evt(
            "j2",
            "Ideate",
            selected_titles=["Gap A"],
            profile_paths=["cv.pdf"],
            user_id="u1",
        ),
        ctx,
    )
    assert pipeline.analyse_calls == 0
    assert pipeline.ideate_calls == 1
    assert result["status"] == "done"


def test_crash_writes_failed_status(monkeypatch: Any) -> None:
    import _actions
    import handler

    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "not_required")

    async def _crash(_p: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(handler, "_rehydrate", _crash)
    monkeypatch.setattr(_actions, "_ensure_init", AsyncMock())
    ctx = FakeDurableContext()
    with pytest.raises(RuntimeError, match="boom"):
        handler.handler({"job_id": "jx", "payload": {"intent": "run", "user_id": "u1"}}, ctx)
    assert "status_failed" in ctx.step_calls
