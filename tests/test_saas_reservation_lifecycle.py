"""Reservation lifecycle tests for the SaaS pipeline handler."""

from __future__ import annotations

import sys
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
    _tc,
)


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


def test_gap_success_fires_convert(monkeypatch: Any, pipeline: FakePipeline) -> None:
    import _actions
    import _reservation_state
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
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    handler.handler(_evt("j3", "Run gaps", user_id="u1", profile_paths=["cv.pdf"]), ctx)
    assert "convert_reservation" in ctx.step_calls


def test_blocked_gap_releases_reservation(monkeypatch: Any) -> None:
    import _actions
    import _reservation_state
    import handler

    fp = FakePipeline()
    fp.router = FakeRouter([_tc("run_gap_analysis"), _DONE])
    monkeypatch.setattr(_actions, "_pipeline", fp)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    handler.handler(_evt("j4", "Run gaps", user_id="u1"), ctx)
    assert "convert_reservation" not in ctx.step_calls
    assert "release_reservation_blocked" in ctx.step_calls


def test_query_only_releases_unused(monkeypatch: Any, pipeline: FakePipeline) -> None:
    import _actions
    import _reservation_state
    import handler

    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("query_knowledge_graph", {"question": "What?"}),
            _DONE,
        ]
    )
    monkeypatch.setattr(_actions, "_pipeline", pipeline)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    release = MagicMock()
    monkeypatch.setattr(handler, "_release_reservation", release)
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    handler.handler(_evt("j5", "What are gaps?", user_id="u1"), ctx)
    assert "release_unused_reservation" in ctx.step_calls
    release.assert_called_once_with("u1", "j5", "claimed")


def test_unlimited_bypass_skips_reservation(monkeypatch: Any, pipeline: FakePipeline) -> None:
    import _actions
    import _reservation_state
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
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "not_required")
    ctx = FakeDurableContext()
    handler.handler(_evt("j6", "Run gaps", user_id="u1", profile_paths=["cv.pdf"]), ctx)
    assert "validate_and_start" in ctx.step_calls
    assert "convert_reservation" not in ctx.step_calls
