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
    install_runtime,
)


@pytest.fixture(autouse=True)
def patch_actions(monkeypatch: Any, request: Any) -> FakePipeline:
    import _actions
    import _reservation_ops

    fake = FakePipeline()
    install_runtime(monkeypatch, fake, FakeStore(), request)
    monkeypatch.setattr(
        _actions, "localise_paths", AsyncMock(side_effect=lambda paths, _owner: paths)
    )
    monkeypatch.setattr(_reservation_ops, "_USAGE_TABLE", "usage-t")
    return fake


@pytest.fixture()
def pipeline(patch_actions: FakePipeline) -> FakePipeline:
    return patch_actions


@pytest.mark.protects("run-slot-counted-on-gap-run")
def test_gap_success_fires_convert(monkeypatch: Any, pipeline: FakePipeline) -> None:
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
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    handler.handler(_evt("j3", "Run gaps", user_id="u1", profile_paths=["uploads/u1/cv.pdf"]), ctx)
    assert "convert_reservation" in ctx.step_calls


@pytest.mark.protects("run-slot-counted-on-gap-run")
def test_blocked_gap_releases_reservation(monkeypatch: Any, request: Any) -> None:
    import _reservation_state
    import handler

    fp = FakePipeline()
    fp.router = FakeRouter([_tc("run_gap_analysis"), _DONE])
    install_runtime(monkeypatch, fp, FakeStore(), request)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    handler.handler(_evt("j4", "Run gaps", user_id="u1"), ctx)
    assert "convert_reservation" not in ctx.step_calls
    assert "release_reservation_blocked" in ctx.step_calls


@pytest.mark.protects("run-slot-returned-on-failure")
def test_query_only_releases_unused(monkeypatch: Any, pipeline: FakePipeline) -> None:
    import _reservation_state
    import handler

    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("query_knowledge_graph", {"question": "What?"}),
            _DONE,
        ]
    )
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
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "j")
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "not_required")
    ctx = FakeDurableContext()
    handler.handler(_evt("j6", "Run gaps", user_id="u1", profile_paths=["uploads/u1/cv.pdf"]), ctx)
    assert "validate_and_start" in ctx.step_calls
    assert "convert_reservation" not in ctx.step_calls
