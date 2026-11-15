"""End-to-end SaaS pipeline handler tests: flow and error handling."""

from __future__ import annotations

import json
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
    install_runtime,
)

from whitespace.store.base import GapRun


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


def test_wait_for_callback_never_called(monkeypatch: Any, pipeline: FakePipeline) -> None:
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
    monkeypatch.setattr(_job_state, "_JOBS_TABLE", "j")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    ctx = FakeDurableContext()
    result = handler.handler(
        _evt("j1", "Run gap analysis", profile_paths=["uploads/u1/cv.pdf"], user_id="u1"), ctx
    )
    assert "wait_for_callback" not in ctx.step_calls
    assert result["status"] == "awaiting_selection"
    assert result["needs"]


def test_request2_rehydrates_without_rerunning(
    monkeypatch: Any, request: Any, pipeline: FakePipeline
) -> None:
    import handler

    prior = GapRun(
        run_id="r1",
        timestamp=datetime.now(UTC),
        needs=[_need("Gap A")],
        domain="robotics",
    )
    install_runtime(monkeypatch, pipeline, FakeStore(gap_run=prior), request)
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
            profile_paths=["uploads/u1/cv.pdf"],
            user_id="u1",
        ),
        ctx,
    )
    assert pipeline.analyse_calls == 0
    assert pipeline.ideate_calls == 1
    assert result["status"] == "done"


@pytest.mark.protects("job-failure-recorded")
def test_crash_writes_failed_status(monkeypatch: Any) -> None:
    import handler

    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "not_required")

    async def _crash(_p: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(handler, "_rehydrate", _crash)
    ctx = FakeDurableContext()
    with pytest.raises(RuntimeError, match="boom"):
        handler.handler({"job_id": "jx", "payload": {"intent": "run", "user_id": "u1"}}, ctx)
    assert "status_failed" in ctx.step_calls


@pytest.mark.protects("job-result-published")
def test_a_finished_job_stores_its_result_and_is_marked_completed(
    monkeypatch: Any, pipeline: FakePipeline
) -> None:
    import _job_state
    import handler

    pipeline.router = FakeRouter([_tc("get_status"), _tc("extract_profile"), _DONE])
    monkeypatch.setattr(_job_state, "_JOBS_TABLE", "jobs")
    monkeypatch.setattr(_job_state, "_RESULTS_BUCKET", "results")
    fb = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", fb)

    result = handler.handler(
        _evt("j1", "Read my profile", profile_paths=["uploads/u1/cv.pdf"], user_id="u1"),
        FakeDurableContext(),
    )

    put = fb.client.return_value.put_object.call_args.kwargs
    assert (put["Bucket"], put["Key"]) == ("results", "results/j1.json")
    assert json.loads(put["Body"]) == result
    last_status = fb.resource.return_value.Table.return_value.update_item.call_args.kwargs
    assert last_status["Key"] == {"job_id": "j1"}
    assert last_status["ExpressionAttributeValues"] == {
        ":st": "completed",
        ":rk": "results/j1.json",
    }


@pytest.mark.protects("gap-analysis-once-per-job")
def test_a_second_gap_request_in_one_job_does_not_run_it_again(
    monkeypatch: Any, pipeline: FakePipeline
) -> None:
    import _job_state
    import handler

    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("extract_profile"),
            _tc("stage", {"domain": "robotics"}),
            _tc("run_gap_analysis"),
            _tc("run_gap_analysis"),
            _DONE,
        ]
    )
    monkeypatch.setattr(_job_state, "_JOBS_TABLE", "j")
    monkeypatch.setitem(sys.modules, "boto3", _handler_boto3(with_reservation=True))
    ctx = FakeDurableContext()

    handler.handler(
        _evt("j1", "Run gap analysis twice", profile_paths=["uploads/u1/cv.pdf"], user_id="u1"),
        ctx,
    )

    assert pipeline.analyse_calls == 1
    assert ctx.step_calls.count("gap_analysis") == 1
